"use client";
import { ReactNode } from "react";

const DashboardLayout = ({ children }: { children: ReactNode }) => {
  return <div className="px-4 min-h-screen">{children}</div>;
};

export default DashboardLayout;
