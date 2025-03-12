import uvloop
import asyncio
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
import aiohttp
import sqlite3
import json

import logging  # Import logging module
logger = logging.getLogger(__name__)

from config import redis_client  # Assuming you already have Redis client in config
from modules.database import count_meteora_pools

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
            
async def send_alert(new_pools):
    for pool in new_pools:
        count = await count_meteora_pools(pool['mint_x'])
        if count == 1:
            # print(f"Related Meteora pools found: {count}")
            print(f"🔎 New pool detected for mint {pool['mint_x']} {pool['name']} at address {pool['address']} Base fee: {pool['base_fee_percentage']}%")
            logger.info(f"🔎 New pool detected for mint {pool['mint_x']} {pool['name']} at address {pool['address']} Base fee: {pool['base_fee_percentage']}%")
            return pool['name'], pool['address'], pool['mint_x'], pool['base_fee_percentage']
            # You can replace this with an email, SMS, or webhook call.
        else:
            return None, None, None, None