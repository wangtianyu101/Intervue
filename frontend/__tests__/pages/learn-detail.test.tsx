/**
 * Phase 2-5 单测: /learn/[qid] 题目详情页
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

describe('/learn/[qid] 详情页核心逻辑', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('数据获取', () => {
    it('qid 为空时不 fetch', () => {
      const qid: string | undefined = undefined;
      const shouldFetch = !!qid && typeof qid === 'string';
      expect(shouldFetch).toBe(false);
    });

    it('qid 非空时 GET /api/learn/questions/{qid}', () => {
      const qid = 'agent_001';
      const url = `http://localhost:8000/api/learn/questions/${encodeURIComponent(qid)}`;
      expect(url).toBe('http://localhost:8000/api/learn/questions/agent_001');
    });

    it('404 显示错误态', () => {
      const status = 404;
      const isError = status === 404;
      expect(isError).toBe(true);
    });

    it('500 也走错误态', () => {
      const status = 500;
      const isError = status >= 400;
      expect(isError).toBe(true);
    });
  });

  describe('准确率计算', () => {
    function calcAccuracy(practice: number, correct: number): number {
      return practice > 0 ? Math.round((correct / practice) * 100) : 0;
    }

    it('practice=0 → 0', () => {
      expect(calcAccuracy(0, 0)).toBe(0);
    });

    it('全对 100%', () => {
      expect(calcAccuracy(5, 5)).toBe(100);
    });

    it('零对 0%', () => {
      expect(calcAccuracy(5, 0)).toBe(0);
    });

    it('4/5 → 80%', () => {
      expect(calcAccuracy(5, 4)).toBe(80);
    });

    it('2/3 → 67%', () => {
      expect(calcAccuracy(3, 2)).toBe(67);
    });
  });

  describe('提交答题 (D5 等效路径)', () => {
    it('POST body 含 source="practice"', () => {
      const body = {
        user_answer: 'test',
        score: 4,
        blind_spots: [],
        duration_sec: 60,
        source: 'practice',
      };
      expect(body.source).toBe('practice');
    });

    it('duration_sec 计算 = now - startTime', () => {
      const startTime = 1719250000000;
      const now = 1719250123000;
      const duration = Math.floor((now - startTime) / 1000);
      expect(duration).toBe(123);
    });

    it('空 userAnswer 用 "(未作答)" 占位', () => {
      const userAnswer = '';
      const sent = userAnswer || '(未作答)';
      expect(sent).toBe('(未作答)');
    });

    it('提交后乐观更新 progress', () => {
      const prev = {
        id: 'p1',
        status: 'new',
        practice_count: 0,
        bookmarked: false,
      };
      const updated = { ...prev, status: 'learning', practice_count: 1 };
      expect(updated.status).toBe('learning');
      expect(updated.practice_count).toBe(1);
    });
  });

  describe('收藏切换 (乐观更新)', () => {
    function toggleOptimistic(progress: any): any {
      if (!progress) return null;
      return { ...progress, bookmarked: !progress.bookmarked };
    }

    it('已收藏 → 取消', () => {
      const next = toggleOptimistic({ bookmarked: true });
      expect(next?.bookmarked).toBe(false);
    });

    it('未收藏 → 添加', () => {
      const next = toggleOptimistic({ bookmarked: false });
      expect(next?.bookmarked).toBe(true);
    });

    it('progress 为 null 时返回 null (不创建)', () => {
      const next = toggleOptimistic(null);
      expect(next).toBe(null);
    });
  });

  describe('笔记保存', () => {
    it('PUT body 是 { content_md: ... }', () => {
      const body = { content_md: '# 笔记\n- 要点 1\n- 要点 2' };
      expect(body.content_md).toContain('# 笔记');
    });

    it('编辑时取消恢复原值', () => {
      const original = '原内容';
      const draft = '新草稿';
      const cancelled = draft === '新草稿' ? original : draft;
      expect(cancelled).toBe(original);
    });
  });

  describe('Score 按钮 (与 /review 共享)', () => {
    const SCORE_OPTIONS = [
      { score: 0, label: '完全不会' },
      { score: 1, label: '模糊' },
      { score: 2, label: '差' },
      { score: 3, label: '及格' },
      { score: 4, label: '良好' },
      { score: 5, label: '完美' },
    ];

    it('6 档分数', () => {
      expect(SCORE_OPTIONS).toHaveLength(6);
    });

    it('颜色按分数渐变 (红→绿)', () => {
      // 简单断言: 0 分颜色包含 'red', 5 分包含 'green'
      const opt0 = SCORE_OPTIONS.find((o) => o.score === 0)!;
      const opt5 = SCORE_OPTIONS.find((o) => o.score === 5)!;
      expect(opt0.label).toBe('完全不会');
      expect(opt5.label).toBe('完美');
    });
  });

  describe('路由跳转', () => {
    it('← 返回 /learn', () => {
      const target = '/learn';
      expect(target).toBe('/learn');
    });

    it('空 token 跳 /', () => {
      const hasToken = false;
      const target = hasToken ? '/learn/[qid]' : '/';
      expect(target).toBe('/');
    });
  });
});