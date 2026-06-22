// 共享组件：质量分徽章（AI 推送）
// 阶段 6.2 Phase B
// 用于：DailyCard / WeeklyReport

import React from "react";
import type { DigestItemQuality } from "@/types/digest";

interface QualityBadgeProps {
  score: DigestItemQuality;
  /** 显示格式：badge（带 ⭐） / star（只显示 ⭐） */
  format?: "badge" | "star";
  size?: "sm" | "md";
}

const CONFIG: Record<DigestItemQuality, { className: string }> = {
  5: { className: "bg-gradient-to-br from-amber-500 to-red-500 text-white font-bold" },
  4: { className: "bg-amber-500/15 text-amber-400 font-semibold" },
  3: { className: "bg-blue-500/15 text-blue-400" },
  2: { className: "bg-gray-700 text-gray-400" },
  1: { className: "bg-gray-800 text-gray-500" },
};

export default function QualityBadge({ score, format = "badge", size = "sm" }: QualityBadgeProps) {
  const cfg = CONFIG[score];
  const sizeClass = size === "md" ? "px-2.5 py-0.5 text-sm" : "px-2 py-0.5 text-xs";
  if (format === "star") {
    return (
      <span className={`inline-flex items-center gap-0.5 font-semibold ${cfg.className} rounded ${sizeClass}`}>
        <span>⭐</span>
        <span>{score.toFixed(1)}</span>
      </span>
    );
  }
  return (
    <span className={`inline-flex items-center gap-1 rounded font-medium ${sizeClass} ${cfg.className}`}>
      <span>⭐</span>
      <span>{score.toFixed(1)}</span>
    </span>
  );
}
