import uvloop
import asyncio
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
import time

import logging  # Import logging module
logger = logging.getLogger(__name__)

import sys
sys.path.append('./')
from config import RPC_ENDPOINT_LIST, PAYER_PRIVATE_KEY, OPERATOR_PRIVATE_KEY

from solana.transaction import Transaction
from solders.pubkey import Pubkey
from solders.keypair import Keypair
from solders.system_program import TransferParams, transfer
from solders.transaction import VersionedTransaction
from solders.message import MessageV0
from solana.rpc.types import TxOpts

from solana.rpc.api import Client
solana_client = Client(RPC_ENDPOINT_LIST[0])

# # Generate a new keypair (or load from file)
# vault = Keypair.from_base58_string(VAULT_PRIVATE_KEY)
payer = Keypair.from_base58_string(PAYER_PRIVATE_KEY)
operator = Keypair.from_base58_string(OPERATOR_PRIVATE_KEY)

async def transfer_all_sol():
    print("Starting transfer...")

    start_time = time.time()    

    # Get SOL balance of the operator
    operator_balance = solana_client.get_balance(operator.pubkey())
    operator_balance = operator_balance.value
    print(f"Operator balance: {operator_balance} SOL")
    
    operator_balance_time = time.time()
    print(f"🕒 Execution time for operator balance: {(operator_balance_time - start_time) * 1000:.3f} ms")

    # Create multiple instructions (e.g., two SOL transfers)
    transfer_ix = transfer(TransferParams(from_pubkey=operator.pubkey(), to_pubkey=payer.pubkey(), lamports=operator_balance))
    transfer_ix_time = time.time()
    print(f"🕒 Execution time for transfer ix: {(transfer_ix_time - start_time) * 1000:.3f} ms")
    
    # Initialize the transaction
    txn = Transaction()
    txn.add(transfer_ix)

    blockhash = solana_client.get_latest_blockhash()

    blockhash_time = time.time()
    print(f"🕒 Execution time for blockhash: {(blockhash_time - start_time) * 1000:.3f} ms")

    # Compile the transaction to v0 message with lookup table
    message_v0 = MessageV0.try_compile(
        payer=payer.pubkey(),
        recent_blockhash=blockhash.value.blockhash,
        instructions=txn.instructions,
        address_lookup_table_accounts=[
        ],
    )

    message_v0_time = time.time()
    print(f"🕒 Execution time for message_v0: {(message_v0_time - start_time) * 1000:.3f} ms")

    # Create the VersionedTransaction from the v0 message
    txn_v0 = VersionedTransaction(message_v0, [payer, operator])

    txn_v0_time = time.time()
    print(f"🕒 Execution time for txn_v0: {(txn_v0_time - start_time) * 1000:.3f} ms")

    send_tx_time = time.time()
    # # Optionally, send the transaction
    send_resp = solana_client.send_transaction(
        # txn_v0, opts=TxOpts(skip_preflight=True)
        txn_v0, opts=TxOpts(skip_preflight=False)
    )

    print(f"🕒 Execution time for transfer: {(send_tx_time - start_time) * 1000:.3f} ms")
    print(f"🚀 Transaction Signature: https://solana.fm/tx/{send_resp.value}")


if __name__ == '__main__':
    asyncio.run(transfer_all_sol())