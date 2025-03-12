import base64
import os
import uvloop
import asyncio
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
from concurrent.futures import ThreadPoolExecutor
executor = ThreadPoolExecutor(max_workers=10)

import logging  # Import logging module
logger = logging.getLogger(__name__)

import sys
sys.path.append('./')
from config import PAYER_PRIVATE_KEY, OPERATOR_PRIVATE_KEY, VAULT_PRIVATE_KEY, RPC_ENDPOINT, TOKEN_PROGRAM, OPERATOR_WSOL_ATA

from solana.rpc.api import Client
from solana.rpc.types import TxOpts
from solana.transaction import Transaction

from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.system_program import (
    CreateAccountWithSeedParams,
    create_account_with_seed,
)
from solders.message import MessageV0
from solders.transaction import VersionedTransaction

from spl.token.instructions import get_associated_token_address, create_associated_token_account, close_account, CloseAccountParams, initialize_account, InitializeAccountParams
from spl.token.client import Token

async def create_associated_token_account_async(mint: str = "So11111111111111111111111111111111111111112"):
    client = Client(RPC_ENDPOINT)

    payer = Keypair.from_base58_string(PAYER_PRIVATE_KEY)
    operator = Keypair.from_base58_string(OPERATOR_PRIVATE_KEY)

    # Define the token mint and operator for the associated token account
    token_mint = Pubkey.from_string(mint)  # Replace with your token mint
    operator = operator.pubkey()

    # Create the associated token account instruction
    associated_token_account_address = get_associated_token_address(operator, token_mint)
    
    # Transaction: Create associated token account
    txn = Transaction()
    txn.add(create_associated_token_account(
        payer.pubkey(),
        operator,
        token_mint
    ))

    try:
        # Send the transaction to create the associated token account
        response = client.send_transaction(
            txn, payer, opts=TxOpts(skip_preflight=False, preflight_commitment='confirmed')
        )

        print(f"🚀 Associated Token Account {associated_token_account_address} created for token: {mint}")
        logger.info(f"🚀 Associated Token Account {associated_token_account_address} created for token: {mint}")
        logger.info(f"Signature: https://solana.fm/tx/{response.value}")

        return f"https://solana.fm/tx/{response.value}", associated_token_account_address
    
    except Exception as e:
        print(f"🚀 Associated Token Account Exists for token: {mint} | {associated_token_account_address}")
        # print("An error occurred:", e)
        logger.error(f"🚀 Associated Token Account Exists for token: {mint} | {associated_token_account_address}")
        # logger.error(f"An error occurred: {e}")
        return None, associated_token_account_address
    
async def create_associated_token_account_with_seed_async(mint: str = "So11111111111111111111111111111111111111112"):
    client = Client(RPC_ENDPOINT)

    payer = Keypair.from_base58_string(PAYER_PRIVATE_KEY)
    operator = Keypair.from_base58_string(OPERATOR_PRIVATE_KEY)
    vault = Keypair.from_base58_string(VAULT_PRIVATE_KEY)

    # Define the token mint and operator for the associated token account
    token_mint = Pubkey.from_string(mint)  # Replace with your token mint

    print("Generating seed for WSOL account...")
    # seed = base64.urlsafe_b64encode(os.urandom(24)).decode("utf-8")
    fixed_seed = "5TY4WTrI-X1ZvWhSdZOwebIIxRfwMm_e"
    seed = fixed_seed

    wsol_token_account = Pubkey.create_with_seed(
        operator.pubkey(), seed, Pubkey.from_string(TOKEN_PROGRAM)
    )
    balance_needed = Token.get_min_balance_rent_for_exempt_for_account(client)
    
    # Transaction: Create associated token account
    txn = Transaction()

    create_wsol_account_instruction = create_account_with_seed(
        CreateAccountWithSeedParams(
            from_pubkey=vault.pubkey(),
            to_pubkey=wsol_token_account,
            base=operator.pubkey(),
            seed=seed,
            lamports=0,
            # lamports=int(balance_needed),
            space=165,
            owner=Pubkey.from_string(TOKEN_PROGRAM),
        )
    )

    txn.add(create_wsol_account_instruction)

    print(f"Creating WSOL account with seed: {wsol_token_account} | {seed}")
    logger.info(f"Creating WSOL account with seed: {wsol_token_account} | {seed}")

    try:
        blockhash = client.get_latest_blockhash()

        # Compile the transaction to v0 message with lookup table
        message_v0 = MessageV0.try_compile(
            payer=payer.pubkey(),
            recent_blockhash=blockhash.value.blockhash,
            instructions=txn.instructions,
            address_lookup_table_accounts=[
            ],
        )
        txn_v0 = VersionedTransaction(message_v0, [payer, vault, operator])

        # # Optionally, send the transaction
        response = client.send_transaction(
            # txn_v0, opts=TxOpts(skip_preflight=True)
            txn_v0, opts=TxOpts(skip_preflight=False, preflight_commitment='confirmed')
        )

        print(f"🚀 Associated Token Account {wsol_token_account} created for token: {mint}")
        logger.info(f"🚀 Associated Token Account {wsol_token_account} created for token: {mint}")
        logger.info(f"Signature: https://solana.fm/tx/{response.value}")

        return f"https://solana.fm/tx/{response.value}", wsol_token_account
    
    except Exception as e:
        print(f"🚀 Associated Token Account Exists for token: {mint} | {wsol_token_account}")
        print("An error occurred:", e)
        logger.error(f"🚀 Associated Token Account Exists for token: {mint} | {wsol_token_account}")
        logger.error(f"An error occurred: {e}")
        return None, wsol_token_account

