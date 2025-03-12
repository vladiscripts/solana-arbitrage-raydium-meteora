import uvloop
import asyncio
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
import asyncpg
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
executor = ThreadPoolExecutor(max_workers=10)

import sys
sys.path.append('./')
from config import DB_CONFIG

# Asynchronous context manager for handling database connections
@asynccontextmanager
async def get_db_connection():
    conn = None
    try:
        # Attempt to connect to the database
        conn = await asyncpg.connect(**DB_CONFIG)
        yield conn
    except Exception as e:
        print(f"DB Connection error: {e}")
    finally:
        if conn:
            await conn.close()

async def main():
    async with get_db_connection() as conn:
        # Reset tradable tokens
        await conn.execute('''UPDATE tokens SET tradable = FALSE WHERE name != 'SOL''')

if __name__ == "__main__":
    asyncio.run(main())