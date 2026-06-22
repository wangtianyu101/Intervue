// 共享组件：通用进度条
// 阶段 6.2 Phase B
// 用于：AI 推送（"N/10 已读"） / 学习复习（"5/8 完成"） / 答题（实时进度）

import React from "react";

interface ProgressBarProps {
  /** 当前进度 */
  current: number;
  /** 总数 */
  total: number;
  /** 主色：indigo（默认）/ purple（AI 推送） / green（复习完成） */
  variant?: "default" | "digest" | "success";
  /** 右侧文字（如 "5/10 已读"） */
  label?: React.ReactNode;
  /** 左侧文字（如 "进度"） */
  prefix?: React.ReactNode;
  /** 高度，默认 8px */
  size?: "sm" | "md" | "lg";
  /** 是否显示百分比（默认 false） */
  showPercent?: boolean;
}

const VARIANT_CLASSES: Record<NonNullable<ProgressBarProps["variant"]>, string> = {
  default: "bg-gradient-to-r from-indigo-500 to-purple-500",
  digest: "bg-gradient-to-r from-purple-500 to-pink-500",
  success: "bg-gradient-to-r from-green-500 to-emerald-500",
};

const SIZE_CLASSES: Record<NonNullable<ProgressBarProps["size"]>, string> = {
  sm: "h-1.5",
  md: "h-2",
  lg: "h-3",
};

export default function ProgressBar({
  current,
  total,
  variant = "default",
  label,
  prefix,
  size = "md",
  showPercent = false,
}: ProgressBarProps) {
  const safeTotal = Math.max(total, 1);
  const percent = Math.min(Math.round((current / safeTotal) * 100), 100);

  return (
    <div className="flex items-center gap-3">
      {prefix && <div className="text-xs text-gray-400">{prefix}</div>}
      <div className={`flex-1 bg-gray-800 rounded-full overflow-hidden ${SIZE_CLASSES[size]}`}>
        <div
          className={`h-full rounded-full transition-all duration-500 ${VARIANT_CLASSES[variant]}`}
          style={{ width: `${percent}%` }}
        />
      </div>
      {label && <div className="text-sm font-semibold text-gray-200 min-w-fit">{label}</div>}
      {showPercent && !label && (
        <div className="text-sm font-semibold text-gray-200 min-w-[3rem] text-right">{percent}%</div>
      )}
    </div>
  );
}
