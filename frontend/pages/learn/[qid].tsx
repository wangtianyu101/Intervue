/**
 * Learn 题目详情页
 *
 * 路由: /learn/[qid]
 * 功能: 显示题目详情 + 答题 + 收藏 + 笔记编辑
 *
 * 数据源: GET /api/learn/questions/{qid} (含 progress + note + tags)
 * 操作:
 *   - POST /api/learn/questions/{qid}/answer → 触发 SM-2
 *   - PATCH /api/learn/progress/{qid} → 切收藏
 *   - PUT /api/learn/questions/{qid}/note → 写笔记
 */

import React, { useEffect, useState, useRef, useCallback } from "react";
import { useRouter } from "next/router";
import { getToken } from "@/lib/api";
import MasteryBadge from "@/components/shared/MasteryBadge";
import ProgressBar from "@/components/shared/ProgressBar";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface ProgressData {
  id: string;
  status: "new" | "learning" | "mastered" | "skipped";
  practice_count: number;
  correct_count: number;
  bookmarked: boolean;
  ease_factor: number;
  interval_days: number;
  next_review_at: string | null;
  last_practiced_at: string | null;
  user_answer: string | null;
  notes_path: string | null;
}

interface NoteData {
  id: string;
  content_md: string;
  updated_at: string | null;
}

interface QuestionData {
  id: string;
  topic: string;
  sub_topic: string;
  difficulty: number;
  question_text: string;
  answer_key_points: string[];
  followup_tree: Record<string, any>;
  source: "seed" | "user_note" | "news" | "mock_interview";
  tags: string[];
  progress: ProgressData | null;
  note: NoteData | null;
}

const SCORE_OPTIONS = [
  { score: 0, label: "完全不会", color: "from-red-600 to-red-700" },
  { score: 1, label: "模糊", color: "from-orange-600 to-orange-700" },
  { score: 2, label: "差", color: "from-amber-600 to-amber-700" },
  { score: 3, label: "及格", color: "from-yellow-600 to-yellow-700" },
  { score: 4, label: "良好", color: "from-emerald-600 to-emerald-700" },
  { score: 5, label: "完美", color: "from-green-500 to-emerald-500" },
];

