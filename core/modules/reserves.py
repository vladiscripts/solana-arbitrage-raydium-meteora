import asyncio
import json
import ssl
import time
import certifi
# Manually configure SSL to use Certifi
ssl_context = ssl.create_default_context()
ssl_context.load_verify_locations(certifi.where())
import aiohttp
import asyncpg
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed
executor = ThreadPoolExecutor(max_workers=10)

import logging  # Import logging module

# Setup logging configuration
logging.basicConfig(
    filename='app.log',           # Log to file
    level=logging.ERROR,           # Logging level
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

import sys
sys.path.append('./')
from config import DB_CONFIG, RPC_ENDPOINT, RPC_ENDPOINT_LIST, RPC_ENDPOINT_LIST_ID, redis_client, RESERVES_RAYDIUM, RESERVES_METEORA
from modules.dlmm.dlmm import DLMM, DLMM_CLIENT

from spl.token._layouts import MINT_LAYOUT
from solders.pubkey import Pubkey
from solana.rpc.api import Client

client = Client(RPC_ENDPOINT)

@asynccontextmanager
async def get_db_connection():
    conn = await asyncpg.connect(**DB_CONFIG)
    try:
        yield conn
    finally:
        await conn.close()

async def fetch_token_decimals(mint_address):
    mint_public_key = Pubkey.from_string(mint_address)
    info = client.get_account_info(mint_public_key)
    return MINT_LAYOUT.parse(info.value.data).decimals

async def fetch_raydium_reserves_api(pool_address):
    """Fetch Raydium pool reserves via API."""
    url = f"https://api-v3.raydium.io/pools/key/ids?ids={pool_address}"
    
    # print(url)
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
        async with session.get(url) as response:
            data = await response.json()
            # print(data)
            if data.get("success") and isinstance(data.get("data"), list) and data["data"]:
                pool_data = data["data"][0]
                return (
                    pool_data.get("vault", {}).get("A", ""),
                    pool_data.get("vault", {}).get("B", ""),
                    pool_data.get("mintA", {}).get("decimals", 9),
                    pool_data.get("mintB", {}).get("decimals", 9),
                    pool_data.get("mintA", {}).get("address", ""),
                    pool_data.get("mintB", {}).get("address", ""),
                    0.0025,  # Raydium fee
                )
    
    return "", "", 9, 9, "", "", 0.0025  # Default fallback values

# async def fetch_meteora_reserves_api(pool_address):
#     url = f'https://dlmm-api.meteora.ag/pair/{pool_address}'
#     async with aiohttp.ClientSession() as session:
#         async with session.get(url) as response:
#             data = await response.json()
#             if 'reserve_x' in data:
#                 # Fix flipped reserves for Meteora
#                 return (
#                     data['reserve_x'],  # Token B
#                     data['reserve_y'],  # Token A
#                     await fetch_token_decimals(data['mint_x']),
#                     await fetch_token_decimals(data['mint_y']),
#                     data['mint_x'],  # Token B
#                     data['mint_y'],  # Token A
#                     float(data['base_fee_percentage']) / 100,
#                 )
#             return '', '', 9, 9, '', '', 0.1
        
async def fetch_meteora_reserves_api(pool_address):
    try:
        dlmm = DLMM(Pubkey.from_string(pool_address), RPC_ENDPOINT_LIST[RPC_ENDPOINT_LIST_ID])
        # dlmm = dlmm_objects.get(pool_address, None)
        # print(f"DLMM: {dlmm}")
        return (
            str(dlmm.token_X.reserve),  # Token B
            str(dlmm.token_Y.reserve),  # Token A
            str(dlmm.token_X.decimal),  # Token B
            str(dlmm.token_Y.decimal),  # Token A
            str(dlmm.token_X.public_key),  # Token B
            str(dlmm.token_Y.public_key),  # Token A
        )
    except Exception as e:
        if f"Fetch Meterora reserves error: {e}" == "Fetch Meterora reserves error: 'lbPair'":
            pass
        else:
            logger.error(f"Fetch Meterora reserves error: {e}")
        return "", "", 9, 9, "", ""

# async def fetch_token_account_balance(client, token_account_address):
#     try:
#         response = await client.get_token_account_balance(Pubkey.from_string(token_account_address))
#         return response.value.amount if response.value else None
#     except Exception as e:
#         print(f"Balance fetch error: {e}")
#         return None
    
def fetch_token_account_balance(client, token_account_address):
    try:
        response = client.get_token_account_balance(Pubkey.from_string(token_account_address))
        return response.value.amount if response.value else None
    except Exception as e:
        logger.error(f"Balance fetch error: {e}")
        return None

def fetch_pool_reserve_balances(client, reserve_addresses):
    balances = {}
    with ThreadPoolExecutor(max_workers=len(reserve_addresses)) as executor:
        # Submit all tasks to the executor
        future_to_addr = {
            executor.submit(fetch_token_account_balance, client, addr): addr 
            for addr in reserve_addresses
        }
        # Collect results as they complete
        for future in as_completed(future_to_addr):
            addr = future_to_addr[future]
            balances[addr] = future.result()
    return balances

def fetch_token_account_balance_redis(token_account_address):
    try:
        # Fetch both balances from Redis
        pool_data_list = redis_client.mget(token_account_address)
        # print(f"{token_account_address} Pool Data List: {pool_data_list}")

        pool_data = pool_data_list[0] if pool_data_list[0] else None

        # Parse JSON if data exists
        pool_data = json.loads(pool_data) if pool_data else None

        # Extract amounts
        amount = pool_data.get("amount") if pool_data else None
        # print(f"Amount: {amount}")

        return amount
    except Exception as e:
        logger.error(f"Balance fetch error: {e}")
        return None
    
def fetch_pool_reserve_balances_redis(reserve_addresses):
    balances = {}
    for addr in reserve_addresses:
        balances[addr] = fetch_token_account_balance_redis(addr)
    return balances

def fetch_pool_reserve_balances_fixed(reserve_addresses, reserve_amounts):
    balances = {}
    for addr in reserve_addresses:
        balances[addr] = reserve_amounts.get(addr, None)
    return balances

# async def calculate_arbitrage_profit(pool_a, pool_b, dex_a, dex_b, fee_a, fee_b):
#     # Determine pool types
#     clmm_pool = pool_a if dex_a == 'raydium' else pool_b if dex_b == 'raydium' else None
#     dlmm_pool = pool_a if dex_a == 'meteora' else pool_b if dex_b == 'meteora' else None

#     if not clmm_pool or not dlmm_pool:
#         return None, 0.0

#     # Calculate prices
#     price_clmm = clmm_pool['reserve_a'] / clmm_pool['reserve_b'] if clmm_pool['reserve_a'] > 0 else 0
#     price_dlmm = dlmm_pool['reserve_b'] / dlmm_pool['reserve_a'] if dlmm_pool['reserve_a'] > 0 else 0

#     print(f"Price CLMM: {price_clmm}, Price DLMM: {price_dlmm}")

#     # Determine direction
#     if price_clmm < price_dlmm:
#         direction = 'a_to_b' if dex_a == 'raydium' else 'b_to_a'
#         amount = await calculate_clmm_swap(clmm_pool, fee_a)
#         received = amount * price_dlmm * (1 - fee_b)
#         cost = amount * price_clmm / (1 - fee_a)
#     else:
#         direction = 'a_to_b' if dex_b == 'raydium' else 'b_to_a'
#         amount = await estimate_dlmm_swap(dlmm_pool, fee_b)
#         received = amount * price_clmm * (1 - fee_a)
#         cost = amount * price_dlmm / (1 - fee_b)

#     profit = received - cost
#     return direction, max(profit, 0.0)

# async def calculate_clmm_swap(pool, fee):
#     try:
#         k = pool['reserve_a'] * pool['reserve_b']
#         return (pool['reserve_b'] - (k / (pool['reserve_a'] * (2 - fee)))) / (1 - fee)
#     except ZeroDivisionError:
#         return 0.0

# async def estimate_dlmm_swap(pool, fee):
#     # Simplified DLMM swap estimation (should be replaced with bin calculations)
#     return min(pool['reserve_a'], pool['reserve_b']) * 0.01  # Conservative 1% estimate

def fetch_reserves_raydium(client, addresses, decimals, reserve_amounts):
    # Function to fetch reserves for Raydium DEX
    if RESERVES_RAYDIUM == 'cache':
        balances = fetch_pool_reserve_balances_fixed(addresses, reserve_amounts)
    elif RESERVES_RAYDIUM == 'rpc':
        balances = fetch_pool_reserve_balances(client, addresses)
    elif RESERVES_RAYDIUM == 'redis':
        balances = fetch_pool_reserve_balances_redis(addresses)
    else:
        logger.error("Invalid Raydium reserves choice in config.py")
        return None
    
    return {
        'reserve_a': float(balances[addresses[0]] or 0) / 10 ** float(decimals[0]),
        'reserve_b': float(balances[addresses[1]] or 0) / 10 ** float(decimals[1])
    }
    # return {
    #     'reserve_a': balances[addresses[0]] or 0,
    #     'reserve_b': balances[addresses[1]] or 0
    # }

async def fetch_reserves_meteora(dlmm, min_bins, max_bins, cache):
    # Fetch reserves and prices from DLMM
    token_X_decimals = dlmm.token_X.decimal
    token_Y_decimals = dlmm.token_Y.decimal

    if cache == 'rpc':
        all_bins = DLMM_CLIENT.get_all_bins(dlmm, min_bins, max_bins)

        bins = []
        for bin in all_bins.bin_liquidty:
            bin_price_per_token = float(bin.price_per_token)
            # print(f"Bin ID: {bin.bin_id}, Price per Token: {bin_price_per_token}")

            # Convert hex values to scaled decimals
            amountX_scaled = scale_value(hex_to_decimal(bin.x_amount), token_X_decimals)
            amountY_scaled = scale_value(hex_to_decimal(bin.y_amount), token_Y_decimals)

            bins.append({
                "bin_id": bin.bin_id,
                "price_per_token": bin_price_per_token,
                "amountX": amountX_scaled,
                "amountY": amountY_scaled
            })

        # Reorder bins by price
        bins = sorted(bins, key=lambda x: x['price_per_token'], reverse=True)

        return bins, token_X_decimals, token_Y_decimals, all_bins, all_bins.active_bin
    
    elif cache == 'redis':
        all_bins = redis_client.get(f"dlmms:bins:{dlmm.pool_address}")

        if all_bins:
            all_bins = json.loads(all_bins)
            return all_bins.get("bins"), all_bins.get("token_X_decimals"), all_bins.get("token_Y_decimals"), None, all_bins.get("active_bin")       
         
        else:
            logger.error(f"DLMM bins not found in Redis for {dlmm.pool_address}")
            return None
    else:
        logger.error("Invalid Meteora reserves choice in config.py")
        return None

# Supporting functions
def scale_value(value, decimals):
    return value / (10 ** decimals)

def hex_to_decimal(hex_str):
    return int(hex_str, 16)

if __name__ == '__main__':
    asyncio.run(fetch_reserves_raydium(None, ['ARFSbQVwQAtquPMWnckGNMcdHiT9P2F92kkrbv5KfWbW', 'DjDYu81bjC2PgudjdhgJLJk6mV315T7vNPWZj9PmeubN'], [6, 9]))