async def close_associated_token_account_async(mint: str = "So11111111111111111111111111111111111111112"):
    client = Client(RPC_ENDPOINT)

    payer = Keypair.from_base58_string(PAYER_PRIVATE_KEY)
    operator = Keypair.from_base58_string(OPERATOR_PRIVATE_KEY)

    # Define the token mint and operator for the associated token account
    token_mint = Pubkey.from_string(mint)  # Replace with your token mint

    # Create the associated token account address
    associated_token_account_address = get_associated_token_address(operator.pubkey(), token_mint)
    # associated_token_account_address = Pubkey.from_string(OPERATOR_WSOL_ATA)
    
    # Transaction: Close associated token account
    txn = Transaction()
    txn.add(close_account(CloseAccountParams(
        Pubkey.from_string(TOKEN_PROGRAM),
        associated_token_account_address,
        payer.pubkey(),
        operator.pubkey(),
        # [operator.pubkey()]
    )))

    # init_wsol_account_instruction = initialize_account(
    #     InitializeAccountParams(
    #         program_id=Pubkey.from_string(TOKEN_PROGRAM),
    #         account=associated_token_account_address,
    #         mint=token_mint,
    #         owner=operator.pubkey(),
    #     )
    # )
    # txn.add(init_wsol_account_instruction)

    try:
        blockhash = client.get_latest_blockhash()

        # Compile the transaction to v0 message with lookup table
        message_v0 = MessageV0.try_compile(
            payer=payer.pubkey(),
            recent_blockhash=blockhash.value.blockhash,
            instructions=txn.instructions,
            address_lookup_table_accounts=[
            ],
        )
        txn_v0 = VersionedTransaction(message_v0, [payer, operator])

        # # Optionally, send the transaction
        response = client.send_transaction(
            # txn_v0, opts=TxOpts(skip_preflight=True)
            txn_v0, opts=TxOpts(skip_preflight=False, preflight_commitment='confirmed')
        )

        print(f"🚀 Associated Token Account {associated_token_account_address} closed for token: {mint}")
        logger.info(f"🚀 Associated Token Account {associated_token_account_address} closed for token: {mint}")
        logger.info(f"Signature: https://solana.fm/tx/{response.value}")

        return f"https://solana.fm/tx/{response.value}", associated_token_account_address
    
    except Exception as e:
        logger.error(f"🚀 Associated Token Account Does Not Exist for token: {mint} | {associated_token_account_address}")
        logger.error(f"An error occurred: {e}")
        return None, associated_token_account_address
    
# Run the async function to create the account
async def main():
    tx_url, associated_token_account = await create_associated_token_account_async()

# Run the async function to create the account
async def create_with_seed():
    tx_url, associated_token_account = await create_associated_token_account_with_seed_async()

# Run the async function to create the account
async def close():
    tx_url, associated_token_account = await close_associated_token_account_async()

# Run the main async function
if __name__ == "__main__":
    if sys.argv[1] == "create":
        asyncio.run(main())
    elif sys.argv[1] == "create_with_seed":
        asyncio.run(create_with_seed())
    elif sys.argv[1] == "close":
        asyncio.run(close())
    else:
        print("Invalid command. Use 'create' or 'close'.")
        sys.exit(1)
