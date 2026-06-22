// AI 推送：每日项卡片
// 阶段 6.2 Phase B
// 配套：docs/10-架构/AI推送设计.md

import React from "react";
import type { DigestDailyItem } from "@/types/digest";
import CategoryBadge from "@/components/shared/CategoryBadge";
import QualityBadge from "@/components/shared/QualityBadge";

interface DailyCardProps {
  item: DigestDailyItem;
  /** 客户端状态 */
  read?: boolean;
  bookmarked?: boolean;
  /** 操作回调 */
  onToggleBookmark?: (item: DigestDailyItem) => void;
  onShare?: (item: DigestDailyItem) => void;
  onHide?: (item: DigestDailyItem) => void;
  onOpen?: (item: DigestDailyItem) => void;
  /** 链接 */
  href?: string;
  /** 隐藏操作（详情页用） */
  showActions?: boolean;
}

export default function DailyCard({
  item,
  read = false,
  bookmarked = false,
  onToggleBookmark,
  onShare,
  onHide,
  onOpen,
  href,
  showActions = true,
}: DailyCardProps) {
  const handleOpen = () => {
    if (href && typeof window !== "undefined") {
      window.open(href, "_blank", "noopener,noreferrer");
    }
    onOpen?.(item);
  };

  return (
    <div
      className={`
        gradient-card rounded-lg p-4 mb-2.5 transition-all duration-200
        ${read ? "opacity-50" : ""}
        ${onOpen || href ? "cursor-pointer hover:border-indigo-500/40" : ""}
      `}
      onClick={onOpen ? () => onOpen(item) : undefined}
    >
      {/* 头部：分类 + 质量分 + 标题 */}
      <div className="flex items-center gap-2 mb-2">
        <QualityBadge score={item.quality_score} />
        <CategoryBadge category={item.category} />
        <div className="text-sm font-semibold text-gray-100 flex-1 leading-snug">
          {item.title}
        </div>
      </div>

      {/* 摘要 */}
      {item.summary && (
        <div className="text-sm text-gray-300 leading-relaxed mb-3 pl-3 border-l-2 border-indigo-500/20">
          {item.summary}
        </div>
      )}

      {/* 底部：来源 + 时长 + 操作 */}
      <div className="flex items-center gap-3 text-xs text-gray-500 pt-2 border-t border-gray-700/50">
        <span>来源: {item.source_name}</span>
        <span>{item.estimated_minutes} 分钟</span>
        {read && <span className="text-green-400 ml-auto">✅ 已读</span>}

        {showActions && (
          <div className={`flex gap-1.5 ${read ? "" : "ml-auto"}`} onClick={(e) => e.stopPropagation()}>
            <button
              type="button"
              onClick={() => onToggleBookmark?.(item)}
              className={`
                px-2 py-1 rounded text-xs transition-colors
                ${bookmarked
                  ? "text-amber-400 border border-amber-500/40"
                  : "text-gray-400 border border-gray-700 hover:text-amber-400 hover:border-amber-500/40"
                }
              `}
              title={bookmarked ? "已收藏" : "收藏"}
            >
              {bookmarked ? "💾 已收藏" : "💾 收藏"}
            </button>
            <button
              type="button"
              onClick={() => onShare?.(item)}
              className="px-2 py-1 rounded text-xs text-gray-400 border border-gray-700 hover:text-gray-200 transition-colors"
              title="分享"
            >
              🔗
            </button>
            <button
              type="button"
              onClick={() => onHide?.(item)}
              className="px-2 py-1 rounded text-xs text-gray-400 border border-gray-700 hover:text-red-400 transition-colors"
              title="不再推类似"
            >
              🔇
            </button>
            {href && (
              <button
                type="button"
                onClick={handleOpen}
                className="px-2 py-1 rounded text-xs text-indigo-300 border border-indigo-500/30 hover:bg-indigo-500/10 transition-colors"
                title="打开原文"
              >
                🔗 原文
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
