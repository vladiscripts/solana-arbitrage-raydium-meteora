import uvloop
import asyncio
import asyncpg
from contextlib import asynccontextmanager

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

import sys
sys.path.append('./')
from config import DB_CONFIG, SOLANA_PROGRAM
from modules.database import add_token, add_pool

# Asynchronous context manager for handling database connections
@asynccontextmanager
async def get_db_connection():
    conn = None
    try:
        # Attempt to connect to the database
        conn = await asyncpg.connect(**DB_CONFIG)
        yield conn
    except Exception as e:
        if f'{e}' == 'syntax error at or near ")"':
            pass
        else:
            print(f"DB Connection error: {e}")
    finally:
        if conn:
            await conn.close()
    
async def set_tradable_token(name, tradable=True):
	async with get_db_connection() as conn:
		await conn.execute('''
			UPDATE tokens SET tradable = $1 WHERE name = $2
		''', tradable, name)
                  
async def main():
	name = sys.argv[1]
	mint = sys.argv[2]
	pool_address = sys.argv[3]

	if sys.argv[4] == 'meteora':
		dex = 'meteora'
		fee = 5
	elif sys.argv[4] == 'raydium':
		dex = 'raydium'
		fee = 0.25
	else:
		dex = ''
		fee = 0

	await add_token(name, mint)
	await set_tradable_token(name)
	print(f"Added token {name} with mint {mint} to database.")
	
	await add_pool(mint, SOLANA_PROGRAM, pool_address, dex, float(fee), None, None, None)
	print(f"Added pool {name} with mint {mint} and pool address {pool_address} to database.")

asyncio.run(main())