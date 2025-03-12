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

async def get_all_luts():
    """
    Fetches all LUT addresses that are associated with non-tradable tokens.
    """
    async with get_db_connection() as conn:
        # Fetch all LUT addresses associated with non-tradable tokens
        rows = await conn.fetch('''
            SELECT * FROM luts
        ''')
        return [row['address'] for row in rows]
    
async def get_unused_luts():
    """
    Fetches all LUT addresses that are associated with non-tradable tokens.
    """
    async with get_db_connection() as conn:
        # Fetch all LUT addresses associated with non-tradable tokens
        rows = await conn.fetch('''
            SELECT * FROM luts
        ''')
        return [row['address'] for row in rows]

async def remove_lut(lut):
    """
    Removes a LUT address from the database.
    """
    async with get_db_connection() as conn:
        # Delete the LUT address from the database
        await conn.execute('''
            DELETE FROM luts WHERE address = $1
        ''', lut)

        return True
    
async def remove_unused_luts_from_db():
    """
    Removes all LUT addresses that are not associated with tradable tokens from the database.
    """
    async with get_db_connection() as conn:
        # Fetch all LUT addresses that are not associated with tradable tokens
        rows = await conn.fetch('''
            SELECT * FROM luts
        ''')
        unused_luts = [dict(row)['address'] for row in rows]

        # Delete all LUT addresses that are not associated with tradable tokens
        await conn.execute('''
            DELETE FROM luts
        ''')

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

async def main():
    print("Fetching LUTs...")

    luts = await get_all_luts()
    print("Unused LUTs:", luts)
    print("Deactivating and closing LUTs...")

    for alt in luts:
        try:
            await deactivate_alt(alt)
        except Exception as e:
            # print(f"Error deactivating LUT: {e}")
            pass
        time.sleep(0.5)
        
    print("Waiting for 4 minutes for block deactivations...")
    time.sleep(240)

    print("Closing LUTs...")
    for alt in luts:
        try:
            await close_alt(alt)
            await remove_lut(alt)
        except Exception as e:
            print(f"Error closing LUT: {e}")
            pass
        time.sleep(0.5)
    print("Unused LUTs deactivated and closed.")

if __name__ == "__main__":
    asyncio.run(main())