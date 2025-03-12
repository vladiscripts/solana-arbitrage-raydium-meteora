import uvloop
import asyncio
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
import time
import pickle

import logging  # Import logging module
logger = logging.getLogger(__name__)

from config import OPERATOR_WSOL_ATA, redis_client, RPC_ENDPOINT_LIST, RPC_STATUS
# from modules.raydium_py.raydium.amm_v4 import buy_ix
from modules.raydium_py.raydium.amm_v4 import buy_ix_fixed
from modules.dlmm.dlmm import DLMM

from solana.transaction import Transaction
from solders.pubkey import Pubkey
from solders.instruction import Instruction, AccountMeta
from solders.system_program import TransferParams, transfer
from solders.transaction import VersionedTransaction
from solders.message import MessageV0
from solana.rpc.types import TxOpts
from solders.address_lookup_table_account import AddressLookupTableAccount
from solders.signature import Signature
from solana.rpc.async_api import AsyncClient

# from solana.rpc.api import Client
# solana_client = Client(RPC_ENDPOINT_LIST[0])

# # Generate a new keypair (or load from file)
# vault = Keypair.from_base58_string(VAULT_PRIVATE_KEY)
# payer = Keypair.from_base58_string(PAYER_PRIVATE_KEY)
# operator = Keypair.from_base58_string(OPERATOR_PRIVATE_KEY)

def deserialize_blockhash_with_pickle(serialized_blockhash):
    """Deserialize the blockhash object using pickle."""
    return pickle.loads(serialized_blockhash)

def get_latest_blockhash_from_redis():
    """Function to retrieve the latest blockhash from Redis."""
    serialized_blockhash = redis_client.get("latest_blockhash")
    if serialized_blockhash:
        # Deserialize the blockhash object using pickle
        blockhash_data = deserialize_blockhash_with_pickle(serialized_blockhash)
        # print(f"Latest Blockhash: {blockhash_data.value.blockhash}")
        # print(type(blockhash_data))
        return blockhash_data
    else:
        logger.warning("🚨 No blockhash found in Redis.")
        return None

async def simulate_transaction(solana_client, txn):
    sim_resp = await solana_client.simulate_transaction(txn)
    if sim_resp.value.err:
        raise Exception(f"Simulation failed: {sim_resp.value.err}")
    return sim_resp

async def broadcast(self, tx: Transaction) -> list[Signature]:
    """Broadcast to multiple nodes simultaneously"""
    tasks = []
    for endpoint in self.rpc_endpoints:
        client = AsyncClient(endpoint)
        tasks.append(client.send_transaction(tx, self.wallet))
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return [r for r in results if not isinstance(r, Exception)]

