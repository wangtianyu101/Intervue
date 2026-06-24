"""SQLAlchemy ORM models for CodeMock.

All primary keys are String(36) to match the existing UUID-as-string pattern
used throughout the API layer (str(uuid4()), str(interview.id), etc.).

JSON columns use SQLAlchemy's JSON type, which maps to MySQL 8.4 JSON.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Computed,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from core.database import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    github_id = Column(String(64), unique=True, nullable=True)       # nullable for email-password users
    github_username = Column(String(128), nullable=True)              # nullable for email-password users
    avatar_url = Column(String(512), nullable=True)
    email = Column(String(256), nullable=True, unique=True)           # unique — used as login credential
    password_hash = Column(String(256), nullable=True)                # bcrypt hash, nullable for GitHub OAuth users
    display_name = Column(String(128), nullable=True)                 # user-chosen display name
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    profiles = relationship("Profile", back_populates="user")
    interviews = relationship("Interview", back_populates="user", foreign_keys="Interview.user_id")
    reports = relationship("Report", back_populates="user", foreign_keys="Report.user_id")


class Profile(Base):
    __tablename__ = "profiles"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    tech_stack = Column(JSON, default=list)
    years_of_exp = Column(Integer, default=0)
    current_level = Column(String(32), default="mid")
    target_companies = Column(JSON, default=list)
    resume_summary = Column(Text, nullable=True)
    skill_map = Column(JSON, default=dict)
    # Phase 1a · 学习复习模块扩字段 (面试题库-技术设计.md 2.8)
    weak_topics = Column(JSON, default=list)
    mastered_topics = Column(JSON, default=list)
    learning_trajectory = Column(JSON, default=dict)
    last_active_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # Relationships
    user = relationship("User", back_populates="profiles")
    interviews = relationship("Interview", back_populates="profile")


class Interview(Base):
    __tablename__ = "interviews"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    profile_id = Column(String(36), ForeignKey("profiles.id"), nullable=False)
    round = Column(String(32), default="round1")
    style = Column(String(32), default="standard")
    status = Column(String(32), default="in_progress")
    started_at = Column(DateTime(timezone=True), default=_utcnow)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    total_questions = Column(Integer, default=0)
    overall_score = Column(Float, nullable=True)
    # P0-2: Session persistence — serialized InterviewState snapshot
    state_snapshot = Column(JSON, nullable=True)
    # User actions: bookmark + soft delete. Nullable defaults so existing
    # dev.db rows stay valid; new rows get the proper defaults.
    is_favorite = Column(Boolean, default=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    # 注: 面试题库-技术设计.md 2.9 列出 is_practice/practice_topic/practice_count,
    # stage 5 决策 D3 (b) 不动 interviews 表 → 不加这些字段

    # Relationships
    user = relationship("User", back_populates="interviews", foreign_keys=[user_id])
    profile = relationship("Profile", back_populates="interviews")
    question_records = relationship("QuestionRecord", back_populates="interview")
    reports = relationship("Report", back_populates="interview")


class QuestionRecord(Base):
    __tablename__ = "question_records"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    interview_id = Column(String(36), ForeignKey("interviews.id"), nullable=False)
    question_id = Column(String(64), nullable=True)  # nullable: seed data uses semantic IDs
    question_text = Column(Text, nullable=False)
    user_answer = Column(Text, nullable=True)
    followup_chain = Column(JSON, default=list)
    score = Column(Integer, nullable=True)
    blind_spots = Column(JSON, default=list)
    time_spent = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    interview = relationship("Interview", back_populates="question_records")


class Question(Base):
    """Seed question bank. IDs are semantic (not UUIDs), e.g. 'agent_001'."""

    __tablename__ = "questions"

    id = Column(String(64), primary_key=True)
    topic = Column(String(64), nullable=False)
    sub_topic = Column(String(64), nullable=False)
    difficulty = Column(Integer, default=3)
    round = Column(String(32), default="round1")
    question_text = Column(Text, nullable=False)
    answer_key_points = Column(JSON, default=list)
    followup_tree = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=_utcnow)


class Report(Base):
    __tablename__ = "reports"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    interview_id = Column(String(36), ForeignKey("interviews.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    radar_data = Column(JSON, default=dict)
    top_blind_spots = Column(JSON, default=list)
    improvement_plan = Column(JSON, default=list)
    summary = Column(Text, nullable=True)
    overall_score = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    interview = relationship("Interview", back_populates="reports")
    user = relationship("User", back_populates="reports", foreign_keys=[user_id])


# ╔════════════════════════════════════════════════════════════════════╗
# ║  Phase 1a · 学习复习模块（5 新表）                                  ║
# ║  配套设计: docs/10-架构/面试题库-技术设计.md 2.3-2.7                ║
# ╚════════════════════════════════════════════════════════════════════╝


class QuestionProgress(Base):
    """题库题目的用户掌握度 (SRS / SM-2)。每对 (user_id, question_id) 一行。

    注: user_id 没有 FK (MySQL 8 分区表不允许 FK)。应用层保证 referential integrity
    (所有写入都从已认证 user_id 出发, 删除 user 用 soft delete 或 CASCADE 在 user 表层做)。
    """

    __tablename__ = "question_progress"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    user_id = Column(String(36), nullable=False, index=True)
    question_id = Column(String(64), nullable=False, index=True)
    status = Column(String(16), nullable=False, default="new")  # new/learning/mastered/skipped
    practice_count = Column(Integer, nullable=False, default=0)
    correct_count = Column(Integer, nullable=False, default=0)
    bookmarked = Column(Boolean, nullable=False, default=False)
    source = Column(String(32), nullable=True)  # seed/user_note/news/mock_interview
    last_review_at = Column(DateTime(timezone=True), nullable=True)
    next_review_at = Column(DateTime(timezone=True), nullable=True, index=True)
    review_count = Column(Integer, nullable=False, default=0)
    ease_factor = Column(Float, nullable=False, default=2.5)
    interval_days = Column(Integer, nullable=False, default=0)
    first_practiced_at = Column(DateTime(timezone=True), nullable=True)
    last_practiced_at = Column(DateTime(timezone=True), nullable=True)
    user_answer = Column(Text, nullable=True)
    notes_path = Column(String(256), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "question_id", name="uniq_user_question"),
        Index("idx_qp_user_status", "user_id", "status"),
        Index("idx_qp_user_next_review", "user_id", "next_review_at", "status"),
        Index("idx_qp_user_source", "user_id", "source"),
        Index("idx_qp_user_bookmarked", "user_id", "bookmarked", "status"),
    )


class LearningSession(Base):
    """题库练习 session。每次 /learn 进入算一次。"""

    __tablename__ = "learning_sessions"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    duration_sec = Column(Integer, nullable=False, default=0)
    type = Column(String(16), nullable=False, default="practice")  # practice/review/qa
    items = Column(JSON, default=list)  # [{question_id, status, duration_sec, score}]
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        Index("idx_ls_user_started", "user_id", "started_at"),
        Index("idx_ls_user_type", "user_id", "type", "started_at"),
    )


class ReviewSchedule(Base):
    """SRS 复习调度。复用 question_progress 的 SRS，但允许指向其他类型 (note/resource)。"""

    __tablename__ = "review_schedules"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    item_type = Column(String(16), nullable=False)  # question/note/resource
    item_id = Column(String(64), nullable=False)
    last_reviewed_at = Column(DateTime(timezone=True), nullable=True)
    next_review_at = Column(DateTime(timezone=True), nullable=False, index=True)
    interval_days = Column(Integer, nullable=False, default=1)
    ease_factor = Column(Float, nullable=False, default=2.5)
    repetition_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "item_type", "item_id", name="uniq_user_item"),
        Index("idx_rs_user_next_review", "user_id", "next_review_at"),
    )


class StudyPlan(Base):
    """学习计划。每条计划含 N 周的 weekly_target + 进度。"""

    __tablename__ = "study_plans"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    goal = Column(String(256), nullable=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    status = Column(String(16), nullable=False, default="active")  # active/completed/archived
    weekly_target = Column(JSON, default=list)  # [{week_idx, target_count, target_topics}]
    progress = Column(JSON, default=dict)  # {done_count, mastered_count, weak_topics_remaining}
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        Index("idx_sp_user_status", "user_id", "status"),
        Index("idx_sp_user_end_date", "user_id", "end_date"),
    )


class MonthlyReport(Base):
    """学习月报。每对 (user_id, year, month) 一行，content_md 是 LLM 生成的报告。"""

    __tablename__ = "monthly_reports"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    content_md = Column(Text, nullable=False)
    summary_stats = Column(JSON, nullable=False)
    obsidian_synced_at = Column(DateTime(timezone=True), nullable=True)
    obsidian_path = Column(String(256), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "year", "month", name="uniq_user_year_month"),
        CheckConstraint("month >= 1 AND month <= 12", name="ck_mr_month_range"),
        Index("idx_mr_user_year_month", "user_id", "year", "month"),
    )


# ╔════════════════════════════════════════════════════════════════════╗
# ║  Phase 1a · 候选 A-E (5 张) + 归档表 (1 张)                         ║
# ║  配套: docs/10-架构/面试题库-技术设计.md 阶段 4.1 + 用户反馈         ║
# ╚════════════════════════════════════════════════════════════════════╝


class QuestionTag(Base):
    """灵活标签。is_system=True = 系统预设（如 "高频"/"字节考过"），user_id=NULL；
    user_id 非空 = 用户自定义标签。

    唯一性约束 (MySQL 不支持 partial unique):
    - 系统标签 (user_id IS NULL): name 全局唯一
    - 用户标签 (user_id IS NOT NULL): (user_id, name) 唯一
    用 generated column trick: NULL user_id 映射为特殊字符串 '__system__'，
    然后 UNIQUE (user_id_key, name) 一条搞定。
    """

    __tablename__ = "question_tags"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    name = Column(String(64), nullable=False)
    color = Column(String(16), nullable=True)  # e.g. '#ff5577' / 'indigo'
    is_system = Column(Boolean, nullable=False, default=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    # Generated column: NULL → '__system__', other → user_id 本身
    # 这样所有行都参与 UNIQUE, NULL 不再走 SQL "NULL != NULL" 漏洞
    user_id_key = Column(
        String(64),
        Computed("COALESCE(user_id, '__system__')", persisted=True),
        nullable=False,
    )
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        UniqueConstraint("user_id_key", "name", name="uniq_qt_userid_key_name"),
    )


class QuestionTagMap(Base):
    """Tag ↔ Question 多对多映射。"""

    __tablename__ = "question_tag_maps"

    question_id = Column(String(64), ForeignKey("questions.id", ondelete="CASCADE"), primary_key=True)
    tag_id = Column(String(36), ForeignKey("question_tags.id", ondelete="CASCADE"), primary_key=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        Index("idx_qtm_tag_question", "tag_id", "question_id"),
    )


class UserQuestionNote(Base):
    """用户对某题的笔记（题库内联 markdown，不依赖 Obsidian）。"""

    __tablename__ = "user_question_notes"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id = Column(String(64), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    content_md = Column(Text, nullable=False, default="")
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "question_id", name="uniq_uqn_user_question"),
    )


class BookmarkCollection(Base):
    """收藏夹分组。QuestionProgress.collection_id FK 过来。"""

    __tablename__ = "bookmark_collections"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(64), nullable=False)
    color = Column(String(16), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uniq_bc_user_name"),
    )


class QuestionAnswerLog(Base):
    """答题明细（每题每次的分数/盲点/停留时间）。用于分数曲线分析。"""

    __tablename__ = "question_answer_logs"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id = Column(String(64), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True)
    score = Column(Integer, nullable=True)  # 1-5
    blind_spots = Column(JSON, default=list, nullable=False)
    duration_sec = Column(Integer, nullable=False, default=0)
    source = Column(String(32), nullable=True)  # practice / review / mock_interview
    answered_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False, index=True)

    __table_args__ = (
        Index("idx_qal_user_question_time", "user_id", "question_id", "answered_at"),
    )


class UserQuestion(Base):
    """用户自建题。题源 user_note 走这里。"""

    __tablename__ = "user_questions"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    question_text = Column(Text, nullable=False)
    answer = Column(Text, nullable=True)  # 用户写的参考回答
    topic = Column(String(64), nullable=True)
    sub_topic = Column(String(64), nullable=True)
    difficulty = Column(Integer, default=3)
    tags = Column(JSON, default=list, nullable=False)  # 用户标签 (字符串数组)
    source = Column(String(32), nullable=False, default="user_note")  # user_note/news/...
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        Index("idx_uq_user_topic", "user_id", "topic"),
    )


class QuestionProgressArchive(Base):
    """question_progress 冷数据归档表。

    与 QuestionProgress 同 schema (无外键约束, 避免被原表 FK 反向引用)。
    archive_service.py 月度 cron 把 mastered > 1Y 的行迁到这里。
    """

    __tablename__ = "question_progress_archive"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), nullable=False, index=True)
    question_id = Column(String(64), nullable=False, index=True)
    status = Column(String(16), nullable=False)
    practice_count = Column(Integer, nullable=False, default=0)
    correct_count = Column(Integer, nullable=False, default=0)
    bookmarked = Column(Boolean, nullable=False, default=False)
    source = Column(String(32), nullable=True)
    last_review_at = Column(DateTime(timezone=True), nullable=True)
    next_review_at = Column(DateTime(timezone=True), nullable=True)
    review_count = Column(Integer, nullable=False, default=0)
    ease_factor = Column(Float, nullable=False, default=2.5)
    interval_days = Column(Integer, nullable=False, default=0)
    first_practiced_at = Column(DateTime(timezone=True), nullable=True)
    last_practiced_at = Column(DateTime(timezone=True), nullable=True)
    user_answer = Column(Text, nullable=True)
    notes_path = Column(String(256), nullable=True)
    archived_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)  # 归档时间
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("idx_qpa_user_status", "user_id", "status"),
    )


class QASession(Base):
    """题库问答 session。每个 session 针对一道题, 含多轮 user/assistant 消息。

    设计决策: 消息存 JSON (不分子表), 因为:
    - 单 session 消息数 < 100 (1v1 模拟面试场景)
    - JSON 让 history 1 次 round-trip 拉完
    """

    __tablename__ = "qa_sessions"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id = Column(String(64), nullable=False, index=True)
    messages = Column(JSON, default=list, nullable=False)
    # [{role: user/assistant, content, ts: iso}, ...]
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        Index("idx_qas_user_question", "user_id", "question_id"),
        Index("idx_qas_user_created", "user_id", "created_at"),
    )
