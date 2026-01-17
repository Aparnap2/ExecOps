"use client";

import { cn } from "@/lib/utils";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";

interface MetricCardProps {
  title: string;
  value: string | number;
  trend?: "up" | "down" | "stable";
  trendValue?: string;
  subtitle?: string;
  className?: string;
}

export function MetricCard({
  title,
  value,
  trend,
  trendValue,
  subtitle,
  className,
}: MetricCardProps) {
  return (
    <div
      className={cn(
        "bg-zinc-50 dark:bg-zinc-900 rounded-lg border border-zinc-200 dark:border-zinc-800 p-4",
        className
      )}
    >
      <div className="flex items-center justify-between mb-2">
        <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400">
          {title}
        </p>
        {trend && (
          <div
            className={cn(
              "flex items-center gap-1 text-xs font-medium",
              trend === "up" && "text-emerald-600",
              trend === "down" && "text-red-600",
              trend === "stable" && "text-zinc-500"
            )}
          >
            {trend === "up" && <TrendingUp className="w-3 h-3" />}
            {trend === "down" && <TrendingDown className="w-3 h-3" />}
            {trend === "stable" && <Minus className="w-3 h-3" />}
            {trendValue}
          </div>
        )}
      </div>
      <p className="text-2xl font-bold text-zinc-900 dark:text-zinc-100">
        {value}
      </p>
      {subtitle && (
        <p className="text-xs text-zinc-400 mt-1">{subtitle}</p>
      )}
    </div>
  );
}

interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  color?: string;
  className?: string;
}

export function Sparkline({
  data,
  width = 80,
  height = 30,
  color = "#10b981",
  className,
}: SparklineProps) {
  if (!data || data.length === 0) return null;

  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;

  const points = data
    .map((value, i) => {
      const x = (i / (data.length - 1)) * width;
      const y = height - ((value - min) / range) * height;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <svg
      width={width}
      height={height}
      className={className}
      viewBox={`0 0 ${width} ${height}`}
    >
      <polyline
        fill="none"
        stroke={color}
        strokeWidth="2"
        points={points}
      />
    </svg>
  );
}
