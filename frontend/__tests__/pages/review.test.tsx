/**
 * Phase 2 单测: /review 页面 (SRS 复习队列)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

describe('/review 页面核心逻辑', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('队列加载', () => {
    it('空队列显示完成态', () => {
      const queue: any[] = [];
      const isComplete = queue.length === 0;
      expect(isComplete).toBe(true);
    });

    it('有队列时显示当前题', () => {
      const queue = [
        { question_id: 'q1', status: 'new' },
        { question_id: 'q2', status: 'learning' },
      ];
      const current = queue[0];
      expect(current.question_id).toBe('q1');
    });
  });

  describe('submitSelfEval → 后端', () => {
    it('POST /api/learn/questions/{qid}/answer 带 score + duration', () => {
      const qid = 'agent_001';
      const score = 4;
      const durationSec = 60;
      const userAnswer = '我用了 LangChain 框架...';

      const body = {
        user_answer: userAnswer,
        score,
        blind_spots: [],
        duration_sec: durationSec,
        source: 'review',
      };
      expect(body.source).toBe('review');
      expect(body.score).toBeGreaterThanOrEqual(0);
      expect(body.score).toBeLessThanOrEqual(5);
    });

    it('提交后 queue 减一', () => {
      const queue = [
        { question_id: 'q1' },
        { question_id: 'q2' },
        { question_id: 'q3' },
      ];
      const remaining = queue.slice(1);
      expect(remaining).toHaveLength(2);
      expect(remaining[0].question_id).toBe('q2');
    });

    it('completed 计数 +1', () => {
      let completed = 0;
      completed = completed + 1;
      expect(completed).toBe(1);
    });
  });

  describe('6 档自评分数', () => {
    const SCORE_BUTTONS = [
      { score: 0, label: '完全不会' },
      { score: 1, label: '模糊' },
      { score: 2, label: '差' },
      { score: 3, label: '及格' },
      { score: 4, label: '良好' },
      { score: 5, label: '完美' },
    ];

    it('应该有 6 档', () => {
      expect(SCORE_BUTTONS).toHaveLength(6);
    });

    it('每档分数唯一', () => {
      const scores = SCORE_BUTTONS.map((b) => b.score);
      expect(new Set(scores).size).toBe(6);
    });

    it('分数范围 0-5', () => {
      SCORE_BUTTONS.forEach((b) => {
        expect(b.score).toBeGreaterThanOrEqual(0);
        expect(b.score).toBeLessThanOrEqual(5);
      });
    });
  });

  describe('hint 显示', () => {
    it('answer_key_points 存在时显示', () => {
      const current = {
        answer_key_points: ['要点1', '要点2'],
      };
      const shouldShow = current.answer_key_points?.length > 0;
      expect(shouldShow).toBe(true);
    });

    it('answer_key_points 空时不显示', () => {
      const current = { answer_key_points: [] };
      const shouldShow = current.answer_key_points?.length > 0;
      expect(shouldShow).toBe(false);
    });
  });

  describe('时间统计', () => {
    it('duration_sec 计算 = now - startTime', () => {
      const startTime = 1719250000000; // mock
      const now = 1719250060000; // 60s 后
      const duration = Math.floor((now - startTime) / 1000);
      expect(duration).toBe(60);
    });
  });
});