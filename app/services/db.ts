import { connectToDatabase, connectToMeteoraDatabase } from '@/lib/sqlite';
import { log } from 'console';

const MAX_RETRIES = 3;
const RETRY_DELAY = 1000; // 1 second

async function retryOperation(operation, retries = MAX_RETRIES, delay = RETRY_DELAY) {
  for (let attempt = 1; attempt <= retries; attempt++) {
    try {
      return await operation();
    } catch (error) {
      if (attempt === retries) {
        throw error;
      }
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }
}


// Function to fetch LP positions from the database
export async function getTradingPositionsFromDb() {
  return retryOperation(async () => {
    const db = await connectToDatabase();
    const selectSQL = `SELECT * FROM positions;`;
    
    const rows = await db.all(selectSQL, [], (err, rows) => {
        if (err) {
          throw new Error(`Failed to fetch positions: ${err.message}`);
        }
        return rows;
    });

    return rows; // Return the rows (positions)
  });
}

// Function to update total claimed fees in the database
export async function updateTradingPositionCurrentAmount(positionId, current_amount) {
  return retryOperation(async () => {
    const db = await connectToDatabase();
    const query = `
      UPDATE positions 
      SET current_amount = ?
      WHERE id = ?
    `;

    await db.run(query, [current_amount, positionId]);
    await db.close();
  });
}

// Function to update total claimed fees in the database
export async function updateTradingPositionValue(positionId, sol_value) {
  return retryOperation(async () => {
    const db = await connectToDatabase();
    const query = `
      UPDATE positions 
      SET max_sell_value = ?
      WHERE id = ?
    `;

    await db.run(query, [sol_value, positionId]);
    await db.close();
  });
}

// Function to update total claimed fees in the database
export async function updateTradingPositionStopLoss(positionId, stop_loss) {
  return retryOperation(async () => {
    const db = await connectToDatabase();
    const query = `
      UPDATE positions 
      SET stop_loss_price = ?
      WHERE id = ?
    `;

    await db.run(query, [stop_loss, positionId]);
    await db.close();
  });
}

// Function to update total claimed fees in the database
export async function updateTradingPositionStatus(positionId, status) {
  return retryOperation(async () => {
    const db = await connectToDatabase();
    const query = `
      UPDATE positions 
      SET status = ?
      WHERE id = ?
    `;

    await db.run(query, [status, positionId]);
    await db.close();
  });
}

// Function to fetch LP positions from the database
export async function getArbitrageRoutesFromDb() {
  return retryOperation(async () => {
    const db = await connectToMeteoraDatabase();
    const selectSQL = `SELECT * FROM pools WHERE liquidity > 10000;`;
    
    const rows = await db.all(selectSQL, [], (err, rows) => {
        if (err) {
          throw new Error(`Failed to fetch positions: ${err.message}`);
        }
        return rows;
    });

    return rows; // Return the rows (positions)
  });
}