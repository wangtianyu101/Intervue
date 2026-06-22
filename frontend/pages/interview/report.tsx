/**
 * Interview Report — 面试报告页
 *
 * 从 history.tsx 跳转过来 (/interview/report?id=...)
 * 显示：interview 摘要 + 每题记录（含用户回答、分数、盲点）+ 雷达图（按 topic 聚合）
 */

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/router";
import { getToken } from "@/lib/api";
import RadarChart from "@/components/RadarChart";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Interview {
  id: string;
  round: string;
  style: string;
  status: string;
  started_at: string;
  ended_at: string | null;
  total_questions: number;
  overall_score: number | null;
}

interface QuestionRecord {
  id: string;
  question_id: string | null;
  question_text: string;
  user_answer: string | null;
  score: number | null;
  blind_spots: string[];
  time_spent: number;
  created_at: string;
}

// Map question_id prefix → topic used by the radar chart's LABEL_MAP.
// The chart only knows a fixed 11-key vocab; unknown topics bucket into
// "other" so the chart never crashes on unseen data.
const TOPIC_BY_PREFIX: Array<[string, string]> = [
  ["agent_", "agent_architecture"],
  ["java_", "java"],
  ["lang_", "langgraph"],
  ["rag_", "retrieval"],
  ["lc_", "langchain"],
];

function topicForQuestionId(qid: string | null): string | null {
  if (!qid) return null;
  for (const [prefix, topic] of TOPIC_BY_PREFIX) {
    if (qid.startsWith(prefix)) return topic;
  }
  return null;
}

const STATUS_BADGE: Record<string, string> = {
  completed: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
  in_progress: "bg-amber-500/20 text-amber-300 border-amber-500/30",
};

const SCORE_COLOR = (s: number) =>
  s >= 4 ? "text-emerald-400" : s >= 3 ? "text-amber-400" : "text-red-400";

function fmtDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("zh-CN", { hour12: false });
}

