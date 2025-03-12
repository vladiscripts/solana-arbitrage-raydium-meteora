"use client";
import React, { useRef, useState } from "react";

interface Token {
  id: string;
  name: string;
  address: string;
  status: string;
}

interface CoinsProps {
  tokens: Token[];
  onSelect: (token: Token) => void;
}

const Coins: React.FC<CoinsProps> = ({ tokens, onSelect }) => {
  const containerRef = useRef<HTMLDivElement>(null); // Ref for the scrollable container
  const [isDragging, setIsDragging] = useState(false); // Track if dragging is active
  const [startX, setStartX] = useState(0); // Initial mouse X position
  const [scrollLeft, setScrollLeft] = useState(0); // Initial scroll position

  // Handle mouse down event
  const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!containerRef.current) return;
    setIsDragging(true);
    setStartX(e.pageX - containerRef.current.offsetLeft);
    setScrollLeft(containerRef.current.scrollLeft);
  };

  // Handle mouse move event
  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!isDragging || !containerRef.current) return;
    e.preventDefault();
    const x = e.pageX - containerRef.current.offsetLeft;
    const walk = (x - startX) * 2; // Adjust scroll speed
    containerRef.current.scrollLeft = scrollLeft - walk;
  };

  // Handle mouse up/leave event
  const handleMouseUpOrLeave = () => {
    setIsDragging(false);
  };

  return (
    <div
      ref={containerRef}
      className="overflow-x-auto whitespace-nowrap cursor-grab active:cursor-grabbing scrollbar-hide" // Add custom class to hide scrollbar
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUpOrLeave}
      onMouseLeave={handleMouseUpOrLeave}
    >
      <div className="flex flex-row gap-4">
        {tokens.map((token) => (
          <div
            key={token.id}
            className="p-6 border rounded-lg shadow-lg cursor-pointer hover:bg-gray-100 transition duration-300 flex-shrink-0"
            onClick={() => onSelect(token)}
          >
            <h2 className="text-xl font-semibold">{token.name}</h2>
            <p className="text-sm text-gray-600">{token.address}</p>
            {/* <p className="text-gray-600">Status: {token.status}</p> */}
          </div>
        ))}
      </div>
    </div>
  );
};

export default Coins;