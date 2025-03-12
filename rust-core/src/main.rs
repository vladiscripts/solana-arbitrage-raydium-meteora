use std::thread;
use std::time::Duration;
use std::collections::HashMap;  // Add this import for HashMap
use std::collections::HashSet;
use std::str::FromStr;
use std::io;
use std::fs::File;
use std::option::Option;

use dotenv::dotenv; // This will load the .env file
use envy;            // This will deserialize environment variables

use tracing::{info, error, span, Level};
use tracing_subscriber;

use redis::{Client as RedisClient, Commands};
use sqlx::postgres::PgPoolOptions;
use sqlx::FromRow;
use serde::Serialize;
use serde::Deserialize;
use serde_json::Value;
use serde_pickle::{from_slice, DeOptions};
use uuid::Uuid;
use reqwest::Client as ReqwestClient;
use reqwest::header::HeaderValue;

use rand::Rng;
use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use base64::Engine;

use solana_sdk::{
    pubkey::Pubkey,
    signature::{Keypair, Signer},
    system_instruction,
    transaction::Transaction,
    transaction::VersionedTransaction,
    address_lookup_table::AddressLookupTableAccount,
    compute_budget::ComputeBudgetInstruction,
    instruction::Instruction,
    instruction::AccountMeta,
    hash::Hash,
    message::{Message, v0, VersionedMessage},
    commitment_config::CommitmentConfig,
};
use solana_client::{
    rpc_client::RpcClient,
    rpc_config::RpcSendTransactionConfig
};
use solana_commitment_config::CommitmentLevel;

use jito_sdk_rust::JitoJsonRpcSDK;

#[derive(Deserialize, Clone)]
struct Env {
    redis_url: url::Url,
    psql_url: url::Url,
    rpc_url: url::Url,
    jito_url: url::Url,
    meteora_sdk_url: url::Url,
    meteora_bins: Vec<i32>,
    // min_y_tradable: f32,
    // min_price_diff_percentage: f32,
    vault_keypair: String,
    vault_pubkey: String,
    vault_wsol_ata: String,
    operator_keypair: String,
    operator_pubkey: String,
    operator_wsol_ata: String,
    fee_payer_keypair: String,
    fee_payer_pubkey: String,
}

#[derive(Debug, PartialEq, FromRow)]
struct ArbitrageRoute {
    id: i32,
    pool_a_id: i32,
    pool_b_id: i32,
    pool_a_address: String,
    pool_b_address: String,
    pool_a_dex: String,
    pool_b_dex: String,
    reserve_a_address_pool_a: String,
    reserve_b_address_pool_a: String,
    reserve_a_address_pool_b: String,
    reserve_b_address_pool_b: String,
    reserve_a_mint_pool_a: String,
    reserve_a_mint_pool_b: String,
    reserve_b_mint_pool_a: String,
    reserve_b_mint_pool_b: String,
    reserve_a_pool_a: f32,
    reserve_b_pool_a: f32,
    reserve_a_pool_b: f32,
    reserve_b_pool_b: f32,
    reserve_a_pool_a_decimals: f32,
    reserve_b_pool_a_decimals: f32,
    reserve_a_pool_b_decimals: f32,
    reserve_b_pool_b_decimals: f32,
    pool_a_fee: f32,
    pool_b_fee: f32,
    lut: Option<String>,
    status: String,
}

// Define the AmmV4PoolKeys struct
#[derive(Debug, Clone)]
pub struct AmmV4PoolKeys {
    pub amm_id: Pubkey,
    pub base_mint: Pubkey,
    pub quote_mint: Pubkey,
    pub base_decimals: u8,
    pub quote_decimals: u8,
    pub open_orders: Pubkey,
    pub target_orders: Pubkey,
    pub base_vault: Pubkey,
    pub quote_vault: Pubkey,
    pub market_id: Pubkey,
    pub market_authority: Pubkey,
    pub market_base_vault: Pubkey,
    pub market_quote_vault: Pubkey,
    pub bids: Pubkey,
    pub asks: Pubkey,
    pub event_queue: Pubkey,
    pub ray_authority_v4: Pubkey,
    pub open_book_program: Pubkey,
    pub token_program_id: Pubkey,
}

#[derive(Serialize)]
struct GetMeteoraSwapIxMessage {
    in_token: String,
    out_token: String,
    in_amount: String,
    min_out_amount: String,
    lb_pair: String,
    user_pubkey: String,
    user_ata_in: String,
    user_ata_out: String,
    bin_arrays: Vec<Value>,
}

#[derive(Debug, Deserialize)]
struct GetLatestBlockhashResp {
    value: Blockhash,
    context: Context,
}

#[derive(Debug, Deserialize)]
struct Blockhash {
    blockhash: String,
    last_valid_block_height: u64,
}

#[derive(Debug, Deserialize)]
struct Context {
    slot: u64,
}

async fn extract_reserve_addresses(data: &[ArbitrageRoute]) -> Vec<String> {
    let mut reserve_addresses: HashSet<String> = HashSet::new();

    for route in data {
        reserve_addresses.insert(route.reserve_a_address_pool_a.clone());
        reserve_addresses.insert(route.reserve_b_address_pool_a.clone());
        reserve_addresses.insert(route.reserve_a_address_pool_b.clone());
        reserve_addresses.insert(route.reserve_b_address_pool_b.clone());
    }

    reserve_addresses.into_iter().collect()
}

