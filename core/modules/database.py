from decimal import Decimal
import asyncpg
import uvloop
import asyncio
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
from contextlib import asynccontextmanager
import json

import logging  # Import logging module
logger = logging.getLogger(__name__)

from config import DB_CONFIG, MIN_METEORA_FEE

# Asynchronous context manager for handling database connections
@asynccontextmanager
async def get_db_connection():
    conn = None
    try:
        # Attempt to connect to the database
        conn = await asyncpg.connect(**DB_CONFIG)
        yield conn
    finally:
        if conn:
            await conn.close()

async def setup_database():
    """
    Set up the PostgreSQL database with the necessary tables.
    """
    async with get_db_connection() as conn:
        # Create the new meteora pools table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS meteora_pools (
                address TEXT PRIMARY KEY,
                name TEXT,
                mint_x TEXT,
                mint_y TEXT,
                apr REAL,
                apy REAL,
                current_price REAL,
                liquidity REAL,
                trade_volume_24h REAL,
                fees_24h REAL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')

        # Create trigger to remove pools if in list
        await conn.execute(f'''
        CREATE OR REPLACE FUNCTION clean_meteora_pool_function()
        RETURNS TRIGGER AS $$
        BEGIN
            IF NEW.mint_x IN ('EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v') 
                OR NEW.mint_y IN ('EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v')
                OR NEW.mint_y != 'So11111111111111111111111111111111111111112' THEN
                DELETE FROM meteora_pools WHERE address = NEW.address;
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        ''')

        # Create the tokens table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS tokens (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                address TEXT UNIQUE NOT NULL,
                status TEXT DEFAULT 'enabled', -- 'enabled', 'disabled', 'skip'
                tradable BOOLEAN DEFAULT FALSE,
                ata TEXT DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')

        # Create the pools table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS pools (
                id SERIAL PRIMARY KEY,
                base_token_address TEXT NOT NULL,
                quote_token_address TEXT NOT NULL,
                address TEXT UNIQUE NOT NULL,
                dex TEXT DEFAULT NULL, -- 'raydium', 'meteora'
                fee REAL DEFAULT 0,
                bin_step REAL DEFAULT NULL,
                price_native REAL DEFAULT NULL,
                price_usd REAL DEFAULT NULL,
                status TEXT DEFAULT 'enabled', -- 'enabled', 'disabled', 'skip'
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (base_token_address) REFERENCES tokens (address),
                FOREIGN KEY (quote_token_address) REFERENCES tokens (address)
            );
        ''')

        # Create the 2-arbitrage routes table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS two_arbitrage_routes (
                id SERIAL PRIMARY KEY,
                pool_a_id INT NOT NULL,
                pool_b_id INT NOT NULL,
                pool_a_address TEXT NOT NULL,
                pool_b_address TEXT NOT NULL,
                pool_a_dex TEXT NOT NULL,
                pool_b_dex TEXT NOT NULL,
                pool_a_fee REAL NOT NULL,
                pool_b_fee REAL NOT NULL,
                reserve_a_address_pool_a TEXT NOT NULL,
                reserve_a_address_pool_b TEXT NOT NULL,
                reserve_b_address_pool_a TEXT NOT NULL,
                reserve_b_address_pool_b TEXT NOT NULL,
                reserve_a_mint_pool_a TEXT NOT NULL,
                reserve_a_mint_pool_b TEXT NOT NULL,
                reserve_b_mint_pool_a TEXT NOT NULL,
                reserve_b_mint_pool_b TEXT NOT NULL,
                reserve_a_pool_a REAL NOT NULL,
                reserve_b_pool_a REAL NOT NULL,
                reserve_a_pool_b REAL NOT NULL,
                reserve_b_pool_b REAL NOT NULL,
                reserve_a_pool_a_decimals REAL NOT NULL,
                reserve_b_pool_a_decimals REAL NOT NULL,
                reserve_a_pool_b_decimals REAL NOT NULL,
                reserve_b_pool_b_decimals REAL NOT NULL,
                lut TEXT DEFAULT NULL,
                status TEXT DEFAULT 'enabled', -- 'enabled', 'disabled', 'skip'
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (pool_a_id) REFERENCES pools (id),
                FOREIGN KEY (pool_b_id) REFERENCES pools (id),
                UNIQUE (pool_a_id, pool_b_id)
            );
        ''')

        # Create the 3-arbitrage routes table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS three_arbitrage_routes (
                id SERIAL PRIMARY KEY,
                pool_a_id INT NOT NULL,
                pool_b_id INT NOT NULL,
                pool_c_id INT NOT NULL,
                pool_a_address TEXT NOT NULL,
                pool_b_address TEXT NOT NULL,
                pool_c_address TEXT NOT NULL,
                pool_a_dex TEXT NOT NULL,
                pool_b_dex TEXT NOT NULL,
                pool_c_dex TEXT NOT NULL,
                pool_a_fee TEXT NOT NULL,
                pool_b_fee TEXT NOT NULL,
                pool_c_fee TEXT NOT NULL,
                reserve_a_address_pool_a TEXT NOT NULL,
                reserve_a_address_pool_b TEXT NOT NULL,
                reserve_a_address_pool_c TEXT NOT NULL,
                reserve_b_address_pool_a TEXT NOT NULL,
                reserve_b_address_pool_b TEXT NOT NULL,
                reserve_b_address_pool_c TEXT NOT NULL,
                reserve_a_mint_pool_a TEXT NOT NULL,
                reserve_a_mint_pool_b TEXT NOT NULL,
                reserve_a_mint_pool_c TEXT NOT NULL,
                reserve_b_mint_pool_a TEXT NOT NULL,
                reserve_b_mint_pool_b TEXT NOT NULL,
                reserve_b_mint_pool_c TEXT NOT NULL,
                reserve_a_pool_a REAL NOT NULL,
                reserve_b_pool_a REAL NOT NULL,
                reserve_a_pool_b REAL NOT NULL,
                reserve_b_pool_b REAL NOT NULL,
                reserve_a_pool_c REAL NOT NULL,
                reserve_b_pool_c REAL NOT NULL,
                reserve_a_pool_a_decimals REAL NOT NULL,
                reserve_b_pool_a_decimals REAL NOT NULL,
                reserve_a_pool_b_decimals REAL NOT NULL,
                reserve_b_pool_b_decimals REAL NOT NULL,
                reserve_a_pool_c_decimals REAL NOT NULL,
                reserve_b_pool_c_decimals REAL NOT NULL,
                lut TEXT DEFAULT NULL,
                status TEXT DEFAULT 'enabled', -- 'enabled', 'disabled', 'skip'
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (pool_a_id) REFERENCES pools (id),
                FOREIGN KEY (pool_b_id) REFERENCES pools (id),
                FOREIGN KEY (pool_c_id) REFERENCES pools (id),
                UNIQUE (pool_a_id, pool_b_id, pool_c_id)
            );
        ''')

        # Create the 3-arbitrage routes table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS opportunities (
                id SERIAL PRIMARY KEY,
                route_type TEXT NOT NULL, -- 'two-pool' or 'three-pool'
                route_id INT NOT NULL, -- The ID from the respective routes table (two or three-pool)
                trade_size REAL NOT NULL, -- Optimal trade size
                estimated_profit_native REAL NOT NULL, -- Profit in the native token
                estimated_profit_usd REAL NOT NULL, -- Profit in USD
                pool_a_trade_direction TEXT NOT NULL, -- 'buy' or 'sell' for pool A
                pool_b_trade_direction TEXT NOT NULL, -- 'buy' or 'sell' for pool B
                pool_c_trade_direction TEXT DEFAULT NULL, -- 'buy' or 'sell' for pool C (if three-pool route)
                execution_status TEXT DEFAULT 'pending', -- 'pending', 'executed', 'failed'
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')

        # Create the LUT table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS luts (
                id SERIAL PRIMARY KEY,
                pool_a_address TEXT NOT NULL,
                pool_b_address TEXT NOT NULL,
                address TEXT NOT NULL,
                addresses JSONB NOT NULL,
                authority_address TEXT NOT NULL,
                payer_address TEXT NOT NULL,
                working BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')

        # Indexes for faster querying
        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_pools_base_quote ON pools (base_token_address, quote_token_address);
        ''')
        # await conn.execute('''
        #     CREATE INDEX IF NOT EXISTS idx_two_arbitrage_profit ON two_arbitrage_routes (estimated_profit_native DESC);
        # ''')
        # await conn.execute('''
        #     CREATE INDEX IF NOT EXISTS idx_three_arbitrage_profit ON three_arbitrage_routes (estimated_profit_native DESC);
        # ''')
        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_luts_address ON luts (address);
        ''')
        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_luts_pools ON luts (pool_a_address, pool_b_address);
        ''')

        # Example setup data (insert tokens into DB)
        await add_token('SOL', 'So11111111111111111111111111111111111111112')
        # await add_token('MOODENG', 'ED5nyyWEzpPPiWimP8vYm7sD7TD3LAt3Q3gRTWHzPJBY')
        # await add_token('SINGULAR', 'G8sGfsSix9FsnQGRnzcxmUy98uNmBcktMNeBNjapump')
        
