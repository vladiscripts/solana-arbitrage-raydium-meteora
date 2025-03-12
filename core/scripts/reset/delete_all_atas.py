import asyncio
import requests
import sys
sys.path.append('./')

from config import RPC_ENDPOINT_LIST, PAYER_PRIVATE_KEY, OPERATOR_PRIVATE_KEY, TOKEN_PROGRAM, OPERATOR_WSOL_ATA
from solders.pubkey import Pubkey
from solana.transaction import Transaction
from solders.instruction import Instruction
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts
from solders.keypair import Keypair
from solders.instruction import AccountMeta
from solders.message import MessageV0
from solders.transaction import VersionedTransaction
from solders.hash import Hash
from spl.token.instructions import close_account, CloseAccountParams

# Define the RPC endpoint and the owner's public key
if not RPC_ENDPOINT_LIST:
    raise ValueError("RPC_ENDPOINT_LIST is empty! Provide at least one valid RPC endpoint.")

RPC_ENDPOINT = RPC_ENDPOINT_LIST[0]  # Use the first available RPC endpoint
owner = Keypair.from_base58_string(OPERATOR_PRIVATE_KEY)
payer = Keypair.from_base58_string(PAYER_PRIVATE_KEY)

def fetch_associated_token_accounts():
    """
    Fetches all associated token accounts owned by the given wallet address.
    """
    params = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTokenAccountsByOwner",
        "params": [
            str(owner.pubkey()),  # Wallet address
            {"programId": TOKEN_PROGRAM},  # SPL Token Program ID
            {"encoding": "jsonParsed"}
        ]
    }
    
    try:
        response = requests.post(RPC_ENDPOINT, json=params)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Request failed: {e}")
        return
    
    result = response.json()
    token_accounts = []
    
    if "result" in result and "value" in result["result"]:
        accounts = result["result"]["value"]
        print(f"Found {len(accounts)} associated token accounts.")
        
        for account in accounts:
            pub_key = account["pubkey"]
            print(f"\nToken Account: {pub_key}")
            token_accounts.append(pub_key)
        
        if token_accounts:
            print("\nAssociated Token Accounts:")
            for token_account in token_accounts:
                print(f"{token_account}")
    else:
        print("No associated token accounts found.")
    
    return token_accounts

async def close_atas(atas):
    """
    Closes all Address Lookup Tables (ALTs) owned by the authority.
    """
    async with AsyncClient(RPC_ENDPOINT) as client:
        for ata in atas:
            if ata == OPERATOR_WSOL_ATA:
                print(f"Skipping WSOL ATA: {ata}")
                continue
            # close_instruction = Instruction(
            #     program_id=Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"),
            #     accounts=[
            #         AccountMeta(pubkey=owner.pubkey(), is_signer=True, is_writable=False),
            #         AccountMeta(pubkey=Pubkey.from_string(ata), is_signer=False, is_writable=True)
            #         ],
            #     data=b""  # Properly encoded data needed for closing
            # )
            
            # txn = Transaction()
            # txn.add(close_instruction)
            
            # blockhash = await client.get_latest_blockhash()

            # # Compile the transaction to v0 message with lookup table
            # message_v0 = MessageV0.try_compile(
            #     payer=payer.pubkey(),
            #     recent_blockhash=blockhash.value.blockhash,
            #     instructions=txn.instructions,
            #     address_lookup_table_accounts=[
            #     ],
            # )

            # # Create the VersionedTransaction from the v0 message
            # txn_v0 = VersionedTransaction(message_v0, [payer, owner])

            # try:
            #     close_resp = await client.send_transaction(
            #         txn_v0, opts=TxOpts(skip_preflight=False)
            #     )
            #     print("🚀 Address Lookup Table Closed")
            #     print(f"Signature: https://solana.fm/tx/{close_resp.value}")

            #     await asyncio.sleep(0.2)  # Add a delay to avoid rate limiting

            # except Exception as e:
            #     print(f"Failed to close ALT {ata}: {e}")

            close_instruction = close_account(
                CloseAccountParams(
                    account=Pubkey.from_string(ata),
                    dest=payer.pubkey(),
                    owner=owner.pubkey(),
                    program_id=Pubkey.from_string(TOKEN_PROGRAM)
                )
            )
            
            txn = Transaction()
            txn.add(close_instruction)
            
            blockhash = await client.get_latest_blockhash()

            # Compile the transaction to v0 message with lookup table
            message_v0 = MessageV0.try_compile(
                payer=payer.pubkey(),
                recent_blockhash=blockhash.value.blockhash,
                instructions=txn.instructions,
                address_lookup_table_accounts=[
                ],
            )

            # Create the VersionedTransaction from the v0 message
            txn_v0 = VersionedTransaction(message_v0, [payer, owner])

            try:
                close_resp = await client.send_transaction(
                    txn_v0, opts=TxOpts(skip_preflight=False)
                )
                print("🚀 ATA Closed")
                print(f"Signature: https://solana.fm/tx/{close_resp.value}")
            except Exception as e:
                print(f"Failed to close ATA {ata}: {e}")

            await asyncio.sleep(0.5)  # Add a delay to avoid rate limiting

async def close_and_delete_all_atas():
    associated_tokens = fetch_associated_token_accounts()
    if associated_tokens:
        await close_atas(associated_tokens)
        
if __name__ == "__main__":
    asyncio.run(close_and_delete_all_atas())