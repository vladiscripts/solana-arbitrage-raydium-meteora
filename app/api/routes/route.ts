// app/api/routes/route.ts
import { NextResponse } from 'next/server';
import { connectToArbitrageDatabase } from '@/lib/database'; // Adjust the path for your PostgreSQL connection

export async function GET() {
  const db = await connectToArbitrageDatabase();

  try {
    // Query to fetch all routes from the two_arbitrage_routes table
    const query = `
      SELECT 
        routes.id,
        routes.pool_a_id,
        routes.pool_b_id,
        routes.pool_a_address,
        routes.pool_b_address,
        routes.pool_a_dex,
        routes.pool_b_dex,
        routes.pool_a_fee,
        routes.pool_b_fee,
        routes.reserve_a_address_pool_a,
        routes.reserve_b_address_pool_a,
        routes.reserve_a_address_pool_b,
        routes.reserve_b_address_pool_b,
        routes.reserve_a_pool_a,
        routes.reserve_b_pool_a,
        routes.reserve_a_pool_b,
        routes.reserve_b_pool_b,
        routes.reserve_a_pool_a_decimals,
        routes.reserve_b_pool_a_decimals,
        routes.reserve_a_pool_b_decimals,
        routes.reserve_b_pool_b_decimals,
        routes.reserve_a_mint_pool_a,
        routes.reserve_b_mint_pool_a,
        routes.reserve_a_mint_pool_b,
        routes.reserve_b_mint_pool_b,
        routes.status,
        routes.created_at,
        routes.updated_at
      FROM two_arbitrage_routes AS routes WHERE routes.status = 'enabled'
    `;

    const result = await db.query(query); // Execute the query

    // Return all routes in the response
    return NextResponse.json(result.rows); // PostgreSQL stores results in `rows`
  } catch (error) {
    console.error('Error fetching routes:', error);
    return NextResponse.json({ error: 'Failed to fetch routes' }, { status: 500 });
  }
}
