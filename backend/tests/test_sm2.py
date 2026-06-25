"""单测: SM-2 算法 (Phase 1b-2)

覆盖:
- 各种 quality 分数下的边界
- 重复答对的 interval 增长
- 答错的 rep 重置 + interval=1
- ease_factor 边界 (min 1.3)
"""

import pytest
from services.learning_progress_service import calculate_next_srs, calc_next_review_at


class TestSM2Quality:
    """quality 0-5 各档"""

    def test_quality_0_failed_total_reset(self):
        srs = calculate_next_srs(0)
        assert srs["repetition_count"] == 0
        assert srs["interval_days"] == 1
        assert srs["next_status"] == "learning"
        assert srs["ease_factor"] < 2.5  # ease 降

    def test_quality_1_partial_forgot(self):
        srs = calculate_next_srs(1)
        assert srs["repetition_count"] == 0
        assert srs["interval_days"] == 1
        assert srs["next_status"] == "learning"

    def test_quality_2_wrong_resets_repetition(self):
        srs = calculate_next_srs(2, repetition_count=5, interval_days=30)
        assert srs["repetition_count"] == 0
        assert srs["interval_days"] == 1

    def test_quality_3_passing_starts_repetition(self):
        srs = calculate_next_srs(3)
        assert srs["repetition_count"] == 1
        assert srs["interval_days"] == 1
        assert srs["next_status"] == "learning"

    def test_quality_4_good_increments(self):
        srs = calculate_next_srs(4)
        assert srs["repetition_count"] == 1
        assert srs["interval_days"] == 1

    def test_quality_5_perfect_increments_ease(self):
        srs = calculate_next_srs(5)
        assert srs["repetition_count"] == 1
        assert srs["interval_days"] == 1
        assert srs["ease_factor"] > 2.5  # ease 升


class TestSM2IntervalGrowth:
    """重复答对 → interval 增长"""

    def test_repeat_correct_grows_interval(self):
        """连答对 5 次, interval 应该从 1 → 6 → 增长"""
        prev_interval = 0
        for _ in range(5):
            srs = calculate_next_srs(
                5, interval_days=prev_interval, repetition_count=3,
            )
            prev_interval = srs["interval_days"]
        # 起始 rep=3 (已 master 阈值附近), 多次 5 分后 interval 应该 ≥ 6
        assert prev_interval >= 6

    def test_mastered_after_5_repetitions(self):
        """rep >= 5 → status=mastered"""
        srs = calculate_next_srs(5, repetition_count=4)
        assert srs["repetition_count"] == 5
        assert srs["next_status"] == "mastered"


class TestSM2EaseBounds:
    """ease_factor 必须 >= 1.3 (SM-2 最小值)"""

    def test_ease_floor_13(self):
        """连续 quality=0 不会让 ease 跌破 1.3"""
        ease = 2.5
        for _ in range(20):
            srs = calculate_next_srs(0, ease_factor=ease)
            ease = srs["ease_factor"]
        assert ease >= 1.3

    def test_ease_quality_5_keeps_growing(self):
        """连续 quality=5, ease 应该稳定增长"""
        srs1 = calculate_next_srs(5, ease_factor=2.5)
        srs2 = calculate_next_srs(5, ease_factor=srs1["ease_factor"])
        assert srs2["ease_factor"] >= srs1["ease_factor"]


class TestSM2QualityOutOfRange:
    """边界值处理"""

    def test_quality_negative_clamped_to_0(self):
        srs = calculate_next_srs(-1)
        assert srs["repetition_count"] == 0  # 视同失败

    def test_quality_above_5_clamped_to_5(self):
        srs = calculate_next_srs(10)
        # 视同满分
        assert srs["ease_factor"] > 2.5


class TestCalcNextReviewAt:
    def test_returns_datetime_with_correct_offset(self):
        from datetime import datetime, timezone, timedelta

        result = calc_next_review_at(7)
        delta = result - datetime.now(timezone.utc)
        # 允许 ±1秒误差
        assert abs(delta.total_seconds() - 7 * 86400) < 1

    def test_zero_interval_means_immediately(self):
        from datetime import datetime, timezone

        result = calc_next_review_at(0)
        delta = result - datetime.now(timezone.utc)
        assert abs(delta.total_seconds()) < 1


class TestSM2Integration:
    """真实场景: 题目答错的完整周期"""

    def test_alternating_correct_wrong(self):
        """q=5, q=0, q=5 → rep 应: 1, 0, 1"""
        srs1 = calculate_next_srs(5, repetition_count=0)
        assert srs1["repetition_count"] == 1

        srs2 = calculate_next_srs(0, repetition_count=srs1["repetition_count"])
        assert srs2["repetition_count"] == 0  # 重置

        srs3 = calculate_next_srs(5, repetition_count=srs2["repetition_count"])
        assert srs3["repetition_count"] == 1  # 重新计数