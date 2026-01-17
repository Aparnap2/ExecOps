"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";

interface BarChartProps {
  data: { label: string; value: number; color?: string }[];
  title?: string;
  maxValue?: number;
  height?: number;
  showValues?: boolean;
  className?: string;
}

export function BarChart({
  data,
  title,
  maxValue,
  height = 200,
  showValues = true,
  className,
}: BarChartProps) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const max = maxValue || Math.max(...data.map((d) => d.value));

  return (
    <div className={cn("w-full", className)}>
      {title && (
        <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400 mb-3">
          {title}
        </p>
      )}
      <div className="flex items-end justify-between gap-2" style={{ height }}>
        {data.map((item, i) => {
          const percentage = (item.value / max) * 100;
          const isHovered = hoveredIndex === i;

          return (
            <div
              key={item.label}
              className="flex-1 flex flex-col items-center gap-1"
              onMouseEnter={() => setHoveredIndex(i)}
              onMouseLeave={() => setHoveredIndex(null)}
            >
              <div
                className="w-full relative flex items-end justify-center"
                style={{ height: `${percentage}%` }}
              >
                <div
                  className={cn(
                    "w-full max-w-[60px] rounded-t transition-all duration-200",
                    isHovered ? "opacity-100" : "opacity-80"
                  )}
                  style={{
                    height: "100%",
                    backgroundColor: item.color || "#6366f1",
                  }}
                />
                {showValues && (
                  <span
                    className={cn(
                      "absolute -top-6 text-xs font-medium transition-opacity",
                      isHovered ? "opacity-100" : "opacity-0"
                    )}
                  >
                    {item.value.toLocaleString()}
                  </span>
                )}
              </div>
              <span
                className={cn(
                  "text-xs text-zinc-500 dark:text-zinc-400 text-center truncate w-full",
                  isHovered && "text-zinc-700 dark:text-zinc-200 font-medium"
                )}
              >
                {item.label}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