async def save_new_meteora_pools(pairs):
    """
    Fetches all tokens from the database.
    """
    # Track newly added pools
    new_pools = []

    async with get_db_connection() as conn:
        for group in pairs.get("groups", []):
            for pair in group.get("pairs", []):
                if pair['mint_x'].endswith('pump'):
                    # Check if the pool already exists
                    exists = await conn.fetchval('SELECT 1 FROM meteora_pools WHERE address = $1 OR mint_x = $2', pair['address'], pair['mint_x'])

                    # If not exists, consider it a new pool
                    if not exists and pair['mint_y'] == 'So11111111111111111111111111111111111111112':
                        new_pools.append(pair)
                        # Insert or update the pool
                        await conn.execute('''
                            INSERT INTO meteora_pools (address, name, mint_x, mint_y, apr, apy, current_price, liquidity, trade_volume_24h, fees_24h, timestamp)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, CURRENT_TIMESTAMP)
                            ON CONFLICT (address) DO UPDATE SET
                                name = EXCLUDED.name,
                                mint_x = EXCLUDED.mint_x,
                                mint_y = EXCLUDED.mint_y,
                                apr = EXCLUDED.apr,
                                apy = EXCLUDED.apy,
                                current_price = EXCLUDED.current_price,
                                liquidity = EXCLUDED.liquidity,
                                trade_volume_24h = EXCLUDED.trade_volume_24h,
                                fees_24h = EXCLUDED.fees_24h,
                                timestamp = CURRENT_TIMESTAMP
                        ''', *(
                            pair['address'],
                            pair['name'],
                            pair['mint_x'],
                            pair['mint_y'],
                            Decimal(pair.get('apr', 0)),
                            Decimal(pair.get('apy', 0)),
                            Decimal(pair.get('current_price', 0)),
                            Decimal(pair.get('liquidity', 0)),
                            Decimal(pair.get('trade_volume_24h', 0)),
                            Decimal(pair.get('fees_24h', 0))
                        ))
                        
                    # else:
                    #     print(f"Pool already exists: {pair['address']}")


        return new_pools

