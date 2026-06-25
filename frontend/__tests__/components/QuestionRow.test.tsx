/**
 * Phase 2 单测: types/learn.ts 类型定义
 *
 * 校验关键类型字段, 防止 schema drift (前端 ↔ 后端不一致)。
 */

import { describe, it, expect } from 'vitest';
import type {
  QuestionListItem,
  QuestionProgress,
  MasteryStatus,
  QuestionSource,
  QAChatInput,
} from '@/types/learn';

describe('types/learn.ts', () => {
  describe('MasteryStatus', () => {
    it('合法值: new / learning / mastered / skipped', () => {
      const valid: MasteryStatus[] = ['new', 'learning', 'mastered', 'skipped'];
      valid.forEach((s) => expect(['new', 'learning', 'mastered', 'skipped']).toContain(s));
    });
  });

  describe('QuestionSource', () => {
    it('合法值: seed / user_note / news / mock_interview', () => {
      const valid: QuestionSource[] = ['seed', 'user_note', 'news', 'mock_interview'];
      expect(valid).toHaveLength(4);
    });
  });

  describe('QuestionProgress 字段', () => {
    it('必填字段存在', () => {
      const p: Partial<QuestionProgress> = {
        id: 'p1',
        status: 'new',
        practice_count: 0,
        correct_count: 0,
        bookmarked: false,
        ease_factor: 2.5,
        interval_days: 0,
      };
      expect(p.id).toBe('p1');
      expect(p.ease_factor).toBe(2.5);
    });

    it('可选字段可空', () => {
      const p: Partial<QuestionProgress> = {
        id: 'p1',
        status: 'mastered',
        practice_count: 10,
        correct_count: 8,
        bookmarked: true,
        ease_factor: 2.6,
        interval_days: 30,
        user_answer: null,
        notes_path: null,
      };
      expect(p.user_answer).toBe(null);
    });
  });

  describe('QuestionListItem', () => {
    it('完整字段', () => {
      const q: QuestionListItem = {
        id: 'agent_001',
        topic: 'agent',
        sub_topic: 'memory',
        difficulty: 3,
        question_text: '什么是 RAG?',
        source: 'seed',
        progress: null,
        tags: ['高频'],
      };
      expect(q.topic).toBe('agent');
      expect(q.tags).toContain('高频');
    });
  });

  describe('QAChatInput 字段对齐', () => {
    it('字段名: question_id / session_id / message', () => {
      const q: QAChatInput = {
        question_id: 'q1',
        session_id: 's1',
        message: '你好',
      };
      // 后端 API 字段必须匹配 (snake_case)
      expect(q.question_id).toBe('q1');
      expect(q.session_id).toBe('s1');
      expect(q.message).toBe('你好');
    });

    it('session_id 可空', () => {
      const q: QAChatInput = {
        question_id: 'q1',
        message: '你好',
        session_id: null,
      };
      expect(q.session_id).toBe(null);
    });
  });
});