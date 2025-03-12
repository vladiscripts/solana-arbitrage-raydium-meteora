import { Pool } from 'pg';

// Create a pool to manage connections
const pool = new Pool({
  host: 'localhost', // Replace with your database host
  user: 'YOUR_USERNAME', // Replace with your database username
  password: 'YOUR_PASSWORD', // Replace with your database password
  database: 'YOUR_DB_NAME', // Replace with your database name
  port: 5432, // Default PostgreSQL port
  ssl: false, // Set to true if you're using SSL
});

export async function connectToArbitrageDatabase() {
  return pool; // Return the connection pool
}
