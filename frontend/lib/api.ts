// frontend/lib/api.ts
// 阶段 6.1 Phase A 扩展：新增 AI 推送 + 学习复习 endpoint
// 配套：types/digest.ts + types/learn.ts

import type {
  DigestSource,
  DigestSourceInput,
  DigestDaily,
  DigestDailyItem,
  DigestWeekly,
  DigestMonthly,
  DigestBookmark,
  DigestReadInput,
  DigestReadResponse,
  DigestHideInput,
  DigestHideResponse,
  DigestSettings,
  DigestSettingsResponse,
  DigestStats,
} from "@/types/digest";
import type {
  QuestionListItem,
  QuestionDetail,
  QuestionListResponse,
  SubmitAnswerInput,
  SubmitAnswerResponse,
  UpdateProgressInput,
  UpdateProgressResponse,
  ProgressListResponse,
  RecommendResponse,
  ReviewQueueResponse,
  StartSessionInput,
  StartSessionResponse,
  EndSessionInput,
  EndSessionResponse,
  RecentSessionsResponse,
  StudyPlan,
  CreateStudyPlanInput,
  UpdateStudyPlanInput,
  StudyPlanProgressResponse,
  QASession,
  QASessionDetail,
  QASessionListResponse,
  QAChatInput,
  QAChatResponse,
  LearnStats,
} from "@/types/learn";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

let token: string | null = null;

export function setToken(t: string) {
  token = t;
  if (typeof window !== "undefined") {
    localStorage.setItem("codemock_token", t);
  }
}

export function getToken(): string | null {
  if (token) return token;
  if (typeof window !== "undefined") {
    token = localStorage.getItem("codemock_token");
  }
  return token;
}

async function request(path: string, options: RequestInit = {}): Promise<any> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> || {}),
  };
  const t = getToken();
  if (t) headers["Authorization"] = `Bearer ${t}`;

  const controller = new AbortController();
  // Use longer timeout: STT can take 10-20s on first model load, LLM 5-15s
  const isTranscribe = path.endsWith("/transcribe");
  const timeoutMs = isTranscribe ? 60000 : 30000;
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(`${BASE_URL}${path}`, {
      ...options,
      headers,
      signal: controller.signal,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  } finally {
    clearTimeout(timer);
  }
}

export function clearToken() {
  token = null;
  if (typeof window !== "undefined") {
    localStorage.removeItem("codemock_token");
  }
}

// Auth
export async function login(email: string, password: string) {
  const data = await request("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  if (data.access_token) setToken(data.access_token);
  return data;
}

export async function register(email: string, password: string, display_name: string) {
  const data = await request("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password, display_name }),
  });
  if (data.access_token) setToken(data.access_token);
  return data;
}

export async function getGitHubLoginUrl() {
  return request("/api/auth/github/url");
}

export async function handleGitHubCallback(code: string) {
  const data = await request(`/api/auth/github/callback?code=${code}`);
  if (data.access_token) {
    setToken(data.access_token);
  }
  return data;
}

export async function devLogin(username: string = "dev_user") {
  const data = await request(`/api/auth/dev-login?username=${encodeURIComponent(username)}`);
  if (data.access_token) {
    setToken(data.access_token);
  }
  return data;
}

// Profile
export async function getProfile() {
  return request("/api/profile/me");
}

export async function updateProfile(profile: Record<string, any>) {
  return request("/api/profile/me", { method: "PUT", body: JSON.stringify(profile) });
}

