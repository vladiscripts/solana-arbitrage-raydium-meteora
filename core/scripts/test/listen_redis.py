import redis

def redis_listener():
    # Connect to the Redis server
    redis_client = redis.StrictRedis(host='localhost', port=6379, db=1, decode_responses=True)
    
    # Create a Redis pub/sub object
    pubsub = redis_client.pubsub()
    
    # Subscribe to a specific channel (e.g., "account_updates")
    pubsub.subscribe('account_updates')
    
    print("Listening for updates on 'account_updates' channel...")
    
    # Start listening for messages in the background
    try:
        for message in pubsub.listen():
            if message['type'] == 'message':  # Check if the message is a new update
                # Parse the message (assuming it's JSON-encoded)
                account_data = message['data']
                print(f"Received update: {account_data}")
                
                # You can further process the data here if needed
                # e.g., update your system, send notifications, etc.
    except KeyboardInterrupt:
        print("Stopped listening for updates.")
        pubsub.unsubscribe()  # Unsubscribe when you stop listening

if __name__ == "__main__":
    redis_listener()
