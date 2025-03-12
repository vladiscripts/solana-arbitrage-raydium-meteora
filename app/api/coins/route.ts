import { NextResponse } from 'next/server';
import { connectToArbitrageDatabase } from '@/lib/database'; // Adjust path to match your project structure

export async function GET() {
  const db = await connectToArbitrageDatabase();

  try {
    // Query to fetch all tokens except SOL
    const query = 'SELECT * FROM tokens WHERE name != $1';
    const values = ['SOL'];

    const result = await db.query(query, values);

    // Send the token data as a response
    return NextResponse.json(result.rows); // PostgreSQL returns data in `rows`
  } catch (error) {
    console.error('Error fetching coins:', error);
    return NextResponse.json({ error: 'Failed to fetch coins' }, { status: 500 });
  }
}
