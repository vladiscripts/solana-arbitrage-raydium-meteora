import json
import websockets
import asyncio

async def websocket_test(endpoint_url):
    async with websockets.connect(endpoint_url) as ws:
        payload = {
            "jsonrpc": "2.0",
            "id": "5jpgzZ3oRhnc3tTtZ3KgjYNVNhN4akhPRA62sSMqVBGk",
            "method": "accountSubscribe",
            "params": ["5jpgzZ3oRhnc3tTtZ3KgjYNVNhN4akhPRA62sSMqVBGk", {"encoding": "jsonParsed", "commitment": RPC_STATUS}]
        }
        await ws.send(json.dumps(payload))
        while True:
            msg = await ws.recv()
            print("WS Event:", msg)

asyncio.run(websocket_test("YOUR_SOLANA_RPC_WSS_URL"))

