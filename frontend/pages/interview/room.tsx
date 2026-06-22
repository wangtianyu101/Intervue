/**
 * Interview Room — WebSocket 语音面试页面
 * 使用阿里云 ASR/TTS + WebSocket
 */

import { useEffect, useState, useRef, useCallback } from "react";
import { useRouter } from "next/router";
import { getToken } from "@/lib/api";
import InterviewerAvatar from "@/components/InterviewerAvatar";
import LiveTranscript from "@/components/LiveTranscript";
import VoiceRecord from "@/components/VoiceRecord";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type RoomState = "connecting" | "ready" | "interviewing" | "ended";

export default function InterviewRoom() {
  const router = useRouter();
  const [roomState, setRoomState] = useState<RoomState>("connecting");
  const [interviewId, setInterviewId] = useState<string>("");
  const [transcript, setTranscript] = useState<{ id: number; speaker: "ai" | "user"; text: string; time: string }[]>([]);
  const [duration, setDuration] = useState(0);
  const [avatarState, setAvatarState] = useState<"idle" | "listening" | "speaking" | "thinking" | "disconnected">("idle");
  const counter = useRef(0);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  // 初始化面试
  useEffect(() => {
    if (!getToken()) {
      router.push("/");
      return;
    }
    if (!router.isReady) return;

    const init = async () => {
      try {
        // If the caller already created the interview (e.g. /interview/setup
        // pushed us here with ?id=...), reuse it. Otherwise POST a new one.
        const queryId = typeof router.query.id === "string" ? router.query.id : "";
        if (queryId) {
          setInterviewId(queryId);
          setRoomState("ready");
          return;
        }

        const h = { Authorization: `Bearer ${getToken()}`, "Content-Type": "application/json" };
        const res = await fetch(`${API}/api/interviews`, {
          method: "POST",
          headers: h,
          body: JSON.stringify({ round: "round1", style: "standard" }),
        });
        const data = await res.json();
        setInterviewId(data.id);
        setRoomState("ready");
      } catch (e) {
        console.error("Init failed:", e);
        setRoomState("connecting");
      }
    };

    init();
  }, [router.isReady, router.query.id]);

  // 计时器
  useEffect(() => {
    if (roomState === "interviewing") {
      timerRef.current = setInterval(() => setDuration(d => d + 1), 1000);
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [roomState]);

  // 添加字幕行
  const addLine = useCallback((text: string, speaker: "ai" | "user") => {
    counter.current += 1;
    const now = new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    setTranscript(prev => [...prev, { id: counter.current, speaker, text, time: now }]);
  }, []);

  // 处理用户语音转写 (isFinal 恒为 true，因为我们用 stop 模式)
  const handleTranscript = useCallback((text: string, _isFinal: boolean) => {
    addLine(text, "user");
    setAvatarState("thinking");
  }, [addLine]);

  // 处理 AI 回复文字
  const handleResponse = useCallback((text: string) => {
    addLine(text, "ai");
    setAvatarState("speaking");
  }, [addLine]);

  // 处理 AI 音频播放完成
  const handleAudio = useCallback(() => {
    setAvatarState("idle");
  }, []);

  // 处理错误
  const handleError = useCallback((msg: string) => {
    console.error("Voice error:", msg);
    setAvatarState("idle");
  }, []);

  // 结束面试 — POST 到后端标记完成，再跳转历史记录
  const endInterview = useCallback(async () => {
    if (timerRef.current) clearInterval(timerRef.current);
    setRoomState("ended");

    // 把 in_progress → completed，幂等；失败也跳走（不要卡住用户）
    if (interviewId) {
      try {
        await fetch(`${API}/api/interviews/${interviewId}/complete`, {
          method: "POST",
          headers: { Authorization: `Bearer ${getToken()}` },
        });
      } catch (e) {
        console.error("complete failed (continuing):", e);
      }
    }
    router.push("/interview/history");
  }, [interviewId, router]);

  // 格式化时长
  const fmtDuration = (s: number) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;

  return (
    <div className="min-h-screen bg-[#050914] text-[#f1f5f9] flex flex-col">
      {/* Top bar */}
      <nav className="flex items-center justify-between px-6 py-3 bg-[#0c1024]/90 backdrop-blur-xl border-b border-indigo-500/10">
        <button onClick={endInterview} className="text-gray-400 hover:text-white text-sm">← 退出</button>
        <div className="text-sm font-medium">面试中</div>
        <div className="text-sm font-mono text-indigo-400">{fmtDuration(duration)}</div>
      </nav>

      {/* Main area */}
      <main className="flex-1 flex flex-col items-center justify-center px-6 py-8 max-w-2xl mx-auto w-full gap-8">
        <InterviewerAvatar state={avatarState} name="Alex" />

        {roomState === "connecting" && (
          <div className="text-gray-400 text-sm animate-pulse">正在创建面试...</div>
        )}

        {roomState === "ready" && interviewId && (
          <VoiceRecord
            interviewId={interviewId}
            token={getToken() || ""}
            onTranscript={handleTranscript}
            onResponse={handleResponse}
            onAudio={handleAudio}
            onError={handleError}
          />
        )}

        <div className="w-full mt-4">
          <LiveTranscript lines={transcript} />
        </div>
      </main>

      {/* Bottom */}
      <footer className="px-6 py-4 border-t border-indigo-500/10 flex justify-center">
        <button onClick={endInterview}
          className="px-8 py-3 rounded-full bg-red-500/20 text-red-400 border border-red-500/30 hover:bg-red-500/30 font-medium text-sm">
          结束面试
        </button>
      </footer>
    </div>
  );
}
