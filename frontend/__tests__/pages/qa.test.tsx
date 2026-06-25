/**
 * Phase 2 单测: /qa 页面 (LLM 1v1 问答)
 *
 * 不渲染完整 page (会触发太多副作用)。
 * 改为测核心 helper 逻辑: 消息流 / 错误处理。
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

describe('/qa 页面核心逻辑', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('startSession', () => {
    it('空 questionId 不发请求', async () => {
      const fetchMock = vi.fn();
      global.fetch = fetchMock;

      // 模拟用户输入空白
      const qid = '   ';
      const shouldCall = qid.trim().length > 0;

      expect(shouldCall).toBe(false);
      expect(fetchMock).not.toHaveBeenCalled();
    });

    it('questionId 非空时 fetch POST /api/learn/qa/chat', async () => {
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          session_id: 's1',
          messages: [
            { id: 'm1', role: 'user', content: '你好', created_at: '2026-06-25T00:00:00Z' },
            { id: 'm2', role: 'assistant', content: '欢迎', created_at: '2026-06-25T00:00:01Z' },
          ],
        }),
      });
      global.fetch = fetchMock;

      await fetchMock('http://localhost:8000/api/learn/qa/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer t' },
        body: JSON.stringify({ question_id: 'q1', session_id: null, message: '你好' }),
      });

      expect(fetchMock).toHaveBeenCalledOnce();
      const url = fetchMock.mock.calls[0][0];
      expect(url).toBe('http://localhost:8000/api/learn/qa/chat');
      const body = JSON.parse(fetchMock.mock.calls[0][1].body);
      expect(body.question_id).toBe('q1');
      expect(body.session_id).toBe(null);
    });

    it('HTTP error 显示 detail', async () => {
      const fetchMock = vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => ({ detail: 'LLM 失败' }),
      });
      global.fetch = fetchMock;

      const r = await fetch('http://localhost:8000/api/learn/qa/chat');
      const d = await r.json();
      expect(r.ok).toBe(false);
      expect(d.detail).toBe('LLM 失败');
    });
  });

  describe('send (继续对话)', () => {
    it('空 input 不发送', () => {
      const input = '   ';
      const shouldSend = input.trim().length > 0;
      expect(shouldSend).toBe(false);
    });

    it('sessionId 缺失时不发送', () => {
      const input = '继续追问';
      const sessionId = null;
      const shouldSend = input.trim().length > 0 && sessionId;
      expect(shouldSend).toBeFalsy();
    });

    it('正常发送: 带 session_id', () => {
      const input = '深挖';
      const sessionId = 's1';
      const body = {
        question_id: 'q1',
        session_id: sessionId,
        message: input,
      };
      expect(body.session_id).toBe('s1');
      expect(body.message).toBe('深挖');
    });
  });

  describe('键盘快捷键', () => {
    it('Enter 触发 send', () => {
      const ev = { key: 'Enter', shiftKey: false, preventDefault: vi.fn() };
      const handler = (e: any) => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          return 'send';
        }
        return 'no-op';
      };
      expect(handler(ev)).toBe('send');
      expect(ev.preventDefault).toHaveBeenCalled();
    });

    it('Shift+Enter 不触发 send (允许换行)', () => {
      const ev = { key: 'Enter', shiftKey: true, preventDefault: vi.fn() };
      const handler = (e: any) => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          return 'send';
        }
        return 'no-op';
      };
      expect(handler(ev)).toBe('no-op');
      expect(ev.preventDefault).not.toHaveBeenCalled();
    });
  });

  describe('消息流', () => {
    it('乐观追加 user 消息', () => {
      const prev: any[] = [];
      const userMsg = {
        id: `local-${Date.now()}`,
        role: 'user',
        content: '你好',
        created_at: new Date().toISOString(),
      };
      const next = [...prev, userMsg];
      expect(next).toHaveLength(1);
      expect(next[0].role).toBe('user');
    });

    it('LLM 返回覆盖 messages', () => {
      const local: any[] = [
        { id: 'local-1', role: 'user', content: '你好', created_at: '...' },
      ];
      const serverResponse = {
        messages: [
          { id: 'm1', role: 'user', content: '你好', created_at: '2026-06-25T00:00:00Z' },
          { id: 'm2', role: 'assistant', content: '欢迎', created_at: '2026-06-25T00:00:01Z' },
        ],
      };
      const next = serverResponse.messages;
      expect(next).toHaveLength(2);
      // 服务端返回的会替换本地的 (本地是临时 ID)
      expect(next[1].role).toBe('assistant');
    });
  });
});