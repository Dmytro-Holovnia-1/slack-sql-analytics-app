# Future Development Roadmap

This roadmap outlines the strategic evolution of the analytics agent from the current MVP to a secure, scalable, and cost-efficient enterprise platform. It balances immediate practical needs with innovative AI patterns.

## 1. Enterprise Security & Governance
*Moving from a global read-only role to user-scoped data access.*
* **Row-Level Security (RLS) via Slack Identity:** Map `slack_user_id` to PostgreSQL roles. The database will automatically filter metrics at the query execution level, ensuring users only see data for apps they manage.
* **PII & Sensitive Data Masking:** Implement a middleware layer to scrub user inputs before they reach the LLM, preventing accidental leakage of internal project codenames or financial targets.
* **Adaptive Rate Limiting:** Token and request quotas per Slack user/channel to prevent budget exhaustion from runaway queries.

## 2. Cost & Context Optimization
*Solving the "Lost in the Middle" hallucination problem and reducing LLM API costs.*
* **Semantic Caching:** Introduce a Vector DB (e.g., Redis/Qdrant) to cache `(User Question -> SQL)` pairs. If a new question is semantically identical to a cached one (similarity > 0.95), bypass the LLM entirely and execute the cached SQL.
* **Sliding Window Summarization:** Use LangGraph's `RemoveMessage` API. When a Slack thread exceeds 10 messages, a fast, cheap model (e.g., Flash-Lite) compresses older context into a dense `SystemMessage`. This guarantees O(1) token cost per turn regardless of thread length.

## 3. Advanced Multi-Agent Orchestration
*Scaling beyond a single table to a 100+ table Data Warehouse.*
* **Dynamic Schema RAG:** Instead of injecting the entire DB schema into the prompt, embed table schemas into a vector store. A "Router Agent" retrieves only the relevant DDLs for the specific question.
* **Planner-Critic Architecture:**
  * *Planner:* Breaks down complex questions ("Compare US Android vs UK iOS ROI").
  * *Critic:* Validates the generated SQL via `EXPLAIN` dry-runs to catch performance bottlenecks (e.g., missing indexes, full table scans) *before* execution.

## 4. Ecosystem Integration via MCP
*Turning the bot into a platform.*
* **Model Context Protocol (MCP) Server:** Expose the validated Text-to-SQL engine as an MCP server. This allows other AI tools in the company (like Cursor, Claude Desktop, or internal agents) to securely query the analytics database using the exact same business glossary and RLS rules, without reinventing the SQL generation logic.

## 5. Automated Evaluation Framework
*Protecting against prompt drift and model updates.*
* **LLM-as-a-Judge CI/CD:** Integrate LangSmith Datasets into GitHub Actions.
* **Golden Dataset:** Maintain a suite of 100+ edge-case questions. Every prompt or model change must pass automated scoring for *Intent Accuracy*, *SQL Correctness*, and *Execution Success* before merging to `main`.
