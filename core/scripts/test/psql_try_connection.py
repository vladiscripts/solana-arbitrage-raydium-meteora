import asyncpg
import uvloop
import asyncio
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

async def connect():
    conn = await asyncpg.connect(user='topswellc', password='admin', database='arbitrage', host='localhost')
    print("Connection successful")
    
    # Example query
    result = await conn.fetch('SELECT * FROM tokens WHERE tradable = TRUE')
    print(f"Tradable tokens:\n{result}")

    await conn.close()

# Run the asyncio event loop
asyncio.run(connect())