export default function InterviewReport() {
  const router = useRouter();
  const id = typeof router.query.id === "string" ? router.query.id : null;

  const [interview, setInterview] = useState<Interview | null>(null);
  const [records, setRecords] = useState<QuestionRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!id) return;
    if (!getToken()) { router.push("/"); return; }

    const h = { Authorization: `Bearer ${getToken()}` };
    Promise.all([
      fetch(`${API}/api/interviews/${id}`, { headers: h }).then((r) => {
        if (!r.ok) throw new Error(`GET /interviews/${id} → ${r.status}`);
        return r.json();
      }),
      fetch(`${API}/api/interviews/${id}/records`, { headers: h }).then((r) => {
        if (!r.ok) throw new Error(`GET /interviews/${id}/records → ${r.status}`);
        return r.json();
      }),
    ])
      .then(([iv, recs]) => {
        setInterview(iv);
        setRecords(recs);
        setLoading(false);
      })
      .catch((e) => {
        setError(String(e));
        setLoading(false);
      });
  }, [id, router]);

  // Aggregate scores by topic for the radar chart
  const radarData = useCallback(() => {
    const sums: Record<string, { total: number; count: number }> = {};
    for (const r of records) {
      if (r.score == null) continue;
      const topic = topicForQuestionId(r.question_id);
      if (!topic) continue;
      if (!sums[topic]) sums[topic] = { total: 0, count: 0 };
      sums[topic].total += r.score;
      sums[topic].count += 1;
    }
    const out: Record<string, number> = {};
    for (const [k, v] of Object.entries(sums)) {
      out[k] = v.total / v.count;
    }
    return out;
  }, [records]);

  // Aggregate blind spots — dedupe + count occurrences
  const blindSpotCounts = useCallback(() => {
    const m = new Map<string, number>();
    for (const r of records) {
      for (const bs of r.blind_spots || []) {
        if (!bs) continue;
        m.set(bs, (m.get(bs) || 0) + 1);
      }
    }
    return Array.from(m.entries()).sort((a, b) => b[1] - a[1]);
  }, [records]);

  if (loading) {
    return (
      <div className="min-h-screen bg-[#050914] text-[#f1f5f9] flex items-center justify-center">
        <div className="text-gray-400 animate-pulse">加载报告中...</div>
      </div>
    );
  }
  if (error) {
    return (
      <div className="min-h-screen bg-[#050914] text-[#f1f5f9] flex items-center justify-center">
        <div className="text-red-400 text-sm">{error}</div>
      </div>
    );
  }
  if (!interview) return null;

  const radar = radarData();
  const spots = blindSpotCounts();
  const answeredCount = records.filter((r) => r.user_answer).length;
  const score = interview.overall_score;

  return (
    <div className="min-h-screen bg-[#050914] text-[#f1f5f9]">
      {/* Top nav */}
      <nav className="sticky top-0 z-50 flex items-center gap-4 px-6 py-3.5 bg-[#0c1024]/90 backdrop-blur-xl border-b border-indigo-500/10">
        <button onClick={() => router.push("/interview/history")} className="text-gray-400 hover:text-white text-sm">
          ← 面试记录
        </button>
        <span className="text-lg font-bold bg-gradient-to-r from-indigo-400 to-purple-400 bg-clip-text text-transparent">
          面试报告
        </span>
        <div className="flex-1" />
        <span className={`text-xs px-3 py-1 rounded-full border ${STATUS_BADGE[interview.status] || "bg-gray-500/20 text-gray-300 border-gray-500/30"}`}>
          {interview.status === "completed" ? "已完成" : "进行中"}
        </span>
      </nav>

      <main className="max-w-5xl mx-auto px-6 py-8 space-y-6">
        {/* Summary card */}
        <section className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="md:col-span-2 bg-white/[0.03] backdrop-blur-xl border border-indigo-500/10 rounded-2xl p-6">
            <div className="text-xs text-gray-500 uppercase tracking-wider mb-2">综合得分</div>
            <div className="flex items-baseline gap-3">
              <div className={`text-5xl font-bold font-mono ${score != null ? SCORE_COLOR(score) : "text-gray-500"}`}>
                {score != null ? score.toFixed(1) : "—"}
              </div>
              <div className="text-sm text-gray-500">/ 5.0</div>
            </div>
            <div className="mt-4 grid grid-cols-3 gap-4 text-xs text-gray-400">
              <div>
                <div className="text-gray-500">轮次</div>
                <div className="text-gray-200 mt-1">{interview.round === "round2" ? "二轮" : "一轮"} · {interview.style}</div>
              </div>
              <div>
                <div className="text-gray-500">已答题数</div>
                <div className="text-gray-200 mt-1">{answeredCount} / {records.length}</div>
              </div>
              <div>
                <div className="text-gray-500">开始 / 结束</div>
                <div className="text-gray-200 mt-1">{fmtDate(interview.started_at).slice(5, 16)} → {fmtDate(interview.ended_at).slice(5, 16)}</div>
              </div>
            </div>
          </div>

          <div className="bg-white/[0.03] backdrop-blur-xl border border-indigo-500/10 rounded-2xl p-6">
            <div className="text-xs text-gray-500 uppercase tracking-wider mb-2">盲点</div>
            {spots.length === 0 ? (
              <div className="text-gray-500 text-sm">未检测到盲点</div>
            ) : (
              <ul className="space-y-1.5 text-sm text-gray-300 max-h-32 overflow-y-auto">
                {spots.slice(0, 5).map(([bs, n], i) => (
                  <li key={i} className="flex items-start gap-2">
                    <span className="text-amber-400 font-mono text-xs mt-0.5 shrink-0">×{n}</span>
                    <span className="line-clamp-2">{bs}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>

        {/* Radar chart (only if we have any scored topic data) */}
        {Object.keys(radar).length > 0 && (
          <section className="bg-white/[0.03] backdrop-blur-xl border border-indigo-500/10 rounded-2xl p-6">
            <div className="text-xs text-gray-500 uppercase tracking-wider mb-4">能力雷达</div>
            <RadarChart data={radar} />
          </section>
        )}

        {/* Per-question records */}
        <section>
          <div className="text-xs text-gray-500 uppercase tracking-wider mb-3 px-1">每题记录</div>
          {records.length === 0 ? (
            <div className="text-gray-500 text-sm bg-white/[0.02] border border-indigo-500/10 rounded-2xl p-8 text-center">
              暂无记录
            </div>
          ) : (
            <div className="space-y-3">
              {records.map((r, i) => (
                <article key={r.id} className="bg-white/[0.03] backdrop-blur-xl border border-indigo-500/10 rounded-2xl p-5">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="text-xs text-gray-500 font-mono">#{i + 1}</span>
                        {r.question_id && (
                          <span className="text-xs text-indigo-400 font-mono">{r.question_id}</span>
                        )}
                      </div>
                      <div className="text-sm text-gray-100">{r.question_text}</div>
                    </div>
                    {r.score != null && (
                      <div className={`text-2xl font-bold font-mono shrink-0 ${SCORE_COLOR(r.score)}`}>
                        {r.score}
                      </div>
                    )}
                  </div>

                  {r.user_answer && (
                    <div className="mt-4 pl-4 border-l-2 border-indigo-500/30">
                      <div className="text-xs text-gray-500 mb-1">你的回答</div>
                      <div className="text-sm text-gray-300 whitespace-pre-wrap">{r.user_answer}</div>
                    </div>
                  )}

                  {r.blind_spots && r.blind_spots.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {r.blind_spots.map((bs, j) => (
                        <span key={j} className="text-xs px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-300 border border-amber-500/20">
                          ⚠ {bs}
                        </span>
                      ))}
                    </div>
                  )}
                </article>
              ))}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
