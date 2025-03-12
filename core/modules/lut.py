import ssl
import certifi
# Manually configure SSL to use Certifi
ssl_context = ssl.create_default_context()
ssl_context.load_verify_locations(certifi.where())
import uvloop
import asyncio
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
import aiohttp
import asyncpg
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
executor = ThreadPoolExecutor(max_workers=10)

import logging  # Import logging module
logger = logging.getLogger(__name__)

from config import DB_CONFIG, PAYER_PRIVATE_KEY, OPERATOR_PRIVATE_KEY, RPC_ENDPOINT

from solana.rpc.async_api import AsyncClient
from solana.rpc.api import Client
from solana.transaction import Transaction
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.system_program import create_lookup_table, extend_lookup_table, deactivate_lookup_table, close_lookup_table
from solana.rpc.types import TxOpts

client = Client(RPC_ENDPOINT)

async def create_and_deploy_alt():
    async with AsyncClient(RPC_ENDPOINT) as client:
        payer = Keypair.from_base58_string(PAYER_PRIVATE_KEY)

        # Create Address Lookup Table
        blockhash = await client.get_latest_blockhash()
        create_alt_ix, alt_address = create_lookup_table(
            {
                "authority_address": payer.pubkey(),
                "payer_address": payer.pubkey(),
                "recent_slot": blockhash.context.slot,
            }
        )

        # Initialize the transaction
        txn = Transaction()
        txn.add(create_alt_ix)

        # Send the transaction to create the ALT
        create_resp = await client.send_transaction(
            txn, payer, opts=TxOpts(skip_preflight=False)
        )
        print(f"🚀 Address Lookup Table Created: {alt_address}")
        logger.info(f"🚀 Address Lookup Table Created: {alt_address}")
        logger.info(f"Signature: https://solana.fm/tx/{create_resp.value}")

        return f"https://solana.fm/tx/{create_resp.value}", alt_address

async def extend_alt(alt, addresses):
    async with AsyncClient(RPC_ENDPOINT) as client:

        payer = Keypair.from_base58_string(PAYER_PRIVATE_KEY)
        
        extend_alt_ix = extend_lookup_table(
            {
                "payer_address": payer.pubkey(),
                "lookup_table_address": Pubkey.from_string(alt),
                "authority_address": payer.pubkey(),
                "new_addresses": addresses,
            }
        )

        # Initialize the transaction
        txn = Transaction()
        txn.add(extend_alt_ix)

        # Send the transaction to extend the ALT
        extend_resp = await client.send_transaction(
            txn, payer, opts=TxOpts(skip_preflight=False)
        )
        print(f"🚀 Address Lookup Table Extended")
        logger.info(f"🚀 Address Lookup Table Extended")
        logger.info(f"Signature: https://solana.fm/tx/{extend_resp.value}")

        return f"https://solana.fm/tx/{extend_resp.value}"

async def deactivate_alt(alt):
    async with AsyncClient(RPC_ENDPOINT) as client:
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
        print(f"🚀 Address Lookup Table Deactivated")
        print(f"Signature: https://solana.fm/tx/{deactivate_resp.value}")

        return f"https://solana.fm/tx/{deactivate_resp.value}"
        
async def close_alt(alt):
    async with AsyncClient(RPC_ENDPOINT) as client:
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
        print(f"🚀 Address Lookup Table Closed")
        print(f"Signature: https://solana.fm/tx/{close_resp.value}")

        return f"https://solana.fm/tx/{close_resp.value}"

# asyncio.run(create_and_deploy_alt())
# alt = "8TUwPotiZsjvmgZCxqwN2xocZVNX4NagqBNdekH3Jrnc"
# addresses = [
#     Pubkey.from_string("4JPhDe5xaqGYHvFcuzG8LoBVFoZZEHRg3nBTmZQitsL1"),
#     Pubkey.from_string("DrhqHbF1FQZpj2ELpjZJnbcxQ8hbcSMEqtdE4NiEtsL3"),
# ]
# asyncio.run(extend_alt(alt, addresses))

@asynccontextmanager
async def get_db_connection():
    conn = await asyncpg.connect(**DB_CONFIG)
    try:
        yield conn
    finally:
        await conn.close()

async def fetch_raydium_lut_addresses_api(pool_address):
    """Fetch Raydium pool reserves via API."""
    url = f"https://api-v3.raydium.io/pools/key/ids?ids={pool_address}"
    
    print(url)
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
        async with session.get(url) as response:
            data = await response.json()
            if data.get("success") and isinstance(data.get("data"), list) and data["data"]:
                pool_data = data["data"][0]
                # print(pool_data)
                return pool_data.get("programId", {}), [pool_data.get("id", {}), 
                     pool_data.get("openOrders", {}),
                     pool_data.get("targetOrders", {}),
                     pool_data.get("vault", {}).get("A", ""),
                     pool_data.get("vault", {}).get("B", ""),
                     pool_data.get("marketId", {}),
                     pool_data.get("marketBids", {}),
                     pool_data.get("marketAsks", {}),
                     pool_data.get("marketEventQueue", {}),
                     pool_data.get("marketBaseVault", {}),
                     pool_data.get("marketQuoteVault", {}),
                     pool_data.get("marketAuthority", {})]
                    
    return None, None  # Default fallback values

async def fetch_meteora_lut_addresses_api(pool_address):
    url = f'https://dlmm-api.meteora.ag/pair/{pool_address}'
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
                if 'reserve_x' in data:
                    # Fix flipped reserves for Meteora
                    return [
                        data['mint_x'],  # Mint A
                        data['mint_y'],  # Mint B
                        data['reserve_x'],  # Token B
                        data['reserve_y'],  # Token A
                    ]
                return None
    except Exception as e:
        return None