async def count_meteora_pools(token):
    """
    Count the number of Meteora pools for a specific token.
    """
    async with get_db_connection() as conn:
        return await conn.fetchval('SELECT COUNT(*) FROM meteora_pools WHERE mint_x = $1 OR mint_y = $1', token)
        
async def get_tokens():
    """
    Fetches all tokens from the database.
    """
    async with get_db_connection() as conn:
        # rows = await conn.fetch('SELECT * FROM tokens')
        rows = await conn.fetch('SELECT * FROM tokens WHERE tradable = TRUE')
        return [dict(row) for row in rows]

async def add_token(name, address):
    """
    Adds a token to the database.
    """
    async with get_db_connection() as conn:
        await conn.execute('''
            INSERT INTO tokens (name, address, tradable)
            VALUES ($1, $2, $3)
            ON CONFLICT (address) DO UPDATE SET
                name = EXCLUDED.name,
                address = EXCLUDED.address,
                tradable = EXCLUDED.tradable,
                updated_at = CURRENT_TIMESTAMP
        ''', name, address, True)
        
async def add_pool(base_token_address, quote_token_address, address, dex, fee, bin_step, price_native, price_usd):
    """
    Adds a pool to the database or updates it if it already exists.
    """
    async with get_db_connection() as conn:
        await conn.execute('''
            INSERT INTO pools (base_token_address, quote_token_address, address, dex, fee, bin_step, price_native, price_usd)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (address) DO UPDATE SET
                base_token_address = EXCLUDED.base_token_address,
                quote_token_address = EXCLUDED.quote_token_address,
                dex = EXCLUDED.dex,
                fee = EXCLUDED.fee,
                bin_step = EXCLUDED.bin_step,
                price_native = EXCLUDED.price_native,
                price_usd = EXCLUDED.price_usd,
                updated_at = CURRENT_TIMESTAMP
        ''', base_token_address, quote_token_address, address, dex, fee, bin_step, price_native, price_usd)

