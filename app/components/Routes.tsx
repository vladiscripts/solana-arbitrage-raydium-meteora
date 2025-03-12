"use client";
import React, { useState } from "react";

interface Route {
  id: number;
  pool_a_dex: string;
  pool_b_dex: string;
  pool_a_address: string;
  pool_b_address: string;
  reserve_a_mint_pool_a: number;
  reserve_b_mint_pool_a: number;
  reserve_a_mint_pool_b: number;
  reserve_b_mint_pool_b: number;
  pool_a_fee: number;
  pool_b_fee: number;
  reserve_a_pool_a: number;
  reserve_b_pool_a: number;
  reserve_a_pool_a_decimals: number;
  reserve_b_pool_a_decimals: number;
  reserve_a_pool_b: number;
  reserve_b_pool_b: number;
  reserve_a_pool_b_decimals: number;
  reserve_b_pool_b_decimals: number;
  status: string;
}

interface RoutesProps {
  routes: Route[];
}

const Routes: React.FC<RoutesProps> = ({ routes }) => {
  // State to manage visibility of iframes per route
  const [iframeVisibility, setIframeVisibility] = useState<{ [key: number]: boolean }>({});

  // Function to toggle iframes for a specific route
  const toggleIframes = (routeId: number) => {
    setIframeVisibility((prev) => ({
      ...prev,
      [routeId]: !prev[routeId], // Toggle visibility for the specific route
    }));
  };

  return (
    <div className="grid grid-cols-3 gap-4">
      {routes.map((route) => (
        <div
          key={route.id}
          className="border rounded-lg shadow-lg p-6 bg-[#080808] text-white"
        >
          {/* Route Header */}
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-2xl font-bold">Route ID: {route.id}</h2>
            <p
              className={`text-sm px-3 py-1 rounded-full ${
                route.status === "enabled"
                  ? "bg-green-100 text-green-800"
                  : "bg-red-100 text-red-800"
              }`}
            >
              {route.status}
            </p>
          </div>

          {/* Mint Address Flow */}
          <p className="text-gray-400 font-medium mb-6">
            <span className="text-blue-400">{route.reserve_a_mint_pool_a}</span>{" "}
            →{" "}
            <span className="text-green-400">{route.reserve_b_mint_pool_a}</span>{" "}
            →{" "}
            <span className="text-blue-400">{route.reserve_a_mint_pool_b}</span>
          </p>

          {/* Pool Details Table */}
          <div className="overflow-x-auto mb-6">
            <table className="w-full border-collapse border border-gray-500 text-sm text-left">
              <thead className="bg-gray-700">
                <tr>
                  <th className="p-3 border border-gray-600">Data</th>
                  <th className="p-3 border border-gray-600">Pool A</th>
                  <th className="p-3 border border-gray-600">Pool B</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className="p-3 border border-gray-600">DEX</td>
                  <td className="p-3 border border-gray-600">
                    {route.pool_a_dex}
                  </td>
                  <td className="p-3 border border-gray-600">
                    {route.pool_b_dex}
                  </td>
                </tr>
                <tr>
                  <td className="p-3 border border-gray-600">Reserve A</td>
                  <td className="p-3 border border-gray-600">
                    {route.reserve_a_pool_a} (Decimals:{" "}
                    {route.reserve_a_pool_a_decimals})
                  </td>
                  <td className="p-3 border border-gray-600">
                    {route.reserve_a_pool_b} (Decimals:{" "}
                    {route.reserve_a_pool_b_decimals})
                  </td>
                </tr>
                <tr>
                  <td className="p-3 border border-gray-600">Reserve B</td>
                  <td className="p-3 border border-gray-600">
                    {route.reserve_b_pool_a} (Decimals:{" "}
                    {route.reserve_b_pool_a_decimals})
                  </td>
                  <td className="p-3 border border-gray-600">
                    {route.reserve_b_pool_b} (Decimals:{" "}
                    {route.reserve_b_pool_b_decimals})
                  </td>
                </tr>
                <tr>
                  <td className="p-3 border border-gray-600">Fee (%)</td>
                  <td className="p-3 border border-gray-600">{route.pool_a_fee}</td>
                  <td className="p-3 border border-gray-600">{route.pool_b_fee}</td>
                </tr>
                <tr>
                  <td className="p-3 border border-gray-600">Price</td>
                  <td className="p-3 border border-gray-600">
                    {(route.reserve_a_pool_a / route.reserve_b_pool_a).toFixed(6)}
                  </td>
                  <td className="p-3 border border-gray-600">
                    {(route.reserve_a_pool_b / route.reserve_b_pool_b).toFixed(6)}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          {/* Button to toggle iframes for this route */}
          <button
            onClick={() => toggleIframes(route.id)}
            className="mb-4 px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
          >
            {iframeVisibility[route.id] ? "Hide Iframes" : "Show Iframes"}
          </button>

          {/* GeckoTerminal Iframes */}
          {iframeVisibility[route.id] && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="aspect-w-16 aspect-h-9 h-64">
                <iframe
                  height="100%"
                  width="100%"
                  id="geckoterminal-embed"
                  title="GeckoTerminal Embed"
                  src={`https://www.geckoterminal.com/it/solana/pools/${route.pool_a_address}?embed=1&info=0&swaps=1&grayscale=0&light_chart=0`}
                  frameBorder="0"
                  allow="clipboard-write"
                  allowFullScreen
                  className="w-full h-full border border-gray-600 rounded-lg"
                ></iframe>
              </div>
              <div className="aspect-w-16 aspect-h-9">
                <iframe
                  height="100%"
                  width="100%"
                  id="geckoterminal-embed"
                  title="GeckoTerminal Embed"
                  src={`https://www.geckoterminal.com/it/solana/pools/${route.pool_b_address}?embed=1&info=0&swaps=1&grayscale=0&light_chart=0`}
                  frameBorder="0"
                  allow="clipboard-write"
                  allowFullScreen
                  className="w-full h-full border border-gray-600 rounded-lg"
                ></iframe>
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
};

export default Routes;