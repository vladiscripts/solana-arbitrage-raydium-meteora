"use client";
import React from "react";

interface Pool {
  address: string;
  dex: string;
  fee?: number;
  bin_step?: number;
  base_token_address: string;
  quote_token_address: string;
}

interface PoolsProps {
  pools: Pool[];
  onSelect: (pool: Pool) => void;
}

const Pools: React.FC<PoolsProps> = ({ pools, onSelect }) => {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      {pools.map((pool, index) => (
        <div
          key={index}
          className="p-6 border rounded-lg shadow-lg cursor-pointer hover:bg-gray-100 transition duration-300"
          onClick={() => onSelect(pool)}
        >
          <h2 className="text-xl font-semibold mb-2">{pool.address}</h2>
          <p className="text-gray-600 mb-1 capitalize">{pool.dex}</p>
          {pool.dex === "meteora" && (
            <div className="flex flex-row justify-between">
              <p className="text-gray-600 mb-1">Fee: {pool.fee}%</p>
              <p className="text-gray-600 mb-1">Bin Step: {pool.bin_step}</p>
            </div>
          )}
          <p className="text-gray-600 mb-1">Base Token: {pool.base_token_address}</p>
          <p className="text-gray-600">Quote Token: {pool.quote_token_address}</p>
        </div>
      ))}
    </div>
  );
};

export default Pools;
