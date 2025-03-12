from decimal import Decimal
import uvloop
import asyncio
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
import json
import time
import networkx as nx

import logging  # Import logging module
logger = logging.getLogger(__name__)

from config import redis_client, MIN_METEORA_FEE, VAULT_PUBLIC_KEY, PAYER_PUBLIC_KEY, OPERATOR_PUBLIC_KEY, TOKEN_PROGRAM, SOLANA_PROGRAM, SYSVARRENT_PROGRAM, RAYDIUM_AMM_PROGRAM, METEORA_DLMM_PROGRAM, SERUM_OPENBOOK_PROGRAM, JITO_TIP_ADDRESS
from modules.database import get_db_connection, get_pools_by_token, get_tradable_tokens, update_two_arbitrage_route_status
from modules.reserves import fetch_raydium_reserves_api, fetch_meteora_reserves_api
from modules.ata import create_associated_token_account_async
from modules.lut import fetch_raydium_lut_addresses_api, fetch_meteora_lut_addresses_api, create_and_deploy_alt, extend_alt

from solders.pubkey import Pubkey

async def normalize_route(route):
    """
    Normalize the route so that pool_a and pool_b are always in the same order.
    This ensures that (pool_a → pool_b) is treated the same as (pool_b → pool_a).
    """
    pool1 = (route["pool_a_id"], route["pool_a_address"])
    pool2 = (route["pool_b_id"], route["pool_b_address"])
    
    # Ensure consistent ordering
    if pool1 > pool2:
        pool1, pool2 = pool2, pool1
        dex1, dex2 = route["pool_b_dex"], route["pool_a_dex"]
    else:
        dex1, dex2 = route["pool_a_dex"], route["pool_b_dex"]
    
    return (
        pool1[0], pool2[0],  # pool_a_id, pool_b_id
        pool1[1], pool2[1],  # pool_a_address, pool_b_address
        dex1, dex2
    )

async def detect_unique_routes(routes):
    """
    Detects unique routes by ensuring that reversed pool orders are considered the same.
    """
    unique_routes = set()
    result = []
    
    for route in routes:
        normalized = await normalize_route(route)
        if normalized not in unique_routes:
            unique_routes.add(normalized)
            result.append(route)  # Keep the original format
    
    return result

