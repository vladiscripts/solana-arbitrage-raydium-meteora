import grpc
import json
import uvloop
import asyncio
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
from base58 import b58decode

import modules.geyser.geyser_pb2 as geyser_pb2
import modules.geyser.geyser_pb2_grpc as geyser_pb2_grpc

def secure_channel(target, credentials, options=None, compression=None):
    """Creates a secure Channel to a server."""
    from grpc import _channel  # pylint: disable=cyclic-import
    from grpc.experimental import _insecure_channel_credentials

    if credentials._credentials is _insecure_channel_credentials:
        raise ValueError(
            "secure_channel cannot be called with insecure credentials."
            + " Call insecure_channel instead."
        )
    return _channel.Channel(
        target,
        () if options is None else options,
        credentials._credentials,
        compression,
    )

GEYSER_GRPC_URL = "YOUR_SOLANA_RPC_URL:443"
GEYSER_API_KEY = "YOUR_SOLANA_RPC_API_KEY"
metadata = [("authorization", f"Bearer {GEYSER_API_KEY}")]

async def listen_geyser_blockhash():
    """Listen to Geyser gRPC for latest blockhash updates."""
    credentials = grpc.ssl_channel_credentials()
    channel = secure_channel(GEYSER_GRPC_URL, credentials)
    stub = geyser_pb2_grpc.GeyserStub(channel)
    request = geyser_pb2.SubscribeBlockhashUpdatesRequest()
    
    print("🔍 Listening for blockhash updates...")
    
    for response in stub.SubscribeBlockhashUpdates(request, metadata=metadata):
        blockhash = response.blockhash
        slot = response.slot
        print(f"🔄 New Blockhash: {blockhash} at Slot: {slot}")
        
# Run the gRPC listener
asyncio.run(listen_geyser_blockhash())
