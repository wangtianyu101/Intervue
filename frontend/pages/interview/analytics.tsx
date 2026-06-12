import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import { getToken } from "@/lib/api";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Simple SVG radar chart component
function RadarSVG({ data }: { data: any[] }) {
  if (!data || data.length === 0) return <div className="text-gray-500 text-center py-8">完成面试后查看雷达图</div>;
  const n = data.length;
  const cx = 150, cy = 140, r = 100;
  const levels = [0.8, 0.6, 0.4, 0.2];
  const toXY = (i: number, val: number) => {
    const angle = (i / n) * Math.PI * 2 - Math.PI / 2;
    return { x: cx + r * val * Math.cos(angle), y: cy + r * val * Math.sin(angle) };
  };
  const pts = data.map((d, i) => toXY(i, d.score / 5));
  const prevPts = data.map((d, i) => toXY(i, (d.first || d.score) / 5));
  return (
    <div className="flex flex-col items-center">
      <svg viewBox="0 0 300 300" className="max-w-[320px] w-full">
        {levels.map(l => {
          const poly = data.map((_, i) => toXY(i, l)).map(p => `${p.x},${p.y}`).join(" ");
          return <polygon key={l} points={poly} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="1" />;
        })}
        {data.map((_, i) => {
          const { x, y } = toXY(i, 1.05);
          return <text key={i} x={x} y={y} fill="#94a3b8" fontSize="10" textAnchor="middle" dominantBaseline="middle">{data[i].label}</text>;
        })}
        {prevPts.length > 0 && <polygon points={prevPts.map(p => `${p.x},${p.y}`).join(" ")} fill="rgba(245,158,11,0.06)" stroke="#f59e0b" strokeWidth="1.2" strokeDasharray="4,3" />}
        <polygon points={pts.map(p => `${p.x},${p.y}`).join(" ")} fill="rgba(99,102,241,0.15)" stroke="#6366f1" strokeWidth="1.8" />
        {pts.map((p, i) => <circle key={i} cx={p.x} cy={p.y} r="3" fill="#a78bfa" />)}
      </svg>
      <div className="flex gap-4 text-xs text-gray-500 mt-2">
        <span><span className="inline-block w-3 h-0.5 bg-amber-500 align-middle mr-1 rounded" />首次</span>
        <span><span className="inline-block w-3 h-0.5 bg-indigo-500 align-middle mr-1 rounded" />当前</span>
      </div>
    </div>
  );
}

