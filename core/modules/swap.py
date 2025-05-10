import json
import base58
import uvloop
import asyncio
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
import time
import pickle

import logging  # Import logging module
logger = logging.getLogger(__name__)

from config import WSOL_ADDRESS, TOKEN_PROGRAM, OPERATOR_WSOL_ATA, USE_JITO, redis_client, RPC_ENDPOINT_LIST, RPC_STATUS, jitoSdk, VAULT_WSOL_ATA
# from modules.raydium_py.raydium.amm_v4 import buy_ix
from modules.raydium_py.raydium.amm_v4 import buy_ix_fixed
from modules.dlmm.dlmm import DLMM

from solana.transaction import Transaction
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts

from solders.pubkey import Pubkey
from solders.instruction import Instruction, AccountMeta
from solders.transaction import VersionedTransaction
from solders.message import MessageV0
from solders.address_lookup_table_account import AddressLookupTableAccount
from solders.signature import Signature
from solders.transaction_status import TransactionConfirmationStatus

from solders.system_program import (
    transfer as native_transfer,
    TransferParams as NativeTransferParams
)

from spl.token.instructions import (
    transfer as spl_transfer,
    TransferParams as SplTransferParams
)

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

async def check_transaction_status(client: AsyncClient, signature_str: str):
    print("Checking transaction status...")
    max_attempts = 60  # 60 seconds
    attempt = 0
    
    signature = Signature.from_string(signature_str)
    
    while attempt < max_attempts:
        try:
            response = await client.get_signature_statuses([signature])
            
            if response.value[0] is not None:
                status = response.value[0]
                slot = status.slot
                confirmations = status.confirmations
                err = status.err
                confirmation_status = status.confirmation_status

                print(f"Slot: {slot}")
                print(f"Confirmations: {confirmations}")
                print(f"Confirmation status: {confirmation_status}")
                
                if err:
                    print(f"Transaction failed with error: {err}")
                    return False
                elif confirmation_status == TransactionConfirmationStatus.Finalized:
                    print("Transaction is finalized.")
                    return True
                elif confirmation_status == TransactionConfirmationStatus.Confirmed:
                    print("Transaction is confirmed but not yet finalized.")
                elif confirmation_status == TransactionConfirmationStatus.Processed:
                    print("Transaction is processed but not yet confirmed or finalized.")
            else:
                print("Transaction status not available yet.")
            
            await asyncio.sleep(1)
            attempt += 1
        except Exception as e:
            print(f"Error checking transaction status: {e}")
            await asyncio.sleep(1)
            attempt += 1
    
    print(f"Transaction not finalized after {max_attempts} attempts.")
    return False

