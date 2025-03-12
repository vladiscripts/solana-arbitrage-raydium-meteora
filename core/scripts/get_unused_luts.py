import requests
import base64
import sys
sys.path.append('./')

from config import RPC_ENDPOINT_LIST, PAYER_PUBLIC_KEY
from solders.pubkey import Pubkey

# Define the RPC endpoint and the authority's public key
if not RPC_ENDPOINT_LIST:
    raise ValueError("RPC_ENDPOINT_LIST is empty! Provide at least one valid RPC endpoint.")

RPC_ENDPOINT = RPC_ENDPOINT_LIST[0]  # Use the first available RPC endpoint
authority = Pubkey.from_string(PAYER_PUBLIC_KEY)  # Convert to a Pubkey object

# Define a function to parse Address Lookup Table data
def parse_address_lookup_table(data):
    """
    Parses the binary data of an Address Lookup Table and extracts public keys.
    """
    keys = []
    key_size = 32  # Solana public keys are 32 bytes
    for i in range(0, len(data), key_size):
        key_bytes = data[i:i + key_size]
        if len(key_bytes) == key_size:
            public_key = Pubkey(key_bytes)
            keys.append(public_key)

    print(f"Parsed {len(keys)} addresses from Address Lookup Table.")
    for key in keys:
        print(f" - {key}")

    return keys

def fetch_address_lookup_tables():
    """
    Fetches all Address Lookup Tables owned by the given authority.
    """
    # Prepare the JSON-RPC request body for getProgramAccounts
    params = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getProgramAccounts",
        "params": [
            "AddressLookupTab1e1111111111111111111111111",  # Address Lookup Table program ID
            {
                "encoding": "base64",
                "filters": [
                    {
                        "memcmp": {
                            "offset": 22,  # This should match the authority offset
                            "bytes": str(authority)  # Use the actual authority public key
                        }
                    }
                ]
            }
        ]
    }

    # Make the request to the RPC endpoint
    try:
        response = requests.post(RPC_ENDPOINT, json=params)
        response.raise_for_status()  # Raise an error for non-200 responses
    except requests.RequestException as e:
        print(f"Request failed: {e}")
        return

    # Parse response
    result = response.json()
    non_extended_luts = []
    if "result" in result and isinstance(result["result"], list):
        print(f"Found {len(result['result'])} Address Lookup Tables.")
        
        # Iterate through the results
        for account in result["result"]:
            pub_key = account["pubkey"]
            data = base64.b64decode(account["account"]["data"][0])  # Decode base64 data

            print(f"\nAddress Lookup Table at {pub_key}:")
            keys = parse_address_lookup_table(data)
            if len(keys) == 1:
                non_extended_luts.append(pub_key)
        
        if non_extended_luts:
            print("\nNon-extended Address Lookup Tables:")
            for lut in non_extended_luts:
                print(f"{lut}")
    else:
        print("No Address Lookup Tables found.")

if __name__ == "__main__":
    fetch_address_lookup_tables()
