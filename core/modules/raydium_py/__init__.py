from solana.rpc.api import Client
from solders.keypair import Keypair

import sys
sys.path.append('/home/swell/git/meteora/arbitrage')
sys.path.append('/home/ubuntu/solana/arbitrage')
from core.config import PAYER_PRIVATE_KEY, VAULT_PRIVATE_KEY, OPERATOR_PRIVATE_KEY, RPC_ENDPOINT_LIST, RPC_ENDPOINT_LIST_ID, UNIT_BUDGET, UNIT_PRICE

payer_keypair = Keypair.from_base58_string(OPERATOR_PRIVATE_KEY)
arb_vault_keypair = Keypair.from_base58_string(VAULT_PRIVATE_KEY)
arb_payer_keypair = Keypair.from_base58_string(PAYER_PRIVATE_KEY)

client = Client(RPC_ENDPOINT_LIST[RPC_ENDPOINT_LIST_ID])

UNIT_BUDGET =  UNIT_BUDGET
UNIT_PRICE =  UNIT_PRICE