// Resume — upload a PDF, get back LLM-extracted fields for the user to review.
// Does NOT auto-save to the profile.
export async function uploadResume(file: File): Promise<{
  extracted: {
    tech_stack: string[];
    years_of_exp: number;
    current_level: "junior" | "mid" | "senior";
    skill_map: Record<string, number>;
    suggested_target_companies: string[];
  } | null;
  resume_text: string;
  page_count: number;
  is_scanned: boolean;
  file_name: string;
  file_size: number;
  warning: string | null;
}> {
  const form = new FormData();
  form.append("file", file);
  const t = getToken();
  const res = await fetch(`${BASE_URL}/api/profile/resume`, {
    method: "POST",
    headers: t ? { Authorization: `Bearer ${t}` } : {},
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function deleteResume() {
  return request("/api/profile/resume", { method: "DELETE" });
}

// Interview
export async function startInterview(round: string = "round1") {
  return request("/api/interviews", {
    method: "POST",
    body: JSON.stringify({ round, style: "standard" }),
  });
}

export async function getNextQuestion(interviewId: string) {
  return request(`/api/interviews/${interviewId}/next-question`, { method: "POST" });
}

export async function submitAnswer(recordId: string, userAnswer: string, timeSpent: number = 0) {
  return request(`/api/interviews/records/${recordId}/answer`, {
    method: "POST",
    body: JSON.stringify({ user_answer: userAnswer, time_spent: timeSpent }),
  });
}

// Report
export async function getReport(interviewId: string) {
  return request(`/api/reports/interview/${interviewId}`);
}

export async function generateReport(interviewId: string) {
  return request(`/api/reports/interview/${interviewId}`, { method: "POST" });
}

// =====================================================================
// ④ AI 推送（独立模块 · 阶段 4.2）
// =====================================================================

// === 日报 / 周报 / 月报 ===
export async function getTodayDigest(): Promise<DigestDaily & { items: DigestDailyItem[] }> {
  return request(`/api/digest/today`);
}

export async function getDailyDigest(date: string): Promise<DigestDaily & { items: DigestDailyItem[] }> {
  return request(`/api/digest/daily/${date}`);
}

export async function getWeeklyDigest(week: string): Promise<DigestWeekly> {
  return request(`/api/digest/weekly/${week}`);
}

export async function getMonthlyDigest(month: string): Promise<DigestMonthly> {
  return request(`/api/digest/monthly/${month}`);
}

export async function getRecentDailies(limit: number = 7): Promise<{ items: DigestDaily[] }> {
  return request(`/api/digest/dailies?limit=${limit}`);
}

// === 收藏 ===
export async function getBookmarks(): Promise<{ items: DigestBookmark[] }> {
  return request(`/api/digest/bookmarks`);
}

export async function addBookmark(item_id: string): Promise<DigestBookmark> {
  return request(`/api/digest/bookmarks`, {
    method: "POST",
    body: JSON.stringify({ item_id }),
  });
}

export async function removeBookmark(bookmark_id: string): Promise<void> {
  return request(`/api/digest/bookmarks/${bookmark_id}`, { method: "DELETE" });
}

// === 阅读 / 屏蔽 ===
export async function markRead(input: DigestReadInput): Promise<DigestReadResponse> {
  return request(`/api/digest/read`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function hideDigestItem(input: DigestHideInput): Promise<DigestHideResponse> {
  return request(`/api/digest/hide`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

// === 写回 Obsidian ===
export async function syncDigestToObsidian(date: string): Promise<{
  obsidian_path: string;
  synced_at: string;
  size_bytes: number;
}> {
  return request(`/api/digest/sync-to-obsidian`, {
    method: "POST",
    body: JSON.stringify({ date }),
  });
}

// === 信源管理 ===
export async function getDigestSources(): Promise<{ items: DigestSource[] }> {
  return request(`/api/digest/sources`);
}

export async function addDigestSource(input: DigestSourceInput): Promise<DigestSource> {
  return request(`/api/digest/sources`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function updateDigestSource(id: string, input: Partial<DigestSourceInput>): Promise<DigestSource> {
  return request(`/api/digest/sources/${id}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

// === 推送设置 ===
export async function getDigestSettings(): Promise<DigestSettings> {
  return request(`/api/digest/settings`);
}

export async function updateDigestSettings(settings: Partial<DigestSettings>): Promise<DigestSettingsResponse> {
  return request(`/api/digest/settings`, {
    method: "PATCH",
    body: JSON.stringify(settings),
  });
}

// === AI 推送统计 ===
export async function getDigestStats(): Promise<DigestStats> {
  return request(`/api/profile/digest-stats`);
}

// =====================================================================
// ② 学习复习（1 模块 3 tab · 阶段 4.1）
// =====================================================================

// === 学 tab：题目 ===
export async function listQuestions(filters: Partial<QuestionListFilter> = {}): Promise<QuestionListResponse> {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") params.append(k, String(v));
  });
  const qs = params.toString();
  return request(`/api/learn/questions${qs ? "?" + qs : ""}`);
}

export async function getQuestionDetail(qid: string): Promise<QuestionDetail> {
  return request(`/api/learn/questions/${qid}`);
}

export async function submitLearnAnswer(qid: string, input: SubmitAnswerInput): Promise<SubmitAnswerResponse> {
  return request(`/api/learn/questions/${qid}/answer`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function updateProgress(qid: string, input: UpdateProgressInput): Promise<UpdateProgressResponse> {
  return request(`/api/learn/progress/${qid}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export async function getMyProgress(filters: { status?: string; topic?: string } = {}): Promise<ProgressListResponse> {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([k, v]) => {
    if (v !== undefined && v !== null) params.append(k, String(v));
  });
  const qs = params.toString();
  return request(`/api/learn/progress${qs ? "?" + qs : ""}`);
}

export async function getRecommend(n: number = 3): Promise<RecommendResponse> {
  return request(`/api/learn/recommend?n=${n}`);
}

export async function getReviewQueue(): Promise<ReviewQueueResponse> {
  return request(`/api/learn/review-queue`);
}

// === 复习 tab：学习会话 ===
export async function startSession(input: StartSessionInput): Promise<StartSessionResponse> {
  return request(`/api/learning/sessions`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function endSession(session_id: string, input: EndSessionInput): Promise<EndSessionResponse> {
  return request(`/api/learning/sessions/${session_id}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export async function getRecentSessions(days: number = 7): Promise<RecentSessionsResponse> {
  return request(`/api/learning/sessions/recent?days=${days}`);
}

// === 复习 tab：学习计划 ===
export async function listPlans(): Promise<{ items: StudyPlan[] }> {
  return request(`/api/learning/plans`);
}

export async function createPlan(input: CreateStudyPlanInput): Promise<StudyPlan> {
  return request(`/api/learning/plans`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function updatePlan(plan_id: string, input: UpdateStudyPlanInput): Promise<StudyPlan> {
  return request(`/api/learning/plans/${plan_id}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export async function getPlanProgress(plan_id: string): Promise<StudyPlanProgressResponse> {
  return request(`/api/learning/plans/${plan_id}/progress`);
}

// === 问答 tab：AI 自由问答 ===
export async function listQASessions(): Promise<QASessionListResponse> {
  return request(`/api/qa/sessions`);
}

export async function getQASession(session_id: string): Promise<QASessionDetail> {
  return request(`/api/qa/sessions/${session_id}`);
}

export async function chatQA(input: QAChatInput): Promise<QAChatResponse> {
  return request(`/api/qa/chat`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

// === 学习统计 ===
export async function getLearnStats(): Promise<LearnStats> {
  return request(`/api/profile/learn-stats`);
}
