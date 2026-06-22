// 共享组件：AI 推送分类徽章
// 阶段 6.2 Phase B
// 用于：DailyCard / WeeklyReport / 月报分类标签

import React from "react";
import type { DigestCategory } from "@/types/digest";

interface CategoryBadgeProps {
  category: DigestCategory;
  size?: "sm" | "md";
}

const CONFIG: Record<DigestCategory, { icon: string; className: string }> = {
  头条: { icon: "🔥", className: "bg-red-500/15 text-red-400" },
  商业: { icon: "🏢", className: "bg-amber-500/15 text-amber-400" },
  论文: { icon: "📚", className: "bg-blue-500/15 text-blue-400" },
  工程: { icon: "🛠", className: "bg-green-500/15 text-green-400" },
  观点: { icon: "💡", className: "bg-purple-500/15 text-purple-400" },
};

export default function CategoryBadge({ category, size = "sm" }: CategoryBadgeProps) {
  const cfg = CONFIG[category];
  const sizeClass = size === "md" ? "px-3 py-1 text-sm" : "px-2 py-0.5 text-xs";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md font-medium whitespace-nowrap ${sizeClass} ${cfg.className}`}
    >
      <span>{cfg.icon}</span>
      <span>{category}</span>
    </span>
  );
}
