# Rounds Analytics Slack Bot

An internal AI-powered Slack assistant for querying the Rounds app portfolio metrics using natural language. It converts user questions into safe PostgreSQL queries, executes them, and returns formatted insights, CSV exports, and raw SQL snippets directly in Slack.

## 🚀 Key Features

* **Text-to-SQL with Self-Repair:** Generates PostgreSQL queries and automatically fixes syntax/schema errors via an LLM repair loop.
* **Zero-Cost Artifact Retrieval:** Uses LangGraph Time Travel to serve CSV exports and SQL snippets from past states without re-triggering the LLM or database.
* **Strict Structured Outputs:** 100% of LLM calls use Gemini Native Structured Outputs (JSON Schema) with `temperature=0`. Zero regex parsing.
* **Database Security:** Executes queries via a restricted `chatbot_ro` PostgreSQL role with strict `statement_timeout` and application-level DML blocking.
* **Slack AI Assistant UI:** Integrates with Slack's native AI Assistant tab for dynamic status updates, suggested prompts, and clean thread management.

## 🏗 Architecture Decisions & Trade-offs

| Decision | Choice | Alternative | Rationale |
|---|---|---|---|
| **Orchestration** | **LangGraph** | LangChain ReAct | Deterministic routing, explicit state caching, and hard recursion limits prevent infinite loops. |
| **Database** | **PostgreSQL** | SQLite | Required for `AsyncPostgresSaver`, robust date handling, and database-level read-only security roles. |
| **LLM Parsing** | **Gemini Structured Output** | Markdown Regex Parsing | Enforces schema at the token-generation level. Eliminates `IndexError` and silent semantic failures. |
| **Artifact Caching** | **Time Travel (Checkpointer)** | Large State Arrays | Storing datasets in active state causes memory bloat. `get_state_history` ensures O(1) state size. |
| **Slack Transport** | **Socket Mode** | HTTP Webhooks | Bypasses firewalls for local development without ngrok. (Will migrate to HTTP for production). |

## 🔧 Slack App Installation (New Workspace)

To run this bot in your own Slack workspace, follow these steps to create and install the app using the provided manifest:

1. **Create the App:**
   * Go to [api.slack.com/apps](https://api.slack.com/apps) and click **Create New App**.
   * Choose **From an app manifest** and select your workspace.
   * Copy the contents of `docs/slack_app_manifest.yaml` from this repository and paste it into the YAML tab. Click **Create**.
2. **Generate App-Level Token (Socket Mode):**
   * Go to **Basic Information** -> **App-Level Tokens**.
   * Click **Generate Token and Scopes**, name it `socket-token`, and add the `connections:write` scope.
   * Copy this token (starts with `xapp-`). This is your `SLACK_APP_TOKEN`.
3. **Install to Workspace:**
   * Go to **Install App** in the left sidebar and click **Install to Workspace**. Allow the permissions.
   * Copy the **Bot User OAuth Token** (starts with `xoxb-`). This is your `SLACK_BOT_TOKEN`.
4. **Get Signing Secret:**
   * Go back to **Basic Information** and scroll down to **App Credentials**.
   * Show and copy the **Signing Secret**. This is your `SLACK_SIGNING_SECRET`.
5. **Enable Chat Tab (Crucial for DMs):**
   * Go to **App Home** -> **Show Tabs**.
   * Ensure **Messages Tab** is enabled and check the box: *"Allow users to send Slash commands and messages from the messages tab"*.

## 🛠 Quickstart

**Prerequisites:** Docker, Python 3.13, Slack App Tokens (from steps above), Google Gemini API Key.

1. **Configure Environment:**
   ```bash
   cp .env.example .env
   # Fill in SLACK_BOT_TOKEN, SLACK_APP_TOKEN, SLACK_SIGNING_SECRET, and GOOGLE_API_KEY
   ```
2. **Setup & Bootstrap Database:**
   ```bash
   make setup
   make db-bootstrap  # Starts Postgres and seeds deterministic demo data
   ```
3. **Run the Bot:**
   ```bash
   make run
   ```

## 🧪 Testing & Observability

* **Run Tests:** `make check` (Runs pytest, ruff, mypy).
* **Observability:** Set `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY` in `.env` to view execution graphs, token usage, and latency in LangSmith.

## 💬 Example Usage in Slack

* *"How many apps do we have?"* -> Returns simple text.
* *"Which country generates the most revenue?"* -> Returns formatted data + explicit assumptions.
* *"What about iOS?"* -> Follow-up using thread context.
* *"Export this as csv"* -> Uploads a `.csv` file instantly (cached).
* *"Show me the SQL"* -> Uploads a `.sql` snippet instantly (cached).
