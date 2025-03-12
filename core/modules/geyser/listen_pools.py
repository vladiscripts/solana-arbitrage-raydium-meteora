import grpc
import json
import time
import uvloop
import asyncio
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
from concurrent.futures import ThreadPoolExecutor
from base58 import b58decode  # Import base58 decoding function

import sys
sys.path.append('./')

# Import generated gRPC protobuf files
import modules.geyser.geyser_pb2 as geyser_pb2
import modules.geyser.geyser_pb2_grpc as geyser_pb2_grpc

from config import RPC_ENDPOINT_LIST, redis_client
from modules.database import get_tradable_two_arbitrage_routes

# Use the first available gRPC endpoint
GEYSER_GRPC_URL = "YOUR_SOLANA_RPC_URL:443"

# Assuming your Geyser API key is stored as a string in the `GEYSER_API_KEY` variable
GEYSER_API_KEY = 'YOUR_SOLANA_RPC_API_KEY'

# Create gRPC metadata
metadata = [
    ('authorization', f'Bearer {GEYSER_API_KEY}')
]

# Thread pool for Redis publishing
executor = ThreadPoolExecutor(max_workers=10)

async def extract_reserve_addresses(data):
    """Extract unique reserve addresses from pool arbitrage routes."""
    reserve_addresses = set()
    for row in data:
        reserve_addresses.update([
            row['reserve_a_address_pool_a'],
            row['reserve_b_address_pool_a'],
            row['reserve_a_address_pool_b'],
            row['reserve_b_address_pool_b']
        ])
    return list(reserve_addresses)

def publish_to_redis_channel(subscription_address, account_data):
    """Publish updates to Redis asynchronously."""
    publish_data = {
        'subscription_address': subscription_address,
        'account_data': account_data
    }
    redis_client.publish('account_updates', json.dumps(publish_data))
    print(f"🔄 Published update for {subscription_address} to 'account_updates' channel")


async def listen_geyser_grpc():
    """Listen to Geyser gRPC for liquidity pool updates."""
    # Get liquidity pools to monitor
    routes = await get_tradable_two_arbitrage_routes()
    LIQUIDITY_POOLS = await extract_reserve_addresses(routes)
    LIQUIDITY_POOLS_BYTES = [b58decode(pubkey) for pubkey in LIQUIDITY_POOLS]

    print(f"🎯 Monitoring {len(LIQUIDITY_POOLS)} reserve accounts across liquidity pools.")

    # Create a gRPC channel
    channel = grpc.insecure_channel(GEYSER_GRPC_URL, 
    options=[
        ("grpc.keepalive_time_ms", 30000),  # Keep-alive time
        ("grpc.keepalive_timeout_ms", 15000),  # Timeout duration for connection
        ("grpc.max_reconnect_backoff_ms", 60000),  # Max reconnection time
    ])
    stub = geyser_pb2_grpc.GeyserStub(channel)

    # Subscription request to Geyser
    request = geyser_pb2.SubscribeAccountUpdatesRequest(accounts=LIQUIDITY_POOLS_BYTES)

    # Track subscription IDs
    subscription_map = {}

    counter = 0
    start_time = time.time()

    # Stream updates
    for response in stub.SubscribeAccountUpdates(request, metadata=metadata):
        print(f"✅ Subscription confirmed for {response}")
        counter += 1
        subscription_id = response.subscription_id
        pubkey = response.pubkey
        slot = response.slot
        account_data_raw = response.data

        print(f"🔄 Received update {counter} in {time.time() - start_time:.2f} seconds for {pubkey}")

        # Decode account data if needed (e.g., Base64 to JSON)
        try:
            account_data = json.loads(account_data_raw.decode())
        except Exception:
            print(f"🚨 Failed to decode account data for {pubkey}")
            continue

        # Map subscription ID to address
        if subscription_id not in subscription_map:
            subscription_map[subscription_id] = pubkey

        # Extract relevant fields
        mint = account_data.get('mint', 'Unknown')
        dex = account_data.get('owner', 'Unknown')
        token_info = account_data.get('tokenAmount', {})
        uiAmount = token_info.get('uiAmount', 0)
        amount = token_info.get('amount', 0)
        decimals = token_info.get('decimals', 0)

        print(f"✅ Mint: {mint}, Dex: {dex}, Pool: {pubkey}, Amount: {amount}, Decimals: {decimals}, Sub ID: {subscription_id}")

        # Save to Redis
        redis_client.set(pubkey, json.dumps({
            'mint': mint,
            'dex': dex,
            'uiAmount': uiAmount,
            'amount': amount,
            'decimals': decimals
        }))
        print(f"💾 Redis updated for {pubkey}")

        # Publish to Redis asynchronously
        executor.submit(publish_to_redis_channel, pubkey, account_data)


# Run the gRPC listener
asyncio.run(listen_geyser_grpc())
