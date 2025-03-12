from dlmm.dlmm import DLMM, DLMM_CLIENT
from solders.pubkey import Pubkey
import matplotlib.pyplot as plt
import time

RPC = "https://YOUR_SOLANA_RPC_URL/YOUR_SOLANA_RPC_API_KEY/"
pool_address = Pubkey.from_string("6oF91bPMncZ6LmeQTtU9XdXJuUqaz9nxkcJ9VDGBSP4W")  # Your desired pool address
print(pool_address)

dlmm = DLMM_CLIENT.create(pool_address, RPC)  # Returns DLMM object instance
print(dlmm)

# print(dlmm.get_active_bin())
# Retrieve token decimals from the DLMM object
token_X_decimals = dlmm.token_X.decimal
token_Y_decimals = dlmm.token_Y.decimal
print(f"Token X decimals: {token_X_decimals}, Token Y decimals: {token_Y_decimals}")

# active_bin = DLMM_CLIENT.get_active_bin(dlmm)
# print(active_bin)

# Fetch all bins
all_bins = DLMM_CLIENT.get_all_bins(dlmm, 1768, 1768)

# Function to convert a hexadecimal string to a decimal integer
def hex_to_decimal(hex_str):
    return int(hex_str, 16)

# Function to scale values based on token decimals
def scale_value(value, decimals):
    return value / (10 ** decimals)

# Function to scale the price
def scale_price(price):
    # price_per_lamports = DLMM_CLIENT.get_price_to_price_per_lamports(dlmm, float(price))
    # print(f"Price per lamports: {price_per_lamports}")
    return price / (10 ** 20)

print(f"Active Bin ID: {all_bins.active_bin}")

for bin in all_bins.bin_liquidty:
    print(f"Bin ID: {bin.bin_id}")

    # Convert hex values to decimals
    amountX = hex_to_decimal(bin.x_amount)
    amountY = hex_to_decimal(bin.y_amount)
    # liquiditySupply = hex_to_decimal(bin_data['liquiditySupply'])
    price = float(bin.price)
    pricePerToken = float(bin.price_per_token)

    # Scale values based on token decimals
    amountX_scaled = scale_value(amountX, token_X_decimals)
    amountY_scaled = scale_value(amountY, token_Y_decimals)

    # # Print the scaled values
    print(f"Bin Reserve X: {amountX_scaled}")
    print(f"Bin Reserve Y: {amountY_scaled}")
    # # print(f"liquiditySupply: {liquiditySupply}")
    print(f"Price per token: {pricePerToken}")
