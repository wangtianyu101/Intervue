// 共享组件：4 档掌握度徽章
// 阶段 6.2 Phase B
// 用于：题库题目行、答题页、统计页

import React from "react";
import type { MasteryStatus } from "@/types/learn";

interface MasteryBadgeProps {
  status: MasteryStatus;
  /** 尺寸 */
  size?: "sm" | "md";
  /** 显示图标 */
  withIcon?: boolean;
}

const CONFIG: Record<MasteryStatus, { label: string; icon: string; className: string }> = {
  new: {
    label: "未学",
    icon: "⚪",
    className: "bg-gray-800 text-gray-400",
  },
  learning: {
    label: "学习中",
    icon: "📖",
    className: "bg-blue-500/15 text-blue-400",
  },
  mastered: {
    label: "已掌握",
    icon: "✅",
    className: "bg-green-500/15 text-green-400",
  },
  skipped: {
    label: "已跳过",
    icon: "⏭",
    className: "bg-gray-800 text-gray-500 line-through",
  },
};

export default function MasteryBadge({ status, size = "sm", withIcon = true }: MasteryBadgeProps) {
  const cfg = CONFIG[status];
  const sizeClass = size === "md" ? "px-3 py-1 text-sm" : "px-2 py-0.5 text-xs";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md font-medium whitespace-nowrap ${sizeClass} ${cfg.className}`}
      title={cfg.label}
    >
      {withIcon && <span>{cfg.icon}</span>}
      <span>{cfg.label}</span>
    </span>
  );
}