async def get_pools_by_dex(dex):
    """
    Fetch pool data for a specific DEX where either the base token or quote token is tradable,
    and the quote token is not 'SOL'.
    """
    async with get_db_connection() as conn:
        rows = await conn.fetch('''
            SELECT p.* FROM pools p
            JOIN tokens t_base ON p.base_token_address = t_base.address
            JOIN tokens t_quote ON p.quote_token_address = t_quote.address
            WHERE p.dex = $1 AND p.status = 'enabled' AND (t_base.tradable = TRUE OR t_quote.tradable = TRUE)
            AND t_quote.name != 'SOL'
        ''', dex)
        return [dict(row) for row in rows]

# async def get_pools_by_token(token_address, dex):
#     """
#     Fetch pool data for a specific token and DEX
#     """
#     async with get_db_connection() as conn:
#         rows = await conn.fetch('''
#             SELECT * FROM pools
#             WHERE (base_token_address = $1 OR (quote_token_address = $1 AND quote_token_address != 'So11111111111111111111111111111111111111112')) AND dex = $2 AND status = 'enabled'
#         ''', token_address, dex)
#         return [dict(row) for row in rows]
    
async def get_pools_by_token(token_address, dex):
    """
    Fetch pool data for a specific token and DEX, but only if one of the token addresses is the given token
    or SOL (represented by So11111111111111111111111111111111111111112).
    """
    sol_address = 'So11111111111111111111111111111111111111112'
    
    async with get_db_connection() as conn:
        rows = await conn.fetch('''
            SELECT * FROM pools
            WHERE (
                (base_token_address = $1 AND quote_token_address = $2)
                OR 
                (base_token_address = $2 AND quote_token_address = $1)
            )
            AND dex = $3
            AND status = 'enabled'
        ''', token_address, sol_address, dex)
        
        return [dict(row) for row in rows]
    
async def get_tradable_tokens():
    """
    Fetch all tradable tokens from the database.
    """
    async with get_db_connection() as conn:
        rows = await conn.fetch('SELECT * FROM tokens WHERE tradable = TRUE')
        return [dict(row) for row in rows]

