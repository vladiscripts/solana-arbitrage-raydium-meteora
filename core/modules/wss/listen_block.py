
import uvloop
import asyncio
import pickle
from concurrent.futures import ThreadPoolExecutor

import logging  # Import logging module
logger = logging.getLogger(__name__)

import sys
sys.path.append('./')
from config import redis_client, RPC_ENDPOINT_LIST, RPC_ENDPOINT_LIST_ID

from solana.rpc.api import Client

# Set event loop policy to uvloop
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
solana_client = Client(RPC_ENDPOINT_LIST[RPC_ENDPOINT_LIST_ID])

RPC_ENDPOINT = RPC_ENDPOINT_LIST[RPC_ENDPOINT_LIST_ID].replace('https://', 'wss://').replace('http://', 'ws://')

executor = ThreadPoolExecutor(max_workers=10)

async def listen_block():
    """Continuously fetch the latest blockhash and store the response object in Redis using pickle."""
    latest_block = None
    while True:
        try:
            # Get the latest blockhash response object
            blockhash_resp = solana_client.get_latest_blockhash()

            # Check if the blockhash has changed
            if blockhash_resp.value.blockhash != latest_block:
                latest_block = blockhash_resp.value.blockhash
                # logger.info(f"🔄 New Block: {blockhash_resp.value.blockhash}")
                # logger.info(type(blockhash_resp))

                # Serialize the entire response object using pickle
                serialized_data = pickle.dumps(blockhash_resp)
                # print(serialized_data)
                
                # Store it in Redis with a 2-second expiration
                redis_client.setex("latest_blockhash", 10, serialized_data)
            else:
                # logger.info("⏳ Waiting for new block...")
                pass

            await asyncio.sleep(0.25)
        except Exception as e:
            logger.warning(f"🚨 Block listen error: {e}")
            logger.error("🔄 Restarting the block listener...")

if __name__ == '__main__':
    # Start the block listening process
    asyncio.run(listen_block())