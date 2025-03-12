from decimal import Decimal
import uvloop
import asyncio

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
import aiohttp
import sqlite3
import json

import logging  # Import logging module
logger = logging.getLogger(__name__)

import sys
sys.path.append('./')
from config import SOLANA_PROGRAM, redis_client  # Assuming you already have Redis client in config
from modules.database import add_pool, add_token, count_meteora_pools
from modules.pools import fetch_pools_for_token

API_URL = "https://dlmm-api.meteora.ag/pair/all_by_groups"

async def fetch_coin_data(page=0, limit=0):
    """Fetch coin data from Meteora API."""
    params = {
        "page": page,
        "limit": limit,
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(API_URL, params=params) as response:
            if response.status == 200:
                return await response.json()
            else:
                logger.error(f"Error fetching Meteora all data: {response.status}, {await response.text()}")
                return {}
            
async def add_filtered_meteora_pools():
    data = await fetch_coin_data()

    filtered_pools = []
    for group in data.get("groups", []):
        for pair in group.get("pairs", []):
            if pair['name'].split("-")[-1] != "SOL":
                continue
            if float(pair['base_fee_percentage']) != 5:
                continue
            if float(pair['trade_volume_24h']) == 0 or float(pair['fees_24h']) == 0:
                continue
            if float(pair['trade_volume_24h']) >= 100000:
                continue
            if float(pair['fees_24h']) <= 1000 or float(pair['fees_24h']) >= 25000:
                continue
            # if float(pair['volume'].get("hour_24", 0)) != 0:
            #     continue
            # if float(pair['volume'].get("hour_12", 0)) != 0:
            #     continue
            # if float(pair['volume'].get("hour_4", 0)) != 0:
            #     continue
            # if float(pair['volume'].get("hour_2", 0)) != 0:
            #     continue
            # if float(pair['volume'].get("hour_1", 0)) != 0:
            #     continue
            # if float(pair['volume'].get("min_30", 0)) != 0:
            #     continue
            if float(pair['volume'].get("min_30", 0)) == 0:
                continue
            filtered_pools.append(pair)

    print(f"Filtered SOL pools with base fee 5% and 30 minutes trade volume: {len(filtered_pools)}")

    for pool in filtered_pools:
        print(f"New pool detected for mint {pool['mint_x']}: {pool['name']} at address {pool['address']}. Base fee: {pool['base_fee_percentage']}%. Trade volume: {pool['trade_volume_24h']}. Fees 24h: {pool['fees_24h']}")
        await add_token(pool['name'].split('-')[0], pool['mint_x'])
        await add_pool(pool['mint_x'], SOLANA_PROGRAM, pool['address'], 'meteora', Decimal(pool['base_fee_percentage']), None, None, None)

        # await fetch_pools_for_token({"name": pool['name'].split('-')[0], "address": pool['mint_x']})
        
if __name__ == "__main__":
    asyncio.run(add_filtered_meteora_pools())