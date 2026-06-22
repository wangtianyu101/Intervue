// AI 推送模块（独立模块 · 阶段 4.2）
// 配套文档：docs/10-架构/AI推送设计.md

// ========== 信源 ==========
export interface DigestSource {
  id: string;
  name: string;
  url: string;
  category: string;            // 大模型 / 应用 / 论文
  enabled: boolean;
  last_fetched_at: string | null;  // ISO datetime
  last_item_count: number;
  created_at: string;
}

export interface DigestSourceInput {
  name: string;
  url: string;
  category: string;
  enabled: boolean;
}

// ========== 日报 ==========
export type DigestCategory = "头条" | "商业" | "论文" | "工程" | "观点";
export type DigestItemQuality = 1 | 2 | 3 | 4 | 5;

export interface DigestDailyItem {
  id: string;
  daily_id: string;
  rank: number;                 // 1-10
  category: DigestCategory;
  title: string;
  summary: string;              // LLM 3-5 行摘要
  quality_score: DigestItemQuality;
  source_name: string;
  source_url: string;
  estimated_minutes: number;    // 1-5
  created_at: string;
  // 客户端派生字段
  read?: boolean;               // 本地缓存是否已读
  bookmarked?: boolean;         // 本地缓存是否已收藏
}

export interface DigestDaily {
  id: string;
  user_id: string;
  date: string;                 // YYYY-MM-DD
  title: string;                // "AI 日报 2026-06-22"
  intro: string;                // LLM 生成的简短引言
  item_ids: string[];
  pushed_at: string | null;
  created_at: string;
  // 客户端派生
  items?: DigestDailyItem[];    // 展开后的完整内容
  read_count?: number;
  total_count?: number;
}

// ========== 周报 / 月报 ==========
export interface DigestWeekly {
  id: string;
  user_id: string;
  year: number;
  week: number;                 // ISO 周数 (1-53)
  title: string;                // "AI 周报 2026-W25"
  top5_events: DigestWeeklyEvent[];
  trends: string[];             // 3 个趋势
  outlook: string;              // 下周展望
  item_ids: string[];
  created_at: string;
}

export interface DigestWeeklyEvent {
  rank: number;                 // 1-5
  title: string;
  quality_score: DigestItemQuality;
  category: DigestCategory;
  summary: string;
}

export interface DigestMonthly {
  id: string;
  user_id: string;
  year: number;
  month: number;                // 1-12
  title: string;
  top3_events: DigestWeeklyEvent[];
  trends: string[];
  paper_summaries: DigestPaper[];
  created_at: string;
}

export interface DigestPaper {
  arxiv_id: string;
  title: string;
  summary: string;
  url: string;
}

// ========== 互动 ==========
export type DigestHideReason = "not_interested" | "low_quality" | "already_seen";

export interface DigestReadInput {
  item_id: string;
  duration_sec: number;
}

export interface DigestReadResponse {
  item_id: string;
  read_at: string;
  duration_sec: number;
  progress: string;             // "5/10"
}

export interface DigestHideInput {
  item_id: string;
  reason: DigestHideReason;
}

export interface DigestHideResponse {
  hide_id: string;
  topic_keywords: string[];
  expires_at: string;
  message: string;
}

export interface DigestBookmark {
  id: string;
  user_id: string;
  item_id: string;
  created_at: string;
  // 展开字段
  item?: DigestDailyItem;
}

// ========== 推送设置 ==========
export interface DigestSettings {
  push_hour: number;             // 0-23
  push_minute: number;          // 0-59
  channels: {
    in_app: boolean;
    email: boolean;
    macos: boolean;
  };
  frequency: {
    daily: boolean;
    weekly: boolean;
    monthly: boolean;
    weekend_pause: boolean;
  };
  interested_tags: string[];
  blocked_tags: string[];
  daily_count: 5 | 10 | 20;
  timezone: string;              // e.g. "Asia/Shanghai"
}

export interface DigestSettingsResponse {
  updated_at: string;
  next_push: string;            // 下次推送时间
}

// ========== 统计 ==========
export interface DigestStats {
  total_reads: number;
  total_bookmarks: number;
  total_minutes: number;
  last_pushed_at: string | null;
  streak_days: number;          // 连续推送天数
}
