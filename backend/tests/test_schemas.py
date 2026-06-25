"""单测: Pydantic schema 校验 (Phase 1c)

覆盖:
- SubmitAnswerInput score 0-5 边界
- StartSessionInput type literal
- ProfileUpdate 各字段 optional
- QuestionListFilter difficulty 1-5
"""

import pytest
from pydantic import ValidationError

from schemas.learn import (
    SubmitAnswerInput,
    StartSessionInput,
    QuestionListFilter,
    UpdateProgressInput,
    EndSessionInput,
    SessionItem,
    CreateStudyPlanInput,
    QAChatInput,
    CreateUserQuestionInput,
    MasteryStatus,
)
from schemas.profile import ProfileUpdate, ProfileOut


class TestSubmitAnswerInput:
    def test_valid_score_3(self):
        s = SubmitAnswerInput(user_answer='x', score=3)
        assert s.score == 3

    def test_valid_score_0(self):
        s = SubmitAnswerInput(user_answer='x', score=0)
        assert s.score == 0

    def test_valid_score_5(self):
        s = SubmitAnswerInput(user_answer='x', score=5)
        assert s.score == 5

    def test_score_6_rejected(self):
        with pytest.raises(ValidationError):
            SubmitAnswerInput(user_answer='x', score=6)

    def test_score_negative_rejected(self):
        with pytest.raises(ValidationError):
            SubmitAnswerInput(user_answer='x', score=-1)

    def test_missing_score_rejected(self):
        with pytest.raises(ValidationError):
            SubmitAnswerInput(user_answer='x')

    def test_blind_spots_default_empty(self):
        s = SubmitAnswerInput(user_answer='x', score=3)
        assert s.blind_spots == []

    def test_source_default_practice(self):
        s = SubmitAnswerInput(user_answer='x', score=3)
        assert s.source == 'practice'


class TestStartSessionInput:
    def test_default_practice(self):
        s = StartSessionInput()
        assert s.type == 'practice'

    def test_valid_type_review(self):
        s = StartSessionInput(type='review')
        assert s.type == 'review'

    def test_valid_type_qa(self):
        s = StartSessionInput(type='qa')
        assert s.type == 'qa'

    def test_invalid_type_rejected(self):
        with pytest.raises(ValidationError):
            StartSessionInput(type='bogus')


class TestQuestionListFilter:
    def test_defaults(self):
        f = QuestionListFilter()
        assert f.topic is None
        assert f.difficulty is None
        assert f.page == 1
        assert f.size == 20
        assert f.sort == 'id'

    def test_difficulty_1(self):
        f = QuestionListFilter(difficulty=1)
        assert f.difficulty == 1

    def test_difficulty_5(self):
        f = QuestionListFilter(difficulty=5)
        assert f.difficulty == 5

    def test_difficulty_0_rejected(self):
        with pytest.raises(ValidationError):
            QuestionListFilter(difficulty=0)

    def test_difficulty_6_rejected(self):
        with pytest.raises(ValidationError):
            QuestionListFilter(difficulty=6)

    def test_invalid_sort_rejected(self):
        with pytest.raises(ValidationError):
            QuestionListFilter(sort='garbage')

    def test_size_max_100(self):
        with pytest.raises(ValidationError):
            QuestionListFilter(size=101)


class TestEndSessionInput:
    def test_empty_items_ok(self):
        e = EndSessionInput(items=[])
        assert e.items == []

    def test_items_with_score(self):
        e = EndSessionInput(items=[{
            'question_id': 'q1', 'status': 'mastered',
            'duration_sec': 60, 'score': 5,
        }])
        assert len(e.items) == 1
        assert e.items[0].score == 5


class TestCreateStudyPlanInput:
    def test_minimal(self):
        p = CreateStudyPlanInput(
            name='Q3 plan', start_date='2026-07-01', end_date='2026-09-30',
        )
        assert p.name == 'Q3 plan'
        assert p.status == 'active'

    def test_missing_required_name_rejected(self):
        with pytest.raises(ValidationError):
            CreateStudyPlanInput(start_date='2026-07-01', end_date='2026-09-30')

    def test_invalid_status_rejected(self):
        with pytest.raises(ValidationError):
            CreateStudyPlanInput(
                name='p', start_date='2026-07-01', end_date='2026-09-30',
                status='invalid',
            )


class TestQAChatInput:
    def test_message_required(self):
        with pytest.raises(ValidationError):
            QAChatInput(question_id='q1')

    def test_session_id_optional(self):
        q = QAChatInput(question_id='q1', message='hello')
        assert q.session_id is None

    def test_with_session_id(self):
        q = QAChatInput(question_id='q1', message='hello', session_id='s1')
        assert q.session_id == 's1'


class TestCreateUserQuestionInput:
    def test_minimal(self):
        u = CreateUserQuestionInput(question_text='什么是 RAG?')
        assert u.difficulty == 3
        assert u.tags == []
        assert u.source == 'user_note'

    def test_difficulty_5(self):
        u = CreateUserQuestionInput(question_text='x', difficulty=5)
        assert u.difficulty == 5

    def test_difficulty_6_rejected(self):
        with pytest.raises(ValidationError):
            CreateUserQuestionInput(question_text='x', difficulty=6)


class TestProfileUpdate:
    def test_all_optional(self):
        p = ProfileUpdate()
        assert p.tech_stack is None
        assert p.summary is None

    def test_summary_d2_field(self):
        """D2 · Phase 1d: ProfileUpdate 加 summary 字段"""
        p = ProfileUpdate(summary='5年工程师')
        assert p.summary == '5年工程师'

    def test_skill_map_dict(self):
        p = ProfileUpdate(skill_map={'Python': 4})
        assert p.skill_map == {'Python': 4}