export default function InterviewAnalytics() {
  const router = useRouter();
  const [overview, setOverview] = useState<any>(null);
  const [radar, setRadar] = useState<any[]>([]);
  const [trends, setTrends] = useState<any[]>([]);
  const [recs, setRecs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!getToken()) { router.push("/"); return; }
    const h = { Authorization: `Bearer ${getToken()}` };
    Promise.all([
      fetch(`${API}/api/analytics/overview`, { headers: h }).then(r => r.json()),
      fetch(`${API}/api/analytics/radar`, { headers: h }).then(r => r.json()),
      fetch(`${API}/api/analytics/trends`, { headers: h }).then(r => r.json()),
      fetch(`${API}/api/analytics/recommendations`, { headers: h }).then(r => r.json()),
    ]).then(([ov, rd, tr, rc]) => {
      setOverview(ov); setRadar(rd.radar || []); setTrends(tr.topic_deltas || []); setRecs(rc.recommendations || []); setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  return (
    <div className="min-h-screen bg-[#050914] text-[#f1f5f9]">
      <nav className="sticky top-0 z-50 flex items-center gap-4 px-6 py-3.5 bg-[#0c1024]/90 backdrop-blur-xl border-b border-indigo-500/10">
        <button onClick={() => router.push("/dashboard")} className="text-gray-400 hover:text-white text-sm">← 仪表盘</button>
        <span className="text-lg font-bold bg-gradient-to-r from-indigo-400 to-purple-400 bg-clip-text text-transparent">面试练习</span>
        <div className="flex gap-1 ml-4">
          {[{ label: "个人信息", href: "/interview/profile" }, { label: "面试记录", href: "/interview/history" }, { label: "能力分析", href: "/interview/analytics", active: true }].map(t => (
            <button key={t.href} onClick={() => router.push(t.href)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${(t as any).active ? "bg-indigo-500/20 text-indigo-300" : "text-gray-400 hover:text-gray-200"}`}
            >{t.label}</button>
          ))}
        </div>
      </nav>

      {loading ? <div className="flex items-center justify-center py-40 text-gray-400">加载中...</div> : (
        <main className="max-w-5xl mx-auto px-6 py-10">
          <h2 className="text-2xl font-bold mb-8">能力分析</h2>

          {/* Stat cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
            {[
              { v: overview?.overall_score || "-", l: "综合得分", c: "text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-purple-400" },
              { v: overview?.score_trend === "up" ? `+0.4` : overview?.score_trend === "down" ? "-0.2" : "—", l: "较上次", c: overview?.score_trend === "up" ? "text-emerald-400" : "text-gray-400" },
              { v: overview?.total_interviews || 0, l: "面试次数", c: "text-indigo-400" },
              { v: overview?.weak_topics?.length || 0, l: "薄弱项", c: "text-amber-400" },
            ].map(s => (
              <div key={s.l} className="bg-white/[0.03] backdrop-blur-xl border border-indigo-500/10 rounded-2xl p-6 text-center">
                <div className={`text-3xl font-bold font-mono ${s.c}`}>{s.v}</div>
                <div className="text-xs text-gray-500 mt-1.5">{s.l}</div>
              </div>
            ))}
          </div>

          {/* Radar + Trends */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5 mb-6">
            <div className="bg-white/[0.03] backdrop-blur-xl border border-indigo-500/10 rounded-2xl p-7">
              <h3 className="text-base font-semibold mb-4">能力雷达图</h3>
              <RadarSVG data={radar} />
            </div>
            <div className="bg-white/[0.03] backdrop-blur-xl border border-indigo-500/10 rounded-2xl p-7">
              <h3 className="text-base font-semibold mb-5">薄弱项趋势</h3>
              {trends.length === 0 ? <div className="text-gray-500 text-sm py-8 text-center">完成 2 次面试后查看趋势</div> : trends.map(t => (
                <div key={t.topic} className="flex items-center gap-3 py-2.5 hover:bg-white/[0.02] rounded-lg px-2 transition-colors">
                  <span className="text-sm text-gray-400 w-20 flex-shrink-0">{t.label}</span>
                  <div className="flex-1 h-1.5 bg-white/[0.04] rounded-full overflow-hidden">
                    <div className={`h-full rounded-full ${t.latest_score >= 4 ? "bg-emerald-500" : t.latest_score >= 3 ? "bg-amber-500" : "bg-red-500"}`}
                      style={{ width: `${Math.min((t.latest_score / 5) * 100, 100)}%` }} />
                  </div>
                  <span className="text-xs font-mono text-gray-300 w-24 text-right">{t.first_score} → {t.latest_score}</span>
                  <span className={`text-xs w-6 text-right ${t.delta > 0 ? "text-emerald-400" : t.delta < 0 ? "text-red-400" : "text-gray-500"}`}>{t.delta > 0 ? "↑" : t.delta < 0 ? "↓" : "—"}</span>
                </div>
              ))}
            </div>
          </div>

          {/* AI Recommendations */}
          <div className="bg-white/[0.03] backdrop-blur-xl border border-indigo-500/10 rounded-2xl p-7">
            <h3 className="text-base font-semibold mb-5">AI 推荐练习计划</h3>
            {recs.length === 0 ? (
              <div className="text-gray-500 text-sm py-4 text-center">完成面试后获取 AI 个性化推荐</div>
            ) : (
              <div className="space-y-3">
                {recs.map((r: any, i: number) => (
                  <div key={i} className="flex gap-3 p-4 bg-indigo-500/[0.03] rounded-xl border-l-3 border-indigo-500">
                    <span className="font-mono font-bold text-indigo-400">{i + 1}</span>
                    <div><div className="text-sm font-medium">{r.label}</div>
                      <div className="text-xs text-gray-500 mt-1">出现 {r.frequency} 次 · 优先级: {r.priority === "high" ? "🔴 高" : r.priority === "medium" ? "🟡 中" : "🟢 低"}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </main>
      )}
    </div>
  );
}
