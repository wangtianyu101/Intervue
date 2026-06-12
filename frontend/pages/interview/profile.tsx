import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import { getProfile, updateProfile, getToken, clearToken, startInterview } from "@/lib/api";

export default function InterviewProfile() {
  const router = useRouter();
  const [profile, setProfile] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ display_name: "", years_of_exp: 3, current_level: "mid", tech_stack: [] as string[], target_companies: [] as string[] });
  const [resumeText, setResumeText] = useState("");

  const allTechs = ["LangChain", "LangGraph", "RAG", "Python", "Java", "Spring Boot", "K8s", "Docker", "React", "Go", "TypeScript", "MCP"];

  useEffect(() => {
    if (!getToken()) { router.push("/"); return; }
    getProfile().then(p => {
      setProfile(p);
      setForm({
        display_name: p.display_name || "",
        years_of_exp: p.years_of_exp || 3,
        current_level: p.current_level || "mid",
        tech_stack: p.tech_stack || [],
        target_companies: p.target_companies || [],
      });
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  const toggle = (arr: string[], item: string) => arr.includes(item) ? arr.filter(t => t !== item) : [...arr, item];

  const save = async () => {
    setSaving(true);
    try {
      await updateProfile({
        tech_stack: form.tech_stack,
        years_of_exp: form.years_of_exp,
        current_level: form.current_level,
        target_companies: form.target_companies,
        resume_text: resumeText || undefined,
      });
      alert("保存成功");
    } catch (e: any) { alert(e.message); }
    finally { setSaving(false); }
  };

  if (loading) return <div className="min-h-screen bg-[#050914] flex items-center justify-center"><div className="text-gray-400">加载中...</div></div>;

  return (
    <div className="min-h-screen bg-[#050914] text-[#f1f5f9]">
      <nav className="sticky top-0 z-50 flex items-center gap-4 px-6 py-3.5 bg-[#0c1024]/90 backdrop-blur-xl border-b border-indigo-500/10">
        <button onClick={() => router.push("/dashboard")} className="text-gray-400 hover:text-white text-sm">← 仪表盘</button>
        <span className="text-lg font-bold bg-gradient-to-r from-indigo-400 to-purple-400 bg-clip-text text-transparent">面试练习</span>
        <div className="flex gap-1 ml-4">
          {[
            { label: "个人信息", href: "/interview/profile", active: true },
            { label: "面试记录", href: "/interview/history" },
            { label: "能力分析", href: "/interview/analytics" },
          ].map(t => (
            <button key={t.href} onClick={() => router.push(t.href)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${t.active ? "bg-indigo-500/20 text-indigo-300" : "text-gray-400 hover:text-gray-200"}`}
            >{t.label}</button>
          ))}
        </div>
        <div className="flex-1" />
        <button onClick={() => router.push("/interview/setup")} className="px-5 py-2.5 rounded-xl font-medium text-sm bg-gradient-to-r from-indigo-500 to-purple-500 text-white shadow-lg shadow-purple-500/20 hover:opacity-90 transition-all">
          开始面试
        </button>
        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-purple-500 flex items-center justify-center text-sm font-bold text-white">{form.display_name?.[0] || "?"}</div>
      </nav>

      <main className="max-w-5xl mx-auto px-6 py-10">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {/* Basic Info */}
          <div className="bg-white/[0.03] backdrop-blur-xl border border-indigo-500/10 rounded-2xl p-7">
            <h3 className="text-lg font-semibold mb-5">基本信息</h3>
            <div className="space-y-4">
              <div><label className="block text-sm text-gray-400 mb-1.5">昵称</label><input className="w-full px-4 py-2.5 rounded-xl bg-white/[0.03] border border-indigo-500/10 text-white focus:border-indigo-500 focus:outline-none" value={form.display_name} onChange={e => setForm({...form, display_name: e.target.value})} /></div>
              <div><label className="block text-sm text-gray-400 mb-1.5">经验年限</label><input type="number" min={0} max={20} className="w-full px-4 py-2.5 rounded-xl bg-white/[0.03] border border-indigo-500/10 text-white focus:border-indigo-500 focus:outline-none" value={form.years_of_exp} onChange={e => setForm({...form, years_of_exp: +e.target.value})} /></div>
              <div><label className="block text-sm text-gray-400 mb-1.5">当前级别</label>
                <select className="w-full px-4 py-2.5 rounded-xl bg-white/[0.03] border border-indigo-500/10 text-white focus:border-indigo-500 focus:outline-none" value={form.current_level} onChange={e => setForm({...form, current_level: e.target.value})}>
                  <option value="junior">初级</option><option value="mid">中级</option><option value="senior">高级</option>
                </select>
              </div>
              <div><label className="block text-sm text-gray-400 mb-1.5">目标公司</label>
                <div className="flex flex-wrap gap-2">
                  {["字节跳动","阿里巴巴","腾讯","美团","小红书","拼多多"].map(c => (
                    <button key={c} onClick={() => setForm({...form, target_companies: form.target_companies.includes(c) ? form.target_companies.filter(x=>x!==c) : [...form.target_companies, c]})}
                      className={`px-3 py-1.5 rounded-full text-xs border transition-all ${form.target_companies.includes(c) ? "bg-indigo-500/20 text-indigo-300 border-indigo-500/30" : "bg-white/[0.02] text-gray-400 border-gray-700/20 hover:border-indigo-500/20"}`}
                    >{c}</button>
                  ))}
                </div>
              </div>
              <button onClick={save} disabled={saving} className="w-full py-2.5 rounded-xl font-medium bg-gradient-to-r from-indigo-500 to-purple-500 text-white hover:opacity-90 transition-all">{saving ? "保存中..." : "保存修改"}</button>
            </div>
          </div>

          {/* Skills & Resume */}
          <div className="bg-white/[0.03] backdrop-blur-xl border border-indigo-500/10 rounded-2xl p-7">
            <h3 className="text-lg font-semibold mb-5">技能栈 & 简历</h3>
            <div className="flex flex-wrap gap-2 mb-6">
              {allTechs.map(t => (
                <button key={t} onClick={() => setForm({...form, tech_stack: toggle(form.tech_stack, t)})}
                  className={`px-3 py-1.5 rounded-full text-xs border transition-all ${form.tech_stack.includes(t) ? "bg-indigo-500/20 text-indigo-300 border-indigo-500/30" : "bg-white/[0.02] text-gray-400 border-gray-700/20 hover:border-indigo-500/20"}`}
                >{form.tech_stack.includes(t) ? "✓ " : "+ "}{t}</button>
              ))}
            </div>
            <div className="border-2 border-dashed border-indigo-500/20 rounded-2xl p-8 text-center text-gray-400 text-sm cursor-pointer hover:border-indigo-500/40 hover:text-indigo-300 transition-all">
              <div className="text-3xl mb-2">📄</div>
              点击或拖拽上传简历 PDF<br /><span className="text-xs text-gray-500">支持 PDF 格式，AI 自动解析技能标签</span>
            </div>
            <div className="mt-4 p-3.5 bg-emerald-500/[0.06] border border-emerald-500/10 rounded-xl text-sm flex items-center gap-2">
              <span className="text-emerald-400">📄</span> 王天宇-Java后端开发-AI应用方向.pdf
              <span className="text-xs text-gray-500 ml-auto">308KB · 2页</span>
            </div>
            <div className="mt-3 p-3.5 bg-indigo-500/[0.04] rounded-xl text-xs text-gray-400 leading-relaxed">
              AI 提取摘要：<em className="text-gray-200 not-italic">3年Java后端开发，熟悉Spring全家桶，有Agent开发经验，掌握LangChain/LangGraph/RAG...</em>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
