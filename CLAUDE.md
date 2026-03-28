# APEX — EstimatingEngine

## Stack
- Backend: FastAPI + SQLAlchemy + SQLite at apex/backend/
- Frontend: React/Vite + Tailwind at apex/frontend/
- 7 agents, all have LLM + rule-based fallbacks
- Multi-model: Gemini 2.5 Flash (Agent 2), Claude Sonnet (3,4,6,7), Haiku (5), Pure Python (1, 6-math)
- Never let LLM touch final dollar amounts — math is always deterministic Python
- Pydantic contracts between all agents (pipeline_contracts.py)
- Per-agent routing via get_llm_provider(agent_number=N)

## Rules
- Always preserve fallback paths
- One spec per feature
- Never combine unrelated changes
