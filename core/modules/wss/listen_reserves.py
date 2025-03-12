import uvloop
import asyncio
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
import websockets
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor

import logging  # Import logging module
logger = logging.getLogger(__name__)

from config import redis_client, WS_MAX_SECONDS, RPC_ENDPOINT_LIST, RPC_ENDPOINT_LIST_ID, WS_RPC_STATUS
from modules.database import get_tradable_two_arbitrage_routes
from modules.cache import setup_cache
from modules.opportunities import find_arbitrage_opportunities

RPC_ENDPOINT = RPC_ENDPOINT_LIST[RPC_ENDPOINT_LIST_ID].replace('https://', 'wss://').replace('http://', 'ws://')

executor = ThreadPoolExecutor(max_workers=10)

def publish_to_redis_channel(subscription_address, account_data):
    """Function to publish to Redis channel in a separate thread."""
    publish_data = {
        'subscription_address': subscription_address,
        'account_data': account_data
    }
    redis_client.publish('reserves', json.dumps(publish_data))

async def extract_reserve_addresses(data):
    """Extract only the reserve addresses from the query result."""
    reserve_addresses = list(set(
        row['reserve_a_address_pool_a'] for row in data
    ) | set(
        row['reserve_b_address_pool_a'] for row in data
    ) | set(
        row['reserve_a_address_pool_b'] for row in data
    ) | set(
        row['reserve_b_address_pool_b'] for row in data
    ))
    return reserve_addresses

reload = False
reserve_amounts = {}

async def listen():
    global reload
    global ws
    global reserve_amounts
    
    reset_counter = 0

    cache_ttl_ms = 5
    
    try:
        # Check for new pool signals in a separate thread
        threading.Thread(target=redis_subscriber, daemon=True).start()

        cache = await setup_cache()
                                 
        while True:
            counter = 0
            start_time = time.time()

            async with websockets.connect(RPC_ENDPOINT) as ws:
                # Fetch tradable pools
                # routes = await get_tradable_two_arbitrage_routes()
                # LIQUIDITY_POOLS = await extract_reserve_addresses(routes)
                LIQUIDITY_POOLS = await extract_reserve_addresses(cache['arbitrage_routes'])
                logger.info(f"Listening to {int(len(LIQUIDITY_POOLS) / 4)} liquidity pools, {len(LIQUIDITY_POOLS)} reserve addresses.")

                # Subscribe to all liquidity pools
                for pool in LIQUIDITY_POOLS:
                    payload = {
                        "jsonrpc": "2.0",
                        "id": pool,
                        "method": "accountSubscribe",
                        "params": [pool, {"encoding": "jsonParsed", "commitment": WS_RPC_STATUS}]
                    }
                    await ws.send(json.dumps(payload))
                    time.sleep(0.15)

                # Initialize an empty dictionary to map subscription IDs to addresses
                subscription_map = {}

                while True:
                    if reload:
                        reset_counter += 1
                        reload = False
                        break

                    subscription_addresses_last_time = {}

                    before = time.time()
                    response = await ws.recv()
                    after = time.time()
                    # print(f"WebSocket delay: {(after - before):.6f} seconds")
                    
                    data = json.loads(response)

                    if "result" in data and "id" in data:
                        logger.info(f"✅ Subscription confirmed for {data['id']}: {data['result']}")
                        subscription_map[data['result']] = data['id']
                        continue

                    if "params" in data:
                        counter += 1

                        subscription_id = data['params']['subscription']
                        subscription_address = subscription_map.get(subscription_id, None)
                        
                        if subscription_addresses_last_time.get(subscription_address, 0) > time.time() - 0.5:
                            logger.warning(f"🚨 Duplicate update for {subscription_address}")
                            continue

                        print(f"🔄 Received {counter} updates in {-(start_time - time.time()):.0f} seconds, reloaded {reset_counter} times | {subscription_address}")

                        if after - before >= WS_MAX_SECONDS / 100:
                            # logger.warning(f"🚨 Slow response: {after - before:.6f} seconds")
                            continue

                        if subscription_address:
                            mint = data['params']['result']['value']['data']['parsed']['info']['mint']
                            dex = data['params']['result']['value']['data']['parsed']['info']['owner']
                            uiAmount = data['params']['result']['value']['data']['parsed']['info']['tokenAmount']['uiAmount']
                            amount = data['params']['result']['value']['data']['parsed']['info']['tokenAmount']['amount']
                            decimals = data['params']['result']['value']['data']['parsed']['info']['tokenAmount']['decimals']

                            reserve_amounts[subscription_address] = amount

                            account_data = {
                                'mint': mint,
                                'dex': dex,
                                'uiAmount': uiAmount,
                                'amount': amount,
                                'decimals': decimals,
                                'timestamp': int(time.time())
                            }

                            if amount == 0:
                                logger.warning(f"❗ Reserve amount is 0 for {subscription_address}.")
                                continue

                            message_data = {
                                'subscription_address': subscription_address,
                                'account_data': account_data
                            }
                            
                            status = await find_arbitrage_opportunities(cache, message_data, reserve_amounts)
                            # threading.Thread(target=find_arbitrage_opportunities, args=(arbitrage_routes, meteora_dlmm_client_objects, meteora_dlmm_objects, meteora_dlmm_bin_arrays_objects, lut_addresses, message_data, solana_client, broadcast_clients, vault, payer, operator, seed, wsol_token_account, balance_needed, compute_unit_limit, compute_unit_price, init_wsol_account_instruction, reserve_amounts), daemon=True).start()

                            # # Store it in Redis with a 500ms expiration
                            # redis_client.psetex("reserves", cache_ttl_ms, json.dumps(message_data))
                            # executor.submit(publish_to_redis_channel, subscription_address, account_data)

                            subscription_addresses_last_time[subscription_address] = time.time()

                            time.sleep(2)

                        else:
                            logger.error(f"❗ Subscription ID {subscription_id} not found in the map.")

                # Disconnect from the WebSocket
                await ws.close()

    except Exception as e:
        logger.error(f"Pools listen error: {e}")
        logger.error("Restarting the listener...")
        # Disconnect from the WebSocket
        await ws.close()

def redis_subscriber():
    """Redis subscriber that listens for 'meteora:new_pool' and triggers a reload."""
    pubsub = redis_client.pubsub()
    pubsub.subscribe("meteora:new_pool")

    for message in pubsub.listen():
        if message["type"] == "message":
            # logger.info(f"🔄 Received Redis signal: {message['data']}")

            message_data = json.loads(message['data'])  # Decode the message into a Python dict
            if message_data.get('reload') == 1:
                print("🔄 Reload triggered! Restarting WebSocket listener...")
                logger.info("🔄 Reload triggered! Restarting WebSocket listener...")

                global reload
                reload = True

                # global ws
                # ws.close()

                # Publish a signal to Redis
                message = {
                    "reload": 0
                }
                redis_client.publish("meteora:new_pool", json.dumps(message))

if __name__ == '__main__':
    asyncio.run(listen())