async def find_and_save_two_arbitrage_routes():
    """
    Finds all possible two-pool arbitrage routes between Raydium and Meteora,
    and saves them to the database.
    """

    async with get_db_connection() as conn:
        try:
            # Store tradable tokens in a set for easy lookup
            rows = await get_tradable_tokens()
            tradable_tokens = {row['address'] for row in rows}
            # logger.info(f"Tradable tokens: {tradable_tokens}")

            # Step 2: Create a graph of tradable tokens
            G = nx.DiGraph()  # Directed graph for token exchanges

            # Step 3: Fetch all pools for tradable tokens
            for token in tradable_tokens:
                raydium_pools = await get_pools_by_token(token, 'raydium')
                meteora_pools = await get_pools_by_token(token, 'meteora')

                filtered_meteora_pools = []
                for pool in meteora_pools:
                    if Decimal(pool['fee']) >= MIN_METEORA_FEE:
                        filtered_meteora_pools.append(pool)
                    
                all_pools = raydium_pools + filtered_meteora_pools

                # Add edges to the graph if tokens are tradable and from different pools and DEXs
                for pool in all_pools:
                    if pool['dex'] == 'pumpfun' or pool['dex'] == 'orca':
                        continue                  

                    base_token = pool['base_token_address']
                    quote_token = pool['quote_token_address']

                    if base_token in tradable_tokens or quote_token in tradable_tokens:
                        # logger.info(f" - Adding edge {pool['id']}: {pool['address']} | {base_token} -> {quote_token} ({pool['dex']})")
                        
                        # Add forward edge (with a list of DEXes)
                        if G.has_edge(base_token, quote_token):
                            # If the edge exists, append the new pool to the list of pools
                            G[base_token][quote_token]['pools'].append({'pool_id': pool['id'], 'pool_address': pool['address'], 'dex': pool['dex'], 'fee': pool['fee']})
                        else:
                            # Otherwise, create a new edge and add the pool as the first item in the list
                            G.add_edge(base_token, quote_token, pools=[{'pool_id': pool['id'], 'pool_address': pool['address'], 'dex': pool['dex'], 'fee': pool['fee']}])

                        # Add reverse edge (for easier lookup of both directions)
                        if G.has_edge(quote_token, base_token):
                            # If the reverse edge exists, append the new pool to the list of pools
                            G[quote_token][base_token]['pools'].append({'pool_id': pool['id'], 'pool_address': pool['address'], 'dex': pool['dex'], 'fee': pool['fee']})
                        else:
                            # Otherwise, create a new reverse edge and add the pool as the first item in the list
                            G.add_edge(quote_token, base_token, pools=[{'pool_id': pool['id'], 'pool_address': pool['address'], 'dex': pool['dex'], 'fee': pool['fee']}])

            # Step 4: Find arbitrage routes (cycles of length 2)
            arbitrage_routes = []

            for start_token in tradable_tokens:
                for intermediate_token in G.neighbors(start_token):
                    if intermediate_token == start_token:
                        continue  # Skip self-loops

                    # Check if there's a path back to the start token
                    if start_token in G.neighbors(intermediate_token):
                        # Get the list of pools for each direction
                        edge1_pools = G[start_token][intermediate_token].get('pools', [])
                        edge2_pools = G[intermediate_token][start_token].get('pools', [])
                        
                        for pool1 in edge1_pools:
                            for pool2 in edge2_pools:
                                # Ensure that the edges are from different pools and different DEXs
                                if pool1['pool_id'] != pool2['pool_id']:  
                                    if pool1['dex'] != pool2['dex']:  # Ensure they are from different DEXs

                                        # logger.info(f"Found arbitrage route: {start_token} -> {intermediate_token} -> {start_token}")
                                        # logger.info(f" - Edge 1 (Pool 1): {pool1}")
                                        # logger.info(f" - Edge 2 (Pool 2): {pool2}")

                                        arbitrage_route = {
                                            'start_token': start_token,
                                            'intermediate_token': intermediate_token,
                                            'end_token': start_token,
                                            'pool1_id': pool1['pool_id'],
                                            'pool2_id': pool2['pool_id'],
                                            'pool1_address': pool1['pool_address'],
                                            'pool2_address': pool2['pool_address'],
                                            'pool1_fee': pool1['fee'],
                                            'pool2_fee': pool2['fee'],
                                            'dex1': pool1['dex'],
                                            'dex2': pool2['dex']
                                        }
                                        arbitrage_routes.append(arbitrage_route)

            # logger.info(f"Found {len(arbitrage_routes)} two-pool arbitrage routes.")
            
            # Step 5: Save the arbitrage routes to the database
            for route in arbitrage_routes:
                # print(f"Route: {route['pool1_address']} → {route['pool2_address']}")
                # logger.info(f"Route: {route['pool1_address']} → {route['pool2_address']}")
                
                # Fetch both reserve_a_address_pool_a and status in a single query
                route_data = await conn.fetchrow('''
                    SELECT 
                        reserve_a_address_pool_a, 
                        status 
                    FROM two_arbitrage_routes
                    WHERE pool_a_id = $1 AND pool_b_id = $2
                ''', route['pool1_id'], route['pool2_id'])

                # Extract the values from the result
                route_current = route_data['reserve_a_address_pool_a'] if route_data else None
                route_status = route_data['status'] if route_data else None

                if route_current != None and route_current != '':
                    # logger.info(f"Route already exists: {route}")
                    continue

                if route_status == 'skip':
                    # Skip the route if the status is 'skip'
                    continue
                
                # Fetch reserves for the route
                try:
                    pool_a_id = route['pool1_id']
                    pool_b_id = route['pool2_id']
                    pool_a_address = route['pool1_address']
                    pool_b_address = route['pool2_address']
                    pool_a_dex = route['dex1']
                    pool_b_dex = route['dex2']

                    # You would need to retrieve the reserves from your pool data
                    reserve_a_pool_a = route.get('reserve_a_pool_a', 0.0)  # Placeholder, get actual reserves
                    reserve_b_pool_a = route.get('reserve_b_pool_a', 0.0)  # Placeholder, get actual reserves
                    reserve_a_pool_b = route.get('reserve_a_pool_b', 0.0)  # Placeholder, get actual reserves
                    reserve_b_pool_b = route.get('reserve_b_pool_b', 0.0)  # Placeholder, get actual reserves

                    meteora_fee = None
                    if pool_a_dex == 'raydium':
                        meteora_fee = route['pool2_fee']
                        reserve_a_address_pool_a, reserve_b_address_pool_a, reserve_a_pool_a_decimals, reserve_b_pool_a_decimals, reserve_a_mint_pool_a, reserve_b_mint_pool_a, pool_a_fee = await fetch_raydium_reserves_api(pool_a_address)
                    elif pool_a_dex == 'meteora':
                        meteora_fee = route['pool1_fee']
                        pool_a_fee = meteora_fee
                        reserve_a_address_pool_a, reserve_b_address_pool_a, reserve_a_pool_a_decimals, reserve_b_pool_a_decimals, reserve_a_mint_pool_a, reserve_b_mint_pool_a = await fetch_meteora_reserves_api(pool_a_address)
                    else:
                        logger.info(f"Unknown DEX: {pool_a_dex} or {pool_b_dex}")
                        continue

                    if pool_b_dex == 'raydium':
                        meteora_fee = route['pool1_fee']
                        reserve_a_address_pool_b, reserve_b_address_pool_b, reserve_a_pool_b_decimals, reserve_b_pool_b_decimals, reserve_a_mint_pool_b, reserve_b_mint_pool_b, pool_b_fee = await fetch_raydium_reserves_api(pool_b_address)
                    elif pool_b_dex == 'meteora':
                        meteora_fee = route['pool2_fee']
                        pool_b_fee = meteora_fee
                        reserve_a_address_pool_b, reserve_b_address_pool_b, reserve_a_pool_b_decimals, reserve_b_pool_b_decimals, reserve_a_mint_pool_b, reserve_b_mint_pool_b = await fetch_meteora_reserves_api(pool_b_address)
                    else:
                        logger.info(f"Unknown DEX: {pool_a_dex} or {pool_b_dex}")
                        continue
                    
                    if int(meteora_fee) < 2:
                        # logger.info(f"Skipping route less than 2%")
                        # Update status of the route to 'disabled' in case of an error
                        await conn.execute('''
                            UPDATE two_arbitrage_routes
                            SET status = 'skip'
                            WHERE pool_a_id = $1 AND pool_b_id = $2
                        ''', route['pool1_id'], route['pool2_id'])
                        continue
                        
                    # Save the route to the database
                    await conn.execute('''
                        INSERT INTO two_arbitrage_routes (
                            pool_a_id, pool_b_id, pool_a_address, pool_b_address, pool_a_dex, pool_b_dex,
                            reserve_a_pool_a, reserve_b_pool_a, reserve_a_pool_b, reserve_b_pool_b,
                            reserve_a_pool_a_decimals, reserve_b_pool_a_decimals, 
                            reserve_a_pool_b_decimals, reserve_b_pool_b_decimals,
                            reserve_a_address_pool_a, reserve_b_address_pool_a, reserve_a_address_pool_b, reserve_b_address_pool_b,
                            pool_a_fee, pool_b_fee,
                            reserve_a_mint_pool_a, reserve_b_mint_pool_a, reserve_a_mint_pool_b, reserve_b_mint_pool_b,
                            status
                        ) VALUES (
                            $1, $2, $3, $4, 
                            $5, $6, $7, $8, $9, $10, 
                            $11, $12, $13, $14, 
                            $15, $16, $17, $18,
                            $19, $20,
                            $21, $22, $23, $24,
                            'enabled'  -- or 'disabled' based on logic, default 'enabled'
                        )
                        ON CONFLICT (pool_a_id, pool_b_id) 
                        DO UPDATE SET 
                            pool_a_address = EXCLUDED.pool_a_address,
                            pool_b_address = EXCLUDED.pool_b_address,
                            pool_a_dex = EXCLUDED.pool_a_dex,
                            pool_b_dex = EXCLUDED.pool_b_dex,
                            pool_a_fee = EXCLUDED.pool_a_fee,
                            pool_b_fee = EXCLUDED.pool_b_fee,
                            reserve_a_pool_a = EXCLUDED.reserve_a_pool_a,
                            reserve_b_pool_a = EXCLUDED.reserve_b_pool_a,
                            reserve_a_pool_b = EXCLUDED.reserve_a_pool_b,
                            reserve_b_pool_b = EXCLUDED.reserve_b_pool_b,
                            reserve_a_pool_a_decimals = EXCLUDED.reserve_a_pool_a_decimals,
                            reserve_b_pool_a_decimals = EXCLUDED.reserve_b_pool_a_decimals,
                            reserve_a_pool_b_decimals = EXCLUDED.reserve_a_pool_b_decimals,
                            reserve_b_pool_b_decimals = EXCLUDED.reserve_b_pool_b_decimals,
                            reserve_a_address_pool_a = EXCLUDED.reserve_a_address_pool_a,
                            reserve_b_address_pool_a = EXCLUDED.reserve_b_address_pool_a,
                            reserve_a_address_pool_b = EXCLUDED.reserve_a_address_pool_b,
                            reserve_b_address_pool_b = EXCLUDED.reserve_b_address_pool_b,
                            reserve_a_mint_pool_a = EXCLUDED.reserve_a_mint_pool_a,
                            reserve_b_mint_pool_a = EXCLUDED.reserve_b_mint_pool_a,
                            reserve_a_mint_pool_b = EXCLUDED.reserve_a_mint_pool_b,
                            reserve_b_mint_pool_b = EXCLUDED.reserve_b_mint_pool_b,
                            lut = EXCLUDED.lut,
                            status = EXCLUDED.status,
                            updated_at = CURRENT_TIMESTAMP;
                    ''', pool_a_id, pool_b_id, pool_a_address, pool_b_address, pool_a_dex, pool_b_dex,
                        reserve_a_pool_a, reserve_b_pool_a, reserve_a_pool_b, reserve_b_pool_b,
                        float(reserve_a_pool_a_decimals), float(reserve_b_pool_a_decimals),
                        float(reserve_a_pool_b_decimals), float(reserve_b_pool_b_decimals),
                        reserve_a_address_pool_a, reserve_b_address_pool_a, reserve_a_address_pool_b, reserve_b_address_pool_b,
                        # str(pool_a_fee), str(pool_b_fee),
                        pool_a_fee, pool_b_fee,
                        reserve_a_mint_pool_a, reserve_b_mint_pool_a, reserve_a_mint_pool_b, reserve_b_mint_pool_b,)
                except Exception as e:
                    logger.info(f"Failed to save route: {route} - {e}")
                    # logger.info(f"Failed to save route: {e}")
                    # Update status of the route to 'disabled' in case of an error
                    await conn.execute('''
                        UPDATE two_arbitrage_routes
                        SET status = 'skip'
                        WHERE pool_a_id = $1 AND pool_b_id = $2
                    ''', route['pool1_id'], route['pool2_id'])

            # Step 6: Detect unique routes        
            # Fetch routes and join with token info to check if both mints are tradable
            routes = await conn.fetch('''
                SELECT r.*, t1.tradable AS tradable_a, t2.tradable AS tradable_b
                FROM two_arbitrage_routes r
                JOIN tokens t1 ON r.reserve_a_mint_pool_a = t1.address  -- Check tradable for reserve_a
                JOIN tokens t2 ON r.reserve_b_mint_pool_a = t2.address  -- Check tradable for reserve_b
                WHERE r.status = 'enabled'
                AND r.pool_b_dex = 'meteora'
            ''')

            # logger.info(f"Found {len(routes)} two-pool arbitrage routes after filtering.")

            # Filter routes based on whether both tokens are tradable
            tradable_routes = [dict(row) for row in routes if row['tradable_a'] and row['tradable_b']]

            unique_routes = await detect_unique_routes(tradable_routes)
            # logger.info(f"Found {len(unique_routes)} unique two-pool arbitrage routes.")

            # unique_routes = routes

            for route in unique_routes:
                # logger.info(f"Route: {route['pool_a_address']} → {route['pool_b_address']}")
                # logger.info(f" - Dex: {route['pool_a_dex']} → {route['pool_b_dex']}")

                # Check or create LUT
                lut = route['lut']
                if lut is not None and lut != '':
                    # logger.info(f" - LUT Exists: {lut}")
                    pass
                else:
                    logger.info(" - Creating LUT...")
                    raydium_pool = None
                    meteora_pool = None
                    if route['pool_a_dex'] == 'raydium':
                        raydium_pool = route['pool_a_address']
                        meteora_pool = route['pool_b_address']
                    else:
                        raydium_pool = route['pool_b_address']
                        meteora_pool = route['pool_a_address']

                    logger.info(f" - Raydium: {raydium_pool}")
                    logger.info(f" - Meteora: {meteora_pool}")

                    # Extend LUT
                    addresses = [
                        VAULT_PUBLIC_KEY,
                        PAYER_PUBLIC_KEY,
                        OPERATOR_PUBLIC_KEY,
                        TOKEN_PROGRAM,
                        SOLANA_PROGRAM,
                        SYSVARRENT_PROGRAM,
                        RAYDIUM_AMM_PROGRAM,
                        METEORA_DLMM_PROGRAM,
                        SERUM_OPENBOOK_PROGRAM,
                        ]
                    
                    # Get the LUT addresses from pools
                    raydium_program_id, raydium_lut = await fetch_raydium_lut_addresses_api(raydium_pool)

                    if raydium_program_id != RAYDIUM_AMM_PROGRAM:
                        logger.info(f" - Raydium pool not matching AMM program")
                        await update_two_arbitrage_route_status(route['id'], 'skip')
                        continue

                    meteora_lut = await fetch_meteora_lut_addresses_api(meteora_pool)
                    
                    if not meteora_lut:
                        logger.info(f" - Meteora pool not found")
                        await update_two_arbitrage_route_status(route['id'], 'skip')
                        continue

                    # Create LUT
                    txid_alt, alt = await create_and_deploy_alt()
                    
                    # Append each LUT address to the list of addresses
                    if raydium_lut and meteora_lut:
                        addresses.extend(raydium_lut)

                        mints = [meteora_lut[0], meteora_lut[1]]
                        for mint in mints:
                            if mint != 'So11111111111111111111111111111111111111112':
                                # Create ATA
                                txid_ata, ata = await create_associated_token_account_async(mint)

                                # Update ATA into database token table
                                await conn.execute('''
                                    UPDATE tokens
                                    SET ata = $1
                                    WHERE address = $2
                                ''', str(ata), mint)

                                addresses.append(str(ata))
                        addresses.extend(meteora_lut)
                    else:
                        logger.info(" - LUT addresses not found from API")
                        continue
                        
                    # Add Jito tip address
                    addresses.append(JITO_TIP_ADDRESS)

                    # Ensure unique addresses while preserving the original order
                    unique_addresses = []
                    seen = set()

                    # logger.info(addresses)

                    for address in addresses:
                        if address not in seen:
                            # logger.info(f" - Adding address: {address}")
                            unique_addresses.append(address)
                            seen.add(address)

                    time.sleep(15)  # Add a delay to avoid rate limiting

                    pubkeys = [Pubkey.from_string(address) for address in unique_addresses]
                    txid = await extend_alt(str(alt), pubkeys)

                    # Insert LUT data into the luts table
                    await conn.execute('''
                        INSERT INTO luts (
                            pool_a_address,
                            pool_b_address,
                            address,
                            addresses,
                            authority_address,
                            payer_address
                        ) VALUES (
                            $1, $2, $3, $4, $5, $6
                        )
                    ''', raydium_pool, meteora_pool, str(alt), json.dumps(unique_addresses), PAYER_PUBLIC_KEY, PAYER_PUBLIC_KEY)

                    # Update the route with the LUT address
                    await conn.execute('''
                        UPDATE two_arbitrage_routes
                        SET lut = $1
                        WHERE id = $2
                    ''', str(alt), route['id'])
                    
                    # Clone LUT address to non-unique routes that have the same pool addresses
                    await conn.execute('''
                        UPDATE two_arbitrage_routes
                        SET lut = $1
                        WHERE (pool_a_address = $2 AND pool_b_address = $3)
                        OR (pool_a_address = $3 AND pool_b_address = $2)
                        AND lut IS NULL
                    ''', str(alt), raydium_pool, meteora_pool)

                    logger.info(f" - LUT created and cloned to other routes with matching pool addresses.")

                    # Publish a signal to Redis
                    message = {
                        "reload": 1
                    }
                    await asyncio.to_thread(redis_client.publish, "meteora:new_pool", json.dumps(message))

                    time.sleep(0.5)  # Add a delay to avoid rate limiting

        except Exception as e:
            # Find if error matches: "The node {mint} is not in the digraph."
            str_e = str(e)
            if str_e.find("The node") != -1 and str_e.find("is not in the digraph") != -1:
                # Extract the node from the error message
                node = str_e.split("The node ")[1].split(" is not in the digraph.")[0]
                if node != SOLANA_PROGRAM:
                    logger.error(f"Node not in digraph error: {e}")
                    logger.error(f"Setting token not in the digraph: {node} to non-tradable")
                    # Update the token to tradable = False
                    await conn.execute('''
                        UPDATE tokens
                        SET tradable = FALSE
                        WHERE address = $1
                    ''', node)
            else:
                logger.error(f"Route edge error: {e}")
            # return None