import time
import numpy as np

import logging  # Import logging module
logger = logging.getLogger(__name__)

from config import MIN_PROFIT, RPC_ENDPOINT_LIST, RESERVES_MAX_SECONDS, VAULT_BALANCE, MIN_TRADE_SIZE, MAX_PRICE_DIFF_PERCENTAGE, RESERVES_METEORA, METEORA_BINS_LEFT, METEORA_BINS_RIGHT, METEORA_BINS_TO_TRADE
from modules.database import update_two_arbitrage_route_status
from modules.reserves import fetch_reserves_raydium, fetch_reserves_meteora
from modules.swap import swap_raydium_to_meteora

from solana.rpc.async_api import AsyncClient

async def raydium_quote_x_for_y(x_amount, reserve_x, reserve_y, swap_fee=0.25):
    # Calculate effective x used after swap fee
    effective_x_used = np.multiply(x_amount, (1 - np.divide(swap_fee, 100)))
    
    # Apply constant product formula for Raydium swap
    result = np.subtract(reserve_y, np.divide(np.multiply(reserve_x, reserve_y), np.add(reserve_x, effective_x_used)))
    
    # Return rounded result
    return np.round(result, 9)

async def raydium_quote_y_for_x(y_amount, reserve_x, reserve_y, swap_fee=0.25):
    # Calculate effective y used after swap fee
    effective_y_used = np.multiply(y_amount, (1 - np.divide(swap_fee, 100)))
    
    # Apply constant product formula for Raydium swap
    result = np.subtract(reserve_x, np.divide(np.multiply(reserve_x, reserve_y), np.add(reserve_y, effective_y_used)))
    
    # Return rounded result
    return np.round(result, 9)

async def raydium_quote_smart(
    y_amount, reserve_x, reserve_y, 
    swap_fee=0.25, base_slippage=0.01, 
    high_slippage_threshold=0.01, max_slippage=7.0, 
    max_iterations=10, min_trade_fraction=0.1
):
    """
    Estimates required X to get Y in a Raydium swap, adjusting trade size to minimize high price impact.

    Parameters:
    - y_amount (float): Desired output amount.
    - reserve_x (float): Token X reserves.
    - reserve_y (float): Token Y reserves.
    - swap_fee (float, optional): Fee percentage (default: 0.25%).
    - base_slippage (float, optional): Default slippage (default: 0.5%).
    - high_slippage_threshold (float, optional): % of pool used before reducing trade size (default: 5%).
    - max_slippage (float, optional): Max allowed slippage (default: 7%).
    - max_iterations (int, optional): Max times to adjust trade size (default: 10).
    - min_trade_fraction (float, optional): Smallest fraction of the original trade allowed (default: 10%).

    Returns:
    - dict: Best trade size & estimated required X, adjusted for slippage.
    """
    if y_amount <= 0:
        raise ValueError("Requested amount must be greater than zero.")

    original_y = y_amount  # Store original requested amount
    low, high = min_trade_fraction * y_amount, y_amount  # Binary search range

    for _ in range(max_iterations):
        trade_impact = y_amount / reserve_y  # % of pool being swapped

        # If impact is too high, reduce trade size
        if trade_impact >= high_slippage_threshold:
            y_amount = (low + high) / 2  # Reduce trade size iteratively
            high = y_amount  # Adjust upper bound
        else:
            low = y_amount  # Trade size is acceptable, update lower bound

        # Calculate required X for new Y amount
        numerator = reserve_x * y_amount
        denominator = (reserve_y - y_amount) * (1 - swap_fee / 100)

        if denominator <= 0:
            raise ValueError("Invalid swap, denominator is zero or negative.")

        x_needed = numerator / denominator

        # Adjust slippage dynamically
        dynamic_slippage = min(base_slippage + (trade_impact * 100), max_slippage)
        slippage_adjustment = x_needed * (dynamic_slippage / 100)
        min_x_needed = x_needed - slippage_adjustment
        max_x_needed = x_needed + slippage_adjustment

        # Stop iterating if impact is acceptable
        if trade_impact < high_slippage_threshold:
            break  

    return {
        "best_y_amount": np.round(y_amount, 6),  # Adjusted output amount
        "exact_x_needed": np.round(x_needed, 9),
        "min_x_needed": np.round(min_x_needed, 9),
        "max_x_needed": np.round(max_x_needed, 9),
        "dynamic_slippage": np.round(dynamic_slippage, 2),
        "original_y_requested": original_y,
        "iterations": _
    }

