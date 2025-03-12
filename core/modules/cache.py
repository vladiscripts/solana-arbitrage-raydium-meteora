import uvloop
import asyncio
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
import base64
import time
import os

import logging  # Import logging module
logger = logging.getLogger(__name__)

from config import RPC_ENDPOINT_LIST, RPC_ENDPOINT_LIST_ID, SOLANA_PROGRAM, VAULT_PRIVATE_KEY, PAYER_PRIVATE_KEY, OPERATOR_PRIVATE_KEY, OPERATOR_WSOL_ATA, VAULT_WSOL_ATA, redis_client, JITO_TIP_ADDRESS
from modules.database import get_two_arbitrage_routes, get_lut_addresses_from_route
from modules.raydium_py.config import client, payer_keypair, UNIT_BUDGET, UNIT_PRICE
from modules.raydium_py.raydium.constants import ACCOUNT_LAYOUT_LEN, SOL_DECIMAL, TOKEN_PROGRAM_ID, WSOL
from modules.dlmm.dlmm import DLMM, DLMM_CLIENT

from solders.pubkey import Pubkey
from solders.keypair import Keypair
from solana.rpc.api import Client
from solana.rpc.async_api import AsyncClient

from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price  # type: ignore
from solders.system_program import (
    CreateAccountWithSeedParams,
    create_account_with_seed,
)
from spl.token.client import Token
from spl.token.instructions import (
    CloseAccountParams,
    InitializeAccountParams,
    close_account,
    create_associated_token_account,
    get_associated_token_address,
    initialize_account,
)

async def setup_cache():
    """
    Preload objects for faster access.
    """
    arbitrage_routes = await get_two_arbitrage_routes()

    # Extract all Meteora pool addresses
    meteora_pools = set()
    for route in arbitrage_routes:
        if route['pool_a_dex'] == 'meteora':
            meteora_pools.add(route['pool_a_address'])
        if route['pool_b_dex'] == 'meteora':
            meteora_pools.add(route['pool_b_address'])

    # Create DLMM objects for each Meteora pool
    meteora_dlmm_client_objects = {}
    meteora_dlmm_objects = {}
    meteora_dlmm_bin_arrays_objects = {}

    for pool_address in meteora_pools:
        try:
            dlmm = DLMM_CLIENT.create(Pubkey.from_string(pool_address), RPC_ENDPOINT_LIST[RPC_ENDPOINT_LIST_ID])
            time.sleep(0.5)
            meteora_dlmm_client_objects[pool_address] = dlmm
            dlmm = DLMM(Pubkey.from_string(pool_address), RPC_ENDPOINT_LIST[RPC_ENDPOINT_LIST_ID])
            time.sleep(0.5)
            meteora_dlmm_objects[pool_address] = dlmm
            bin_arrays = DLMM.get_bin_array_for_swap(dlmm, True, 4)
            meteora_dlmm_bin_arrays_objects[pool_address] = bin_arrays
            time.sleep(0.5)
        except Exception as e:
            if "429" in str(e):
                logger.error("Rate limited, sleeping for 5s...")
                time.sleep(5)
            elif "503" in str(e):
                logger.error("unavailable...")
            elif "lbPair" in str(e):
                logger.warning("lbPair not found, skipping...")
            else:
                logger.error(f"DLMM Cache error: {e}")

    # Fetch LUT addresses for each route and store them in a dictionary
    lut_mapping = dict(await asyncio.gather(
        *[get_lut_addresses_from_route(route['lut']) for route in arbitrage_routes if route['lut'] is not None]
    ))

    vault = Keypair.from_base58_string(VAULT_PRIVATE_KEY)
    payer = Keypair.from_base58_string(PAYER_PRIVATE_KEY)
    operator = Keypair.from_base58_string(OPERATOR_PRIVATE_KEY)

    # solana_client = Client(RPC_ENDPOINT_LIST[0])
    solana_client = Client(RPC_ENDPOINT_LIST[RPC_ENDPOINT_LIST_ID])
    broadcast_clients = []
    for endpoint in RPC_ENDPOINT_LIST:
        broadcast_client = AsyncClient(endpoint)
        broadcast_clients.append(broadcast_client)

    # print("Generating seed for WSOL account...")
    seed = base64.urlsafe_b64encode(os.urandom(24)).decode("utf-8")
    # wsol_token_account = Pubkey.create_with_seed(
    #     payer_keypair.pubkey(), seed, TOKEN_PROGRAM_ID
    # )
    operator_wsol_token_account = Pubkey.from_string(OPERATOR_WSOL_ATA)
    vault_wsol_token_account = Pubkey.from_string(VAULT_WSOL_ATA)

    balance_needed = Token.get_min_balance_rent_for_exempt_for_account(client)

    compute_unit_limit = set_compute_unit_limit(UNIT_BUDGET)
    compute_unit_price = set_compute_unit_price(UNIT_PRICE)
    
    create_wsol_account_instruction = create_associated_token_account(
        vault.pubkey(),
        operator.pubkey(),
        Pubkey.from_string(SOLANA_PROGRAM)
    )

    init_wsol_account_instruction = initialize_account(
        InitializeAccountParams(
            program_id=TOKEN_PROGRAM_ID,
            account=operator_wsol_token_account,
            mint=WSOL,
            owner=operator.pubkey(),
        )
    )

    # print("Preparing to close WSOL account after swap...")
    close_wsol_account_instruction = close_account(
        CloseAccountParams(
            program_id=TOKEN_PROGRAM_ID,
            account=operator_wsol_token_account,
            # dest=vault.pubkey(),
            dest=operator.pubkey(),
            owner=operator.pubkey(),
        )
    )

    jito_tip_address = Pubkey.from_string(JITO_TIP_ADDRESS)

    logger.info("🧠 Cache setup complete.")
    
    return {
        "arbitrage_routes": arbitrage_routes,
        "meteora_dlmm_client_objects": meteora_dlmm_client_objects,
        "meteora_dlmm_objects": meteora_dlmm_objects,
        "meteora_dlmm_bin_arrays_objects": meteora_dlmm_bin_arrays_objects,
        "lut_mapping": lut_mapping,
        "solana_client": solana_client,
        "broadcast_clients": broadcast_clients,
        "vault": vault,
        "payer": payer,
        "operator": operator,
        "seed": seed,
        "operator_wsol_token_account": operator_wsol_token_account,
        "vault_wsol_token_account": vault_wsol_token_account,
        "balance_needed": balance_needed,
        "compute_unit_limit": compute_unit_limit,
        "compute_unit_price": compute_unit_price,
        "create_wsol_account_instruction": create_wsol_account_instruction,
        "close_wsol_account_instruction": close_wsol_account_instruction,
        "init_wsol_account_instruction": init_wsol_account_instruction,
        "jito_tip_address": jito_tip_address,
    }

