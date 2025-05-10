from decimal import Decimal
import uvloop
import asyncio
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
import json
import time
# import networkx as nx
from graph_tool.all import Graph
from solders.pubkey import Pubkey

import logging  # Import logging module
logger = logging.getLogger(__name__)
log_handler = logging.StreamHandler()
log_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
logger.addHandler(log_handler)

from core.config import redis_client, MIN_METEORA_FEE, VAULT_PUBLIC_KEY, PAYER_PUBLIC_KEY, OPERATOR_PUBLIC_KEY, TOKEN_PROGRAM, WSOL_ADDRESS, SYSVARRENT_PROGRAM, RAYDIUM_AMM_PROGRAM, METEORA_DLMM_PROGRAM, SERUM_OPENBOOK_PROGRAM, JITO_TIP_ADDRESS
from core.modules.database import get_db_connection, get_pools_by_token, get_sol_pools_by_tokens, get_tradable_tokens, update_two_arbitrage_route_status
from core.modules.reserves import fetch_raydium_reserves_api, fetch_meteora_reserves_api
from core.modules.ata import create_associated_token_account_async
from core.modules.lut import fetch_raydium_lut_addresses_api, fetch_meteora_lut_addresses_api, create_and_deploy_alt, extend_alt

async def normalize_route(route):
    """
    Normalize the route so that pool_a and pool_b are always in the same order.
    This ensures that (pool_a → pool_b) is treated the same as (pool_b → pool_a).
    """
    pool1 = (route["pool_a_id"], route["pool_a_address"])
    pool2 = (route["pool_b_id"], route["pool_b_address"])
    
    # Ensure consistent ordering
    if pool1 > pool2:
        pool1, pool2 = pool2, pool1
        dex1, dex2 = route["pool_b_dex"], route["pool_a_dex"]
    else:
        dex1, dex2 = route["pool_a_dex"], route["pool_b_dex"]
    
    return (
        pool1[0], pool2[0],  # pool_a_id, pool_b_id
        pool1[1], pool2[1],  # pool_a_address, pool_b_address
        dex1, dex2
    )

async def detect_unique_routes(routes):
    """
    Detects unique routes by ensuring that reversed pool orders are considered the same.
    """
    unique_routes = set()
    result = []
    
    for route in routes:
        normalized = await normalize_route(route)
        if normalized not in unique_routes:
            unique_routes.add(normalized)
            result.append(route)  # Keep the original format
    
    return result


def calculate_arbitrage_routes(all_pools, token_addresses):
    # Шаг 1-3: Построение графа с нормализацией направления
    t0 = time.time()
    G = Graph(directed=True)
    token_to_vertex = {token: G.add_vertex() for token in token_addresses}
    edge_pools_property = G.new_edge_property("object")

    # Инициализация списков пулов для всех рёбер
    for e in G.edges():
        edge_pools_property[e] = []

    # Добавление рёбер с нормализацией направления
    for pool in all_pools:
        try:
            base, quote = pool['base_token_address'], pool['quote_token_address']

            # Нормализация направления: сортируем адреса токенов
            sorted_tokens = sorted([base, quote])
            token1, token2 = sorted_tokens[0], sorted_tokens[1]

            if token1 not in token_to_vertex or token2 not in token_to_vertex:
                continue

            u, v = token_to_vertex[token1], token_to_vertex[token2]

            # Добавляем ребро только в одном направлении
            edge = G.edge(u, v)
            if not edge:
                edge = G.add_edge(u, v)
                edge_pools_property[edge] = []

            # Проверка на дубликаты пулов
            existing_ids = {p['pool_id'] for p in edge_pools_property[edge]}
            if pool['id'] not in existing_ids:
                edge_pools_property[edge].append({'pool_id': pool['id'], 'pool_address': pool['address'], 'dex': pool['dex'], 'fee': pool['fee']})

        except Exception as e:
            logger.error(f"Error processing pool {pool.get('address', '?')}: {str(e)}")
    print('Шаг 3: Добавление рёбер в граф', time.time() - t0, 'сек')

    # Шаг 4: Поиск уникальных арбитражных пар
    t1 = time.time()
    arbitrage_routes = []
    processed_pairs = set()

    edges = G.get_edges()
    for edge in edges:
        u, v = edge[0], edge[1]

        # Ищем обратные рёбра (v -> u не существует из-за нормализации)
        # Вместо этого проверяем только исходное ребро

        # Получаем все пулы для текущего ребра
        pools = edge_pools_property[edge]

        # Ищем пары пулов из разных DEX
        for i in range(len(pools)):
            for j in range(i + 1, len(pools)):
                p1, p2 = pools[i], pools[j]

                if p1['dex'] == p2['dex']:
                    continue

                # пропуск дубликатов
                pair_key = frozenset({p1['pool_id'], p2['pool_id']})
                if pair_key in processed_pairs:
                    continue
                processed_pairs.add(pair_key)

                try:
                    token_a = next(k for k, vt in token_to_vertex.items() if vt == u)
                    token_b = next(k for k, vt in token_to_vertex.items() if vt == v)
                except StopIteration:
                    continue

                arbitrage_routes.append({
                    'start_token': token_a,
                    'intermediate_token': token_b,
                    'end_token': token_a,
                    'pool1_id': p1['pool_id'],
                    'pool2_id': p2['pool_id'],
                    'pool1_address': p1['pool_address'],
                    'pool2_address': p2['pool_address'],
                    'pool1_fee': float(p1['fee']),
                    'pool2_fee': float(p2['fee']),
                    'dex1': p1['dex'],
                    'dex2': p2['dex']
                })
    print('Шаг 4: Поиск арбитражных маршрутов', time.time() - t1, 'сек')

    return arbitrage_routes


