import * as fs from 'fs';
import { Keypair } from '@solana/web3.js';

import { AMM_V4, AMM_STABLE, DEVNET_PROGRAM_ID } from '@raydium-io/raydium-sdk-v2'

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export const loadKeypairFromJSON = (filePath: string): Keypair => {
  // Read the raw array from the JSON file
  const json = fs.readFileSync(filePath, 'utf8');
  const privateKeyArray = new Uint8Array(JSON.parse(json));

  // Validate the length of the private key
  if (privateKeyArray.length !== 64) {
      throw new Error(`Invalid private key length: ${privateKeyArray.length}. Expected: 64.`);
  }

  return Keypair.fromSecretKey(privateKeyArray);
};

export async function delay(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function getDurationString(duration: number) {
  const estimateInSeconds = Math.floor(duration / 1000);
  const minutes = Math.floor(estimateInSeconds / 60);
  const seconds = estimateInSeconds % 60;

  return `${minutes > 0 ? `${minutes}m, ` : ""}${seconds}s`;
}

export function downloadStringToFile(filename: string, text: string) {
  const element = document.createElement("a");

  element.setAttribute(
    "href",
    "data:text/plain;charset=utf-8," + encodeURIComponent(text),
  );
  element.setAttribute("download", filename);

  element.style.display = "none";
  document.body.appendChild(element);

  element.click();

  document.body.removeChild(element);
}

export function objArrayToCsvString<T extends Object>(
  objArray: Array<T>,
  columns?: Array<keyof T>,
): string {
  if (objArray.length == 0) {
    return "";
  }

  columns = columns ?? (Object.keys(objArray[0]) as Array<keyof T>);

  const output = columns.join(",");
  const lines: string[] = [];

  objArray.forEach((obj) => {
    const line = columns!
      .map((key) => {
        const value = obj[key];

        return value !== undefined && value !== null && typeof value != "object"
          ? '"' + value.toString().replace(/"/g, '""') + '"'
          : "";
      })
      .join(",");

    lines.push(line);
  });

  return output + "\n" + lines.join("\n");
}

export function downloadObjArrayAsCsv<T extends Object>(
  filename: string,
  objArray: Array<T>,
  columns?: Array<keyof T>,
) {
  downloadStringToFile(filename, objArrayToCsvString(objArray, columns));
}

export const printSimulateInfo = () => {
  console.log(
    'you can paste simulate tx string here: https://explorer.solana.com/tx/inspector and click simulate to check transaction status'
  )
  console.log(
    'if tx simulate successful but did not went through successfully after running execute(xxx), usually means your txs were expired, try set up higher priority fees'
  )
  console.log('strongly suggest use paid rpcs would get you better performance')
}

const VALID_PROGRAM_ID = new Set([
  AMM_V4.toBase58(),
  AMM_STABLE.toBase58(),
  DEVNET_PROGRAM_ID.AmmV4.toBase58(),
  DEVNET_PROGRAM_ID.AmmStable.toBase58(),
])

export const isValidAmm = (id: string) => VALID_PROGRAM_ID.has(id)