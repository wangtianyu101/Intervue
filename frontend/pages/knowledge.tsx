import { useRouter } from "next/router";
export default function Knowledge() {
  const router = useRouter();
  return (
    <div className="min-h-screen bg-[#050914] text-[#f1f5f9] flex flex-col items-center justify-center">
      <nav className="sticky top-0 z-50 w-full flex items-center gap-4 px-6 py-3.5 bg-[#0c1024]/90 backdrop-blur-xl border-b border-indigo-500/10">
        <button onClick={() => router.push("/dashboard")} className="text-gray-400 hover:text-white text-sm">← 仪表盘</button>
        <span className="text-lg font-bold bg-gradient-to-r from-indigo-400 to-purple-400 bg-clip-text text-transparent">知识管理</span>
      </nav>
      <div className="flex-1 flex flex-col items-center justify-center text-center px-6">
        <div className="text-5xl mb-6">📚</div>
        <h2 className="text-2xl font-bold mb-3">知识管理 — 即将上线</h2>
        <p className="text-gray-400 text-sm max-w-md">Obsidian 知识库集成 · 全文检索 · 知识图谱 · Phase 3 开发中</p>
      </div>
    </div>
  );
}