async def swap_raydium_to_meteora(borrow_amount, expected_amount, trade_size, borrow_decimals, raydium_slippage, meteora_slippage, pool_raydium_address, pool_meteora_address, meteora_in_token, meteora_out_token, lut, lut_addresses, client, dlmm_object, bin_arrays, all_bins, solana_client, broadcast_clients, vault, payer, operator, seed, ata, wsol_token_account, balance_needed, compute_unit_limit, compute_unit_price, init_wsol_account_instruction):
    logger.info("Starting swap...")

    start_time = time.time()    
    lut = Pubkey.from_string(lut)
    lut_addresses = [Pubkey.from_string(address) for address in lut_addresses]

    luts_time = time.time()
    logger.info(f"🕒 Execution time for luts: {(luts_time - start_time) * 1000:.3f} ms")

    # pool_meteora_address = Pubkey.from_string(pool_meteora_address)
    # dlmm = DLMM(pool_meteora_address, RPC_ENDPOINT)
    dlmm = dlmm_object
    pool_meteora_address = dlmm.pool_address
    dlmm_token_x_decimals = dlmm.token_X.decimal
    dlmm_token_y_decimals = dlmm.token_Y.decimal
    
    borrow_amount_lamports = int(borrow_amount * 10 ** borrow_decimals)

    # wsol_token_account_fixed = wsol_token_account
    # wsol_token_account = Pubkey.from_string(OPERATOR_WSOL_ATA)

    # Create multiple instructions (e.g., two SOL transfers)
    borrow_ix = transfer(TransferParams(from_pubkey=vault.pubkey(), to_pubkey=operator.pubkey(), lamports=borrow_amount_lamports))
    borrow_ix_time = time.time()
    logger.info(f"🕒 Execution time for borrow ix: {(borrow_ix_time - start_time) * 1000:.3f} ms")
    
    # swap_1_ix, minimum_amount_out, wsol_token_account, token_account, amount_out = buy_ix(pool_raydium_address, borrow_amount, dlmm_token_x_decimals, dlmm_token_y_decimals, raydium_slippage, lut_addresses, seed, wsol_token_account, balance_needed, compute_unit_limit, compute_unit_price, init_wsol_account_instruction)
    ata = Pubkey.from_string(ata)
    swap_1_ix, minimum_amount_out, wsol_token_account_fixed, token_account, amount_out, close_wsol_account_instruction, total_amount_to_repay = buy_ix_fixed(pool_raydium_address, borrow_amount, expected_amount, dlmm_token_x_decimals, dlmm_token_y_decimals, raydium_slippage, lut_addresses, seed, wsol_token_account, ata, balance_needed, compute_unit_limit, compute_unit_price, init_wsol_account_instruction, borrow_ix)
    swap_1_ix_time = time.time()
    logger.info(f"🕒 Execution time for swap 1 ix: {(swap_1_ix_time - start_time) * 1000:.3f} ms")

    pool_meteora_in_token = Pubkey.from_string(meteora_in_token)
    pool_meteora_out_token = Pubkey.from_string(meteora_out_token)

    pool_meteora_in_amount = int(minimum_amount_out)
    # pool_meteora_in_amount = int(amount_out)
    # pool_meteora_in_amount = int(expected_amount * 10 ** dlmm_token_x_decimals)

    pool_meteora_min_out_amount = int(borrow_amount_lamports)
    # pool_meteora_min_out_amount = int(trade_size * 10 ** 9)
    # pool_meteora_min_out_amount = 0
    # pool_meteora_min_out_amount = int(borrow_amount_lamports * 1.01)

    pool_meteora_lb_pair = pool_meteora_address

    userTokenIn = token_account
    userTokenOut = wsol_token_account_fixed

    # bin_arrays = DLMM.get_bin_array_for_swap(dlmm, True, 2)
    bin_arrays_time = time.time()
    logger.info(f"🕒 Execution time for bin_arrays: {(bin_arrays_time - start_time) * 1000:.3f} ms")

    swap_2_ix = DLMM.swap_ixs(dlmm, pool_meteora_in_token, pool_meteora_out_token, pool_meteora_in_amount, pool_meteora_min_out_amount, pool_meteora_lb_pair, operator.pubkey(), userTokenIn, userTokenOut, bin_arrays)
    swap_2_ix_time = time.time()
    logger.info(f"🕒 Execution time for swap 2 ix: {(swap_2_ix_time - start_time) * 1000:.3f} ms")

    repay_ix = transfer(TransferParams(from_pubkey=operator.pubkey(), to_pubkey=vault.pubkey(), lamports=total_amount_to_repay))

    # Initialize the transaction
    txn = Transaction()
    # txn.add(borrow_ix)  # Add Borrow instruction

    # Add Swap 1 instructions to the transaction
    for ix in swap_1_ix:  # Swap 1
        txn.add(ix)

    # Add Swap 2 instructions to the transaction
    for id, ix in enumerate(swap_2_ix):  # Swap 2
        # Extract relevant fields from the instruction
        program_id = Pubkey.from_string(ix['programId'])
        accounts = [
            AccountMeta(
                pubkey=Pubkey.from_string(account['pubkey']),
                is_signer=account['isSigner'],
                is_writable=account['isWritable']
            ) for account in ix['keys']
        ]
        
        # Convert data to bytes (critical fix)
        data_bytes = bytes(ix['data'])  # Ensure ix['data'] is list of integers

        # Add the instruction to the transaction
        txn.add(Instruction(
            program_id=program_id,
            accounts=accounts,
            data=data_bytes
        ))

    # Add close WSOL account instruction
    txn.add(close_wsol_account_instruction)
    # Add Repay instruction
    txn.add(repay_ix)  # Repay

    # print("Transaction Instructions:", txn.instructions)

    # blockhash = solana_client.get_latest_blockhash()
    blockhash = get_latest_blockhash_from_redis()

    blockhash_time = time.time()
    logger.info(f"🕒 Execution time for blockhash: {(blockhash_time - start_time) * 1000:.3f} ms")

    # Compile the transaction to v0 message with lookup table
    message_v0 = MessageV0.try_compile(
        payer=payer.pubkey(),
        recent_blockhash=blockhash.value.blockhash,
        instructions=txn.instructions,
        address_lookup_table_accounts=[
            AddressLookupTableAccount(
                key=lut,
                addresses=lut_addresses
            )
        ],
    )

    message_v0_time = time.time()
    logger.info(f"🕒 Execution time for message_v0: {(message_v0_time - start_time) * 1000:.3f} ms")

    # Create the VersionedTransaction from the v0 message
    # txn_v0 = VersionedTransaction(message_v0, [vault, payer, operator]) # Order matters?
    txn_v0 = VersionedTransaction(message_v0, [payer, vault, operator])

    txn_v0_time = time.time()
    logger.info(f"🕒 Execution time for txn_v0: {(txn_v0_time - start_time) * 1000:.3f} ms")
    
    # Simulate transaction before sending
    # sim_resp = await solana_client.simulate_transaction(txn_v0)
    # print("Simulation Response:", sim_resp)

    # # Simulate transaction before sending
    # simulate_time = time.time()
    # try:
    #     # Simulate the transaction and check for errors
    #     sim_resp = await solana_client.simulate_transaction(txn_v0)
    #     if sim_resp.value.err:
    #         raise Exception(f"Simulation failed: {sim_resp.value.err}")
    #     print("Simulation successful, proceeding with transaction.")
    #     print(f"🕒 Execution time for simulate: {(simulate_time - start_time) * 1000:.3f} ms")
    # except Exception as e:
    #     print(f"Simulation failed: {str(e)}")
    #     print(f"🕒 Execution time for simulate: {(simulate_time - start_time) * 1000:.3f} ms")
    #     return  # Exit early if the simulation failed

    swap_ixs_time = time.time()
    print(f"🕒 Execution time for swap ixs: {(swap_ixs_time - start_time) * 1000:.3f} ms")
    logger.info(f"🕒 Execution time for swap ixs: {(swap_ixs_time - start_time) * 1000:.3f} ms")

    # # Optionally, send the transaction
    send_resp = solana_client.send_transaction(
        # txn_v0, opts=TxOpts(skip_preflight=True)
        txn_v0, opts=TxOpts(skip_preflight=False, preflight_commitment=RPC_STATUS)
    )

    # if send_resp.value.err:
    #     logger.error(f"❌ Transaction failed: {send_resp}")
    # else:
    #     print("🚀 Transaction Signature:", send_resp.value)
    #     logger.info(f"🚀 Transaction Signature: {send_resp.value}")

    print(f"🚀 Transaction Signature: https://solana.fm/tx/{send_resp.value}")
    logger.info(f"🚀 Transaction Signature: https://solana.fm/tx/{send_resp.value}")
    
    # tasks = []
    # for broadcast_client in broadcast_clients:
    #     tasks.append(
    #         broadcast_client.send_transaction,
    #         txn_v0,
    #         opts=TxOpts(skip_preflight=False)
    #     )
    
    # results = await asyncio.gather(*tasks, return_exceptions=True)

    # for result in results:
    #     if isinstance(result, Exception):
    #         logger.error(f"❌ Transaction failed: {result}")
    #     else:
    #         print("🚀 Transaction Signature:", result.value)
    #         logger.info(f"🚀 Transaction Signature: {result.value}")

    swap_time = time.time()
    print(f"🕒 Execution time for swap: {(swap_time - start_time) * 1000:.3f} ms")
    logger.info(f"🕒 Execution time for swap: {(swap_time - start_time) * 1000:.3f} ms")

async def swap_meteora_to_raydium(borrow_amount, borrow_decimals, raydium_slippage, meteora_slippage, pool_raydium_address, pool_meteora_address, meteora_in_token, meteora_out_token, lut, lut_addresses, rpc_client):
    ## TODO: Implement this function
    pass
        
# Run async function
# asyncio.run(send_transaction())
