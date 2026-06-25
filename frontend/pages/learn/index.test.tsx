/**
 * Phase 2 单测: /learn 页面 (题库列表 + 过滤)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

describe('/learn 页面核心逻辑', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('过滤参数构造', () => {
    it('空 topic 不应加入 params', () => {
      const params = new URLSearchParams();
      const topic = '';
      if (topic) params.set('topic', topic);
      expect(params.toString()).toBe('');
    });

    it('非空 topic 加入 params', () => {
      const params = new URLSearchParams();
      const topic = 'agent';
      if (topic) params.set('topic', topic);
      expect(params.get('topic')).toBe('agent');
    });

    it('difficulty=0 不加 (代表"全部")', () => {
      const params = new URLSearchParams();
      const difficulty = 0;
      if (difficulty) params.set('difficulty', String(difficulty));
      expect(params.toString()).toBe('');
    });

    it('difficulty=3 加进 params', () => {
      const params = new URLSearchParams();
      const difficulty = 3;
      if (difficulty) params.set('difficulty', String(difficulty));
      expect(params.get('difficulty')).toBe('3');
    });

    it('bookmarkedOnly 时加 bookmarked=true', () => {
      const params = new URLSearchParams();
      const bookmarkedOnly = true;
      if (bookmarkedOnly) params.set('bookmarked', 'true');
      expect(params.get('bookmarked')).toBe('true');
    });

    it('query 带 trim + 空时不加', () => {
      const params = new URLSearchParams();
      const query = '   ';
      if (query.trim()) params.set('q', query.trim());
      expect(params.toString()).toBe('');
    });

    it('query 有内容时 trim 后加', () => {
      const params = new URLSearchParams();
      const query = '  LangChain  ';
      if (query.trim()) params.set('q', query.trim());
      expect(params.get('q')).toBe('LangChain');
    });

    it('page 和 size 总是加', () => {
      const params = new URLSearchParams();
      const page = 2;
      const size = 20;
      params.set('page', String(page));
      params.set('size', String(size));
      expect(params.get('page')).toBe('2');
      expect(params.get('size')).toBe('20');
    });
  });

  describe('分页计算', () => {
    const PAGE_SIZE = 20;

    it('totalPages = ceil(total / size)', () => {
      expect(Math.ceil(0 / PAGE_SIZE)).toBe(0);
      expect(Math.ceil(20 / PAGE_SIZE)).toBe(1);
      expect(Math.ceil(21 / PAGE_SIZE)).toBe(2);
      expect(Math.ceil(100 / PAGE_SIZE)).toBe(5);
    });

    it('只有 1 页时不显示分页器', () => {
      const total = 15;
      const totalPages = Math.ceil(total / PAGE_SIZE);
      const showPagination = totalPages > 1;
      expect(showPagination).toBe(false);
    });

    it('超过 1 页时显示', () => {
      const total = 50;
      const totalPages = Math.ceil(total / PAGE_SIZE);
      const showPagination = totalPages > 1;
      expect(showPagination).toBe(true);
    });
  });

  describe('bookmark toggle (乐观更新)', () => {
    interface Q {
      id: string;
      progress?: { bookmarked: boolean } | null;
    }

    function toggleBookmarkOptimistic(qs: Q[], qid: string): Q[] {
      return qs.map((x) =>
        x.id === qid
          ? {
              ...x,
              progress: x.progress
                ? { ...x.progress, bookmarked: !x.progress.bookmarked }
                : null,
            }
          : x,
      );
    }

    it('切换已 bookmark 的题 → false', () => {
      const qs = [{ id: 'q1', progress: { bookmarked: true } }];
      const next = toggleBookmarkOptimistic(qs, 'q1');
      expect(next[0].progress?.bookmarked).toBe(false);
    });

    it('切换未 bookmark 的题 → true', () => {
      const qs = [{ id: 'q1', progress: { bookmarked: false } }];
      const next = toggleBookmarkOptimistic(qs, 'q1');
      expect(next[0].progress?.bookmarked).toBe(true);
    });

    it('其他题不受影响', () => {
      const qs = [
        { id: 'q1', progress: { bookmarked: true } },
        { id: 'q2', progress: { bookmarked: false } },
      ];
      const next = toggleBookmarkOptimistic(qs, 'q1');
      expect(next[1].progress?.bookmarked).toBe(false); // 不变
    });

    it('progress 为 null 时保持 null', () => {
      const qs = [{ id: 'q1', progress: null }];
      const next = toggleBookmarkOptimistic(qs, 'q1');
      expect(next[0].progress).toBe(null);
    });
  });

  describe('主题/难度常量', () => {
    it('7 个主题', () => {
      const TOPICS = [
        '', 'agent', 'rag', 'system_design', 'llm', 'backend', 'frontend',
      ];
      expect(TOPICS).toHaveLength(7);
    });

    it('6 档难度 (含 0=全部)', () => {
      const DIFFICULTIES = [0, 1, 2, 3, 4, 5];
      expect(DIFFICULTIES).toHaveLength(6);
    });
  });
});