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
from scripts.reset.delete_all_atas import close_and_delete_all_atas
from scripts.reset.delete_all_luts import close_and_delete_all_luts
from scripts.get_meteora_pools import add_filtered_meteora_pools

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

async def reset_db_tables():
    async with get_db_connection() as conn:
        # # Remove all routes from database
        # await conn.execute('DELETE FROM two_arbitrage_routes WHERE created_at < NOW() - INTERVAL \'1 hours\'')
        # # Remove all pools from database
        # await conn.execute('DELETE FROM pools WHERE created_at < NOW() - INTERVAL \'1 hours\'')
        # # Reset tradable tokens
        # await conn.execute('UPDATE tokens SET tradable = FALSE WHERE created_at < NOW() - INTERVAL \'1 hours\'')

        # Remove all routes from database
        await conn.execute('DELETE FROM two_arbitrage_routes WHERE created_at < NOW() - INTERVAL \'20 minutes\'')
        # Remove all pools from database
        await conn.execute('DELETE FROM pools WHERE created_at < NOW() - INTERVAL \'20 minutes\'')
        # Reset tradable tokens
        await conn.execute('UPDATE tokens SET tradable = FALSE WHERE created_at < NOW() - INTERVAL \'20 minutes\'')

        # Reset tradable tokens
        await conn.execute('''UPDATE tokens SET tradable = TRUE WHERE name = 'SOL' ''')

        # Keep the following token tradable
        # await conn.execute('''UPDATE tokens SET tradable = TRUE WHERE name = 'CARTOON' ''')
    
async def reset():
    print("Resetting database tables...")
    await reset_db_tables()
    await close_and_delete_all_atas()
    await close_and_delete_all_luts()
    # await add_filtered_meteora_pools()
    print("Database tables reset successfully.")

if __name__ == "__main__":
    asyncio.run(reset())