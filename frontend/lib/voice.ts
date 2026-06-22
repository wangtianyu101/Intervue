/**
 * Voice WebSocket 客户端封装
 * 用于连接后端 WebSocket 语音面试端点
 */

const WS_URL = process.env.NEXT_PUBLIC_API_URL?.replace("http", "ws") || "ws://localhost:8000";

export interface VoiceMessage {
  type: string;
  text?: string;
  data?: string;
  message?: string;
  is_final?: boolean;
}

export type VoiceMessageHandler = (msg: VoiceMessage) => void;

export class VoiceWSClient {
  private ws: WebSocket | null = null;
  private url: string;
  private handlers: Set<VoiceMessageHandler> = new Set();
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 3;

  constructor(interviewId: string, token: string) {
    this.url = `${WS_URL}/ws/voice/${interviewId}?token=${encodeURIComponent(token)}`;
  }

  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      try {
        this.ws = new WebSocket(this.url);

        this.ws.onopen = () => {
          console.log("[VoiceWS] Connected");
          this.reconnectAttempts = 0;
          resolve();
        };

        this.ws.onmessage = (event) => {
          try {
            const msg = JSON.parse(event.data) as VoiceMessage;
            this.handlers.forEach((h) => h(msg));
          } catch (e) {
            console.error("[VoiceWS] Parse error:", e);
          }
        };

        this.ws.onerror = (e) => {
          console.error("[VoiceWS] Error:", e);
        };

        this.ws.onclose = () => {
          console.log("[VoiceWS] Disconnected");
          this.ws = null;
          this.attemptReconnect();
        };
      } catch (e) {
        reject(e);
      }
    });
  }

  private attemptReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.log("[VoiceWS] Max reconnect attempts reached");
      return;
    }
    this.reconnectAttempts++;
    console.log(`[VoiceWS] Reconnecting (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);
    setTimeout(() => this.connect(), 1000 * this.reconnectAttempts);
  }

  send(msg: object) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    } else {
      console.warn("[VoiceWS] Cannot send, not connected");
    }
  }

  sendAudio(audioData: string, format: string = "webm") {
    this.send({ type: "audio", data: audioData, format });
  }

  sendStop() {
    this.send({ type: "stop" });
  }

  sendPing() {
    this.send({ type: "ping" });
  }

  onMessage(handler: VoiceMessageHandler) {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  disconnect() {
    this.ws?.close();
    this.ws = null;
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}
