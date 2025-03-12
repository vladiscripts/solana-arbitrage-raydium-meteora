import uvloop
import asyncio
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
import json

from config import redis_client

# Global variables to store data from Redis listener
account_updates = []

# This function will listen for Redis updates and store them in the global account_updates list
def redis_listener(pubsub):
    """This function listens for Redis messages and adds them to the account_updates list."""
    print("Listening for updates on 'account_updates' channel...")
    
    try:
        for message in pubsub.listen():
            if message['type'] == 'message':  # Check if it's a new update
                account_data = json.loads(message['data'])  # Decode the message into a Python dict
                print(f"Received account update: {account_data}")
                account_updates.append(account_data)  # Store updates in a global list
    except KeyboardInterrupt:
        print("Stopped listening for updates.")
        pubsub.unsubscribe()  # Unsubscribe when you stop listening

# Main loop for scanning and reacting to new opportunities
async def setup_redis():
    """
    Setup redis pubsub
    """
    pubsub = redis_client.pubsub()
    pubsub.subscribe('account_updates')  # Subscribe to the 'account_updates' channel
    
    # Start the Redis listener in the background
    loop = asyncio.get_event_loop()
    redis_listener_task = loop.run_in_executor(None, redis_listener, pubsub)
    
    # Cancel the Redis listener task when done (if you plan to stop scanning arbitrage)
    # redis_listener_task.cancel()

    return redis_listener_task, account_updates
