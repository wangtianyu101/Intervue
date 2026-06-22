/**
 * LiveKitVoice — full-duplex audio + transcript data channel.
 */

import { useEffect, useRef, useState, useCallback } from "react";
import { Room, RoomEvent, Track, RemoteTrack } from "livekit-client";

type VoiceState = "connecting" | "connected" | "listening" | "speaking" | "disconnected" | "error";

interface Props {
  roomName: string;
  token: string;
  onTranscript?: (text: string, speaker: "ai" | "user") => void;
  onStateChange?: (state: VoiceState) => void;
}

export default function LiveKitVoice({ roomName, token, onTranscript, onStateChange }: Props) {
  const [state, setState] = useState<VoiceState>("connecting");
  const roomRef = useRef<Room | null>(null);

  const updateState = useCallback((s: VoiceState) => { setState(s); onStateChange?.(s); }, [onStateChange]);

  useEffect(() => {
    if (!roomName || !token) return;
    const room = new Room({ audioCaptureDefaults: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    roomRef.current = room;

    const connect = async () => {
      try {
        updateState("connecting");
        room.on(RoomEvent.TrackSubscribed, (track, _publication, _participant) => {
          if (track.kind === Track.Kind.Audio && track) {
            updateState("speaking");
            const el = track.attach(); el.setAttribute("autoplay", "true");
            document.getElementById("ai-audio-sink")?.appendChild(el);
          }
        });
        room.on(RoomEvent.TrackUnsubscribed, (track, _publication, _participant) => {
          if (track.kind === Track.Kind.Audio) updateState("listening");
        });
        room.on(RoomEvent.Connected, () => { updateState("listening"); });
        room.on(RoomEvent.Disconnected, () => updateState("disconnected"));

        // Transcript via data channel
        room.on(RoomEvent.DataReceived, (payload: Uint8Array) => {
          try {
            const msg = JSON.parse(new TextDecoder().decode(payload));
            if (msg.speaker && msg.text) onTranscript?.(msg.text, msg.speaker);
          } catch {}
        });

        await room.connect(process.env.NEXT_PUBLIC_LIVEKIT_URL || "ws://localhost:7880", token);
        await room.localParticipant.setMicrophoneEnabled(true);
      } catch (err) {
        console.error("LiveKitVoice:", err);
        updateState("error");
      }
    };
    connect();
    return () => { room.disconnect(); roomRef.current = null; };
  }, [roomName, token]);

  const labels: Record<VoiceState, string> = { connecting:"连接中...", connected:"已连接", listening:"● 聆听中", speaking:"● 面试官说话中", disconnected:"已断开", error:"连接失败" };
  const colors: Record<VoiceState, string> = { connecting:"text-amber-400", connected:"text-emerald-400", listening:"text-emerald-400", speaking:"text-indigo-400", disconnected:"text-gray-500", error:"text-red-400" };

  return (
    <div className="flex flex-col items-center gap-2">
      <div id="ai-audio-sink" className="hidden" />
      <div className={`flex items-center gap-2 text-sm ${colors[state]}`}>
        <span className={`w-2 h-2 rounded-full inline-block ${state==="speaking"?"bg-indigo-400 animate-pulse":state==="listening"?"bg-emerald-400":state==="connecting"?"bg-amber-400 animate-pulse":"bg-gray-500"}`} />
        {labels[state]}
      </div>
    </div>
  );
}
