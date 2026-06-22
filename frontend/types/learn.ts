// 学习复习模块（1 模块 3 tab · 阶段 4.1）
// 配套文档：docs/10-架构/面试题库设计.md

// ========== 题目 / 进度 ==========
export type MasteryStatus = "new" | "learning" | "mastered" | "skipped";
export type QuestionSource = "seed" | "user_note" | "news" | "mock_interview";
export type RecommendReason = "weak_spot" | "due_review" | "untouched" | "bookmark" | "random";

export interface Question {
  id: string;
  topic: string;
  sub_topic: string;
  difficulty: number;            // 1-5
  question_text: string;
  answer_key_points: string[];
  followup_tree: Record<string, any>;
  source: QuestionSource;
  tags: string[];
}

export interface QuestionListItem {
  id: string;
  topic: string;
  sub_topic: string;
  difficulty: number;
  question_text: string;
  source: QuestionSource;
  progress: QuestionProgress | null;
}

export interface QuestionDetail {
  id: string;
  topic: string;
  sub_topic: string;
  difficulty: number;
  question_text: string;
  answer_key_points: string[];
  followup_tree: Record<string, any>;
  source: QuestionSource;
  tags: string[];
  progress: QuestionProgress | null;
  related_notes: RelatedNote[];
}

export interface RelatedNote {
  path: string;
  title: string;
}

export interface QuestionProgress {
  id: string;
  user_id: string;
  question_id: string;
  status: MasteryStatus;
  practice_count: number;
  correct_count: number;
  bookmarked: boolean;
  source: QuestionSource | null;
  last_review_at: string | null;
  next_review_at: string | null;
  review_count: number;
  ease_factor: number;          // SM-2 (默认 2.5)
  interval_days: number;
  first_practiced_at: string | null;
  last_practiced_at: string | null;
  user_answer: string | null;
  notes_path: string | null;
  created_at: string;
  updated_at: string;
}

export interface QuestionListFilter {
  topic?: string;
  difficulty?: number;
  status?: MasteryStatus;
  source?: QuestionSource;
  bookmarked?: boolean;
  q?: string;                   // 关键词搜索
  sort?: "id" | "difficulty" | "last_practiced" | "random";
  page?: number;
  size?: number;
}

export interface QuestionListResponse {
  items: QuestionListItem[];
  total: number;
  page: number;
  size: number;
}

// ========== 答题 ==========
export interface SubmitAnswerInput {
  user_answer: string;
  time_spent_sec: number;
  session_id?: string;
}

export interface SubmitAnswerResponse {
  score: number;                // 1-5
  feedback: string;
  blind_spots: string[];
  progress: {
    status: MasteryStatus;
    practice_count: number;
    correct_count: number;
    review_count: number;
    next_review_at: string | null;
  };
  srs: {
    previous_interval_days: number;
    new_interval_days: number;
    ease_factor: number;
  };
}

export interface UpdateProgressInput {
  status?: MasteryStatus;
  is_bookmarked?: boolean;
}

export interface UpdateProgressResponse {
  qid: string;
  status: MasteryStatus;
  is_bookmarked: boolean;
  updated_at: string;
}

export interface ProgressListResponse {
  items: Array<{
    qid: string;
    topic: string;
    difficulty: number;
    status: MasteryStatus;
    practice_count: number;
    correct_count: number;
    next_review_at: string | null;
    is_bookmarked: boolean;
    source: QuestionSource;
  }>;
  summary: {
    total: number;
    by_status: Record<MasteryStatus, number>;
  };
}

// ========== 推荐 / 复习队列 ==========
export interface RecommendItem {
  qid: string;
  topic: string;
  difficulty: number;
  reason: RecommendReason;
  reason_detail: string;
}

export interface RecommendResponse {
  items: RecommendItem[];
}

export interface ReviewQueueItem {
  qid: string;
  topic: string;
  next_review_at: string;
  review_count: number;
  interval_days: number;
}

export interface ReviewQueueResponse {
  items: ReviewQueueItem[];
  count: number;
}

// ========== 学习会话 ==========
export type SessionType = "practice" | "review" | "mock_interview";

export interface StartSessionInput {
  type: SessionType;
  planned_items: string[];
}

export interface StartSessionResponse {
  id: string;
  user_id: string;
  type: SessionType;
  started_at: string;
  duration_sec: number;
}

export interface EndSessionInput {
  ended_at: string;             // ISO datetime
  items: Array<{
    kind: "question" | "note";
    qid?: string;
    path?: string;
    score?: number;
  }>;
}

export interface EndSessionResponse {
  id: string;
  duration_sec: number;
  items_count: number;
}

export interface RecentSession {
  id: string;
  type: SessionType;
  started_at: string;
  duration_sec: number;
  items_count: number;
}

export interface RecentSessionsResponse {
  items: RecentSession[];
  summary: {
    total_sessions: number;
    total_minutes: number;
    by_type: Record<SessionType, number>;
  };
}

// ========== 学习计划 ==========
export interface StudyPlan {
  id: string;
  user_id: string;
  name: string;
  description: string | null;
  goal: string | null;
  start_date: string;
  end_date: string;
  status: "active" | "completed" | "abandoned";
  weekly_target: Array<{
    week: number;
    questions: string[];
    notes: string[];
  }>;
  progress: {
    completed_questions: number;
    total_questions: number;
    percent: number;
  };
  created_at: string;
  updated_at: string;
}

export interface CreateStudyPlanInput {
  name: string;
  description?: string;
  goal?: string;
  start_date: string;
  end_date: string;
  weekly_target: StudyPlan["weekly_target"];
}

export interface UpdateStudyPlanInput {
  name?: string;
  description?: string;
  status?: StudyPlan["status"];
  weekly_target?: StudyPlan["weekly_target"];
}

export interface StudyPlanProgressResponse {
  plan_id: string;
  by_week: Array<{
    week: number;
    target_questions: string[];
    completed_questions: string[];
    percent: number;
  }>;
  overall: {
    completed: number;
    total: number;
    percent: number;
    days_remaining: number;
  };
}

// ========== AI 问答 ==========
export interface QAMessage {
  id: string;
  role: "user" | "ai";
  content: string;
  citations?: Array<{
    type: "question" | "wrong_question";
    id: string;
    title: string;
  }>;
  created_at: string;
}

export interface QASession {
  id: string;
  user_id: string;
  title: string;                // 第一条消息的摘要
  message_count: number;
  created_at: string;
  last_message_at: string;
}

export interface QASessionDetail extends QASession {
  messages: QAMessage[];
}

export interface QASessionListResponse {
  items: QASession[];
}

export interface QAChatInput {
  session_id?: string;           // 不传则新建会话
  question: string;
}

export interface QAChatResponse {
  session_id: string;
  user_message: QAMessage;
  ai_message: QAMessage;
}

// ========== 学习统计 ==========
export interface LearnStats {
  total_questions_attempted: number;
  by_status: Record<MasteryStatus, number>;
  by_topic: Record<string, number>;
  due_today: number;            // 今日到期复习
  due_this_week: number;
  streak_days: number;          // 连续学习天数
  total_minutes: number;
}

// ========== 通用 API 错误 ==========
export interface ApiError {
  detail: string;
  code?: string;
}
