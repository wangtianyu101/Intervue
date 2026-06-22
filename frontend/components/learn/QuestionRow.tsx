// 学习复习：题目行
// 阶段 6.2 Phase B
// 配套：docs/10-架构/面试题库设计.md / 4.2 学 tab

import React from "react";
import type { QuestionListItem } from "@/types/learn";
import MasteryBadge from "@/components/shared/MasteryBadge";

interface QuestionRowProps {
  question: QuestionListItem;
  /** 点击跳详情（Next router） */
  href?: string;
  onClick?: (q: QuestionListItem) => void;
  onToggleBookmark?: (q: QuestionListItem) => void;
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${m}-${day}`;
}

function DifficultyStars({ level }: { level: number }) {
  return (
    <span className="text-amber-400 text-xs tracking-tight" title={`难度 ${level}/5`}>
      {"⭐".repeat(level)}
      <span className="text-gray-600">{"⭐".repeat(5 - level)}</span>
    </span>
  );
}

export default function QuestionRow({
  question,
  href,
  onClick,
  onToggleBookmark,
}: QuestionRowProps) {
  const { id, topic, difficulty, question_text, progress } = question;
  const isBookmarked = progress?.bookmarked ?? false;
  const status = progress?.status ?? "new";
  const lastPracticed = progress?.last_practiced_at ?? null;

  const handleClick = (e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest(".row-action")) return;
    if (onClick) onClick(question);
    else if (href && typeof window !== "undefined") {
      window.location.href = href;
    }
  };

  return (
    <div
      onClick={handleClick}
      className="gradient-card rounded-lg px-4 py-3 mb-2 flex items-center gap-3 cursor-pointer hover:border-indigo-500/30 transition-all"
    >
      {/* 题号 */}
      <div className="text-xs text-gray-500 font-mono min-w-[3rem]">{id}</div>

      {/* 标题 */}
      <div className="text-sm font-medium text-gray-100 flex-1 truncate">{question_text}</div>

      {/* topic */}
      <div className="hidden md:inline-block px-2 py-0.5 rounded bg-gray-800 text-gray-400 text-xs">
        {topic}
      </div>

      {/* 难度 */}
      <DifficultyStars level={difficulty} />

      {/* 状态 */}
      <MasteryBadge status={status} />

      {/* 最后练习 */}
      <div className="text-xs text-gray-500 min-w-[3rem] text-right">
        {formatDate(lastPracticed)}
      </div>

      {/* 收藏 */}
      <button
        type="button"
        className="row-action px-2 py-1 text-sm hover:scale-110 transition-transform"
        onClick={(e) => {
          e.stopPropagation();
          onToggleBookmark?.(question);
        }}
        title={isBookmarked ? "取消收藏" : "收藏"}
      >
        {isBookmarked ? "⭐" : "☆"}
      </button>

      {/* 进入箭头 */}
      <div className="text-gray-500 text-sm">→</div>
    </div>
  );
}