async def get_two_arbitrage_routes():
    """
    Fetch all arbitrage routes from the database where at least one tradable token is involved.
    """
    async with get_db_connection() as conn:
        query = '''
            SELECT 
                tar.id,
                tar.pool_a_id,
                tar.pool_b_id,
                tar.pool_a_address,
                tar.pool_b_address,
                tar.pool_a_dex,
                tar.pool_b_dex,
                tar.reserve_a_address_pool_a,
                tar.reserve_b_address_pool_a,
                tar.reserve_a_address_pool_b,
                tar.reserve_b_address_pool_b,
                tar.reserve_a_mint_pool_a,
                tar.reserve_a_mint_pool_b,
                tar.reserve_b_mint_pool_a,
                tar.reserve_b_mint_pool_b,
                tar.reserve_a_pool_a,
                tar.reserve_b_pool_a,
                tar.reserve_a_pool_b,
                tar.reserve_b_pool_b,
                tar.reserve_a_pool_a_decimals,
                tar.reserve_b_pool_a_decimals,
                tar.reserve_a_pool_b_decimals,
                tar.reserve_b_pool_b_decimals,
                tar.pool_a_fee,
                tar.pool_b_fee,
                tar.lut,
                tar.status
            FROM two_arbitrage_routes tar
            JOIN tokens t ON (
                tar.reserve_a_mint_pool_a = t.address OR
                tar.reserve_b_mint_pool_a = t.address OR
                tar.reserve_a_mint_pool_b = t.address OR
                tar.reserve_b_mint_pool_b = t.address
            )
            WHERE tar.status = 'enabled'
            AND t.tradable = TRUE
            AND tar.pool_b_dex = 'meteora'
            AND tar.pool_b_fee >= 2;
        '''
        #     AND t.tradable = TRUE
        #     AND tar.lut IS NOT NULL;
        # '''
        rows = await conn.fetch(query)
        logger.info(f"Fetched {len(rows)} arbitrage routes with at least one tradable token from the database.")
        print(f"Fetched {len(rows)} arbitrage routes with at least one tradable token from the database.")
        # return [dict(row) for row in rows]

        # print(f"Filtered Rows: {filtered_rows}")
        # Keep unique routes
        unique_routes = []
        for row in rows:
            if row not in unique_routes:
                unique_routes.append(row)
        logger.info(f"Unique Routes found: {len(unique_routes)}")
        print(f"Unique Routes found: {len(unique_routes)}")

        # Filter rows where the non-0.0025 fee is at least 0.02
        filtered_rows = []
        for row in unique_routes:
            pool_a_fee = float(round(Decimal(row["pool_a_fee"]), 4))
            pool_b_fee = float(round(Decimal(row["pool_b_fee"]), 4))

            # print(f"Pool A Fee: {pool_a_fee}, Pool B Fee: {pool_b_fee}")

            if pool_a_fee == 0.0025 and pool_b_fee >= MIN_METEORA_FEE / 100:
                filtered_rows.append(dict(row))
            elif pool_b_fee == 0.0025 and pool_a_fee >= MIN_METEORA_FEE / 100:
                filtered_rows.append(dict(row))

        # If same raydium pool is is present in multiple routes, keep the first route found
        last_raydium_pool = None
        unique_pair_routes = []
        for row in filtered_rows:
            if row["pool_a_dex"] == "raydium":
                if row["pool_a_address"] == last_raydium_pool:
                    continue
                last_raydium_pool = row["pool_a_address"]
            if row["pool_b_dex"] == "raydium":
                if row["pool_b_address"] == last_raydium_pool:
                    continue
                last_raydium_pool = row["pool_b_address"]
            unique_pair_routes.append(dict(row))
        logger.info(f"Unique Pair Routes found: {len(unique_pair_routes)}")
        print(f"Unique Pair Routes found: {len(unique_pair_routes)}")
        

        logger.info(f"Filtered {len(unique_pair_routes)} arbitrage routes with at least 2% Meteora fee.")
        print(f"Filtered {len(unique_pair_routes)} arbitrage routes with at least 2% Meteora fee.")
        return unique_pair_routes
    
async def get_tradable_two_arbitrage_routes():
    """
    Fetch all arbitrage routes from the database where at least one tradable token is involved.
    """
    async with get_db_connection() as conn:
        query = '''
            SELECT 
                tar.id,
                tar.pool_a_id,
                tar.pool_b_id,
                tar.pool_a_address,
                tar.pool_b_address,
                tar.pool_a_dex,
                tar.pool_b_dex,
                tar.reserve_a_address_pool_a,
                tar.reserve_b_address_pool_a,
                tar.reserve_a_address_pool_b,
                tar.reserve_b_address_pool_b,
                tar.reserve_a_mint_pool_a,
                tar.reserve_a_mint_pool_b,
                tar.reserve_b_mint_pool_a,
                tar.reserve_b_mint_pool_b,
                tar.reserve_a_pool_a,
                tar.reserve_b_pool_a,
                tar.reserve_a_pool_b,
                tar.reserve_b_pool_b,
                tar.reserve_a_pool_a_decimals,
                tar.reserve_b_pool_a_decimals,
                tar.reserve_a_pool_b_decimals,
                tar.reserve_b_pool_b_decimals,
                tar.pool_a_fee,
                tar.pool_b_fee,
                tar.lut,
                tar.status
            FROM two_arbitrage_routes tar
            JOIN tokens t ON (
                tar.reserve_a_mint_pool_a = t.address OR
                tar.reserve_b_mint_pool_a = t.address OR
                tar.reserve_a_mint_pool_b = t.address OR
                tar.reserve_b_mint_pool_b = t.address
            )
            WHERE tar.status = 'enabled'
            AND t.tradable = TRUE
            AND t.name != 'SOL'
            AND tar.pool_b_dex = 'meteora';
        '''
        #     AND t.tradable = TRUE
        #     AND tar.lut IS NOT NULL;
        # '''
        rows = await conn.fetch(query)
        logger.info(f"Fetched {len(rows)} arbitrage routes with at least one tradable token from the database.")
        print(f"Fetched {len(rows)} arbitrage routes with at least one tradable token from the database.")
        # return [dict(row) for row in rows]

        # print(f"Filtered Rows: {filtered_rows}")
        # Keep unique routes
        unique_routes = []
        for row in rows:
            if row not in unique_routes:
                unique_routes.append(row)
        logger.info(f"Unique Routes found: {len(unique_routes)}")
        print(f"Unique Routes found: {len(unique_routes)}")

        # Filter rows where the non-0.0025 fee is at least 0.02
        filtered_rows = []
        for row in unique_routes:
            pool_a_fee = float(round(Decimal(row["pool_a_fee"]), 4))
            pool_b_fee = float(round(Decimal(row["pool_b_fee"]), 4))

            # print(f"Pool A Fee: {pool_a_fee}, Pool B Fee: {pool_b_fee}")

            if pool_a_fee == 0.0025 and pool_b_fee >= MIN_METEORA_FEE / 100:
                filtered_rows.append(dict(row))
            elif pool_b_fee == 0.0025 and pool_a_fee >= MIN_METEORA_FEE / 100:
                filtered_rows.append(dict(row))

        logger.info(f"Filtered {len(filtered_rows)} arbitrage routes with at least 2% Meteora fee.")
        print(f"Filtered {len(filtered_rows)} arbitrage routes with at least 2% Meteora fee.")
        return filtered_rows
      
