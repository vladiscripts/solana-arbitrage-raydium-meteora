import aiohttp
import requests
from concurrent.futures import ThreadPoolExecutor
executor = ThreadPoolExecutor(max_workers=10)

import logging  # Import logging module
logger = logging.getLogger(__name__)

from config import SOLANA_PROGRAM
from modules.database import *
# from modules.raydium_py.utils.api import get_pool_info_by_id

API_URL = "https://dlmm-api.meteora.ag/pair/"

async def fetch_coin_data(pair_address):
    """Fetch coin data from Meteora API."""
    async with aiohttp.ClientSession() as session:
        async with session.get(API_URL + pair_address) as response:
            if response.status == 200:
                return await response.json()
            else:
                # logger.error(f"Error fetching Meteora pool {pair_address} data: {response.status}, {await response.text()}")
                return {}
            
async def fetch_pools_for_token(token):
    """
    Fetches pools for a given token and adds them to the database.
    """
    name = token['name']
    address = token['address']

    # Skip stablecoins
    blacklisted_coins = ['SOL', 'USDC', 'USDT']
    if name in blacklisted_coins:
        return []

    # print(f"Fetching all pools for: {name} ({address})")

    try:
        response = requests.get(
            f"https://api.dexscreener.com/token-pairs/v1/solana/{address}",
            headers={},
        )
        response.raise_for_status()
        data = response.json()

        # print(f"Found {len(data)} pools for {name}")

        for pool in data:
            try:
                # Extract pool data
                dex = pool['dexId']
                pool_address = pool['pairAddress']
                # base_token_name = pool['baseToken']['symbol']
                base_token_address = pool['baseToken']['address']
                # quote_token_name = pool['quoteToken']['symbol']
                quote_token_address = pool['quoteToken']['address']
                # price_native = float(pool['priceNative'])
                # price_usd = float(pool['priceUsd'])

                if base_token_address != SOLANA_PROGRAM and quote_token_address != SOLANA_PROGRAM:
                    # print(f"Skipping pool with base token address: {base_token_address} and quote token address: {quote_token_address}")
                    continue
                
                # if dex == 'orca':
                #     # print(f"Skipping Orca pool: {base_token_name} - {quote_token_name}")
                #     continue

                # print(f"Adding pool: {base_token_name} - {quote_token_name} ({dex})")
                
                # # Ensure base_token_address and quote_token_address are inserted into the tokens table
                # await add_token(base_token_name, base_token_address)
                # await add_token(quote_token_name, quote_token_address)

                fee = 0
                bin_step = None

                if dex == 'meteora':
                    # Fetch fee and bin step from Meteora API
                    meteora_pool_data = await fetch_coin_data(pool_address)
                    fee = meteora_pool_data.get('base_fee_percentage', 5)
                    bin_step = meteora_pool_data.get('bin_step', 100)

                # Add pool to the database
                await add_pool(base_token_address, quote_token_address, pool_address, dex, Decimal(fee), bin_step, 0, 0)

            except Exception as e:
                print(f"Error adding pool: {e}")

        return data if data else []

    except requests.exceptions.RequestException as e:
        print(f"Error fetching pools for {name}: {e}")
         
async def fetch_raydium_pools_for_token(token):
    """
    Fetches pools for a given token and adds them to the database.
    """
    name = token['name']
    address = token['address']

    # Skip stablecoins
    blacklisted_coins = ['SOL', 'USDC', 'USDT']
    if name in blacklisted_coins:
        return []

    # print(f"Fetching all pools for: {name} ({address})")

    try:
        response = requests.get(
            f"https://api-v3.raydium.io/pools/info/mint?mint1={address}&poolType=all&poolSortField=volume24h&sortType=desc&pageSize=10&page=0",
            headers={},
        )
        response.raise_for_status()
        data = response.json()

        # print(f"Found {data['data']['count']} Raydium pools for {name}")

        for pool in data['data']['data']:
            try:
                # Extract pool data
                pool_type = pool['type']
                if pool_type != 'Standard':
                    print(f"Skipping pool with type: {pool_type}")
                    logger.warning(f"Skipping pool with type: {pool_type}")
                    continue

                pool_address = pool['id']
                # base_token_name = pool['mintA']['symbol']
                base_token_address = pool['mintA']['address']
                # quote_token_name = pool['mintB']['symbol']
                quote_token_address = pool['mintB']['address']
                # price_native = float(pool['price'])
                # price_usd = float(pool['priceUsd']) # Not available in the API response

                if base_token_address != SOLANA_PROGRAM and quote_token_address != SOLANA_PROGRAM:
                    # print(f"Skipping pool with base token address: {base_token_address} and quote token address: {quote_token_address}")
                    continue

                dex = 'raydium'
                fee = 0
                bin_step = None

                # Add pool to the database
                await add_pool(base_token_address, quote_token_address, pool_address, dex, Decimal(fee), bin_step, 0, 0)
            except Exception as e:
                print(f"Error adding pool: {e}")

        return data['data']['data'] if data['data']['data'] else []

    except requests.exceptions.RequestException as e:
        print(f"Error fetching pools for {name}: {e}")

# async def fetch_raydium_prices_api():
#     """
#     API Fetch Raydium prices for each pool with dex = 'raydium'.
#     """
#     print("API Fetching reserves from Raydium...")

#     pools = await get_pools_by_dex('raydium')
    
#     for pool in pools:
#         pool_id = pool['address']
#         pool_info = await asyncio.get_event_loop().run_in_executor(executor, get_pool_info_by_id, pool_id)

#         if 'data' in pool_info and pool_info['data']:
#             pool_data = pool_info['data'][0]
#             print(f"Pool Info for: {pool_id}")
#             print(f" - Price: {pool_data.get('price', 'N/A')}")
#         else:
#             print(f"No data found for the pool ID: {pool_id}")

#         await asyncio.sleep(0.01)  # Add a delay to avoid rate limiting

#     print("Finished fetching Raydium prices.")