async def setup_dlmm_cache():
    """
    Preload objects for faster access.
    """
    arbitrage_routes = await get_two_arbitrage_routes()

    # Extract all Meteora pool addresses
    meteora_pools = set()
    for route in arbitrage_routes:
        if route['pool_a_dex'] == 'meteora':
            meteora_pools.add(route['pool_a_address'])
        if route['pool_b_dex'] == 'meteora':
            meteora_pools.add(route['pool_b_address'])

    # Create DLMM objects for each Meteora pool
    meteora_dlmm_client_objects = {}
    meteora_dlmm_bin_arrays_objects = {}

    for pool_address in meteora_pools:
        try:
            dlmm = DLMM_CLIENT.create(Pubkey.from_string(pool_address), RPC_ENDPOINT_LIST[RPC_ENDPOINT_LIST_ID])
            time.sleep(0.5)
            meteora_dlmm_client_objects[pool_address] = dlmm
            bin_arrays = DLMM.get_bin_array_for_swap(dlmm, True, 3)
            meteora_dlmm_bin_arrays_objects[pool_address] = bin_arrays
            time.sleep(0.5)
        except Exception as e:
            if "429" in str(e):
                logger.error("Rate limited, sleeping for 5s...")
                time.sleep(5)
            elif "503" in str(e):
                logger.error("unavailable...")
            elif "lbPair" in str(e):
                logger.warning("lbPair not found, skipping...")
            else:
                logger.error(f"DLMM Cache error: {e}")


    # Fetch LUT addresses for each route and store them in a dictionary
    lut_mapping = dict(await asyncio.gather(
        *[get_lut_addresses_from_route(route['lut']) for route in arbitrage_routes if route['lut'] is not None]
    ))

    logger.info("🧠 Cache setup complete.")
    
    return {
        "meteora_dlmm_client_objects": meteora_dlmm_client_objects,
        "meteora_dlmm_bin_arrays_objects": meteora_dlmm_bin_arrays_objects,
        "lut_mapping": lut_mapping,
    }
