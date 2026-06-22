// 共享组件：4 档状态切换按钮组
// 阶段 6.2 Phase B
// 用于：题库答题页（new / learning / mastered / skipped）

import React from "react";
import type { MasteryStatus } from "@/types/learn";

interface StatusSwitcherProps {
  value: MasteryStatus;
  onChange: (next: MasteryStatus) => void;
  disabled?: boolean;
}

const OPTIONS: Array<{ value: MasteryStatus; label: string; icon: string }> = [
  { value: "new", label: "未学", icon: "⚪" },
  { value: "learning", label: "学习中", icon: "📖" },
  { value: "mastered", label: "已掌握", icon: "✅" },
  { value: "skipped", label: "跳过", icon: "⏭" },
];

export default function StatusSwitcher({ value, onChange, disabled }: StatusSwitcherProps) {
  return (
    <div className="grid grid-cols-4 gap-2">
      {OPTIONS.map((opt) => {
        const active = opt.value === value;
        return (
          <button
            key={opt.value}
            type="button"
            disabled={disabled}
            onClick={() => onChange(opt.value)}
            className={`
              px-2 py-2.5 rounded-md text-sm transition-all duration-200
              ${active
                ? "bg-indigo-500/20 text-indigo-300 border border-indigo-500"
                : "bg-gray-800/50 text-gray-400 border border-gray-700 hover:border-indigo-500/50 hover:text-gray-200"
              }
              ${disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}
            `}
          >
            <div className="text-lg mb-1">{opt.icon}</div>
            <div className="text-xs">{opt.label}</div>
          </button>
        );
      })}
    </div>
  );
}
