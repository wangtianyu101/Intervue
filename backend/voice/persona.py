"""InterviewerPersona — virtual interviewer personality engine.

Wraps raw Agent output in natural interviewer language:
- Transition phrases between questions
- Feedback tones based on answer quality
- Consistent interviewer voice (Alex)
"""

import random

class InterviewerPersona:
    """Wraps LangGraph agent output in conversational interviewer style."""

    def __init__(self, name: str = "Alex", style: str = "professional-friendly"):
        self.name = name
        self.style = style

        self.openings = {
            "first_question": [
                "好的，我们开始吧。",
                "那我们先从基础开始。",
                "准备好了吗？第一个问题——",
            ],
            "next_question": [
                "好的。那我们换一个方向——",
                "不错，接下来——",
                "嗯。下一个问题——",
                "好的，继续——",
            ],
            "after_interrupt": [
                "抱歉，你刚才说的——",
                "好的，那——",
                "嗯，继续——",
            ],
        }

        self.transitions = {
            "correct": [
                "对，答得很好。", "基本正确。", "嗯，不错。",
            ],
            "partial": [
                "方向对了。还能再深入吗？", "可以再补充一点。",
                "我给你个提示——",
            ],
            "wrong": [
                "没关系，这个确实容易搞混。", "嗯，我们换个角度。",
                "这个不太对，不过没问题——",
            ],
            "probe": [
                "能再展开一点吗？", "具体说说？", "举个例子？",
                "这个点你实际用过吗？",
            ],
        }

        self.closings = [
            "好的，今天的面试就到这里。你的表现不错，有几个方向可以再深入。稍后给你一份完整的报告。",
            "好的，面试结束。感谢你的时间。报告马上出来，你可以去面试记录里查看。",
        ]

    def wrap(self, agent_output: dict) -> str:
        """Wrap raw agent output in interviewer persona."""
        action = agent_output.get("action", "next_question")
        text = agent_output.get("followup_text") or agent_output.get("question_text", "")

        if not text:
            return random.choice(self.closings)

        if action == "next_question":
            prefix = random.choice(self.openings["next_question"])
            return f"{prefix} {text}"

        if action in ("followup", "probe", "give_hint"):
            prefix = random.choice(self.transitions["probe"])
            return f"{prefix} {text}"

        if action == "skip_and_record":
            prefix = random.choice(self.transitions["wrong"])
            return f"{prefix} {text}"

        return text

    def greeting(self, tech_stack: list[str]) -> str:
        stack_str = "、".join(tech_stack[:4]) if tech_stack else "通用技术"
        return (
            f"你好，我是{self.name}，今天的面试官。"
            f"我看到你的技术栈主要是{stack_str}，我们就围绕这些来聊。"
            f"准备好了吗？"
        )

    def closing(self) -> str:
        return random.choice(self.closings)

    def interrupted_response(self) -> str:
        return random.choice(self.openings["after_interrupt"])
