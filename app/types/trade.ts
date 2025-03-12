export interface TradePosition {
    id: number; // Unique identifier for the trading position
    address: string; // Wallet or contract address associated with the position
    symbol: string; // Token symbol (e.g., "MOODENG")
    buy_amount: number; // Amount of tokens bought, in base units
    buy_price: number; // Price per token at the time of purchase
    current_amount: number; // Current amount of tokens held, in base units
    current_price: number; // Current price per token
    highest_price: number; // Highest recorded price per token for this position
    stop_loss_price: number; // Price at which the position triggers a stop-loss sell
    stop_loss_percentage: number | null;  // Price at which the position triggers a stop-loss sell
    max_sell_value: number; // Maximum value of tokens for sale
    profit_amount: number; // Absolute profit (current amount - buy amount), in base units
    profit_percentage: number; // Profit percentage relative to buy price
    status: 'active' | 'idle' | 'stopped'; // Status of the position
    enable_scan: boolean; // Whether scanning is enabled for this position
    enable_trade: boolean; // Whether trading is enabled for this position
    decimals: number; // Number of decimal places for the token
    created_at: string; // ISO string format timestamp for the creation date
    updated_at: string; // ISO string format timestamp for the last update date
    max_sell_value_at: string; // ISO string format timestamp for the last update date
  }
  