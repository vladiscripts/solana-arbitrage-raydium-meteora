// app/api/pools/route.ts (if using Next.js with PostgreSQL)
import { NextResponse } from 'next/server';
import { connectToArbitrageDatabase } from '@/lib/database'; // Adjust the path to your PostgreSQL connection

export async function GET(request: Request) {
  const url = new URL(request.url);
  const tokenAddress = url.searchParams.get('address'); // Extract token address from query parameters

  if (!tokenAddress) {
    return NextResponse.json({ error: 'Token address is required' }, { status: 400 });
  }

  const db = await connectToArbitrageDatabase(); // Connect to PostgreSQL

  try {
    // Query to fetch all pools for the specified token
    const query = `
      SELECT * FROM pools 
      WHERE base_token_address = $1 OR quote_token_address = $1
    `;
    const values = [tokenAddress]; // Use parameterized queries to prevent SQL injection

    const result = await db.query(query, values); // Execute the query

    // Send the pool data as a response
    return NextResponse.json(result.rows); // PostgreSQL returns data in `rows`
  } catch (error) {
    console.error('Error fetching pools:', error);
    return NextResponse.json({ error: 'Failed to fetch pools' }, { status: 500 });
  }
}
