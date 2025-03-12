import { Connection, PublicKey } from '@solana/web3.js';
import * as SPLToken from '@solana/spl-token';

import { sleep } from '@/app/services/util';

// Function to get availanble SOL
export async function getAvailableSOL(user: PublicKey, connection: Connection) {
    const solMint = process.env.NEXT_PUBLIC_SOL_ADDRESS;

    const maxRetries = 50; // Set the maximum number of retries
    let retries = 0;
    let amount = 0;
    // console.log(`Checking available tokens for ${solMint}...`);    

    while (retries < maxRetries) {
        try {
            // Fetch the SOL balance for the user's public key
            let balance = await connection.getBalance(user.publicKey);

            // Convert the balance from lamports to SOL (1 SOL = 1e9 lamports)
            balance = balance / 1e9;

            if (balance > 0) {
                // If we successfully find SOL, return the balance immediately
                return balance.toFixed(6);
            }

            // console.log(`No tokens available on attempt ${retries + 1} from ${solMint}.`);
        } catch (error) {
            console.error(`Error in getAvailableTokens (Attempt ${retries + 1}/${maxRetries}): ${error.message}`);
        }

        await sleep(1000);
        retries++;
    }

    // After all retries, check if we still have no tokens
    if (amount === 0) {
        console.log(`No tokens available for swapping from ${solMint} after ${maxRetries} attempts.`);
    }

    return amount; // Return 0 if no tokens were found after all retries
}

// Function to get availanble tokens
export async function getAvailableTokens(mint: string, publickKey: PublicKey, connection: Connection) {    
    // console.log(publickKey);

    const maxRetries = 50; // Set the maximum number of retries
    let retries = 0;
    let amount = 0;    

    while (retries < maxRetries) {
        try {
            // Fetch token accounts for the specified mint
            const response = await connection.getTokenAccountsByOwner(publickKey, {
                mint: new PublicKey(mint),
            });

            // Reset amount on each try
            amount = 0;

            // Retrieve the token balance
            response.value.forEach((e) => {
                const accountInfo = SPLToken.AccountLayout.decode(e.account.data);
                if (accountInfo.amount > 0) {
                    amount = accountInfo.amount;
                }
            });

            if (amount > 0) {
                // If we successfully find tokens, return the amount immediately
                return amount;
            }

            // console.log(`No tokens available on attempt ${retries + 1} from ${mint}.`);
        } catch (error) {
            console.error(`Error in getAvailableTokens (Attempt ${retries + 1}/${maxRetries}): ${error.message}`);
        }

        await sleep(10000);
        retries++;
    }

    // After all retries, check if we still have no tokens
    if (amount === 0) {
        console.log(`No tokens available for swapping from ${mint} after ${maxRetries} attempts.`);
        return false;
    }

    return amount; // Return 0 if no tokens were found after all retries
}

// Function to get decimals for a token
export async function getTokenDecimals(mint: string, connection: Connection) {
    try {
        const mintInfo = await connection.getParsedAccountInfo(new PublicKey(mint));
        const decimals = mintInfo.value.data.parsed.info.decimals;
        return decimals;
    } catch (error) {
        console.error(`Error in getTokenDecimals: ${error.message}`);
        return 0;
    }
}