async def process_route(route, cache, lut, reserve_amounts):
    start_time = time.time()    

    ata = lut[21]

    if route['reserve_b_mint_pool_b'] != 'So11111111111111111111111111111111111111112':
        logger.warning(f"🚨 route['reserve_b_mint_pool_b'] != 'So11111111111111111111111111111111111111112'")
        await update_two_arbitrage_route_status(route['id'], 'skip')
        return None

    reserve_addresses_pool_a = [route['reserve_a_address_pool_a'], route['reserve_b_address_pool_a']]
    reserve_addresses_pool_b = [route['reserve_a_address_pool_b'], route['reserve_b_address_pool_b']]

    dlmm_pool_address = route['pool_b_address'] if route['pool_a_dex'] == 'raydium' else route['pool_a_address']

    # dlmm = DLMM_CLIENT.create(Pubkey.from_string(dlmm_pool_address), RPC_ENDPOINT)
    dlmm = cache['meteora_dlmm_client_objects'].get(dlmm_pool_address)
    dlmm_object = cache['meteora_dlmm_objects'].get(dlmm_pool_address)
    bin_arrays = cache['meteora_dlmm_bin_arrays_objects'].get(dlmm_pool_address)
    dlmm_time = time.time()
    # print(f"Execution time after dlmm: {(dlmm_time - start_time) * 1000:.3f} ms")

    pool_a = fetch_reserves_raydium(cache['solana_client'], reserve_addresses_pool_a, [int(route['reserve_a_pool_a_decimals']), int(route['reserve_b_pool_a_decimals'])], reserve_amounts) if route['pool_a_dex'] == 'raydium' else await fetch_reserves_meteora(dlmm, METEORA_BINS_LEFT, METEORA_BINS_RIGHT, RESERVES_METEORA)
    pool_a_time = time.time()
    pool_b = fetch_reserves_raydium(cache['solana_client'], reserve_addresses_pool_b, [int(route['reserve_a_pool_b_decimals']), int(route['reserve_b_pool_b_decimals'])], reserve_amounts) if route['pool_b_dex'] == 'raydium' else await fetch_reserves_meteora(dlmm, METEORA_BINS_LEFT, METEORA_BINS_RIGHT, RESERVES_METEORA)
    pool_b_time = time.time()
    
    # print(f"Execution time after pool A: {(pool_a_time - start_time) * 1000:.3f} ms, (+{(pool_a_time - dlmm_time) * 1000:.3f} ms since last)")
    # print(f"Execution time after pool B: {(pool_b_time - start_time) * 1000:.3f} ms, (+{(pool_b_time - pool_a_time) * 1000:.3f} ms since last)")
    
    if (pool_b_time - start_time) * 1000 > RESERVES_MAX_SECONDS:
        print(f"🚨 Execution time is too high: {(pool_b_time - start_time) * 1000}ms")
        logger.warning(f"🚨 Execution time is too high: {(pool_b_time - start_time) * 1000}ms")
        return None

    pools_time = time.time()
    # print(f"Execution time for pools block: {(pools_time - start_time) * 1000:.3f} ms")

    # Raydium Price Calculation
    raydium_price, raydium_fee, raydium_adjusted_price = None, None, None

    # Map route keys to corresponding pools and fees
    dex_mapping = {
        'pool_a_dex': ('pool_a', pool_a),
        'pool_b_dex': ('pool_b', pool_b)
    }

    # Check for Raydium pools
    for key, (pool_name, pool_data) in dex_mapping.items():
        if route[key] == 'raydium':
            # if pool_data['reserve_a'] == 0 or pool_data['reserve_b'] == 0:
            #     print(f"🚨 Raydium reserve has 0 balance, skipping route.")
            #     logger.warning(f"🚨 Raydium reserve has 0 balance, skipping route.")

            #     await update_two_arbitrage_route_status(route['id'], 'skip')
            #     return None
            
            try:
                raydium_price = pool_data['reserve_a'] / pool_data['reserve_b']
                raydium_fee = float(route[f"{pool_name}_fee"])
            except ZeroDivisionError:
                raydium_price = 0
                raydium_fee = float(route[f"{pool_name}_fee"])
            
            raydium_adjusted_price = raydium_price * (1 - raydium_fee)
            break  # Exit loop once Raydium pool is found

    # Check if Meteora is used in either pool
    meteora_pool = None
    if route['pool_a_dex'] == 'meteora':
        meteora_pool = pool_a
        meteora_fee = float(route['pool_a_fee'])
    elif route['pool_b_dex'] == 'meteora':
        meteora_pool = pool_b
        meteora_fee = float(route['pool_b_fee'])

    # Extract bins and active bin info if Meteora pool is found
    if meteora_pool:
        meteora_bins, _, _, all_bins, active_bin_id = meteora_pool
        
        # Convert to dictionary for O(1) lookups
        bins_dict = {bin['bin_id']: bin for bin in meteora_bins}
        active_bin = bins_dict.get(active_bin_id)
        
        # If no active bin, exit early
        if not active_bin:
            # logger.warning("❌ No active bin found for Meteora pool.")
            return None
        
        # Calculate price difference percentage directly
        meteora_active_price = active_bin['price_per_token']
        price_diff_percentage = (raydium_price - meteora_active_price) / meteora_active_price * 100
        price_diff_percentage_threshold = MAX_PRICE_DIFF_PERCENTAGE

        print(f"Price difference: {price_diff_percentage:.2f}% | Raydium Price: {raydium_price:.9f} | Meteora Active Price: {meteora_active_price:.9f}")
        
        # Store abs result to avoid recalculating
        if price_diff_percentage > price_diff_percentage_threshold or price_diff_percentage < -price_diff_percentage_threshold:
            # await update_two_arbitrage_route_status(route['id'], 'skip')

            print(f"🚨 Price difference is too high: {price_diff_percentage:.2f}% | Raydium Price: {raydium_price:.9f} | Meteora Active Price: {meteora_active_price:.9f}")
            # logger.warning(f"🚨 Price difference is too high: {price_diff_percentage:.2f}% | Raydium Price: {raydium_price:.9f} | Meteora Active Price: {meteora_active_price:.9f}")

            # # Publish a signal to Redis
            # message = {
            #     "reload": 1
            # }
            # redis_client.publish("meteora:new_pool", json.dumps(message))
            return None

        meteora_fee_threshold = meteora_fee
    else:
        meteora_active_price = None

    # Check price difference and determine direction early
    abs_diff = abs(price_diff_percentage)
    if meteora_fee_threshold < abs_diff < price_diff_percentage_threshold:
        direction = 'b_to_a' if price_diff_percentage > 0 else 'a_to_b'

        # Skip if direction is reverse
        if direction == 'b_to_a':
            return None

        # Calculate price range once and reuse
        low_price, high_price = (raydium_price, meteora_active_price) if direction == 'a_to_b' else (meteora_active_price, raydium_price)
        
        # Convert bin data to NumPy arrays for faster calculations
        bin_prices = np.array([bin['price_per_token'] for bin in meteora_bins])
        bin_amount_x = np.array([bin['amountX'] for bin in meteora_bins])
        bin_amount_y = np.array([bin['amountY'] for bin in meteora_bins])

        # Use NumPy filtering for price range and liquidity calculations
        within_range = (bin_prices >= low_price) & (bin_prices <= high_price)
        available_liquidity_x = np.sum(bin_amount_x[within_range])
        available_liquidity_y = np.sum(bin_amount_y[within_range])

        # Early return if liquidity is insufficient
        if available_liquidity_y < MIN_TRADE_SIZE:
            # logger.warning("❌ No min liquidity in Meteora bins.")
            return None

        print("-" * 50)
        print(f"🧮 Available Liquidity Y: {available_liquidity_y:.9f}")
        print(f"Price difference: {price_diff_percentage:.2f}% | Raydium Price: {raydium_price:.9f} | Meteora Active Price: {meteora_active_price:.9f}")

        # Reverse bins once using NumPy flip, outside loop
        meteora_bins = np.flip(meteora_bins)
        
        bins_y_to_trade = []
        counter_y = 0
        for bin in meteora_bins:
            if counter_y >= METEORA_BINS_TO_TRADE:
                break
            if bin['amountY'] > 0:
                bins_y_to_trade.append(bin)
                counter_y += 1
        
        # Sort bins by best price first (descending order)
        sorted_bins = sorted(
            bins_y_to_trade,
            key=lambda x: x['price_per_token'], 
            reverse=True
        )
        
        total_price = 0.0
        total_x_bins = 0.0
        total_y_available = 0.0
        meteora_fee_decimal = meteora_fee / 100  # Convert percentage to decimal

        for bin in sorted_bins:
            bin_price = bin['price_per_token']
            # bin_price = bin['price_per_token'] * (1 + meteora_fee_decimal) # Apply fee to bin price
            bin_y = bin['amountY']
            # bin_y = bin['amountY'] * (1 - meteora_fee_decimal) # Apply fee to bin Y amount
            
            # print(bin)

            total_price += bin_price
            # total_x_bins += bin_y / bin_price
            total_x_bins += (bin_y / bin_price) / (1 - meteora_fee_decimal)
            total_y_available += bin_y

        if total_y_available < MIN_TRADE_SIZE:
            logger.warning(f"❌ Total Y Available is less than min trade size: {total_y_available:.9f}")
            return None

        # ✅ Fee adjustment
        # total_y_available = total_y_available * (1 - meteora_fee_decimal) # Fee subtracted to total_y_available

        vault_balance = VAULT_BALANCE  # Temporary fix
        trade_size = min(total_y_available, vault_balance)

        # Calculate final metrics
        total_x_needed = trade_size / total_price
        total_x_needed = total_x_needed / (1 - meteora_fee_decimal)  # Fee added to total_x_needed

        print(f"Total Y Available: {total_y_available}")
        logger.info(f"Total Y Available: {total_y_available}")
        print(f"X Needed to fill Bin: {total_x_bins}")
        logger.info(f"X Needed to fill Bin: {total_x_bins}")
        print(f"Tokens needed: {total_x_needed:.9f}")
        logger.info(f"Tokens needed: {total_x_needed:.9f}")
        print(f"Tokens needed after fee: {total_x_needed:.9f}")
        logger.info(f"Tokens needed after fee: {total_x_needed:.9f}")

        # ✅ Fee adjustment
        # total_x_needed = total_x_needed * (1 - meteora_fee_decimal) # Fee subtracted to total_x_needed
        # total_x_needed = total_x_needed / (1 - meteora_fee_decimal) # Fee added from total_x_needed

        # Get cost using Raydium quote function
        # cost = await raydium_quote_y_for_x(total_x_needed, pool_a['reserve_a'], pool_a['reserve_b'])
        quote = await raydium_quote_smart(
                            y_amount=total_x_needed, 
                            reserve_x=pool_a['reserve_a'], 
                            reserve_y=pool_a['reserve_b']
                        )

        cost = quote['exact_x_needed']
        exact_x_needed = quote['best_y_amount']
        # min_x_needed = quote['min_x_needed']
        # max_x_needed = quote['max_x_needed']
        # dynamic_slippage = quote['dynamic_slippage']
        # original_y_requested = quote['original_y_requested']

        exact_trade_size = trade_size * exact_x_needed / total_x_needed
        total_x_needed = exact_x_needed

        # ✅ Fee adjustment
        # cost = cost / (1 - meteora_fee_decimal)

        # Skip if final trade size is too small
        if cost < MIN_TRADE_SIZE:
            # logger.warning("❌ Final cost is less than min trade size.")
            return None

        # Check for arbitrage opportunity
        if cost < trade_size:               
            print(f"🔥 Arbitrage opportunity: {route['pool_a_address']} -> {route['pool_b_address']}")
            logger.info(f"🔥 Arbitrage opportunity: {route['pool_a_address']} -> {route['pool_b_address']}")

            # Performance logging
            opportunity_time = time.time()
            print(f"🕒 Execution time for opportunity block: {(opportunity_time - start_time) * 1000:.3f} ms, (+{(opportunity_time - pools_time) * 1000:.3f} ms since last)")
            logger.info(f"🕒 Execution time for opportunity block: {(opportunity_time - start_time) * 1000:.3f} ms, (+{(opportunity_time - pools_time) * 1000:.3f} ms since last)")

            # if trade_size == vault_balance:
            #     proportion = vault_balance / cost
            #     total_y_available = total_y_available * proportion
            #     total_x_needed = total_x_needed * proportion
            #     total_x_bins = total_x_bins * proportion
            # else:
            #     total_x_bins = total_x_bins
            #     total_y_available = total_y_available
            #     total_x_needed = total_x_needed
        
            # print(f"Price difference: {price_diff_percentage:.2f}% | Raydium Price: {raydium_price:.9f} | Meteora Active Price: {meteora_active_price:.9f}")

            print(f"Total Y Available: {total_y_available}")
            print(f"Total X Available: {total_x_bins}")
            print(f"Trade size: {trade_size}")
            print(f"Tokens needed: {total_x_needed:.9f}")
            print(f"Cost: {cost:.9f} SOL")
            print(f"Exact Y Available: {exact_trade_size}")

            logger.info(f"Total Y Available: {total_y_available}")
            logger.info(f"Total X Available: {total_x_bins}")
            logger.info(f"Trade size: {trade_size}")
            logger.info(f"Tokens needed: {total_x_needed:.9f}")
            logger.info(f"Cost: {cost:.9f} SOL")
            logger.info(f"Exact Y Available: {exact_trade_size}")

            profit = exact_trade_size - cost
            print(f"Profit: {profit:.9f} SOL")
            logger.info(f"Profit: {profit:.9f} SOL")
            
            # if profit < MIN_PROFIT:
            #     logger.warning("❌ Profit is less than minimum profit.")
            #     return None

            # Execute swap
            result = await swap_raydium_to_meteora(
                profit, cost, total_x_needed, 9, 0, 1, route['pool_a_address'], 
                route['pool_b_address'], route['reserve_b_mint_pool_b'], 
                route['reserve_a_mint_pool_b'], route['lut'], lut, 
                dlmm_object, bin_arrays, cache['solana_client'], cache['broadcast_clients'], 
                cache['vault'], cache['payer'], cache['operator'], cache['seed'], ata, cache['vault_wsol_token_account'], cache['operator_wsol_token_account'], 
                cache['balance_needed'], cache['compute_unit_limit'], cache['compute_unit_price'], 
                cache['create_wsol_account_instruction'], cache['init_wsol_account_instruction'], cache['close_wsol_account_instruction'],
                cache['jito_tip_address']
            )

            if result == 'Error sending transaction':
                # print(f"Jito too many requests")
                # logger.warning(f"Jito too many requests")
                time.sleep(1)
                
    # else:
    #     # Set token to non tradable
    #     await update_two_arbitrage_route_status(route['id'], 'skip')
    
    return route