fn scale_value(value: f64, decimals: u32) -> f64 {
    value / 10f64.powi(decimals as i32)
}

fn hex_to_decimal(hex_str: &str) -> u64 {
    u64::from_str_radix(hex_str, 16).unwrap_or(0)
}

fn raydium_quote_y_for_x(x_desired_lamports: f64, reserve_x: f64, reserve_y: f64, swap_fee: f64) -> u64 {
    let k = reserve_x * reserve_y;

    let new_reserve_y = reserve_y + x_desired_lamports.trunc();
    let new_reserve_x = k / new_reserve_y;

    let y_received = reserve_x - new_reserve_x;
    let y_received_with_fee = y_received / (1.0 - swap_fee);
    let y_required = y_received_with_fee.trunc() as u64;
    y_required
}

fn raydium_quote_x_for_y(y_input_lamports: f64, reserve_x: f64, reserve_y: f64, swap_fee: f64) -> u64 {
    let k = reserve_x * reserve_y;

    let new_reserve_y = reserve_y + y_input_lamports;
    let new_reserve_x = k / new_reserve_y;

    let x_received = reserve_x - new_reserve_x;
    let x_received_with_fee = x_received * (1.0 - swap_fee);
    let x_required = x_received_with_fee as u64;

    x_required
}

// Function to fetch AmmV4PoolKeys from a list of addresses
pub fn fetch_amm_v4_pool_keys_from_lut_addresses(
    addresses: Vec<Pubkey>,
    dlmm_token_x_decimals: u8,
    dlmm_token_y_decimals: u8,
) -> Option<AmmV4PoolKeys> {
    // Ensure the addresses vector has enough elements
    if addresses.len() < 25 {
        println!("Not enough addresses provided.");
        return None;
    }

    // Extract addresses from the list
    let amm_id = addresses[9];
    let market_id = addresses[14];
    let ray_authority_v4 = Pubkey::from_str("5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1").unwrap();
    let open_book_program = addresses[8];
    let token_program_id = addresses[3];

    // Create and return the AmmV4PoolKeys struct
    Some(AmmV4PoolKeys {
        amm_id,
        base_mint: addresses[4],
        quote_mint: addresses[22],
        base_decimals: dlmm_token_y_decimals,
        quote_decimals: dlmm_token_x_decimals,
        open_orders: addresses[10],
        target_orders: addresses[11],
        base_vault: addresses[12],
        quote_vault: addresses[13],
        market_id,
        market_authority: addresses[20],
        market_base_vault: addresses[18],
        market_quote_vault: addresses[19],
        bids: addresses[15],
        asks: addresses[16],
        event_queue: addresses[17],
        ray_authority_v4,
        open_book_program,
        token_program_id,
    })
}

