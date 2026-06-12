---
name: intervue-dev
description: Intervue (CodeMock) project development — AI mock interview platform with LangGraph + FastAPI + Next.js + WebRTC voice. Use when modifying the Intervue codebase, adding features, fixing bugs, or understanding the multi-agent architecture.
---

# Intervue (CodeMock) 开发

## 项目概览

CodeMock 是一个 AI 模拟面试平台，核心差异化是**追问引擎**——不是静态题库，而是根据用户回答动态追问的 AI 面试官。

| 层级 | 技术栈 |
|------|--------|
| Agent 引擎 | LangGraph 1.0 + LangChain 1.0 |
| 后端 | FastAPI + SQLAlchemy 2.0 async + MySQL 8.4 |
| 语音 | LiveKit WebRTC + WhisperLive STT + Piper TTS |
| 前端 | Next.js 15 + React 19 + Tailwind CSS 4 |
| LLM | DeepSeek V3 (via siliconflow/OpenAI-compatible API) |

## 关键文件路径

```
Intervue/
├── docs/CODE-MOCK.md              ← 完整架构文档（含 P0 实现状态）
├── backend/
│   ├── models/__init__.py          ← 6 个 SQLAlchemy ORM 模型（P0 完成）
│   ├── agents/
│   │   ├── interview_graph.py      ← LangGraph StateGraph 定义
│   │   ├── question_agent.py       ← 选题引擎（难度匹配 + 盲点优先）
│   │   ├── followup_agent.py       ← ⭐ 追问引擎（核心差异化）
│   │   ├── evaluate_agent.py       ← 回答评估（1-5 分 + 盲点 + 反馈）
│   │   ├── report_agent.py         ← 报告生成（11 维雷达图）
│   │   └── states.py               ← InterviewState TypedDict
│   ├── services/
│   │   ├── interview_service.py    ← InterviewSessionManager（含持久化）
│   │   └── seed_service.py         ← 种子数据加载
│   ├── api/
│   │   ├── auth.py                 ← GitHub OAuth + dev-login
│   │   ├── interview.py            ← 面试核心 API（含持久化调用）
│   │   ├── profile.py              ← 用户画像管理
│   │   └── report.py               ← 报告 API
│   ├── voice/
│   │   ├── stt.py                  ← 三路 STT：SimpleSTT / DashScope / WhisperLive
│   │   ├── tts.py                  ← Piper TTS 中文语音
│   │   └── livekit_worker.py       ← LiveKit VoicePipelineAgent
│   ├── core/
│   │   ├── database.py             ← AsyncEngine + Base + get_db
│   │   ├── config.py               ← pydantic-settings (.env)
│   │   └── dependencies.py         ← JWT 认证 + 虚拟用户 fallback
│   └── seed_data/                  ← 50 道种子题（agent_core / rag_tech / langgraph / java_backend）
└── frontend/
    └── pages/                      ← 6 个页面（index / onboarding / setup / interview / report / _app）
```

## When to Use This Skill

- 修改或新增后端 API / Agent / 模型
- 理解 Intervue 项目架构和数据流
- 添加新题库或种子数据
- 调试语音管线（STT/TTS/LiveKit）
- 前端面试页面改动
- 数据库 migration 或模型变更
- 部署配置（Docker Compose）

## 架构约定

### ORM Models（P0 已建立）`backend/models/__init__.py`

6 个模型，全部 String(36) UUID 主键。新增模型遵循此模式：

```python
from core.database import Base

class NewModel(Base):
    __tablename__ = "new_models"
    id = Column(String(36), primary_key=True, default=_new_uuid)
    # FK: String(36), nullable=False
    # JSON: Column(JSON, default=dict/list)
    # Timestamps: DateTime(timezone=True), default=_utcnow
```

**约束**：
- 不用 `UUID` 原生类型 — 所有 ID 在代码里都是 `str(uuid4())` 流式传递
- 不用 MySQL ENUM — 用 String(32) + 代码层校验
- JSON 列用 `sqlalchemy.JSON`（MySQL 8.4 原生支持）
- `created_at` 用 `default=_utcnow`，`updated_at` 加 `onupdate=_utcnow`

### API 路由模式

```python
@router.post("/{id}/action")
async def some_action(
    id: UUID,
    data: RequestSchema,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 1. 鉴权（通过 get_current_user）
    # 2. 查资源 → 404
    # 3. 业务逻辑
    # 4. db.add / db.commit
    # 5. 返回
```

### Session 持久化（P0 已建立）

每次 session 状态变更后调用 `session_manager.save_state()`：
- `POST /api/interviews` → 创建 session 后 save
- `POST /{id}/next-question` → 选题后 save
- `POST /records/{id}/answer` → 评估后 save

Session 丢失时的恢复链：内存 → `restore_from_db()` → 重建新 session → fallback 直接 agent 调用

### Agent 开发

`InterviewSessionManager` 直接操作 `session["state"]`（dict），不调用 LangGraph graph。这是**有意为之**————REST API 使用请求/响应模式，不适合流式 graph 调用。

添加新 Agent 节点时：
1. 在 `agents/` 下创建新文件
2. 在 `states.py` 的 `InterviewState` 添加相关字段（`Annotated[list, operator.add]` 用于累积字段）
3. 在 `interview_service.py` 的 `process_answer` 或其他方法中调用
4. 确保 `_serializable_state` 能序列化新字段（或自动跳过）

## 已知待办

| 优先级 | 任务 | 工作量 |
|------|------|--------|
| P1 | 追问引擎 2.0 — LLM 动态生成追问，去掉手写 JSON 依赖 | 2-3d |
| P1 | 报告生成接真实评估数据（当前 stub 写死 3 分） | 1d |
| P2 | 简历解析 → 自动提取技能栈 → 影响出题策略 | 1d |
| P2 | 面试回放页面：逐字稿 + 标注 + 改进建议 | 2d |
| P2 | 题库扩展到系统设计、行为面试、薪资谈判 | 持续 |
| P3 | Alembic migration 配置 | 0.5d |

## 快速命令

```bash
cd Intervue

# 启动全部服务
docker-compose up -d

# 启动单个服务
docker-compose up -d mysql
docker-compose up -d backend

# 进容器调试
docker-compose exec backend python -c "from models import User; print('OK')"

# 种子数据灌入
docker-compose exec backend python -c "
from core.database import async_session, init_db
from services.seed_service import seed_questions
import asyncio
asyncio.run(seed_questions(async_session()))
"

# 运行 Agent 单元测试
docker-compose exec backend python -m pytest tests/test_core.py -v
```
