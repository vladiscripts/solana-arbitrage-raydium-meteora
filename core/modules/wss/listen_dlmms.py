import time
import uvloop
import asyncio

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
import websockets
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import logging  # Import logging module
logger = logging.getLogger(__name__)

import sys
sys.path.append('./')
from config import redis_client, METEORA_BINS_LEFT, METEORA_BINS_RIGHT, RESERVES_METEORA
from modules.cache import setup_dlmm_cache
from modules.reserves import fetch_reserves_meteora
from modules.dlmm.dlmm.types import BinLiquidty, GetBins

executor = ThreadPoolExecutor(max_workers=10)

def publish_to_redis_channel(subscription_address, account_data):
    """Function to publish to Redis channel in a separate thread."""
    publish_data = {
        'subscription_address': subscription_address,
        'account_data': account_data
    }
    redis_client.publish('dlmms:get_bins', json.dumps(publish_data))

reload = False

async def listen():
    global reload
    global ws
    
    reset_counter = 0

    while True:
        try:
            # Check for new pool signals in a separate thread
            threading.Thread(target=redis_reload_subscriber, daemon=True).start()

            cache = await setup_dlmm_cache()

            await redis_dlmm_bins_subscriber(cache, 2000)

        except Exception as e:
            logger.error(f"DLMMs listen error: {e}")
            logger.error("Restarting the listener...")

def redis_reload_subscriber():
    """Redis subscriber that listens for 'meteora:new_pool' and triggers a reload."""
    pubsub = redis_client.pubsub()
    pubsub.subscribe("meteora:new_pool")

    for message in pubsub.listen():
        if message["type"] == "message":
            # logger.info(f"🔄 Received Redis signal: {message['data']}")

            message_data = json.loads(message['data'])  # Decode the message into a Python dict
            if message_data.get('reload') == 1:
                print("🔄 Reload triggered! Restarting DLMMs listener...")
                logger.info("🔄 Reload triggered! Restarting DLMMs listener...")

                global reload
                reload = True

                # Publish a signal to Redis
                message = {
                    "reload": 0
                }
                redis_client.publish("meteora:new_pool", json.dumps(message))

async def process_dlmm(dlmm_pool_address):
    """Process a DLMM pool and fetch reserves."""
    bins, token_X_decimals, token_Y_decimals, all_bins, active_bin = await fetch_reserves_meteora(dlmm_pool_address, METEORA_BINS_LEFT, METEORA_BINS_RIGHT, 'rpc')

    # Convert GetBins objects to dictionaries using the `to_dict` method
    if isinstance(bins, GetBins):
        bins = bins.to_dict()  # Convert to dict if it's a GetBins object
    # if isinstance(all_bins, GetBins):
    #     all_bins = all_bins.to_dict()  # Convert to dict if it's a GetBins object

    # If bins or all_bins are lists of BinLiquidty, convert each item to a dictionary
    # Otherwise, assume they are already dictionaries or JSON serializable
    if isinstance(bins, list):
        bins = [bin_item.to_dict() if isinstance(bin_item, BinLiquidty) else bin_item for bin_item in bins]
    
    # if isinstance(all_bins, list):
    #     all_bins = [bin_item.to_dict() if isinstance(bin_item, BinLiquidty) else bin_item for bin_item in all_bins]

    # Store the bins in a dictionary to be used later in redis
    dlmm_data = {
        "bins": bins,
        "token_X_decimals": token_X_decimals,
        "token_Y_decimals": token_Y_decimals,
        # "all_bins": all_bins,
        "active_bin": active_bin
    }

    return dlmm_data

async def send_bins(response_data, cache_ttl_ms):
    """Send response data over Redis."""
    try:
        # redis_client.publish(f"dlmms:bins:{response_data.get("pool_address")}", json.dumps(response_data))
        # redis_client.psetex(f"dlmms:bins:{response_data.get("pool_address")}", cache_ttl_ms, json.dumps(response_data))

        # redis_client.set(f"dlmms:bins:{response_data.get("pool_address")}", json.dumps(response_data))
        redis_client.setex(f"dlmms:bins:{response_data.get("pool_address")}", cache_ttl_ms, json.dumps(response_data))
        
        # print(f"Response sent: {response_data.get("pool_address")} {response_data.get("bins")}")
    except Exception as e:
        print(f"Error sending response: {e}")

async def redis_dlmm_bins_subscriber(cache, cache_ttl_ms):
    """Redis subscriber that listens for 'meteora:bins' and fetches data."""
    global reload
    while True:
        if reload:
            reload = False
            break

        for meteora_dlmm_client_object in cache['meteora_dlmm_client_objects']:
            dlmm_client_object = cache['meteora_dlmm_client_objects'][meteora_dlmm_client_object]
            try:
                dlmm_data = await process_dlmm(dlmm_client_object)
                dlmm_data['pool_address'] = meteora_dlmm_client_object
                dlmm_data['bin_arrays'] = cache['meteora_dlmm_bin_arrays_objects'].get(meteora_dlmm_client_object, [])
                dlmm_data['luts'] = cache['lut_mapping']
                
                # if dlmm_data['bin_arrays'] == []:
                #     print(f"Empty bin arrays: {dlmm_data['bin_arrays']}")
                #     continue

                # print(f"DLMM data: {dlmm_data}")
                print(f"DLMM data updated for pool: {meteora_dlmm_client_object}")

                # Store the bins in Redis
                await send_bins(dlmm_data, cache_ttl_ms)

                # await asyncio.sleep(0.025)
                await asyncio.sleep(0.125) # Because of lag

            except Exception as e:
                print(f"Error processing DLMM: {e}")

        # print(f"All DLMM bins: {dlmm_bins}")

if __name__ == '__main__':
    asyncio.run(listen())
