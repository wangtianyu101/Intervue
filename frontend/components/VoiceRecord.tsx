/**
 * VoiceRecord — push-to-talk 按钮
 * 使用 MediaRecorder 采集音频，通过 lib/voice.ts 的 VoiceWSClient 上传
 * 收到 AI 文本/音频时通过 props 回调给父组件
 */

import { useState, useRef, useCallback, useEffect } from "react";
import { VoiceWSClient, type VoiceMessageHandler } from "@/lib/voice";

interface VoiceRecordProps {
  interviewId: string;
  token: string;
  onTranscript?: (text: string, isFinal: boolean) => void;
  onResponse?: (text: string) => void;
  onAudio?: (audioData: ArrayBuffer) => void;
  onError?: (error: string) => void;
  onConnected?: () => void;
  onDisconnected?: () => void;
  disabled?: boolean;
}

type RecordState = "idle" | "connecting" | "recording" | "processing" | "error";

const LOG_MAX = 20;

export default function VoiceRecord({
  interviewId,
  token,
  onTranscript,
  onResponse,
  onAudio,
  onError,
  onConnected,
  onDisconnected,
  disabled = false,
}: VoiceRecordProps) {
  const [state, setState] = useState<RecordState>("idle");
  const [errorMsg, setErrorMsg] = useState("");
  const [debugLogs, setDebugLogs] = useState<string[]>([]);
  const [audioLevel, setAudioLevel] = useState(0);

  const clientRef = useRef<VoiceWSClient | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const animFrameRef = useRef<number>(0);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const logIndexRef = useRef(0);
  const messageHandlerRef = useRef<(() => void) | null>(null);

  const log = useCallback((tag: string, detail: string) => {
    const ts = new Date().toISOString().slice(11, 23);
    const line = `[${ts}] ${tag}: ${detail}`;
    console.log(`[VoiceRecord] ${line}`);
    logIndexRef.current += 1;
    setDebugLogs((prev) => {
      const next = [...prev, line];
      return next.length > LOG_MAX ? next.slice(-LOG_MAX) : next;
    });
  }, []);

  // ── Cleanup ──
  const cleanup = useCallback(() => {
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = 0;
    }
    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }
    analyserRef.current = null;
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      mediaRecorderRef.current.stop();
    }
    mediaRecorderRef.current = null;
    audioChunksRef.current = [];
    setAudioLevel(0);
  }, []);

  // ── WS message dispatcher ──
  const handleMessage: VoiceMessageHandler = useCallback((msg) => {
    log("WS", `type=${msg.type}`);
    switch (msg.type) {
      case "processing":
        setState("processing");
        break;
      case "transcript":
        onTranscript?.(msg.text ?? "", msg.is_final ?? true);
        break;
      case "response":
        onResponse?.(msg.text ?? "");
        break;
      case "audio":
        if (msg.data) {
          const bytes = Uint8Array.from(atob(msg.data), (c) => c.charCodeAt(0));
          const blob = new Blob([bytes], { type: "audio/mp3" });
          const url = URL.createObjectURL(blob);
          if (audioRef.current) {
            audioRef.current.src = url;
            audioRef.current.play().catch(console.error);
          }
          onAudio?.(bytes.buffer);
        }
        break;
      case "done":
        setState("idle");
        break;
      case "error":
        setErrorMsg(msg.message || "Unknown error");
        setState("error");
        onError?.(msg.message ?? "Unknown error");
        break;
    }
  }, [log, onTranscript, onResponse, onAudio, onError]);

  // ── Connect WS lazily on first pointer-down ──
  const ensureConnected = useCallback(async () => {
    if (clientRef.current?.isConnected) return clientRef.current;

    const client = new VoiceWSClient(interviewId, token);
    clientRef.current = client;

    // subscribe handler
    const unsubscribe = client.onMessage(handleMessage);
    messageHandlerRef.current = unsubscribe;

    setState("connecting");
    try {
      await client.connect();
      onConnected?.();
    } catch (e: any) {
      setErrorMsg(`连接失败: ${e?.message ?? e}`);
      setState("error");
      onError?.(`连接失败: ${e?.message ?? e}`);
      throw e;
    }
    return client;
  }, [interviewId, token, handleMessage, onConnected, onError]);

  // ── Init audio + start recording ──
  const initAudio = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const ctx = new AudioContext();
      audioContextRef.current = ctx;
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      analyserRef.current = analyser;

      const source = ctx.createMediaStreamSource(stream);
      source.connect(analyser);

      const dataArray = new Uint8Array(analyser.frequencyBinCount);
      const updateLevel = () => {
        if (!analyserRef.current) return;
        analyserRef.current.getByteFrequencyData(dataArray);
        const avg = dataArray.reduce((a, b) => a + b, 0) / dataArray.length;
        setAudioLevel(Math.min(100, avg * 2));
        animFrameRef.current = requestAnimationFrame(updateLevel);
      };
      updateLevel();

      let mimeType = "audio/webm";
      if (!MediaRecorder.isTypeSupported("audio/webm")) {
        mimeType = "audio/mp4";
      }
      audioChunksRef.current = [];
      const mr = new MediaRecorder(stream, { mimeType });
      mediaRecorderRef.current = mr;

      mr.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };
      mr.onerror = (e: any) => {
        log("REC", `ERROR: ${e?.error}`);
        setErrorMsg(`录音错误: ${e?.error?.message || e}`);
        setState("error");
      };
      mr.start(100);
      log("REC", `MediaRecorder started: ${mimeType}`);
      setState("recording");
    } catch (err: any) {
      log("MIC", `ERROR: ${err?.name} - ${err?.message}`);
      if (err?.name === "NotAllowedError") {
        setErrorMsg("麦克风权限被拒绝，请在浏览器设置中允许");
      } else if (err?.name === "NotFoundError") {
        setErrorMsg("未检测到麦克风设备");
      } else {
        setErrorMsg(`麦克风错误: ${err?.message}`);
      }
      setState("error");
    }
  }, [log]);

  // ── Stop & send ──
  const stopAndSend = useCallback(() => {
    const mr = mediaRecorderRef.current;
    if (!mr || mr.state === "inactive") return;

    setState("processing");

    mr.onstop = async () => {
      log("REC", `onstop: chunks=${audioChunksRef.current.length}`);

      const mimeType = mr.mimeType || "audio/webm";
      const format = mimeType.includes("mp4") ? "mp4" : "webm";
      const blob = new Blob(audioChunksRef.current, { type: mimeType });

      cleanup();

      if (blob.size < 100) {
        log("REC", "Blob too small");
        setState("idle");
        return;
      }

      const reader = new FileReader();
      reader.onloadend = () => {
        const base64 = (reader.result as string).split(",")[1];
        const client = clientRef.current;
        if (!client) {
          log("SEND", "no client — dropping audio");
          setState("error");
          return;
        }
        client.sendAudio(base64, format);
        client.sendStop();
        log("SEND", `Sent ${blob.size} bytes (${format})`);
      };
      reader.readAsDataURL(blob);
    };

    mr.stop();
  }, [cleanup, log]);

  // ── Pointer handlers ──
  const handlePointerDown = useCallback(async () => {
    if (disabled || state === "processing" || state === "recording") return;
    try {
      await ensureConnected();
    } catch {
      return;
    }
    await initAudio();
  }, [disabled, state, ensureConnected, initAudio]);

  const handlePointerUp = useCallback(() => {
    if (state !== "recording") return;
    stopAndSend();
  }, [state, stopAndSend]);

  // ── Lifecycle ──
  useEffect(() => {
    return () => {
      cleanup();
      messageHandlerRef.current?.();
      clientRef.current?.disconnect();
      clientRef.current = null;
    };
  }, [cleanup]);

  // Expose onDisconnected when socket dies (best-effort polling)
  useEffect(() => {
    const t = setInterval(() => {
      if (clientRef.current && !clientRef.current.isConnected && state !== "idle") {
        onDisconnected?.();
      }
    }, 1000);
    return () => clearInterval(t);
  }, [state, onDisconnected]);

  // ── Render ──
  const stateLabel = {
    idle: "按住说话",
    connecting: "连接中...",
    recording: "松开发送",
    processing: "处理中...",
    error: errorMsg || "错误",
  }[state];

  const stateColor = {
    idle: "bg-indigo-500 hover:bg-indigo-600",
    connecting: "bg-yellow-500",
    recording: "bg-red-500",
    processing: "bg-purple-500 animate-pulse",
    error: "bg-red-600",
  }[state];

  return (
    <div className="flex flex-col items-center gap-4">
      <details className="w-full text-xs text-gray-500">
        <summary>调试日志 ({debugLogs.length})</summary>
        <pre className="mt-1 p-2 bg-gray-900 rounded text-green-400 overflow-auto max-h-40">
          {debugLogs.join("\n")}
        </pre>
      </details>

      <button
        onPointerDown={handlePointerDown}
        onPointerUp={handlePointerUp}
        onPointerLeave={handlePointerUp}
        disabled={disabled || state === "processing" || state === "connecting"}
        className={`w-24 h-24 rounded-full ${stateColor} text-white font-medium shadow-lg transition-all active:scale-95 ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}
      >
        <div className="flex flex-col items-center justify-center h-full">
          {state === "recording" && (
            <div className="w-3 h-3 bg-white rounded-full animate-pulse mb-1" />
          )}
          {state === "processing" && (
            <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin mb-1" />
          )}
          {state === "idle" && (
            <div
              className="w-0 h-0 border-l-8 border-r-8 border-b-12 border-l-transparent border-r-transparent border-b-white mb-1"
              style={{ borderLeftWidth: 8, borderRightWidth: 8, borderBottomWidth: 12 }}
            />
          )}
          <span className="text-xs">{stateLabel}</span>
        </div>
      </button>

      <div className="w-48 h-2 bg-gray-700 rounded-full overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-green-500 to-red-500 transition-all"
          style={{ width: `${audioLevel}%` }}
        />
      </div>

      <audio ref={audioRef} />

      {errorMsg && (
        <div className="text-red-400 text-sm text-center">{errorMsg}</div>
      )}
    </div>
  );
}
