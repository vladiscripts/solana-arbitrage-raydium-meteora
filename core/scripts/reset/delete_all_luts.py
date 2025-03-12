import uvloop
import asyncio
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
import time
from concurrent.futures import ThreadPoolExecutor
executor = ThreadPoolExecutor(max_workers=10)

import sys
sys.path.append('./')
from config import RPC_ENDPOINT_LIST, PAYER_PRIVATE_KEY
from scripts.get_all_luts import fetch_address_lookup_tables

from solana.rpc.async_api import AsyncClient
from solana.rpc.api import Client
from solana.transaction import Transaction
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.system_program import deactivate_lookup_table, close_lookup_table
from solana.rpc.types import TxOpts

client = Client(RPC_ENDPOINT_LIST[0])

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

alts = [
    "4u9DRQMFxxYTTKBvCKWQdNzhzK2vG5ASk9nQRMrwbmp4",
    "4bC4giZytwvzqwe2cWFJ3KtZm889rq6UySw1398YhuJu",
    "CPQGpg2e81cFXgaagReo4PxTR4gcZW6b7b9qsQeLQtna",
    "qRh1TmmGJth8Fszfm5h8yTk1ZmySew9gLT4qWrYZ4Uc",
    "4s4oryZPrtE6fmh1KvkeZK8yeHEYuzCtPRFSPrYc5L3o",
    "3kJrejoA8undg1xYusinCFFLLhiKsgvNT88Ftpoub5Mx",
    "ApEWdZ7qoyzcFfXmPRZSfDCy3LpbxjzvjJc9XjqwYPGb",
    "6866Lne7HEaM1QB22Pv2ogbF8fLEN14HcUP2nVZvvKH6",
    "Hb7QkvJ837EWCdQgdvNRKThqQcP9hb7BAtUNffLn5bAZ",
    "AbMnC71q39ELEQdGo5hnotwCvLw53rYiTGQej8G5AaJz",
    "5QqRePMk4XSFXGKXej7nXQWSUJKr6d2TtWierbgT49hp",
    "B1u5tHQXZgzPfHUWpHZXALZWjna8dawTCSPixoUBQi28",
    "BSTGxDqLwppnswDuj6vsvKisD1tQDqw5XHyGEmcRgCbd",
    "FumUzqzsBTv7XhRhKTBx9dvESvWpWHxcFSgiJyDKwMBv",
    "CAtc4g5XuJf4MbwtNu3DrJry1Bn4HvmYuhCsuGLiKE9q",
    "7v1dFyciX6KNiEVLbjhHPMdzzm5g3PwDQ2R44tVuZRUG",
    "AY8nYU2gxGHE3z1JmWXyZ2XngKV2fkrTZ6K1ccpuF3AC",
    "pwpHC92skW8TkzKSqSg1yHEvY6QTxYbUz33Ufwh4q13",
    "7tceQjnhUN2TGT2L8cHfYsYB7eMtqyfckynXKYVzeyQt",
    "2z247Qdh3REzAFsCYxT9ZqT9CbcSanMSYXXispoCX1XD",
    "2MGrKeZSqkuCUCyViadD2EXwgv4yhYeTo63G1vBxoyJe",
    "4H5gFAXbjb3KDuE2QGkWDpYryKcPgbXQ9y9XbFPPDVGv",
    "JBXxwUNc57F8bu7my8Kvabuq7vp1utSc3B7WgbcHhTsp",
    "5pRxDiH8eJj83rQ3dJMuEm6xEaZSArzeJQ6F68nPAoGS",
    "EfPwSwVGUvzeKjagsHeM5uCKgXZQ2KgR9H1A8c4UpG2X",
    "J8zkaTavYdg1QEM7TofFShATaUYiNvVNJNJjNuvH66ct",
    "DmnMgcWNC92HaxXqXfYxrsE2tikxs1UC59BKj23UUQnY",
    "9J5xoJauZ7uGXPP9RcqJLKGPpZvD9a4Ka3j717s9dGrW",
    "GBA9BXWoAzMi2U7Axf5g8HHXZw3jWZSTzBDmkdJLFJZe",
    "3a82DCWsbjiAD5BaYBdQeT8Y4ctszHdp8X8bcoSqiJac",
    "6sFyvaRGy1szr2FHf5qMd2GpuWpU8Txq83YsT7dyeiYA",
    "GJy2D8pWEyifxJ5QGdnCeY714V8skxDzmBPfmKbwsRyi",
    "2VcXNiyVvHjMWttF2PHS8TwJf4nMjmHsj27Wrgbx1PE6",
    "5paxPRmTFV21N69P3zuujTnybXL7TiXpq5enToJ1vFoA",
    "9Q4GuPYZuLretFQy4sFDQL1LxyPejAq8bFNHXmCetrFj"
]

async def close_and_delete_all_luts():
    print("Fetching LUTs...")
    alts = fetch_address_lookup_tables()
    
    print("LUTs:", alts)
    print("Deactivating and closing LUTs...")

    for alt in alts:
        if alt == 'FaNqDY82RCmJLajswJjxE6veGWmqvVbKpSkscpcJoQ5B':
            # print("Skipping LUT:", alt)
            continue
        try:
            await deactivate_alt(alt)
        except Exception as e:
            # print(f"Error deactivating LUT: {e}")
            pass
        time.sleep(0.5)
        
    print("Waiting for 4 minutes for block deactivations...")
    time.sleep(240)

    print("Closing LUTs...")
    for alt in alts:
        try:
            await close_alt(alt)
        except Exception as e:
            print(f"Error closing LUT: {e}")
            pass
        time.sleep(0.5)
    print("Unused LUTs deactivated and closed.")

if __name__ == "__main__":
    asyncio.run(close_and_delete_all_luts())