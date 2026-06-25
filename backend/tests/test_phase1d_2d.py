"""单测: D2 (resume_summary 真摘要) 集成 (Phase 1d)

覆盖:
- resume_parser.extract_profile_from_text 返回值含 summary
- summary 长度 ≤ 250
- summary 缺失时自动兜底
"""

import pytest
from unittest.mock import patch, AsyncMock


class TestResumeParserSummary:
    """D2: extract_profile_from_text 返回 summary 字段"""

    def test_extract_returns_summary_field(self):
        """成功调用必须有 summary 字段"""
        from services.resume_parser import extract_profile_from_text

        async def run():
            # Mock LLM
            fake_response = AsyncMock()
            fake_response.content = '''{
                "tech_stack": ["Python", "LangChain"],
                "years_of_exp": 5,
                "current_level": "senior",
                "skill_map": {"Python": 4},
                "suggested_target_companies": ["字节"],
                "summary": "5年后端工程师, 主导过千万级系统。"
            }'''
            with patch("services.resume_parser._make_llm") as mock_llm:
                mock_llm.return_value.ainvoke = AsyncMock(return_value=fake_response)
                result = await extract_profile_from_text("sample resume text")
                return result

        result = pytest.run(run) if False else None
        # 用 asyncio 跑
        import asyncio
        result = asyncio.run(run())

        assert "summary" in result
        assert "5年后端工程师" in result["summary"]

    def test_summary_length_capped_at_250(self):
        """LLM 返回超长 summary 应该被截到 250"""
        from services.resume_parser import extract_profile_from_text

        long_summary = "X" * 500

        async def run():
            fake_response = AsyncMock()
            fake_response.content = f'''{{
                "tech_stack": [],
                "years_of_exp": 0,
                "current_level": "mid",
                "skill_map": {{}},
                "suggested_target_companies": [],
                "summary": "{long_summary}"
            }}'''
            with patch("services.resume_parser._make_llm") as mock_llm:
                mock_llm.return_value.ainvoke = AsyncMock(return_value=fake_response)
                return await extract_profile_from_text("x")

        import asyncio
        result = asyncio.run(run())
        assert len(result["summary"]) <= 250

    def test_summary_fallback_when_missing(self):
        """LLM 没返回 summary → 自动从 extracted fields 拼一段"""
        from services.resume_parser import extract_profile_from_text

        async def run():
            fake_response = AsyncMock()
            # 没有 summary 字段
            fake_response.content = '''{
                "tech_stack": ["Python"],
                "years_of_exp": 3,
                "current_level": "mid",
                "skill_map": {"Python": 3},
                "suggested_target_companies": ["小红书"]
            }'''
            with patch("services.resume_parser._make_llm") as mock_llm:
                mock_llm.return_value.ainvoke = AsyncMock(return_value=fake_response)
                return await extract_profile_from_text("x")

        import asyncio
        result = asyncio.run(run())
        assert result["summary"]  # 非空
        assert "3年" in result["summary"] or "mid" in result["summary"]


class TestProfileUpdateSummary:
    """D2: ProfileUpdate schema 加 summary 字段"""

    def test_summary_field_accepted(self):
        from schemas.profile import ProfileUpdate
        p = ProfileUpdate(summary="测试摘要")
        assert p.summary == "测试摘要"

    def test_summary_field_optional(self):
        from schemas.profile import ProfileUpdate
        p = ProfileUpdate()
        assert p.summary is None


class TestResumeTextNotStoredInSummary:
    """D2: PUT /me 改用 summary, resume_text 不再写入 resume_summary"""

    def test_profile_update_route_uses_summary(self):
        """读 api/profile.py:update_profile 源码验证"""
        import inspect
        from api import profile as prof_api
        src = inspect.getsource(prof_api.update_profile)
        # 关键变化: 不再有 `profile.resume_summary = data.resume_text`
        assert "profile.resume_summary = data.resume_text" not in src
        # 新行为: 用 data.summary
        assert "profile.resume_summary = data.summary" in src