async def find_and_save_two_arbitrage_routes():
    """
    Finds all possible two-pool arbitrage routes between Raydium and Meteora,
    and saves them to the database.
    """

    # Store tradable tokens in a set for easy lookup
    tokens = await get_tradable_tokens()
    token_addresses = {t['address'] for t in tokens}
    # logger.info(f"Tradable tokens: {token_addresses}")

    raydium_pools_ = await get_sol_pools_by_tokens(token_addresses, 'raydium', liquidity_k_le=1, trade_volume_24h_k_le=1)
    meteora_pools_ = await get_sol_pools_by_tokens(token_addresses, 'meteora', liquidity_k_le=1, trade_volume_24h_k_le=1)
    all_pools = []
    unique_addresses = set()
    for pool in raydium_pools_ + meteora_pools_:
        if pool['address'] not in unique_addresses:
            unique_addresses.add(pool['address'])
            all_pools.append(pool)

    arbitrage_routes = calculate_arbitrage_routes(all_pools, token_addresses)


    try:
        async with get_db_connection() as conn:

            t2 = time.time()
            if arbitrage_routes:
                # 1. Оптимизация: Получение всех существующих рутов за один запрос
                pool_pairs = [(r['pool1_id'], r['pool2_id']) for r in arbitrage_routes]
                db_existing_routes = await conn.fetch('''
                    SELECT pool_a_id, pool_b_id, reserve_a_address_pool_a, status 
                    FROM two_arbitrage_routes
                    WHERE (pool_a_id, pool_b_id) IN (
                        SELECT (value->>0)::INT, (value->>1)::INT
                        FROM jsonb_array_elements($1::jsonb) AS value)
                      AND status != 'skip' ''', json.dumps(pool_pairs))

                db_existing_dict = {(r['pool_a_id'], r['pool_b_id']): {'reserve_a_address': r['reserve_a_address_pool_a'], 'status': r['status']}
                                 for r in db_existing_routes}

                valid_routes = []
                _runiq = set()
                raydium_pools_addresses = set()
                meteora_pools_addresses = set()
                for route in arbitrage_routes:
                    key = (route['pool1_id'], route['pool2_id'])
                    existing = db_existing_dict.get(key)
                    if existing and (existing['status'] == 'skip' or existing['reserve_a_address']):
                        continue
                    if route['dex1'] == 'raydium':
                        raydium_pools_addresses.add(route['pool1_address'])
                    if route['dex2'] == 'raydium':
                        raydium_pools_addresses.add(route['pool2_address'])
                    if route['dex1'] == 'meteora':
                        meteora_pools_addresses.add(route['pool1_address'])
                    if route['dex2'] == 'meteora':
                        meteora_pools_addresses.add(route['pool2_address'])
                    if key in _runiq:
                        continue
                    _runiq.add(key)
                    valid_routes.append(route)

                t2_ = time.time()
                # raydium_pool_reserves = await fetch_raydium_reserves_api(raydium_pools_addresses)
                # meteora_pool_reserves = [await fetch_meteora_reserves_api(a) for a in meteora_pools_addresses]
                # print('Step 5: fetch api 1', time.time() - t2_, 'сек')
                t2__ = time.time()
                raydium_pool_reserves, meteora_pool_reserves = await asyncio.gather(
                    fetch_raydium_reserves_api(raydium_pools_addresses),
                    asyncio.gather(*[fetch_meteora_reserves_api(a) for a in meteora_pools_addresses])
                )
                print('Step 5: fetch api 2', time.time() - t2__, 'сек')
                _raydium_pool_reserves = {pr[0]: pr[1:] for pr in raydium_pool_reserves}
                _meteora_pool_reserves = {pr[0]: pr[1:] for pr in meteora_pool_reserves}

                # 2. Группировка API-запросов и параллельная обработка
                valid_routes = []
                tasks = []
                for route in arbitrage_routes:
                    key = (route['pool1_id'], route['pool2_id'])
                    if key in db_existing_dict:
                        route_current = db_existing_dict[key]['reserve_a_address']
                        route_status = db_existing_dict[key]['status']
                        if route_current and route_current != '':
                            continue
                        if route_status == 'skip':
                            continue

                # 4. Батчевая вставка/обновление данных
                insert_values = []
                # update_values = []
                skip_values = []

                for route in arbitrage_routes:

                    pool_a_id = route['pool1_id']
                    pool_b_id = route['pool2_id']
                    pool_a_address = route['pool1_address']
                    pool_b_address = route['pool2_address']
                    pool_a_dex = route['dex1']
                    pool_b_dex = route['dex2']
                    pool_a_fee = route['pool1_fee']
                    pool_b_fee = route['pool2_fee']

                    # You would need to retrieve the reserves from your pool data
                    reserve_a_pool_a = route.get('reserve_a_pool_a', 0.0)  # Placeholder, get actual reserves
                    reserve_b_pool_a = route.get('reserve_b_pool_a', 0.0)  # Placeholder, get actual reserves
                    reserve_a_pool_b = route.get('reserve_a_pool_b', 0.0)  # Placeholder, get actual reserves
                    reserve_b_pool_b = route.get('reserve_b_pool_b', 0.0)  # Placeholder, get actual reserves

                    if pool_a_dex not in ['raydium', 'meteora']:
                        logger.info(f"Unknown DEX: {pool_a_dex} or {pool_b_dex}")
                        continue
                    if pool_b_dex not in ['raydium', 'meteora']:
                        logger.info(f"Unknown DEX: {pool_a_dex} or {pool_b_dex}")
                        continue
                    if any([pool_a_dex == 'raydium' and pool_a_address not in _raydium_pool_reserves,
                            pool_a_dex == 'meteora' and pool_a_address not in _meteora_pool_reserves,
                            pool_b_dex == 'raydium' and pool_b_address not in _raydium_pool_reserves,
                            pool_b_dex == 'meteora' and pool_b_address not in _meteora_pool_reserves]):
                        continue

                    meteora_fee = None
                    if pool_a_dex == 'raydium':
                        meteora_fee = pool_b_fee
                        # reserve_a_address_pool_a, reserve_b_address_pool_a, reserve_a_pool_a_decimals, reserve_b_pool_a_decimals, reserve_a_mint_pool_a, reserve_b_mint_pool_a, pool_a_fee = await fetch_raydium_reserves_api(pool_a_address)
                        reserve_a_address_pool_a, reserve_b_address_pool_a, reserve_a_pool_a_decimals, reserve_b_pool_a_decimals, reserve_a_mint_pool_a, reserve_b_mint_pool_a, reserve_pool_a_fee = _raydium_pool_reserves[pool_a_address]
                    elif pool_a_dex == 'meteora':
                        meteora_fee = pool_a_fee
                        # reserve_a_address_pool_a, reserve_b_address_pool_a, reserve_a_pool_a_decimals, reserve_b_pool_a_decimals, reserve_a_mint_pool_a, reserve_b_mint_pool_a = await fetch_meteora_reserves_api(pool_a_address)
                        reserve_a_address_pool_a, reserve_b_address_pool_a, reserve_a_pool_a_decimals, reserve_b_pool_a_decimals, reserve_a_mint_pool_a, reserve_b_mint_pool_a = _meteora_pool_reserves[pool_a_address]

                    if pool_b_dex == 'raydium':
                        meteora_fee = pool_a_fee
                        # reserve_a_address_pool_b, reserve_b_address_pool_b, reserve_a_pool_b_decimals, reserve_b_pool_b_decimals, reserve_a_mint_pool_b, reserve_b_mint_pool_b, pool_b_fee = await fetch_raydium_reserves_api(pool_b_address)
                        reserve_a_address_pool_b, reserve_b_address_pool_b, reserve_a_pool_b_decimals, reserve_b_pool_b_decimals, reserve_a_mint_pool_b, reserve_b_mint_pool_b, reserve_pool_b_fee = _raydium_pool_reserves[pool_b_address]
                    elif pool_b_dex == 'meteora':
                        meteora_fee = pool_b_fee
                        # reserve_a_address_pool_b, reserve_b_address_pool_b, reserve_a_pool_b_decimals, reserve_b_pool_b_decimals, reserve_a_mint_pool_b, reserve_b_mint_pool_b = await fetch_meteora_reserves_api(pool_b_address)
                        reserve_a_address_pool_b, reserve_b_address_pool_b, reserve_a_pool_b_decimals, reserve_b_pool_b_decimals, reserve_a_mint_pool_b, reserve_b_mint_pool_b = _meteora_pool_reserves[pool_b_address]

                    if not meteora_fee:
                        continue
                    if int(meteora_fee) < 2:
                        insert_values.append((
                            pool_a_id, pool_b_id, pool_a_address, pool_b_address,
                            pool_a_dex, pool_b_dex, reserve_a_pool_a, reserve_b_pool_a, reserve_a_pool_b, reserve_b_pool_b,
                            # float(reserve_a_pool_a_decimals), float(reserve_b_pool_a_decimals),
                            # float(reserve_a_pool_b_decimals), float(reserve_b_pool_b_decimals),
                            reserve_a_address_pool_a, reserve_b_address_pool_a, reserve_a_address_pool_b, reserve_b_address_pool_b,
                            pool_a_fee, pool_b_fee, reserve_a_mint_pool_a, reserve_b_mint_pool_a, reserve_a_mint_pool_b, reserve_b_mint_pool_b
                        ))
                    else:
                        skip_values.append((pool_a_id, pool_b_id))

                if insert_values:
                    await conn.executemany('''
                        INSERT INTO two_arbitrage_routes (
                            pool_a_id, pool_b_id, pool_a_address, pool_b_address, pool_a_dex, pool_b_dex,
                            reserve_a_pool_a, reserve_b_pool_a, reserve_a_pool_b, reserve_b_pool_b,
                            -- reserve_a_pool_a_decimals, reserve_b_pool_a_decimals, 
                            -- reserve_a_pool_b_decimals, reserve_b_pool_b_decimals,
                            reserve_a_address_pool_a, reserve_b_address_pool_a, reserve_a_address_pool_b, reserve_b_address_pool_b,
                            pool_a_fee, pool_b_fee,
                            reserve_a_mint_pool_a, reserve_b_mint_pool_a, reserve_a_mint_pool_b, reserve_b_mint_pool_b,
                            status
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, 
                        -- $21, $22, $23, $24, 
                        'enabled')
                        ON CONFLICT (pool_a_id, pool_b_id) 
                        DO UPDATE SET 
                            pool_a_address = EXCLUDED.pool_a_address,
                            pool_b_address = EXCLUDED.pool_b_address,
                            pool_a_dex = EXCLUDED.pool_a_dex,
                            pool_b_dex = EXCLUDED.pool_b_dex,
                            pool_a_fee = EXCLUDED.pool_a_fee,
                            pool_b_fee = EXCLUDED.pool_b_fee,
                            reserve_a_pool_a = EXCLUDED.reserve_a_pool_a,
                            reserve_b_pool_a = EXCLUDED.reserve_b_pool_a,
                            reserve_a_pool_b = EXCLUDED.reserve_a_pool_b,
                            reserve_b_pool_b = EXCLUDED.reserve_b_pool_b,
                            -- reserve_a_pool_a_decimals = EXCLUDED.reserve_a_pool_a_decimals,
                            -- reserve_b_pool_a_decimals = EXCLUDED.reserve_b_pool_a_decimals,
                            -- reserve_a_pool_b_decimals = EXCLUDED.reserve_a_pool_b_decimals,
                            -- reserve_b_pool_b_decimals = EXCLUDED.reserve_b_pool_b_decimals,
                            reserve_a_address_pool_a = EXCLUDED.reserve_a_address_pool_a,
                            reserve_b_address_pool_a = EXCLUDED.reserve_b_address_pool_a,
                            reserve_a_address_pool_b = EXCLUDED.reserve_a_address_pool_b,
                            reserve_b_address_pool_b = EXCLUDED.reserve_b_address_pool_b,
                            reserve_a_mint_pool_a = EXCLUDED.reserve_a_mint_pool_a,
                            reserve_b_mint_pool_a = EXCLUDED.reserve_b_mint_pool_a,
                            reserve_a_mint_pool_b = EXCLUDED.reserve_a_mint_pool_b,
                            reserve_b_mint_pool_b = EXCLUDED.reserve_b_mint_pool_b,
                            lut = EXCLUDED.lut,
                            status = EXCLUDED.status,
                            updated_at = CURRENT_TIMESTAMP
                    ''', insert_values)

                if skip_values:
                    await conn.executemany('''
                        UPDATE two_arbitrage_routes
                        SET status = 'skip'
                        WHERE pool_a_id = $1 AND pool_b_id = $2
                    ''', skip_values)

            print('Step 5: Save the arbitrage routes to the database', time.time() - t2, 'сек')




            # logger.info(f"Found {len(arbitrage_routes)} two-pool arbitrage routes.")

            t3 = time.time()
            # Step 6: Detect unique routes
            # Fetch routes and join with token info to check if both mints are tradable
            routes = await conn.fetch('''
                SELECT r.*, t1.tradable AS tradable_a, t2.tradable AS tradable_b
                FROM two_arbitrage_routes r
                JOIN tokens t1 ON r.reserve_a_mint_pool_a = t1.address
                JOIN tokens t2 ON r.reserve_b_mint_pool_a = t2.address
                WHERE r.status = 'enabled'
                AND r.pool_b_dex = 'meteora'
                AND t1.tradable IS NOT NULL AND t2.tradable IS NOT NULL
            ''')

            # logger.info(f"Found {len(routes)} two-pool arbitrage routes after filtering.")

            # Filter routes based on whether both tokens are tradable
            # tradable_routes = [dict(row) for row in routes if row['tradable_a'] and row['tradable_b']]
            tradable_routes = [dict(row) for row in routes]

            unique_routes = await detect_unique_routes(tradable_routes)
            # logger.info(f"Found {len(unique_routes)} unique two-pool arbitrage routes.")

            # unique_routes = routes

            for route in unique_routes:
                # logger.info(f"Route: {route['pool_a_address']} → {route['pool_b_address']}")
                # logger.info(f" - Dex: {route['pool_a_dex']} → {route['pool_b_dex']}")

                # Check or create LUT
                lut = route['lut']
                if lut is not None and lut != '':
                    # logger.info(f" - LUT Exists: {lut}")
                    pass
                else:
                    logger.info(" - Creating LUT...")
                    raydium_pool = None
                    meteora_pool = None
                    if route['pool_a_dex'] == 'raydium':
                        raydium_pool = route['pool_a_address']
                        meteora_pool = route['pool_b_address']
                    else:
                        raydium_pool = route['pool_b_address']
                        meteora_pool = route['pool_a_address']

                    logger.info(f" - Raydium: {raydium_pool}")
                    logger.info(f" - Meteora: {meteora_pool}")

                    # Extend LUT
                    addresses = [
                        VAULT_PUBLIC_KEY,
                        PAYER_PUBLIC_KEY,
                        OPERATOR_PUBLIC_KEY,
                        TOKEN_PROGRAM,
                        SOLANA_PROGRAM,
                        SYSVARRENT_PROGRAM,
                        RAYDIUM_AMM_PROGRAM,
                        METEORA_DLMM_PROGRAM,
                        SERUM_OPENBOOK_PROGRAM,
                        ]

                    # Get the LUT addresses from pools
                    raydium_program_id, raydium_lut = await fetch_raydium_lut_addresses_api(raydium_pool)

                    if raydium_program_id != RAYDIUM_AMM_PROGRAM:
                        logger.info(f" - Raydium pool not matching AMM program")
                        await update_two_arbitrage_route_status(route['id'], 'skip')
                        continue

                    meteora_lut = await fetch_meteora_lut_addresses_api(meteora_pool)

                    if not meteora_lut:
                        logger.info(f" - Meteora pool not found")
                        await update_two_arbitrage_route_status(route['id'], 'skip')
                        continue

                    # Create LUT
                    txid_alt, alt = await create_and_deploy_alt()

                    # Append each LUT address to the list of addresses
                    if raydium_lut and meteora_lut:
                        addresses.extend(raydium_lut)

                        mints = [meteora_lut[0], meteora_lut[1]]
                        for mint in mints:
                            if mint != 'So11111111111111111111111111111111111111112':
                                # Create ATA
                                txid_ata, ata = await create_associated_token_account_async(mint)

                                # Update ATA into database token table
                                await conn.execute('''
                                    UPDATE tokens
                                    SET ata = $1
                                    WHERE address = $2
                                ''', str(ata), mint)

                                addresses.append(str(ata))
                        addresses.extend(meteora_lut)
                    else:
                        logger.info(" - LUT addresses not found from API")
                        continue

                    # Add Jito tip address
                    addresses.append(JITO_TIP_ADDRESS)

                    # Ensure unique addresses while preserving the original order
                    unique_addresses = []
                    seen = set()

                    # logger.info(addresses)

                    for address in addresses:
                        if address not in seen:
                            # logger.info(f" - Adding address: {address}")
                            unique_addresses.append(address)
                            seen.add(address)

                    time.sleep(15)  # Add a delay to avoid rate limiting

                    pubkeys = [Pubkey.from_string(address) for address in unique_addresses]
                    txid = await extend_alt(str(alt), pubkeys)

                    # Insert LUT data into the luts table
                    await conn.execute('''
                        INSERT INTO luts (
                            pool_a_address,
                            pool_b_address,
                            address,
                            addresses,
                            authority_address,
                            payer_address
                        ) VALUES (
                            $1, $2, $3, $4, $5, $6
                        )
                    ''', raydium_pool, meteora_pool, str(alt), json.dumps(unique_addresses), PAYER_PUBLIC_KEY, PAYER_PUBLIC_KEY)

                    # Update the route with the LUT address
                    await conn.execute('''
                        UPDATE two_arbitrage_routes
                        SET lut = $1
                        WHERE id = $2
                    ''', str(alt), route['id'])

                    # Clone LUT address to non-unique routes that have the same pool addresses
                    await conn.execute('''
                        UPDATE two_arbitrage_routes
                        SET lut = $1
                        WHERE (pool_a_address = $2 AND pool_b_address = $3)
                        OR (pool_a_address = $3 AND pool_b_address = $2)
                        AND lut IS NULL
                    ''', str(alt), raydium_pool, meteora_pool)

                    logger.info(f" - LUT created and cloned to other routes with matching pool addresses.")

                    # Publish a signal to Redis
                    message = {
                        "reload": 1
                    }
                    await asyncio.to_thread(redis_client.publish, "meteora:new_pool", json.dumps(message))

                    await asyncio.sleep(0.5)  # Add a delay to avoid rate limiting
            print('Step 6: Detect unique routes', time.time() - t3, 'сек')

        except Exception as e:
            # Find if error matches: "The node {mint} is not in the digraph."
            str_e = str(e)
            if str_e.find("The node") != -1 and str_e.find("is not in the digraph") != -1:
                # Extract the node from the error message
                node = str_e.split("The node ")[1].split(" is not in the digraph.")[0]
                if node != SOLANA_PROGRAM:
                    logger.error(f"Node not in digraph error: {e}")
                    logger.error(f"Setting token not in the digraph: {node} to non-tradable")
                    # Update the token to tradable = False
                    await conn.execute('''
                        UPDATE tokens
                        SET tradable = FALSE
                        WHERE address = $1
                    ''', node)
            else:
                logger.error(f"Route edge error: {e}", exc_info=True)
            # return None