export default function QuestionDetailPage() {
  const router = useRouter();
  const { qid } = router.query;
  const [q, setQ] = useState<QuestionData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 答题状态
  const [userAnswer, setUserAnswer] = useState("");
  const [showHint, setShowHint] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitResult, setSubmitResult] = useState<{
    progress: ProgressData;
    review_queue_remaining: number;
  } | null>(null);
  const [startTime, setStartTime] = useState<number>(0);

  // 笔记
  const [noteEditing, setNoteEditing] = useState(false);
  const [noteDraft, setNoteDraft] = useState("");
  const [noteSaving, setNoteSaving] = useState(false);

  const initRef = useRef(false);

  const fetchQuestion = useCallback(async () => {
    if (!qid || typeof qid !== "string") return;
    setLoading(true);
    setError(null);
    try {
      const r = await fetch(`${API}/api/learn/questions/${encodeURIComponent(qid)}`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (!r.ok) {
        if (r.status === 404) {
          throw new Error("题目不存在或已被删除");
        }
        throw new Error(`HTTP ${r.status}`);
      }
      const d = await r.json();
      setQ(d);
      setNoteDraft(d.note?.content_md || "");
      setStartTime(Date.now());
    } catch (e: any) {
      setError(e.message || "加载失败");
    }
    setLoading(false);
  }, [qid]);

  useEffect(() => {
    if (initRef.current) return;
    initRef.current = true;
    if (!getToken()) {
      router.push("/");
      return;
    }
  }, []);

  useEffect(() => {
    if (qid) fetchQuestion();
  }, [qid, fetchQuestion]);

  // 提交答题 (D5: 面试里也会调, /learn 这里 source='practice')
  async function submitAnswer(score: number) {
    if (!q || submitting) return;
    setSubmitting(true);
    try {
      const duration = Math.floor((Date.now() - startTime) / 1000);
      const r = await fetch(
        `${API}/api/learn/questions/${encodeURIComponent(q.id)}/answer`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${getToken()}`,
          },
          body: JSON.stringify({
            user_answer: userAnswer || "(未作答)",
            score,
            blind_spots: [],
            duration_sec: duration,
            source: "practice",
          }),
        }
      );
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      setSubmitResult(d);
      // 重新拉详情更新 progress
      await fetchQuestion();
    } catch (e: any) {
      setError(e.message || "提交失败");
    }
    setSubmitting(false);
  }

  // 切收藏
  async function toggleBookmark() {
    if (!q) return;
    const newVal = !q.progress?.bookmarked;
    try {
      await fetch(`${API}/api/learn/progress/${encodeURIComponent(q.id)}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify({ bookmarked: newVal }),
      });
      // 乐观更新
      setQ((prev) =>
        prev
          ? {
              ...prev,
              progress: prev.progress
                ? { ...prev.progress, bookmarked: newVal }
                : {
                    id: "new",
                    status: "new",
                    practice_count: 0,
                    correct_count: 0,
                    bookmarked: newVal,
                    ease_factor: 2.5,
                    interval_days: 0,
                    next_review_at: null,
                    last_practiced_at: null,
                    user_answer: null,
                    notes_path: null,
                  },
            }
          : prev
      );
    } catch (e: any) {
      setError(e.message || "切收藏失败");
    }
  }

  // 保存笔记
  async function saveNote() {
    if (!q) return;
    setNoteSaving(true);
    try {
      await fetch(
        `${API}/api/learn/questions/${encodeURIComponent(q.id)}/note`,
        {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${getToken()}`,
          },
          body: JSON.stringify({ content_md: noteDraft }),
        }
      );
      setQ((prev) =>
        prev
          ? {
              ...prev,
              note: {
                id: prev.note?.id || "new",
                content_md: noteDraft,
                updated_at: new Date().toISOString(),
              },
            }
          : prev
      );
      setNoteEditing(false);
    } catch (e: any) {
      setError(e.message || "保存笔记失败");
    }
    setNoteSaving(false);
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-[#0a0a1a] via-[#0f0f2e] to-[#1a0a2e] text-white flex items-center justify-center">
        <div className="inline-block w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mr-3" />
        加载题目…
      </div>
    );
  }

  if (error && !q) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-[#0a0a1a] via-[#0f0f2e] to-[#1a0a2e] text-white">
        <main className="max-w-3xl mx-auto px-6 py-12 text-center">
          <div className="text-6xl mb-4">😢</div>
          <h1 className="text-2xl font-bold mb-2">{error}</h1>
          <button
            onClick={() => router.push("/learn")}
            className="mt-6 px-4 py-2 rounded-xl bg-gradient-to-r from-indigo-500 to-purple-500 text-sm font-medium"
          >
            ← 返回题库
          </button>
        </main>
      </div>
    );
  }

  if (!q) return null;

  const accuracy = q.progress && q.progress.practice_count > 0
    ? Math.round((q.progress.correct_count / q.progress.practice_count) * 100)
    : 0;

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#0a0a1a] via-[#0f0f2e] to-[#1a0a2e] text-white">
      <main className="max-w-4xl mx-auto px-6 py-8">
        {/* Top bar */}
        <div className="flex items-center justify-between mb-6">
          <button
            onClick={() => router.push("/learn")}
            className="text-sm text-gray-400 hover:text-indigo-300 transition-colors"
          >
            ← 返回题库
          </button>
          <div className="flex items-center gap-2">
            {q.progress && <MasteryBadge status={q.progress.status} />}
            <button
              onClick={toggleBookmark}
              className={`px-3 py-1.5 rounded-lg text-xs transition-all ${
                q.progress?.bookmarked
                  ? "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                  : "bg-white/[0.04] text-gray-400 hover:bg-white/[0.08]"
              }`}
            >
              {q.progress?.bookmarked ? "★ 已收藏" : "☆ 收藏"}
            </button>
          </div>
        </div>

        {/* Question card */}
        <div className="gradient-card rounded-2xl p-6 mb-6">
          <div className="flex items-center gap-2 mb-3 text-xs">
            <span className="px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300">
              {q.topic}
            </span>
            {q.sub_topic && (
              <span className="px-2 py-0.5 rounded bg-white/[0.04] text-gray-400">
                {q.sub_topic}
              </span>
            )}
            <span className="text-amber-400">
              {"⭐".repeat(q.difficulty)}
              <span className="text-gray-600">{"⭐".repeat(5 - q.difficulty)}</span>
            </span>
            <span className="px-2 py-0.5 rounded bg-purple-500/20 text-purple-300 ml-auto">
              {q.source}
            </span>
          </div>
          <div className="text-base leading-relaxed text-gray-100 whitespace-pre-wrap">
            {q.question_text}
          </div>
          {q.tags.length > 0 && (
            <div className="flex gap-1.5 mt-4 pt-4 border-t border-white/[0.04]">
              {q.tags.map((t) => (
                <span
                  key={t}
                  className="px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-300 text-xs"
                >
                  #{t}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Progress section */}
        {q.progress && (
          <div className="gradient-card rounded-2xl p-5 mb-6">
            <div className="grid grid-cols-4 gap-4 text-center">
              <div>
                <div className="text-2xl font-bold font-mono">{q.progress.practice_count}</div>
                <div className="text-xs text-gray-500 mt-1">练习次数</div>
              </div>
              <div>
                <div className="text-2xl font-bold font-mono">{accuracy}%</div>
                <div className="text-xs text-gray-500 mt-1">准确率</div>
              </div>
              <div>
                <div className="text-2xl font-bold font-mono">{q.progress.ease_factor.toFixed(2)}</div>
                <div className="text-xs text-gray-500 mt-1">Ease</div>
              </div>
              <div>
                <div className="text-2xl font-bold font-mono">{q.progress.interval_days}d</div>
                <div className="text-xs text-gray-500 mt-1">下次间隔</div>
              </div>
            </div>
            {q.progress.practice_count > 0 && (
              <div className="mt-4">
                <ProgressBar
                  current={q.progress.correct_count}
                  total={q.progress.practice_count}
                  variant="success"
                  prefix="准确率"
                  showPercent
                />
              </div>
            )}
          </div>
        )}

        {/* Answer section */}
        <div className="gradient-card rounded-2xl p-5 mb-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-gray-300">你的回答</h3>
            <button
              onClick={() => setShowHint(!showHint)}
              className="text-xs text-gray-400 hover:text-indigo-300"
            >
              {showHint ? "隐藏提示" : "💡 看要点"}
            </button>
          </div>
          <textarea
            value={userAnswer}
            onChange={(e) => setUserAnswer(e.target.value)}
            rows={6}
            placeholder="写下你的回答…"
            className="w-full bg-transparent border border-gray-700/30 rounded-lg p-3 outline-none resize-none text-sm text-white placeholder-gray-500 focus:border-indigo-500 transition-colors"
          />
          <div className="text-xs text-gray-500 text-right mt-1">{userAnswer.length} 字</div>
          {showHint && q.answer_key_points?.length > 0 && (
            <div className="mt-3 p-3 bg-amber-500/[0.06] border border-amber-500/20 rounded-lg text-xs text-amber-200">
              <div className="font-medium mb-1">要点：</div>
              <ul className="list-disc list-inside space-y-1">
                {q.answer_key_points.map((p, i) => <li key={i}>{p}</li>)}
              </ul>
            </div>
          )}
        </div>

        {/* Self-eval */}
        <div className="grid grid-cols-6 gap-2 mb-2">
          {SCORE_OPTIONS.map((s) => (
            <button
              key={s.score}
              onClick={() => submitAnswer(s.score)}
              disabled={submitting}
              className={`px-3 py-3 rounded-xl bg-gradient-to-r ${s.color} text-xs font-medium disabled:opacity-30 hover:opacity-90 transition-all`}
            >
              {s.label}
            </button>
          ))}
        </div>
        <p className="text-xs text-gray-500 text-center mb-6">
          自我评估 0-5 分 · 后端 SM-2 重算下次复习
        </p>

        {/* Submit result */}
        {submitResult && (
          <div className="gradient-card rounded-2xl p-4 mb-6 border-l-4 border-emerald-500">
            <div className="text-sm font-semibold text-emerald-300 mb-1">
              ✓ 已记录 · 复习队列剩余 {submitResult.review_queue_remaining} 题
            </div>
            <div className="text-xs text-gray-400">
              下次复习:{" "}
              {submitResult.progress.next_review_at
                ? new Date(submitResult.progress.next_review_at).toLocaleString("zh-CN")
                : "—"}
            </div>
          </div>
        )}

        {/* Note section */}
        <div className="gradient-card rounded-2xl p-5 mb-6">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-gray-300">📝 我的笔记</h3>
            {!noteEditing && (
              <button
                onClick={() => setNoteEditing(true)}
                className="text-xs text-indigo-400 hover:text-indigo-300"
              >
                {q.note ? "编辑" : "写笔记"}
              </button>
            )}
          </div>
          {noteEditing ? (
            <>
              <textarea
                value={noteDraft}
                onChange={(e) => setNoteDraft(e.target.value)}
                rows={6}
                placeholder="Markdown 笔记… (# 标题, **粗体**, - 列表)"
                className="w-full bg-transparent border border-gray-700/30 rounded-lg p-3 outline-none resize-none text-sm text-white placeholder-gray-500 focus:border-indigo-500 font-mono"
              />
              <div className="flex justify-end gap-2 mt-2">
                <button
                  onClick={() => {
                    setNoteDraft(q.note?.content_md || "");
                    setNoteEditing(false);
                  }}
                  className="px-3 py-1.5 rounded-lg bg-white/[0.04] hover:bg-white/[0.08] text-xs"
                >
                  取消
                </button>
                <button
                  onClick={saveNote}
                  disabled={noteSaving}
                  className="px-3 py-1.5 rounded-lg bg-gradient-to-r from-indigo-500 to-purple-500 text-xs font-medium disabled:opacity-30"
                >
                  {noteSaving ? "保存中…" : "保存"}
                </button>
              </div>
            </>
          ) : (
            <div className="text-sm text-gray-300 whitespace-pre-wrap font-mono">
              {q.note?.content_md || (
                <span className="text-gray-500 italic">还没有笔记</span>
              )}
              {q.note?.updated_at && (
                <div className="text-xs text-gray-500 mt-2">
                  更新于 {new Date(q.note.updated_at).toLocaleString("zh-CN")}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Error banner */}
        {error && (
          <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-300 text-xs mb-4">
            ❌ {error}
          </div>
        )}

        {/* Followup tree (debug only) */}
        {Object.keys(q.followup_tree || {}).length > 0 && (
          <details className="gradient-card rounded-2xl p-5 mb-6">
            <summary className="text-sm font-semibold text-gray-300 cursor-pointer">
              🔍 追问树 (调试)
            </summary>
            <pre className="text-xs text-gray-400 mt-3 overflow-auto">
              {JSON.stringify(q.followup_tree, null, 2)}
            </pre>
          </details>
        )}
      </main>
    </div>
  );
}