// Function to create a Raydium AMM V4 swap instruction
pub fn make_amm_v4_swap_instruction(
    amount_in: u64,
    minimum_amount_out: u64,
    token_account_in: Pubkey,
    token_account_out: Pubkey,
    accounts: &AmmV4PoolKeys,
    owner: Pubkey,
) -> Instruction {
    // Define the accounts for the instruction
    let keys = vec![
        AccountMeta::new_readonly(accounts.token_program_id, false),
        AccountMeta::new(accounts.amm_id, false),
        AccountMeta::new_readonly(accounts.ray_authority_v4, false),
        AccountMeta::new(accounts.open_orders, false),
        AccountMeta::new(accounts.target_orders, false),
        AccountMeta::new(accounts.base_vault, false),
        AccountMeta::new(accounts.quote_vault, false),
        AccountMeta::new_readonly(accounts.open_book_program, false),
        AccountMeta::new(accounts.market_id, false),
        AccountMeta::new(accounts.bids, false),
        AccountMeta::new(accounts.asks, false),
        AccountMeta::new(accounts.event_queue, false),
        AccountMeta::new(accounts.market_base_vault, false),
        AccountMeta::new(accounts.market_quote_vault, false),
        AccountMeta::new_readonly(accounts.market_authority, false),
        AccountMeta::new(token_account_in, false),
        AccountMeta::new(token_account_out, false),
        AccountMeta::new_readonly(owner, true),
    ];

    // Define the instruction data
    let mut data = Vec::new();
    data.push(9); // Discriminator for the swap instruction
    data.extend_from_slice(&amount_in.to_le_bytes());
    data.extend_from_slice(&minimum_amount_out.to_le_bytes());

    // Create and return the instruction
    Instruction {
        program_id: Pubkey::from_str("675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8").unwrap(), // Replace with the actual Raydium AMM V4 program ID
        accounts: keys,
        data,
    }
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>>  {
    // Load environment variables from the .env file
    dotenv().ok();
    let env = envy::from_env::<Env>();

    tracing_subscriber::fmt::init();
    let span = span!(Level::INFO, "main_function");
    let _enter = span.enter();
    
    let vault_keypair = Keypair::from_base58_string(&env.clone().unwrap().vault_keypair);
    let vault_pubkey = Pubkey::from_str(&env.clone().unwrap().vault_pubkey).unwrap();
    let vault_wsol_ata = Pubkey::from_str(&env.clone().unwrap().vault_wsol_ata).unwrap();

    let operator_keypair = Keypair::from_base58_string(&env.clone().unwrap().operator_keypair);
    let operator_pubkey = Pubkey::from_str(&env.clone().unwrap().operator_pubkey).unwrap();
    let operator_wsol_ata = Pubkey::from_str(&env.clone().unwrap().operator_wsol_ata).unwrap();

    let fee_payer_keypair = Keypair::from_base58_string(&env.clone().unwrap().fee_payer_keypair);
    let fee_payer_pubkey = Pubkey::from_str(&env.clone().unwrap().fee_payer_pubkey).unwrap();

    let rpc_client = RpcClient::new_with_commitment(
        env.clone().unwrap().rpc_url.to_string().to_string(),
        CommitmentConfig::processed(),
    );

    let jito_sdk = JitoJsonRpcSDK::new(&env.clone().unwrap().jito_url.to_string(), None);
    
    let meteora_sdk_client = ReqwestClient::new();

    let redis_client = RedisClient::open(env.clone().unwrap().redis_url.to_string())?;
    let mut redis_pubsub_connection = redis_client.get_connection()?;
    let mut redis_bins_pubsub_connection = redis_client.get_connection()?;
    
    // Use the redis_connection for pub/sub
    let mut pubsub = redis_pubsub_connection.as_pubsub();
    let mut bins_pubsub = redis_bins_pubsub_connection.as_pubsub();
    pubsub.subscribe("reserves")?;
    println!("Listening for messages on 'reserves' channel...");

    let pool = PgPoolOptions::new()
        .max_connections(5)
        .connect(&env.clone().unwrap().psql_url.to_string())
        .await?;

    // SQL query to fetch the required data
    let query = r#"
        SELECT 
            tar.id,
            tar.pool_a_id,
            tar.pool_b_id,
            tar.pool_a_address,
            tar.pool_b_address,
            tar.pool_a_dex,
            tar.pool_b_dex,
            tar.reserve_a_address_pool_a,
            tar.reserve_b_address_pool_a,
            tar.reserve_a_address_pool_b,
            tar.reserve_b_address_pool_b,
            tar.reserve_a_mint_pool_a,
            tar.reserve_a_mint_pool_b,
            tar.reserve_b_mint_pool_a,
            tar.reserve_b_mint_pool_b,
            tar.reserve_a_pool_a,
            tar.reserve_b_pool_a,
            tar.reserve_a_pool_b,
            tar.reserve_b_pool_b,
            tar.reserve_a_pool_a_decimals,
            tar.reserve_b_pool_a_decimals,
            tar.reserve_a_pool_b_decimals,
            tar.reserve_b_pool_b_decimals,
            tar.pool_a_fee,
            tar.pool_b_fee,
            tar.lut,
            tar.status
        FROM two_arbitrage_routes tar
        JOIN tokens t ON (
            tar.reserve_a_mint_pool_a = t.address OR
            tar.reserve_b_mint_pool_a = t.address OR
            tar.reserve_a_mint_pool_b = t.address OR
            tar.reserve_b_mint_pool_b = t.address
        )
        WHERE tar.status = 'enabled'
        AND t.tradable = TRUE
        AND t.name != 'SOL'
        AND tar.pool_b_dex = 'meteora'
        AND tar.pool_b_fee >= 2.0;
    "#;

    let arbitrage_routes: Vec<ArbitrageRoute> = sqlx::query_as::<_, ArbitrageRoute>(query)
        .fetch_all(&pool)
        .await?;

    // Print amount of routes
    println!("Amount of routes: {}", arbitrage_routes.len());
    // println!("{:?}", arbitrage_routes);

    // Filter unique routes
    let mut unique_routes: Vec<ArbitrageRoute> = Vec::new();
    for route in arbitrage_routes {
        if !unique_routes.contains(&route) {
            unique_routes.push(route);
        }
    }
    println!("Amount of unique routes: {}", unique_routes.len());
    // println!("{:?}", unique_routes);

    // Extract reserve addresses
    let reserve_addresses = extract_reserve_addresses(&unique_routes).await;
    println!("Amount of reserve addresses: {}", reserve_addresses.len());
    // println!("{:?}", reserve_addresses);
    
    // Create a HashMap to store the last amounts for each reserve
    let mut reserve_amounts: HashMap<String, u64> = HashMap::new();

    // Create a HashMap to store the lut for each pool as Pubkey
    let mut pool_luts: HashMap<String, Pubkey> = HashMap::new();
    
    for route in &unique_routes {
        if let Some(lut) = &route.lut {
            let lut_pubkey = match Pubkey::from_str(&lut) {
                Ok(pubkey) => pubkey,
                Err(_) => {
                    error!("Invalid LUT pubkey: {:?}", &lut);
                    continue;
                }
            };
            pool_luts.insert(lut.clone(), lut_pubkey);
        }
    }

    println!("Amount of pool LUTs: {}", pool_luts.len());

    // // Retrieve the serialized data from Redis
    // let serialized_data: Vec<u8> = redis_client.get_connection()?.get("latest_blockhash")?;
    // println!("Serialized data length: {}", serialized_data.len());
    
    // let options = DeOptions::new()
    //     .replace_unresolved_globals();

    // // Deserialize the pickled data
    // let blockhash_resp: GetLatestBlockhashResp = from_slice(&serialized_data, options)?;

    // // Print the latest blockhash and context
    // println!("Latest Blockhash: {:?}", blockhash_resp.value.blockhash);
    // println!("Last Valid Block Height: {:?}", blockhash_resp.value.last_valid_block_height);
    // println!("Context Slot: {:?}", blockhash_resp.context.slot);

    // Add a delay to prevent spamming the same DLMM pool address
    let mut last_swap_times: HashMap<String, std::time::Instant> = HashMap::new();

    loop {
        // println!("{} Waiting for messages {}", "-".repeat(15), "-".repeat(15));
        println!("{}", "-".repeat(35));
        match pubsub.get_message() {
            Ok(msg) => {
                info!("Received message");
                let start = std::time::Instant::now();

                let payload: String = msg.get_payload()?;
                // println!("Received: {}", payload);

                let parsed: serde_json::Value = match serde_json::from_str(&payload) {
                    Ok(val) => val,
                    Err(err) => {
                        error!("Error parsing JSON: {}", err);
                        continue;
                    }
                };
                let subscription_address = parsed["subscription_address"].as_str().unwrap_or_default();
                let account_data = &parsed["account_data"];
                let amount = account_data["amount"].as_str().unwrap_or_default();
                // let mint = account_data["mint"].as_str().unwrap_or_default();
                // let dex = account_data["dex"].as_str().unwrap_or_default();
                // let decimals = account_data["decimals"].as_u64().unwrap_or_default();
                // let timestamp = account_data["timestamp"].as_u64().unwrap_or_default();

                // println!("Subscription_address: {}", subscription_address);
                // println!("Mint: {}", mint);
                // println!("Dex: {}", dex);
                // println!("Amount: {}", amount);
                // println!("Decimals: {}", decimals);
                // println!("Timestamp: {}", timestamp);

                // let account_pubkey = match Pubkey::from_str(&subscription_address.to_string()) {
                //     Ok(pubkey) => pubkey,
                //     Err(_) => {
                //         error!("Invalid account pubkey: {}", subscription_address);
                //         continue;
                //     }
                // };
                
                // Attempt to parse the amount as a u64
                match amount.parse::<u64>() {
                    Ok(amount_u64) => {
                        // Insert or update the amount in the HashMap using the account's public key
                        reserve_amounts.insert(subscription_address.to_string(), amount_u64);
                        // println!("Amount updated for reserve {}: {}", subscription_address, amount_u64);
                    }
                    Err(_) => error!("Failed to parse amount '{}' as u64", amount),
                }

                // Optionally print the reserve amounts for debugging
                // println!("Reserve Amounts: {:?}", reserve_amounts);

                // Sample reserve addresses set
                let reserve_addresses: Vec<String> = reserve_amounts.keys().cloned().collect();

                // Find the routes belonging to the reserve address
                let mut matched_routes: Vec<&ArbitrageRoute> = Vec::new();
                for route in &unique_routes {
                    if reserve_addresses.contains(&route.reserve_a_address_pool_a)
                        || reserve_addresses.contains(&route.reserve_a_address_pool_b)
                        || reserve_addresses.contains(&route.reserve_b_address_pool_a)
                        || reserve_addresses.contains(&route.reserve_b_address_pool_b)
                    {
                        matched_routes.push(route);
                    }
                }
                
                // Print the routes for debugging
                // println!("Found {} routes based on scanned reserves", matched_routes.len());

                for route in matched_routes {
                    // Check if subscription_address is in the route
                    if !&route.reserve_a_address_pool_a.eq(subscription_address) 
                        && !&route.reserve_a_address_pool_b.eq(subscription_address)
                        && !&route.reserve_b_address_pool_a.eq(subscription_address)
                        && !&route.reserve_b_address_pool_b.eq(subscription_address) {
                        // error!("Route does not contain subscription address");
                        continue;
                    }

                    let route_start = std::time::Instant::now();
                    
                    let dex_a = &route.pool_a_dex;
                    let dex_b = &route.pool_b_dex;
                    let pool_a_address = &route.pool_a_address;
                    let pool_b_address = &route.pool_b_address;

                    // Skip if dex_a is not meteora
                    if dex_b != "meteora" {
                        error!("Route ID {:?} --> Not raydium -> meteora", &route.id);
                        continue;
                    }

                    // Get the LUT for the pool
                    let lut_pubkey = match pool_luts.get(&route.lut.clone().unwrap()) {
                        Some(pubkey) => pubkey,
                        None => {
                            error!("Route ID {:?} --> LUT not found for pool: {}", &route.id, &route.lut.clone().unwrap());
                            continue;
                        }
                    };

                    // println!("LUT Pubkey: {}", lut_pubkey);
                    
                    // Extract the reserve addresses for the pools
                    let reserve_addresses_pool_a = vec![&route.reserve_a_address_pool_a, &route.reserve_b_address_pool_a];
                    // let reserve_addresses_pool_b = vec![&route.reserve_a_address_pool_b, &route.reserve_b_address_pool_b];

                    // Extract the reserve amounts for the pools
                    let reserve_amounts_pool_a: Vec<u64> = reserve_addresses_pool_a
                        .iter()
                        .map(|address| reserve_amounts.get(*address).unwrap_or(&0).clone())
                        .collect();
                    // let reserve_amounts_pool_b: Vec<u64> = reserve_addresses_pool_b
                    //     .iter()
                    //     .map(|address| reserve_amounts.get(*address).unwrap_or(&0).clone())
                    //     .collect();

                    // Make it a dictionary
                    let mut reserves: HashMap<String, u64> = HashMap::new();
                    for (i, address) in reserve_addresses_pool_a.iter().enumerate() {
                        reserves.insert(address.to_string(), reserve_amounts_pool_a[i]);
                    }
                    let raydium_reserve_a = reserves.get(reserve_addresses_pool_a[0]).unwrap_or(&0);
                    let raydium_reserve_b = reserves.get(reserve_addresses_pool_a[1]).unwrap_or(&0);
                    if raydium_reserve_a == &0 || raydium_reserve_b == &0 {
                        error!("Route ID {:?} --> Raydium reserves 0 or not found", &route.id);
                        continue;
                    }
                    
                    let raydium_price = (*raydium_reserve_a as f64 * 1e6) / (*raydium_reserve_b as f64 * 1e9);
                    // println!("Raydium price: {:?}", raydium_price as f64);
                    
                    // Extract the DLMM pool address
                    let dlmm_pool_address = pool_b_address;
                    let dlmm_pool_address_pubkey = Pubkey::from_str(&dlmm_pool_address).unwrap();

                    let meteora_fee_decimal = route.pool_b_fee as f32 / 100.0;
                    // println!("Meteora Pool Address: {}, Fee: {}", dlmm_pool_address, meteora_fee_decimal);
                    
                    if let Some(&last_swap_time) = last_swap_times.get(dlmm_pool_address) {
                        if std::time::Instant::now().duration_since(last_swap_time) < Duration::from_millis(500) {
                            error!("Skipping swap for DLMM pool address {} to prevent spamming", dlmm_pool_address);
                            continue;
                        }
                    }

                    bins_pubsub.subscribe(&format!("dlmms:bins:{}", dlmm_pool_address));
                    
                    if route_start.elapsed() > Duration::from_millis(1) {
                        // error!("Route ID {:?} --> Pre bins above max time: {:?}", &route.id, route_start.elapsed());
                        continue;
                    }

                    info!("Route ID {:?} --> Pre bins time: {:?}", &route.id, route_start.elapsed());  
                    
                    // Retrieve the last message from the Redis key (as a String)
                    let last_bins: Option<String> = redis_client.get_connection()?.get(&format!("dlmms:bins:{}", dlmm_pool_address))?;

                    if let Some(msg) = last_bins {
                        // println!("Received response: {}", msg);
                        let route_bins_duration = route_start.elapsed();
                        if route_bins_duration > Duration::from_millis(5) {
                            error!("Route ID {:?} --> Get bins above max time: {:?}", &route.id, route_bins_duration);
                            continue;
                        }
                        info!("Route ID {:?} --> Bins time: {:?}", &route.id, route_start.elapsed());                            
        
                        let msg_parsed: serde_json::Value = match serde_json::from_str(&msg) {
                            Ok(val) => val,
                            Err(err) => {
                                error!("Error parsing JSON: {}", err);
                                continue;
                            }
                        };

                        // Get data from response
                        let active_bin_id = &msg_parsed["active_bin"];
                        let bins = &msg_parsed["bins"].as_array().unwrap();
                        let bin_arrays = msg_parsed["bin_arrays"].as_array().unwrap();
                        let luts = &msg_parsed["luts"].as_object().unwrap();
                        
                        // // println!("Bins: {:?}", bins);
                        // println!("Bin Arrays: {:?}", bin_arrays);
                        // for bin_array in bin_arrays {
                        //     println!("Bin Array: {:?}", bin_array);
                        // }

                        // Get lut addresses based on an address ""
                        let lut_addresses: Vec<Pubkey> = luts.get(&route.lut.clone().unwrap())
                            .unwrap()
                            .as_array()
                            .unwrap()
                            .iter()
                            .map(|addr| Pubkey::from_str(addr.as_str().unwrap()).unwrap())
                            .collect();
                        // println!("LUT Addresses: {:?}", lut_addresses);

                        // Get the bin with the active bin ID
                        let active_bin = &bins.iter().find(|bin| bin["bin_id"] == *active_bin_id);
                        if active_bin.is_none() {
                            error!("Route ID {:?} --> Active bin not found", &route.id);
                            error!("Route ID {:?} --> Finish time: {:?}", &route.id, route_start.elapsed());
                            continue;
                        }

                        let active_bin_price = active_bin.unwrap()["price_per_token"].as_f64().unwrap_or_default();

                        let price_diff_percentage = ((raydium_price - active_bin_price) / active_bin_price) * 100.0;

                        if price_diff_percentage > 90.0 || price_diff_percentage < -90.0 {
                            error!("Route ID {:?} --> Price difference percentage {:.2}% is not within the acceptable range", &route.id, price_diff_percentage);
                            error!("Route ID {:?} --> Finish time: {:?}", &route.id, route_start.elapsed());
                            continue;
                        }
                        
                        if raydium_price >= active_bin_price {
                            error!("Route ID {:?} --> Raydium price is greater than active bin price", &route.id);
                            error!("Route ID {:?} --> Finish time: {:?}", &route.id, route_start.elapsed());
                            continue;
                        }

                        if price_diff_percentage < -40.0 {
                            error!("Route ID {:?} --> Price difference percentage {:.2}% is less than {}%", &route.id, price_diff_percentage, -40.0);
                            error!("Route ID {:?} --> Finish time: {:?}", &route.id, route_start.elapsed());
                            continue;
                        }
                        
                        // // Get highest bin price
                        // let highest_bin_price = bins.iter().max_by(|a, b| a["price_per_token"].as_f64().unwrap_or_default().partial_cmp(&b["price_per_token"].as_f64().unwrap_or_default()).unwrap());                                
                        
                        // Get all bins with Y amount greater than 0
                        let bins_with_y = &bins.iter().filter(|bin| bin["amountY"].as_f64().unwrap_or_default() > 0.000000001).collect::<Vec<_>>();

                        if bins_with_y.is_empty() {
                            error!("Route ID {:?} --> No bins with Y amount greater than 0", &route.id);
                            error!("Route ID {:?} --> Finish time: {:?}", &route.id, route_start.elapsed());
                            continue;
                        }

                        let mut total_y_available = 0.0;
                        let mut total_x_needed = 0.0;
                        for (idx, bin) in bins_with_y.iter().enumerate() {
                            if idx > 1 {
                                continue;
                            }
                            
                            // Get bin ID
                            let bin_id = bin["bin_id"].to_string();
                            // Get bin price
                            let bin_price_per_token = bin["price_per_token"].as_f64().unwrap_or_default();
                            // Get bin amount X
                            let bin_amount_x = bin["amountX"].as_f64().unwrap_or_default();
                            // Get bin amount Y
                            let bin_amount_y = bin["amountY"].as_f64().unwrap_or_default();

                            // println!("Bin ID: {}, Price Per Token: {}, Amount X: {}, Amount Y: {}", bin_id, bin_price_per_token, bin_amount_x, bin_amount_y);

                            total_y_available += bin_amount_y;
                            total_x_needed += bin_amount_y / bin_price_per_token;
                        }    

                        // Vault balance is max 5_000_000, if total_y_needed is above cap it to vault balance and do the proportion for total_x_needed
                        let vault_balance = 0.5;
                        if total_y_available > vault_balance {
                            let proportion = vault_balance / total_y_available;
                            total_y_available = vault_balance;
                            total_x_needed *= proportion;
                        }

                        // Add meteora fee to totall X needed
                        total_x_needed = total_x_needed / (1.0 - meteora_fee_decimal as f64);

                        let total_x_needed_lamports = (total_x_needed * 1e6) as u64;

                        if total_y_available <= 0.005 {
                            error!("Route ID {:?} --> Total Y available is less than {}", &route.id, 0.005);
                            error!("Route ID {:?} --> Finish time: {:?}", &route.id, route_start.elapsed());
                            continue;
                        }                            

                        let y_cost_raydium = raydium_quote_y_for_x(total_x_needed_lamports as f64, *raydium_reserve_a as f64, *raydium_reserve_b as f64, route.pool_a_fee as f64);
                        
                        if y_cost_raydium <= 0 {
                            error!("Route ID {:?} --> Y cost Raydium is less than 0", &route.id);
                            error!("Route ID {:?} --> Finish time: {:?}", &route.id, route_start.elapsed());
                            continue;
                        }

                        if y_cost_raydium as f64 >= total_y_available as f64 * 1e9 {
                            error!("Route ID {:?} --> Y cost Raydium {} is greater than total Y available {}", &route.id, y_cost_raydium as f64, total_y_available as f64 * 1e9);
                            error!("Route ID {:?} --> Finish time: {:?}", &route.id, route_start.elapsed());
                            continue;
                        }

                        // Double check how many X will Raydium give for Y
                        // let x_received_raydium = raydium_quote_x_for_y(y_cost_raydium as f64, *raydium_reserve_b as f64, *raydium_reserve_a as f64, route.pool_a_fee as f64);

                        println!("Route: {} -> {} | {} -> {}", dex_a, pool_a_address, dex_b, pool_b_address);
                        // println!("Raydium Reserves: {:?}", reserves);
                        println!("Raydium Price: {}", raydium_price as f32);
                        println!("Meteora active Bin Price: {}", active_bin_price);

                        println!("Price Difference Percentage: {:.2}%", price_diff_percentage);

                        println!("Total Y Available: {}", total_y_available);
                        println!("Total X Needed: {}", total_x_needed);
                        println!("Total X Needed Lamports: {}", total_x_needed_lamports);
                        println!("Y Cost Raydium: {}", y_cost_raydium as f64 / 1e9);
                        // println!("X Received Raydium: {}", x_received_raydium);

                        println!("Borrow Amount Lamports: {}", y_cost_raydium);
                        
                        // Calculate profit
                        let profit = (total_y_available * 1e9) as u64 - y_cost_raydium;
                        println!("Profit: {}", profit);

                        // Get lut addresses based on an address ""
                        let lut_addresses: Vec<Pubkey> = luts.get(&route.lut.clone().unwrap())
                            .unwrap()
                            .as_array()
                            .unwrap()
                            .iter()
                            .map(|addr| Pubkey::from_str(addr.as_str().unwrap()).unwrap())
                            .collect();
                        // println!("LUT Addresses: {:?}", lut_addresses);

                        // Fetch pool keys
                        let pool_keys = fetch_amm_v4_pool_keys_from_lut_addresses(lut_addresses.clone(), route.reserve_a_pool_a_decimals as u8, route.reserve_b_pool_a_decimals as u8);

                        // // If y_cost_raydium is more than 500_000_000 set it to 500_000_000
                        // let y_cost_raydium = if y_cost_raydium > 500_000_000 { 500_000_000 } else { y_cost_raydium };
                        
                        // Compute units
                        let compute_units_ix: Instruction = ComputeBudgetInstruction::set_compute_unit_limit(750_000);

                        // Compute price
                        let compute_price_ix: Instruction = ComputeBudgetInstruction::set_compute_unit_price(1_000_000);

                        // Create WSOL token account with seed
                        let mut rng = rand::thread_rng();
                        let mut bytes = [0u8; 24];
                        rng.fill(&mut bytes);

                        let seed = URL_SAFE_NO_PAD.encode(&bytes);
                        println!("{}", seed);

                        let wsol_ata_from_seed = Pubkey::create_with_seed(&operator_pubkey, &seed, &spl_token::id()).unwrap();

                        let create_wsol_ata_ix: Instruction = system_instruction::create_account_with_seed(
                            &vault_pubkey, // From
                            &wsol_ata_from_seed, // To
                            &operator_pubkey, // Base
                            &seed, // Seed
                            2_000_0, // Lamports
                            165, // Space
                            &spl_token::id(), // Owner
                        );
                        
                        // Transfer WSOL from vault to operator
                        let borrow_ix: Instruction = spl_token::instruction::transfer(
                            &spl_token::id(),
                            &vault_wsol_ata,
                            &operator_wsol_ata,
                            &vault_pubkey,
                            &[&vault_pubkey],
                            y_cost_raydium,
                        )?;

                        // Sync WSOL token account
                        // let sync_ix: Instruction = spl_token::instruction::sync_native(&spl_token::id(), &operator_wsol_ata)?;

                        // Swap on Raydium
                        let swap_raydium_ix = match pool_keys {
                            Some(keys) => {
                                // println!("Pool Keys: {:?}", keys);

                                // Create the swap instruction
                                make_amm_v4_swap_instruction(
                                    y_cost_raydium, // amount_in
                                    0,  // minimum_amount_out
                                    operator_wsol_ata, // WSOL ATA
                                    lut_addresses.clone()[21], // token ATA
                                    &keys, // pool keys
                                    operator_pubkey, // operator pubkey
                                )
                            }
                            None => {
                                println!("Failed to fetch pool keys.");
                                continue;
                            }
                        };

                        // Swap on Meteora
                        // Assuming `dlmm_pool_address` is a String or can be converted into one
                        let get_swap_ix_request = GetMeteoraSwapIxMessage {
                            in_token: "So11111111111111111111111111111111111111112".to_string(),
                            out_token: "So11111111111111111111111111111111111111112".to_string(),
                            
                            in_amount: total_x_needed_lamports.to_string(),
                            // in_amount: x_received_raydium.to_string(),

                            min_out_amount: 0.to_string(),
                            lb_pair: dlmm_pool_address_pubkey.to_string(),
                            user_pubkey: operator_pubkey.to_string(),
                            user_ata_in: lut_addresses.clone()[21].to_string(),
                            user_ata_out: operator_wsol_ata.to_string(),
                            bin_arrays: bin_arrays.to_vec(),
                        };

                        // Convert the Pubkey to a string for the header
                        let pool_header = HeaderValue::from_str(&dlmm_pool_address_pubkey.to_string())
                            .map_err(|e| {
                                error!("Failed to create HeaderValue: {}", e);
                                io::Error::new(io::ErrorKind::InvalidInput, "Invalid header value") // Convert to a standard I/O error
                            })?;


                        let get_swap_ix_response = meteora_sdk_client
                            .post(&format!("{}/swap-ixs-arbitrage", env.clone().unwrap().meteora_sdk_url.to_string()))
                            .header("Content-Type", "application/json")
                            .header("Accept", "text/plain")
                            .header("pool", pool_header)
                            .header("rpc", env.clone().unwrap().rpc_url.to_string())
                            .json(&get_swap_ix_request)
                            .send()
                            .await;
                        
                        let swap_meteora_ix = match get_swap_ix_response {
                            Ok(response) => {
                                match response.text().await {
                                    Ok(response_payload) => {
                                        info!("Route ID {:?} --> Meteora swap ix time: {:?}", &route.id, route_start.elapsed());
                                        // println!("Received response: {}", response_payload);

                                        let response_parsed: serde_json::Value = match serde_json::from_str(&response_payload) {
                                            Ok(val) => val,
                                            Err(err) => {
                                                error!("Error parsing JSON: {}", err);
                                                error!("Route ID {:?} --> Finish time: {:?}", &route.id, route_start.elapsed());
                                                continue;
                                            }
                                        };
                                        // println!("Meteora Swap IX Response: {:?}", response_parsed);
                                        
                                        // Get the swap instruction
                                        let swap_ix = &response_parsed[0];
                                        let program_id = Pubkey::from_str(swap_ix["programId"].as_str().unwrap()).unwrap();
                                        let accounts = swap_ix["keys"].as_array().unwrap().iter().map(|account| {
                                            AccountMeta {
                                                pubkey: Pubkey::from_str(account["pubkey"].as_str().unwrap()).unwrap(),
                                                is_signer: account["isSigner"].as_bool().unwrap(),
                                                is_writable: account["isWritable"].as_bool().unwrap(),
                                            }
                                        }).collect::<Vec<AccountMeta>>();

                                        let data_bytes = swap_ix["data"].as_array().unwrap().iter().map(|byte| byte.as_u64().unwrap() as u8).collect::<Vec<u8>>();

                                        Instruction {
                                            program_id,
                                            accounts,
                                            data: data_bytes,
                                        }
                                    }                                 
                                    Err(e) => {
                                        error!("Error reading response body: {}", e);
                                        error!("Route ID {:?} --> Finish time: {:?}", &route.id, route_start.elapsed());
                                        continue;
                                    }
                                }
                            }
                            Err(e) => {
                                error!("Error sending request: {}", e);
                                error!("Route ID {:?} --> Finish time: {:?}", &route.id, route_start.elapsed());
                                continue;
                            }
                        };

                        // println!("Meteora Swap Instruction: {:?}", meteora_swap_ix);

                        // Transfer WSOL from vault to operator
                        let repay_ix: Instruction = spl_token::instruction::transfer(
                            &spl_token::id(),
                            &operator_wsol_ata,
                            &vault_wsol_ata,
                            &operator_pubkey,
                            &[&operator_pubkey],
                            y_cost_raydium,
                        )?;

                        // Make the sol WSOL available for the Jito tip
                        let claim_ix: Instruction = spl_token::instruction::close_account(
                            &spl_token::id(),
                            &wsol_ata_from_seed, // ATA
                            &operator_pubkey, // Destination
                            &operator_pubkey, // Owner
                            &[&operator_pubkey],
                        )?;

                        // Jito tip
                        // let jito_tip_lamports = 1_000_000;
                        let jito_tip_lamports = ((profit as u64) as f64 * 0.5) as u64; // 0.33
                        let random_jito_tip_account = jito_sdk.get_random_tip_account().await?;
                        let jito_tip_account = Pubkey::from_str(&random_jito_tip_account)?;
                        let jito_tip_ix: Instruction = system_instruction::transfer(
                            &operator_pubkey,
                            &jito_tip_account,
                            jito_tip_lamports,
                        );

                        // Get the recent blockhash
                        // TODO: Get the blockhash from Redis
                        let recent_blockhash: Hash = rpc_client.get_latest_blockhash()?;

                        // Create the AddressLookupTableAccount
                        let lookup_table = AddressLookupTableAccount {
                            key: Pubkey::from_str(&route.lut.clone().unwrap()).unwrap(),
                            addresses: lut_addresses, // Stored addresses
                        };

                        // Create a Versioned Transaction
                        let versioned_transaction = VersionedTransaction::try_new(
                            VersionedMessage::V0(v0::Message::try_compile(
                                &fee_payer_keypair.pubkey(),
                                // &[compute_units_ix, compute_price_ix, borrow_ix, sync_ix, swap_raydium_ix, repay_ix],
                                &[compute_units_ix, compute_price_ix, borrow_ix, swap_raydium_ix, swap_meteora_ix, repay_ix, jito_tip_ix],
                                &[lookup_table],
                                recent_blockhash,
                            )?),
                            &[&vault_keypair, &operator_keypair, &fee_payer_keypair],
                        )?;
            
                        let tx_hash = rpc_client.send_transaction_with_config(
                            &versioned_transaction,
                            RpcSendTransactionConfig {
                                skip_preflight: true,
                                preflight_commitment: Some(CommitmentLevel::Confirmed),
                                encoding: None,
                                max_retries: None,
                                min_context_slot: None,
                            },
                        )?;

                        let rpc_url = env.clone().unwrap().rpc_url.to_string().replace("https://", "");
                        let cluster = rpc_url.split('/').nth(0).unwrap_or_default();
                        info!("Transaction Hash: {:?}", format!("https://solana.fm/tx/{:?}?cluster=custom-{}", tx_hash, cluster));

                        // Update the last swap time for the DLMM pool address
                        last_swap_times.insert(dlmm_pool_address.clone(), std::time::Instant::now());

                        info!("Route ID {:?} --> Finish time: {:?}", &route.id, route_start.elapsed());
                    } else {
                        println!("No message found in the Redis key.");
                    }

                    bins_pubsub.unsubscribe(&format!("dlmms:bins:{}", dlmm_pool_address))?;
                    println!("Unsubscribed from 'dlmms:bins:{}'", dlmm_pool_address);
                }
            }
            Err(err) => {
                error!("Error receiving message: {}", err);
                thread::sleep(Duration::from_secs(1));
            }
        }
    }
}

