import uvloop
import asyncio
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
import time
import asyncpg
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
executor = ThreadPoolExecutor(max_workers=10)

import sys
sys.path.append('./')
from config import DB_CONFIG, RPC_ENDPOINT_LIST, PAYER_PRIVATE_KEY

from solana.rpc.async_api import AsyncClient
from solana.rpc.api import Client
from solana.transaction import Transaction
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.system_program import deactivate_lookup_table, close_lookup_table
from solana.rpc.types import TxOpts

client = Client(RPC_ENDPOINT_LIST[0])

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

async def get_unused_luts():
    """
    Fetches all LUT addresses that are associated with non-tradable tokens.
    """
    async with get_db_connection() as conn:
        # Fetch all LUT addresses that are not associated with tradable tokens
        rows = await conn.fetch('''
            SELECT * FROM luts
        ''')

        unused_luts = []

        # Step 2: For each LUT address pair, find routes in two_arbitrage_routes
        for row in rows:
            pool_a_address = row['pool_a_address']
            pool_b_address = row['pool_b_address']
            
            # Step 3: Fetch two_arbitrage_routes related to the current pool addresses
            routes = await conn.fetch('''
                SELECT * FROM two_arbitrage_routes
                WHERE (pool_a_address = $1 AND pool_b_address = $2 AND status = 'skip') 
                OR (pool_a_address = $2 AND pool_b_address = $1 AND status = 'skip')
            ''', pool_a_address, pool_b_address)
            
            # Step 4: Check if tokens in the route are tradable
            for route in routes:
                # # Assuming the route has token addresses for pool_a and pool_b
                # pool_a_token_address = route['reserve_a_mint_pool_a'] if route['pool_a_dex'] == 'raydium' else route['reserve_b_mint_pool_a']
                # pool_b_token_address = route['reserve_a_mint_pool_b'] if route['pool_a_dex'] == 'raydium' else route['reserve_b_mint_pool_b']
                
                # # Check if both tokens are tradable
                # token_a = await conn.fetchrow('''
                #     SELECT tradable FROM tokens WHERE address = $1
                # ''', pool_a_token_address)
                
                # token_b = await conn.fetchrow('''
                #     SELECT tradable FROM tokens WHERE address = $1
                # ''', pool_b_token_address)

                # # Step 5: If any token is not tradable, return the LUT
                # if token_a and not token_a['tradable'] or token_b and not token_b['tradable']:
                #     print(f"LUT with pool addresses {pool_a_address} and {pool_b_address} has non-tradable tokens")
                #     # Handle the LUT as needed (e.g., return or store it)
                #     unused_luts.append(row['address'])
                unused_luts.append(row['address'])

        return unused_luts

async def remove_unused_luts_from_db(unused_luts):
    """
    Removes all LUT addresses that are not associated with tradable tokens from the database.
    """
    async with get_db_connection() as conn:
        # Delete all LUT addresses that are not associated with tradable tokens
        await conn.execute('''
            DELETE FROM luts
            WHERE address = ANY($1)
        ''', unused_luts)

        return True

async def deactivate_alt(alt):
    async with AsyncClient(RPC_ENDPOINT_LIST[0]) as client:
        payer = Keypair.from_base58_string(PAYER_PRIVATE_KEY)

        blockhash = await client.get_latest_blockhash()
        deactivate_alt_ix = deactivate_lookup_table(
            {
                "lookup_table_address": Pubkey.from_string(alt),
                "authority_address": payer.pubkey(),
            }
        )

        # Initialize the transaction
        txn = Transaction()
        txn.add(deactivate_alt_ix)

        # Send the transaction to deactivate the ALT
        deactivate_resp = await client.send_transaction(
            txn, payer, opts=TxOpts(skip_preflight=False)
        )
        print("🚀 Address Lookup Table Deactivated")
        print(f"Signature: https://solana.fm/tx/{deactivate_resp.value}")

        return f"https://solana.fm/tx/{deactivate_resp.value}"
        
async def close_alt(alt):
    async with AsyncClient(RPC_ENDPOINT_LIST[0]) as client:
        payer = Keypair.from_base58_string(PAYER_PRIVATE_KEY)

        close_alt_ix = close_lookup_table(
            {
                "lookup_table_address": Pubkey.from_string(alt),
                "authority_address": payer.pubkey(),
                "recipient_address": payer.pubkey(),
            }
        )

        # Initialize the transaction
        txn = Transaction()
        txn.add(close_alt_ix)

        # Send the transaction to deactivate the ALT
        close_resp = await client.send_transaction(
            txn, payer, opts=TxOpts(skip_preflight=False)
        )
        print("🚀 Address Lookup Table Closed")
        print(f"Signature: https://solana.fm/tx/{close_resp.value}")

        return f"https://solana.fm/tx/{close_resp.value}"

async def get_and_delete_unused_luts():
    print("Fetching unused LUTs...")

    unused_luts = await get_unused_luts()
    print("Unused LUTs:", unused_luts)

    print("Deactivating and closing unused LUTs...")
    for alt in unused_luts:
        try:
            await deactivate_alt(alt)
        except Exception as e:
            # print(f"Error deactivating LUT: {e}")
            pass
        time.sleep(0.5)
        
    print("Waiting for 4 minutes for block deactivations...")
    time.sleep(240)

    print("Closing unused LUTs...")
    for alt in unused_luts:
        try:
            await close_alt(alt)
        except Exception as e:
            print(f"Error closing LUT: {e}")
            pass
        time.sleep(0.5)
    print("Unused LUTs deactivated and closed.")
    
    if await remove_unused_luts_from_db(unused_luts):
        print("Unused LUTs removed from database.")

if __name__ == "__main__":
    asyncio.run(get_and_delete_unused_luts())