import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import { getToken, clearToken } from "@/lib/api";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function InterviewHistory() {
  const router = useRouter();
  const [interviews, setInterviews] = useState<any[]>([]);
  const [filter, setFilter] = useState("all");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!getToken()) { router.push("/"); return; }
    fetch(`${API}/api/interviews?size=50`, { headers: { Authorization: `Bearer ${getToken()}` } })
      .then(r => r.json()).then(d => { setInterviews(d.items || []); setLoading(false); }).catch(() => setLoading(false));
  }, []);

  const filtered = filter === "all" ? interviews : interviews.filter(i => i.status === filter);
  const scoreColor = (s: number) => s >= 4 ? "text-emerald-400" : s >= 3 ? "text-amber-400" : "text-red-400";
  const scoreStars = (s: number) => s >= 4.5 ? "★★★★★" : s >= 3.5 ? "★★★★☆" : s >= 2.5 ? "★★★☆☆" : s >= 1.5 ? "★★☆☆☆" : "★☆☆☆☆";

  return (
    <div className="min-h-screen bg-[#050914] text-[#f1f5f9]">
      <nav className="sticky top-0 z-50 flex items-center gap-4 px-6 py-3.5 bg-[#0c1024]/90 backdrop-blur-xl border-b border-indigo-500/10">
        <button onClick={() => router.push("/dashboard")} className="text-gray-400 hover:text-white text-sm">← 仪表盘</button>
        <span className="text-lg font-bold bg-gradient-to-r from-indigo-400 to-purple-400 bg-clip-text text-transparent">面试练习</span>
        <div className="flex gap-1 ml-4">
          {[
            { label: "个人信息", href: "/interview/profile" },
            { label: "面试记录", href: "/interview/history", active: true },
            { label: "能力分析", href: "/interview/analytics" },
          ].map(t => (
            <button key={t.href} onClick={() => router.push(t.href)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${(t as any).active ? "bg-indigo-500/20 text-indigo-300" : "text-gray-400 hover:text-gray-200"}`}
            >{t.label}</button>
          ))}
        </div>
        <div className="flex-1" />
        <button onClick={() => router.push("/interview/setup")} className="px-5 py-2.5 rounded-xl font-medium text-sm bg-gradient-to-r from-indigo-500 to-purple-500 text-white shadow-lg shadow-purple-500/20 hover:opacity-90 transition-all">
          新面试
        </button>
      </nav>

      <main className="max-w-4xl mx-auto px-6 py-10">
        <h2 className="text-2xl font-bold mb-6">面试记录</h2>
        <div className="flex gap-3 mb-6 flex-wrap">
          {[{ k: "all", v: "全部" }, { k: "completed", v: "已完成" }, { k: "in_progress", v: "进行中" }].map(f => (
            <button key={f.k} onClick={() => setFilter(f.k)}
              className={`px-4 py-2 rounded-full text-xs font-medium border transition-all ${filter === f.k ? "bg-indigo-500/20 text-indigo-300 border-indigo-500/30" : "bg-white/[0.02] text-gray-400 border-gray-700/20 hover:border-indigo-500/20"}`}
            >{f.v}</button>
          ))}
        </div>

        {loading ? <div className="text-gray-400 text-center py-20">加载中...</div> : filtered.length === 0 ? (
          <div className="text-center py-20 text-gray-500">
            <div className="text-4xl mb-4">🎯</div>
            <p>还没有面试记录</p>
            <button onClick={() => router.push("/interview/setup")} className="mt-4 px-6 py-2.5 rounded-xl bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 hover:bg-indigo-500/30 transition-all text-sm">开始第一次面试</button>
          </div>
        ) : (
          <div className="space-y-3">
            {filtered.map(iv => (
              <div key={iv.id} onClick={() => router.push(`/interview/report?id=${iv.id}`)}
                className="bg-white/[0.03] backdrop-blur-xl border border-indigo-500/10 rounded-2xl p-5 flex items-center justify-between cursor-pointer hover:border-indigo-500/30 transition-all group"
              >
                <div className="flex items-center gap-5">
                  <span className="text-xs text-gray-500 font-mono min-w-[80px]">{iv.started_at?.slice(0, 10) || "-"}</span>
                  <div>
                    <div className="font-medium">{iv.round === "round2" ? "二轮" : "一轮"}面试 · {iv.style === "standard" ? "标准" : iv.style}</div>
                    <div className="text-xs text-gray-500 mt-1">{iv.total_questions || 0} 题 · 状态: {iv.status === "completed" ? "已完成" : "进行中"}</div>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  {iv.overall_score && <div className="text-center"><div className={`text-2xl font-bold font-mono ${scoreColor(iv.overall_score)}`}>{iv.overall_score}</div><div className={`text-xs ${scoreColor(iv.overall_score)}`}>{scoreStars(iv.overall_score)}</div></div>}
                  <span className="text-xs text-indigo-400 group-hover:translate-x-1 transition-transform">查看 →</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