async def update_two_arbitrage_routes(route_id, reserve_a_pool_a, reserve_b_pool_a, reserve_a_pool_b, reserve_b_pool_b):
    """
    Update reserves for a specific arbitrage route in the database.

    Args:
        conn (asyncpg.Connection): The database connection object.
        route_id (int): The ID of the arbitrage route to update.
        reserve_a_pool_a (float): Reserve A of Pool A.
        reserve_b_pool_a (float): Reserve B of Pool A.
        reserve_a_pool_b (float): Reserve A of Pool B.
        reserve_b_pool_b (float): Reserve B of Pool B.

    Returns:
        bool: True if the update was successful, False otherwise.
    """
    async with get_db_connection() as conn:
        query = '''
            UPDATE two_arbitrage_routes
            SET 
                reserve_a_pool_a = $1,
                reserve_b_pool_a = $2,
                reserve_a_pool_b = $3,
                reserve_b_pool_b = $4,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = $5;
        '''
        try:
            await conn.execute(
                query,
                reserve_a_pool_a,
                reserve_b_pool_a,
                reserve_a_pool_b,
                reserve_b_pool_b,
                route_id
            )
            print(f"Updated reserves for route ID {route_id}")
            return True
        except Exception as e:
            print(f"Failed to update route ID {route_id}: {e}")
            return False

async def update_two_arbitrage_route_status(route_id, status):
    """
    Update the status of a specific arbitrage route in the database.

    Args:
        route_id (int): The ID of the arbitrage route to update.
        status (str): The new status for the route.

    Returns:
        bool: True if the update was successful, False otherwise.
    """
    async with get_db_connection() as conn:
        query = '''
            UPDATE two_arbitrage_routes
            SET status = $1, updated_at = CURRENT_TIMESTAMP
            WHERE id = $2;
        '''
        try:
            await conn.execute(query, status, route_id)
            logger.info(f"Updated status for route ID {route_id}")
            # print(f"Updated status for route ID {route_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to update status for route ID {route_id}: {e}")
            # print(f"Failed to update status for route ID {route_id}: {e}")
            return False
          
async def get_lut_addresses_from_route(lut):
    """
    Fetch the LUT addresses for a specific LUT address from the database.
    """
    async with get_db_connection() as conn:
        # Fetch the LUT record from the database using the LUT address
        lut_record = await conn.fetchrow('''
            SELECT addresses FROM luts WHERE address = $1
        ''', lut)

        # If the LUT record exists, convert the addresses to a list
        if lut_record:
            # Parse the string into a valid list
            lut_addresses = json.loads(lut_record['addresses'])  # Convert from string to list
        else:
            lut_addresses = []  # If not found, return an empty list

        return lut, lut_addresses

async def get_ata_for_token(token_address):
    """
    Fetch the ATA address for a specific token from the database.
    """
    async with get_db_connection() as conn:
        # Fetch the ATA address for the token from the database
        ata_address = await conn.fetchval('''
            SELECT ata FROM tokens WHERE address = $1
        ''', token_address)

        return ata_address
    
if __name__ == "__main__":
    asyncio.run(setup_database())
