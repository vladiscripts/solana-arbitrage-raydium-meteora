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
    luts = []
    if "result" in result and isinstance(result["result"], list):
        print(f"Found {len(result['result'])} Address Lookup Tables.")
        
        # Iterate through the results
        for account in result["result"]:
            pub_key = account["pubkey"]
            print(f"\nAddress Lookup Table at {pub_key}:")
            luts.append(pub_key)
        
        if luts:
            print("\nAddress Lookup Tables:")
            for lut in luts:
                print(f"{lut}")
    else:
        print("No Address Lookup Tables found.")

    return luts

if __name__ == "__main__":
    fetch_address_lookup_tables()
