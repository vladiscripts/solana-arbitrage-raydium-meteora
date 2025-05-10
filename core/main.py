import sys
import uvloop
import asyncio

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

import logging  # Import logging module

# Setup logging configuration
logging.basicConfig(
    filename='app.log',           # Log to file
    level=logging.INFO,           # Logging level
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

logging.getLogger('asyncio').setLevel(logging.WARNING)
logging.getLogger('uvloop').setLevel(logging.WARNING)
logging.getLogger('redis').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('requests').setLevel(logging.WARNING)
logging.getLogger('aiohttp').setLevel(logging.WARNING)

from core.config import WSOL_ADDRESS
from core.modules.database import add_pool, setup_database, save_new_meteora_pools, add_token, get_tokens
from core.modules.meteora.scan import fetch_coin_data, send_alert
from core.modules.pools import fetch_pools_for_token, fetch_raydium_pools_for_token
from core.modules.routes import find_and_save_two_arbitrage_routes
from scripts.delete_unused_luts import get_and_delete_unused_luts
from scripts.reset.delete_outdated import reset as reset_outdated
from scripts.reset.reset_db import reset as reset

from modules.wss.listen_reserves import listen
from modules.wss.listen_block import listen_block
from modules.wss.listen_dlmms import listen as listen_dlmms

async def scan_new_meteora_pools():
    """
    Fetch new pools on Meteora concurrently.
    """
    print("🔊 Listening for new Meteora pools...")
    logger.info("🔊 Listening for new Meteora pools...")
    while True:
        try:
            # Get Meteora pools data
            data = await fetch_coin_data()

            # Save data to the database and get new pools
            new_pools = await save_new_meteora_pools(data)

            # Send alert for new pools
            if new_pools:
                pool_name, pool_address, mint, fee = await send_alert(new_pools)
                if mint is not None:
                    if pool_name.split('-')[-1] == 'SOL':
                        # logger.info(f"Adding {pool_name.split('-')[0]}: {mint}")
                        await add_token(pool_name.split('-')[0], mint)
                        await add_pool(mint, WSOL_ADDRESS, pool_address, 'meteora', float(fee), None, None, None)

            sleep_time = 2
            await asyncio.sleep(sleep_time)  # Add a delay to avoid rate limiting
        except Exception as e:
            logger.error(f"Scanning new Meteora pools error: {e}")

async def scan_pools():
    """
    Fetch pools for all tokens concurrently.
    """
    print("🔊 Listening for pools...")
    logger.info("🔊 Listening for pools...")
    while True:
        tokens = await get_tokens()
        
        for token in tokens:
            if token['address'] == WSOL_ADDRESS:
                continue
            pools = await fetch_pools_for_token(token, tokens)
            raydium_pools = await fetch_raydium_pools_for_token(token)
            # print(f"Found {len(pools)} pools for {token['address']}, {len(raydium_pools)} on Raydium")
            # logger.info(f"Found {len(pools)} pools for {token['address']}, {len(raydium_pools)} on Raydium")
            await asyncio.sleep(0.2)  # Add a delay to avoid rate limiting

        sleep_time = 5
        # logger.info(f"Finished fetching pools, sleeping {sleep_time}s...")
        await asyncio.sleep(sleep_time)  # Add a delay to avoid rate limiting

async def scan_routes():
    """
    Fetch routes for all pools concurrently.
    """
    print("🔊 Listening for routes...")
    logger.info("🔊 Listening for routes...")
    while True:
        try:
            await find_and_save_two_arbitrage_routes()
        except Exception as e:
            logger.error(f"Scanning routes error: {e}")
        
        sleep_time = 5
        # logger.info(f"Finished fetching routes, sleeping {sleep_time}s...")
        await asyncio.sleep(sleep_time)  # Add a delay to avoid rate limiting

async def scan_reserves():
    """
    Listen for pool updates and refresh subscriptions periodically.
    """
    print("🔊 Listening for reserves updates...")
    logger.info("🔊 Listening for reserves updates...")
    while True:
        await listen()  # Modify listen_to_pools to accept dynamic pools

async def scan_dlmms():
    """
    Listen for pool updates and refresh subscriptions periodically.
    """
    print("🔊 Listening for DLMM requests...")
    logger.info("🔊 Listening for DLMM requests...")
    while True:
        await listen_dlmms()  # Modify listen_to_pools to accept dynamic pools

async def scan_blocks():
    """
    Listen for blockhash updates and refresh subscriptions periodically.
    """
    print("🔊 Listening for blocks...")
    logger.info("🔊 Listening for blocks...")
    while True:
        await listen_block()  # Modify listen_to_pools to accept dynamic pools

async def main():
    await setup_database()
    tasks = []

    if len(sys.argv) < 2:
        logger.error("Main execution error: Not enough arguments")
        return

    options = {
        'n': scan_new_meteora_pools,
        'p': scan_pools,
        'r': scan_routes,
        'l': scan_reserves,
        'm': scan_dlmms,
        'b': scan_blocks,
    }

    if sys.argv[1] in options:
        tasks.append(asyncio.create_task(options[sys.argv[1]]()))
        await asyncio.gather(*tasks)
    elif sys.argv[1] == 'listen':
        tasks.extend([
            asyncio.create_task(scan_blocks()),
            asyncio.create_task(scan_reserves()),
        ])
        await asyncio.gather(*tasks)
    elif sys.argv[1] == 'pools':
        tasks.extend([
            asyncio.create_task(scan_new_meteora_pools()),
            asyncio.create_task(scan_pools()),
            asyncio.create_task(scan_routes()),
        ])
        await asyncio.gather(*tasks)
    elif sys.argv[1] == 'full':
        tasks.extend([
            asyncio.create_task(scan_new_meteora_pools()),
            asyncio.create_task(scan_pools()),
            asyncio.create_task(scan_routes()),
            asyncio.create_task(scan_blocks()),
            asyncio.create_task(scan_reserves()),
        ])
        await asyncio.gather(*tasks)
    elif sys.argv[1] == 'clean':
        tasks.extend([
            asyncio.create_task(get_and_delete_unused_luts()),
        ])
        await asyncio.gather(*tasks)
    elif sys.argv[1] == 'reset_outdated':
        tasks.extend([
            asyncio.create_task(reset_outdated()),
        ])
        await asyncio.gather(*tasks)
    elif sys.argv[1] == 'reset':
        tasks.extend([
            asyncio.create_task(reset()),
        ])
        await asyncio.gather(*tasks)
    else:
        logger.error("Main execution error: Invalid argument")
        return

if __name__ == "__main__":
    asyncio.run(main())
