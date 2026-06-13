import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import { getProfile, getToken, clearToken } from "@/lib/api";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Dashboard() {
  const router = useRouter();
  const [profile, setProfile] = useState<any>(null);
  const [dashData, setDashData] = useState<any>({});
  const [navOpen, setNavOpen] = useState(false);

  useEffect(() => {
    if (!getToken()) { router.push("/"); return; }
    getProfile().then(setProfile).catch(() => {});
    fetch(`${API}/api/dashboard`, { headers: { Authorization: `Bearer ${getToken()}` } })
      .then(r => r.json()).then(setDashData).catch(() => {});
  }, []);

  const iv = dashData?.interview || {};
  const kn = dashData?.knowledge || {};
  const st = dashData?.stats || {};
  const recs = dashData?.recommendations || [];
  const displayName = profile?.display_name || profile?.github_username || "用户";

  const recItems = recs.length > 0
    ? recs.map((r: any, i: number) => ({ key: `r${i}`, n: `${i+1}`, t: r.title, d: r.detail }))
    : [
        { key: "d1", n: "1", t: "完善个人信息", d: "上传简历，AI 自动提取技能标签" },
        { key: "d2", n: "2", t: "开始首次面试", d: "选择 AI Agent 方向，体验追问引擎" },
        { key: "d3", n: "3", t: "浏览知识库", d: "Obsidian 集成 · 49 篇笔记可搜索" },
      ];

  const fmtNum = (v: any) => v >= 10000 ? ((v/1000).toFixed(0)+'K') : (v ?? '-');

  return (
    <div className="min-h-screen bg-[#050914] text-[#f1f5f9]">
      <nav className="sticky top-0 z-50 flex items-center justify-between px-6 py-3.5 bg-[#0c1024]/90 backdrop-blur-xl border-b border-indigo-500/10">
        <div className="flex items-center gap-3">
          <span className="text-lg font-bold bg-gradient-to-r from-indigo-400 to-purple-400 bg-clip-text text-transparent">DevBrain</span>
          <div className="hidden md:flex gap-1 ml-6">
            {[
              { label: "仪表盘", href: "/dashboard", active: true },
              { label: "面试", href: "/interview/profile" },
              { label: "知识库", href: "/knowledge" },
              { label: "信息流", href: "/news" },
            ].map(t => (
              <button key={t.href} onClick={() => router.push(t.href)}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${t.active ? "bg-indigo-500/20 text-indigo-300" : "text-gray-400 hover:text-gray-200"}`}
              >{t.label}</button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-400 hidden sm:inline">{iv.completed || 0} 次面试 · 得分 {iv.latest_score || "-"}</span>
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-purple-500 flex items-center justify-center text-sm font-bold text-white">{displayName[0]}</div>
          <button onClick={() => { clearToken(); router.push("/"); }} className="text-xs text-gray-500 hover:text-gray-300">退出</button>
        </div>
      </nav>

      <main className="max-w-6xl mx-auto px-6 py-10">
        <div className="mb-10">
          <h1 className="text-3xl font-bold">欢迎回来，{displayName}</h1>
          <p className="text-gray-400 text-sm mt-1">中级工程师 · 3年经验</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-10">
          {[
            { icon: M_Interview, title: "面试练习", desc: "AI 追问引擎 · 实时语音对话\n50+ 题库 · 能力雷达图", badge: `${iv.total || 0}次 · 得分 ${iv.latest_score || "-"}`, badgeColor: "bg-indigo-500/10 text-indigo-300 border-indigo-500/20", href: "/interview/profile" },
            { icon: M_Knowledge, title: "知识管理", desc: "Obsidian 集成 · 全文检索\n知识图谱 · 智能关联", badge: `${kn.total_notes || 0} 篇笔记`, badgeColor: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20", href: "/knowledge" },
            { icon: M_News, title: "信息推送", desc: "AI 日报 · 周报深度分析\n代码统计 · 信源管理", badge: `${fmtNum(st.total_tokens)} tokens`, badgeColor: "bg-amber-500/10 text-amber-400 border-amber-500/20", href: "/news" },
          ].map(card => (
            <div key={card.title} onClick={() => router.push(card.href)}
              className="group relative bg-white/[0.03] backdrop-blur-xl border border-indigo-500/10 rounded-2xl p-7 cursor-pointer hover:border-indigo-500/30 hover:-translate-y-1 transition-all duration-300 overflow-hidden"
            >
              <div className="absolute inset-0 rounded-2xl bg-gradient-to-br from-indigo-500/[0.04] to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
              <div className="relative z-10">
                <svg className="w-10 h-10 text-indigo-400 mb-4" fill="none" viewBox="0 0 44 44" stroke="currentColor" strokeWidth="1.5">{card.icon}</svg>
                <h3 className="text-lg font-semibold mb-2">{card.title}</h3>
                <p className="text-sm text-gray-400 leading-relaxed whitespace-pre-line">{card.desc}</p>
                <span className={`inline-block mt-4 px-3 py-1 text-xs rounded-full border ${card.badgeColor}`}>{card.badge}</span>
              </div>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          <div className="bg-white/[0.03] backdrop-blur-xl border border-indigo-500/10 rounded-2xl p-7">
            <h3 className="text-base font-semibold mb-5">本周概览</h3>
            <div className="grid grid-cols-2 gap-4">
              {[
                { v: iv.latest_score || "-", l: "面试得分", c: "text-indigo-400", bg: "bg-indigo-500/5" },
                { v: kn.total_notes || 0, l: "知识笔记", c: "text-emerald-400", bg: "bg-emerald-500/5" },
                { v: fmtNum(st.total_tokens), l: "Token 消耗", c: "text-amber-400", bg: "bg-amber-500/5" },
                { v: fmtNum(st.total_code), l: "代码变更行", c: "text-indigo-400", bg: "bg-indigo-500/5" },
              ].map(s => (
                <div key={s.l} className={`${s.bg} rounded-xl p-4 text-center`}>
                  <div className={`text-2xl font-bold font-mono ${s.c}`}>{s.v}</div>
                  <div className="text-xs text-gray-500 mt-1">{s.l}</div>
                </div>
              ))}
            </div>
          </div>
          <div className="bg-white/[0.03] backdrop-blur-xl border border-indigo-500/10 rounded-2xl p-7">
            <h3 className="text-base font-semibold mb-5">AI 智能推荐</h3>
            <div className="space-y-3">
              {recItems.map(r => (
                <div key={r.key} className="flex gap-3 p-3.5 bg-indigo-500/[0.03] rounded-xl border-l-3 border-indigo-500">
                  <span className="font-mono font-bold text-indigo-400 text-sm">{r.n}</span>
                  <div><div className="text-sm font-medium">{r.t}</div><div className="text-xs text-gray-500 mt-0.5">{r.d}</div></div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

const M_Interview = <><rect x="6" y="8" width="32" height="28" rx="4" /><path d="M14 18h16M14 24h12M14 30h14" strokeLinecap="round" /><circle cx="36" cy="26" r="5" fill="currentColor" opacity="0.3" /></>;
const M_Knowledge = <><path d="M8 6h18l10 10v22a2 2 0 01-2 2H8a2 2 0 01-2-2V8a2 2 0 012-2z" /><path d="M26 6v10h10M14 20h16M14 26h10M14 32h14" strokeLinecap="round" /></>;
const M_News = <><path d="M8 8h28a4 4 0 014 4v18a4 4 0 01-4 4H8a4 4 0 01-4-4V12a4 4 0 014-4z" /><path d="M4 16h36M14 22l4 4 6-6 8 8" strokeLinecap="round" strokeLinejoin="round" /></>;