async def swap_raydium_to_meteora(profit, borrow_amount, expected_amount, borrow_decimals, raydium_slippage, meteora_slippage, pool_raydium_address, pool_meteora_address, meteora_in_token, meteora_out_token, lut, lut_addresses, dlmm_object, bin_arrays, solana_client, broadcast_clients, vault, payer, operator, seed, ata, vault_wsol_token_account, operator_wsol_token_account, balance_needed, compute_unit_limit_ix, compute_unit_price_ix, create_wsol_account_ix, init_wsol_account_ix, close_wsol_account_ix, jito_tip_address):
    logger.info("Starting swap...")

    start_time = time.time()    
    lut = Pubkey.from_string(lut)
    lut_addresses = [Pubkey.from_string(address) for address in lut_addresses]

    luts_time = time.time()
    logger.info(f"🕒 Execution time for luts: {(luts_time - start_time) * 1000:.3f} ms")

    dlmm = dlmm_object
    pool_meteora_address = dlmm.pool_address
    dlmm_token_x_decimals = dlmm.token_X.decimal
    dlmm_token_y_decimals = dlmm.token_Y.decimal
    
    borrow_amount_lamports = int(borrow_amount * 10 ** borrow_decimals)

    token_program = Pubkey.from_string(TOKEN_PROGRAM)

    # Create multiple instructions (e.g., two SOL transfers)
    borrow_ix = spl_transfer(SplTransferParams(
        program_id=token_program, 
        source=vault_wsol_token_account,
        dest=operator_wsol_token_account,
        owner=vault.pubkey(),
        amount=borrow_amount_lamports, 
        # signers=[]
        )
    )

    borrow_ix_time = time.time()
    logger.info(f"🕒 Execution time for borrow ix: {(borrow_ix_time - start_time) * 1000:.3f} ms")
    
    ata = Pubkey.from_string(ata)
    minimum_amount_out, wsol_token_account_fixed, token_account, amount_out, swap_ix, total_amount_to_repay = buy_ix_fixed(pool_raydium_address, borrow_amount, expected_amount, dlmm_token_x_decimals, dlmm_token_y_decimals, raydium_slippage, lut_addresses, seed, operator_wsol_token_account, ata, balance_needed, compute_unit_limit_ix, compute_unit_price_ix, init_wsol_account_ix, borrow_ix)
    swap_1_ix_time = time.time()
    logger.info(f"🕒 Execution time for swap 1 ix: {(swap_1_ix_time - start_time) * 1000:.3f} ms")

    pool_meteora_in_token = Pubkey.from_string(meteora_in_token)
    pool_meteora_out_token = Pubkey.from_string(meteora_out_token)

    pool_meteora_in_amount = int(minimum_amount_out)
    pool_meteora_min_out_amount = int(borrow_amount_lamports)

    pool_meteora_lb_pair = pool_meteora_address

    userTokenIn = token_account
    userTokenOut = wsol_token_account_fixed

    bin_arrays_time = time.time()
    logger.info(f"🕒 Execution time for bin_arrays: {(bin_arrays_time - start_time) * 1000:.3f} ms")

    swap_2_ix = DLMM.swap_ixs(dlmm, pool_meteora_in_token, pool_meteora_out_token, pool_meteora_in_amount, pool_meteora_min_out_amount, pool_meteora_lb_pair, operator.pubkey(), userTokenIn, userTokenOut, bin_arrays)
    swap_2_ix_time = time.time()
    logger.info(f"🕒 Execution time for swap 2 ix: {(swap_2_ix_time - start_time) * 1000:.3f} ms")

    repay_ix = spl_transfer(SplTransferParams(
        program_id=token_program, 
        source=operator_wsol_token_account,
        dest=vault_wsol_token_account,
        owner=operator.pubkey(),
        amount=borrow_amount_lamports, 
        # signers=[]
        )
    )

    # Jito tip transfer
    profit = int(profit * 10 ** borrow_decimals)
    jito_tip_amount = int(profit * 0.5)
    jito_tip_amount = int(1_000_000_0)

    # jito_tip_address = jitoSdk.get_random_tip_account()
    logger.info(f"Jito tip account: {str(jito_tip_address)}")
    
    jito_tip_ix = native_transfer(NativeTransferParams(from_pubkey=operator.pubkey(), to_pubkey=jito_tip_address, lamports=jito_tip_amount))
    jito_tip_ix_time = time.time()
    logger.info(f"🕒 Execution time for Jito tip ix: {(jito_tip_ix_time - start_time) * 1000:.3f} ms")

    # Initialize the transaction
    txn = Transaction()

    txn.add(compute_unit_limit_ix)  # Add Compute unit limit instruction
    txn.add(compute_unit_price_ix)  # Add Compute unit price instruction
    txn.add(create_wsol_account_ix)  # Add Create WSOL account instruction
    # txn.add(init_wsol_account_ix)  # Add Init WSOL account instruction
    txn.add(borrow_ix)  # Add Borrow instruction
    txn.add(swap_ix)  # Add Raydium swap instruction

    # Add Meteora swap instruction
    for id, ix in enumerate(swap_2_ix): # Meteora swap instructions
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

    txn.add(repay_ix)  # Repay
    txn.add(close_wsol_account_ix) # Close WSOL account
    txn.add(jito_tip_ix)  # Tip

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
    txn_v0 = VersionedTransaction(message_v0, [payer, vault, operator])

    txn_v0_time = time.time()
    logger.info(f"🕒 Execution time for txn_v0: {(txn_v0_time - start_time) * 1000:.3f} ms")

    swap_ixs_time = time.time()
    print(f"🕒 Execution time for swap ixs: {(swap_ixs_time - start_time) * 1000:.3f} ms")
    logger.info(f"🕒 Execution time for swap ixs: {(swap_ixs_time - start_time) * 1000:.3f} ms")

    signature = None

    if USE_JITO:
        serialized_transaction = base58.b58encode(bytes(txn_v0)).decode('ascii')
        
        # print(f"Serialized transaction: {serialized_transaction}")
        
        response = jitoSdk.send_txn(params=serialized_transaction, bundleOnly=False)

        if response['success']:
            # print(f"Full Jito SDK response: {response}")
            signature_str = response['data']['result']
            # print(f"Transaction signature: {signature_str}")

            # finalized = await check_transaction_status(solana_client, signature_str)
            
            # if finalized:
            #     print(f"🚀 Transaction Signature: https://solana.fm/tx/{send_resp.value}")
            #     logger.info(f"🚀 Transaction Signature: https://solana.fm/tx/{send_resp.value}")
            # else:
            #     print("Transaction was not finalized within the expected time.")
            #     logger.error("Transaction was not finalized within the expected time.")

            signature = signature_str
            print(f"🚀 Transaction Signature: https://solana.fm/tx/{signature}")
            logger.info(f"🚀 Transaction Signature: https://solana.fm/tx/{signature}")
        else:
            print(f"Error sending transaction: {response['error']}")
            logger.error(f"Error sending transaction: {response['error']}")
            return 'Error sending transaction'

    else:
        # # Optionally, send the transaction
        send_resp = solana_client.send_transaction(
            txn_v0, opts=TxOpts(skip_preflight=False, preflight_commitment=RPC_STATUS)
        )

        # if send_resp.value.err:
        #     logger.error(f"❌ Transaction failed: {send_resp}")
        # else:
        #     print("🚀 Transaction Signature:", send_resp.value)
        #     logger.info(f"🚀 Transaction Signature: {send_resp.value}")

        signature = send_resp.value
        print(f"🚀 Transaction Signature: https://solana.fm/tx/{signature}")
        logger.info(f"🚀 Transaction Signature: https://solana.fm/tx/{signature}")
    
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
    return signature

async def swap_meteora_to_raydium(borrow_amount, borrow_decimals, raydium_slippage, meteora_slippage, pool_raydium_address, pool_meteora_address, meteora_in_token, meteora_out_token, lut, lut_addresses, rpc_client):
    ## TODO: Implement this function
    pass
        
# Run async function
# asyncio.run(send_transaction())
