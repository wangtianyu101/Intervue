"""SQLAlchemy ORM models for CodeMock.

All primary keys are String(36) to match the existing UUID-as-string pattern
used throughout the API layer (str(uuid4()), str(interview.id), etc.).

JSON columns use SQLAlchemy's JSON type, which maps to MySQL 8.4 JSON.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Integer, Float, Text, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship

from core.database import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    github_id = Column(String(64), unique=True, nullable=False)
    github_username = Column(String(128), nullable=False)
    avatar_url = Column(String(512), nullable=True)
    email = Column(String(256), nullable=True)
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
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    interview = relationship("Interview", back_populates="reports")
    user = relationship("User", back_populates="reports", foreign_keys=[user_id])
