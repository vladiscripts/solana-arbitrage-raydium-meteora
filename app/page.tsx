"use client";
import React, { useState, useEffect } from "react";
import DashboardLayout from "./components/DashboardLayout";
import Coins from "./components/Coins";
import Pools from "./components/Pools";
import Routes from "./components/Routes";

export default function Home() {
  const [tokens, setTokens] = useState([]);
  const [pools, setPools] = useState([]);
  const [routes, setRoutes] = useState([]);
  const [selectedToken, setSelectedToken] = useState(null);
  const [selectedPool, setSelectedPool] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function fetchTokens() {
      try {
        const response = await fetch("/api/coins");
        if (!response.ok) {
          throw new Error("Failed to fetch tokens");
        }
        const data = await response.json();
        setTokens(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }

    fetchTokens();
  }, []);

  const fetchPools = async (tokenAddress: string) => {
    setLoading(true);
    setPools([]);
    setRoutes([]);
    try {
      const response = await fetch(`/api/pools?address=${tokenAddress}`);
      if (!response.ok) {
        throw new Error("Failed to fetch pools");
      }
      const data = await response.json();
      setPools(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    const interval = setInterval(fetchRoutes, 100);
    return () => clearInterval(interval);
  }, []);

  const fetchRoutes = async () => {
    try {
      const response = await fetch(`/api/routes`);
      if (!response.ok) {
        throw new Error("Failed to fetch routes");
      }
      const data = await response.json();
      setRoutes(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleTokenSelect = (token: any) => {
    setSelectedToken(token);
    fetchPools(token.address);
  };

  const handlePoolSelect = (pool: any) => {
    setSelectedPool(pool);
    fetchRoutes();
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center h-screen">
        <div className="loader ease-linear rounded-full border-8 border-t-8 border-gray-200 h-32 w-32"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex justify-center items-center h-screen text-red-500">
        Error: {error}
      </div>
    );
  }

  return (
    // <div className="container mx-auto p-4">
    <div className="mx-auto p-4">
      <DashboardLayout>
        <h1 className="text-2xl font-bold mb-4">
          {selectedPool
            ? `Routes for Pool ${selectedPool.address}`
            : selectedToken
            ? `Pools for ${selectedToken.name}`
            : "Available Tokens"}
        </h1>
        {(selectedToken || selectedPool) && (
          <button
            className="mb-4 px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition duration-300"
            onClick={() => {
              if (selectedPool) {
                setSelectedPool(null);
              } else {
                setSelectedToken(null);
              }
            }}
          >
            Back
          </button>
        )}
        {selectedToken ? (
          <Pools pools={pools} onSelect={handlePoolSelect} />
        ) : (
          <Coins tokens={tokens} onSelect={handleTokenSelect} />
        )}
        <h1 className="text-2xl font-bold my-4">
          Available Routes
        </h1>
        <Routes routes={routes} />
      </DashboardLayout>
    </div>
  );
}