# Main async function that processes arbitrage opportunities
async def find_arbitrage_opportunities(cache, account_data, reserve_amounts):
    """
    Fetch and process arbitrage opportunities concurrently for each route.
    Listen for Redis updates and process them as new account data comes in.
    """
    # Process the update as required for the arbitrage logic
    subscription_address = account_data.get('subscription_address')
    # mint = account_data.get('account_data').get('mint')
    # print(f"Mint: {mint}\nPool: {subscription_address}")

    global routes
    # Find all possible routes based on the subscription address
    routes = [route for route in cache['arbitrage_routes'] 
              if (route['reserve_a_address_pool_a'] == subscription_address and route['status'] == 'enabled')
              or (route['reserve_b_address_pool_a'] == subscription_address and route['status'] == 'enabled')
              or (route['reserve_a_address_pool_b'] == subscription_address and route['status'] == 'enabled')
              or (route['reserve_b_address_pool_b'] == subscription_address and route['status'] == 'enabled')]
    # print(f"Routes: {routes}")

    luts = []
    for route in routes:
        luts.append(cache['lut_mapping'].get(route['lut']))
    # print(f"LUTs: {luts}")

    async with AsyncClient(RPC_ENDPOINT_LIST[0]) as client:
        # For example, you might want to process this update based on the `route` and `lut`
        for route, lut in zip(routes, luts):
            try:
                # Pass the relevant data to `process_route` based on the update
                result = await process_route(route, cache, lut, reserve_amounts)  # Assuming `process_route` takes account data
                # if result:
                #     return result
                # else:
                #     return None
                # if result:
                #     print(f"Arbitrage Opportunity: {result}")
                # else:
                #     print(f"No arbitrage opportunity found for route {route['id']}")
            except Exception as e:
                logger.error(f"Error processing route {route['id']}: {str(e)}")
                if str(e) == 'float division by zero':
                    # print(f"TTL expired")
                    return None
