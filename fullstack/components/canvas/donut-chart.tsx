"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";

interface DonutChartProps {
  data: { label: string; value: number; color: string }[];
  title?: string;
  size?: number;
  showLegend?: boolean;
  className?: string;
}

export function DonutChart({
  data,
  title,
  size = 180,
  showLegend = true,
  className,
}: DonutChartProps) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  const total = data.reduce((sum, item) => sum + item.value, 0);

  // Calculate stroke-dasharray for each segment
  const circumference = 2 * Math.PI * 40; // radius = 40
  let currentOffset = 0;

  const segments = data.map((item, i) => {
    const percentage = item.value / total;
    const strokeLength = percentage * circumference;
    const strokeDasharray = `${strokeLength} ${circumference}`;
    const offset = currentOffset;
    currentOffset += strokeLength;

    return {
      ...item,
      percentage,
      strokeDasharray,
      offset,
      isHovered: hoveredIndex === i,
    };
  });

  return (
    <div className={cn("flex flex-col items-center", className)}>
      {title && (
        <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400 mb-3">
          {title}
        </p>
      )}
      <div className="relative">
        <svg
          width={size}
          height={size}
          viewBox="0 0 80 80"
          className="transform -rotate-90"
        >
          {segments.map((segment, i) => (
            <circle
              key={segment.label}
              cx="40"
              cy="40"
              r="32"
              fill="none"
              stroke={segment.isHovered ? segment.color : `${segment.color}80`}
              strokeWidth={segment.isHovered ? 14 : 12}
              strokeDasharray={segment.strokeDasharray}
              strokeDashoffset={-segment.offset}
              className="transition-all duration-200 cursor-pointer"
              onMouseEnter={() => setHoveredIndex(i)}
              onMouseLeave={() => setHoveredIndex(null)}
            />
          ))}
          {/* Inner circle to create donut effect */}
          <circle
            cx="40"
            cy="40"
            r="26"
            fill="transparent"
          />
        </svg>
        {/* Center text */}
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-2xl font-bold text-zinc-900 dark:text-zinc-100">
            {total.toLocaleString()}
          </span>
          <span className="text-xs text-zinc-500">Total</span>
        </div>
      </div>
      {showLegend && (
        <div className="flex flex-wrap justify-center gap-3 mt-4">
          {segments.map((segment, i) => (
            <div
              key={segment.label}
              className={cn(
                "flex items-center gap-2 px-2 py-1 rounded transition-colors",
                segment.isHovered && "bg-zinc-100 dark:bg-zinc-800"
              )}
              onMouseEnter={() => setHoveredIndex(i)}
              onMouseLeave={() => setHoveredIndex(null)}
            >
              <div
                className="w-3 h-3 rounded-full"
                style={{ backgroundColor: segment.color }}
              />
              <span className="text-xs text-zinc-600 dark:text-zinc-400">
                {segment.label}
              </span>
              <span className="text-xs font-medium text-zinc-900 dark:text-zinc-100">
                {segment.percentage.toFixed(0)}%
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
