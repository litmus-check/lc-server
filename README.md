# Litmus Check

Litmus Check is an AI-driven browser test-automation platform. It uses large language models to **generate, run, triage, and self-heal** end-to-end browser tests on top of [Playwright](https://playwright.dev/). A Flask backend manages tests, suites, schedules, and runs; a TypeScript agent drives the browser and talks to the LLM; and a lightweight Node.js gateway proxies live browser sessions to the frontend.

This repository (`lc-server`) is the open-source server for Litmus Check.

---

## Architecture

The project is composed of three independent services (no monorepo tooling — each service is built and run on its own):

```
Frontend
   │  WebSocket
   ▼
GatewayService  (Node.js — Bearer-token auth + Kubernetes pod discovery, WS proxy)
   │  WebSocket
   ▼
LitmusAgent     (TypeScript — Playwright browser automation + Azure OpenAI)
   │  REST
   ▼
Flask Backend   (Python — test/suite/run management, triage, scheduling)
   │
   ▼
PostgreSQL · Redis · Azure Blob & Queue Storage
```

**Communication flow:** the frontend opens a WebSocket to the **GatewayService**, which authenticates the request and proxies it to the correct **LitmusAgent** pod. The agent executes browser actions and calls the **Flask backend** REST API for test data and state. The backend persists to **PostgreSQL** (via SQLAlchemy), uses **Redis** for shared run state and as the Celery broker, runs scheduled jobs with **Celery + RedBeat**, and stores artifacts (traces, GIFs) in **Azure Blob/Queue Storage**.

| Service | Path | Language | Port | Role |
|---|---|---|---|---|
| Flask Backend | `src/` | Python 3.12 | `6010` | REST API for tests, suites, runs, schedules, triage |
| LitmusAgent | `LitmusAgent/` | TypeScript / Node.js | `8080` (WS) | Browser automation, LLM orchestration, live screencast |
| GatewayService | `GatewayService/` | Node.js | `8080` (WS) | WebSocket proxy + Kubernetes pod discovery |

---

## Repository layout

```
lc-server/
├── src/                     # Python Flask backend
│   ├── app.py               # Entry point (runs on :6010)
│   ├── app_factory.py       # App factory: get_app() / create_app()
│   ├── tasks.py             # Celery app + scheduled tasks (RedBeat)
│   ├── api/                 # Flask blueprints (all mounted under /api/v1)
│   ├── service/             # Business logic
│   ├── models/              # SQLAlchemy ORM models
│   ├── database/            # SQLAlchemy setup + Postgres connection
│   ├── llm/                 # Azure OpenAI client + LangChain triage agent/tools
│   ├── prompts/             # Backend LLM prompt templates (triage, test-plan)
│   ├── security/            # JWT auth + org-scoped authorization
│   ├── access_control/      # Role/permission definitions
│   ├── log_config/          # Logging setup
│   └── utils/               # Azure blob, email, Slack, Docker/K8s runners, crypto
├── LitmusAgent/             # TypeScript Playwright agent
│   ├── src/                 # Agent source (see "How the agent works")
│   ├── Dockerfile           # Builds the `litmus-test-runner` image
│   └── docker-compose.yml   # Agent + Redis for local runs
├── GatewayService/          # Node.js WebSocket gateway
│   ├── gateway_logic.js     # Gateway entry point
│   └── *.yaml               # Kubernetes RBAC, Deployment, LoadBalancer manifests
├── requirements.txt         # Python dependencies
└── pyproject.toml
```

---

## Prerequisites

- **Python 3.12+** (`pyproject.toml` requires `>=3.12`).<br/>
  _Note: the checked-in `.python-version` currently pins `3.11.9`; use 3.12+ to satisfy `pyproject.toml`._
- **Node.js 18+** (the `LitmusAgent` Docker image is built on `node:18-slim`).
- **PostgreSQL** and **Redis** instances (Redis can be started locally via the provided Docker Compose file).
- **Azure OpenAI** access — both the backend and the agent use Azure OpenAI through LangChain.
- **Azure Storage** account for trace/GIF artifacts (Blob + Queue).
- **Docker** (to build the agent image) and, for cloud/self-hosted deployments, a **Kubernetes** cluster.

---

## Getting started

### 1. Python backend (`src/`)

```bash
# Create and activate a virtual environment
virtualenv venv --python=python3.12
source ./venv/bin/activate          # Windows: ./venv/Scripts/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment (see "Configuration" below)
# Create an app.env file in the repo root, then:

cd src
python app.py                       # Flask server on http://localhost:6010
```

Run the Celery worker (for scheduled tasks and background jobs) in a separate shell:

```bash
cd src
celery -A tasks worker --loglevel=info
```

Configuration is loaded from an **`app.env`** file via `python-dotenv` (`load_dotenv(find_dotenv('app.env'))`). `app.env` is git-ignored — create it locally.

### 2. LitmusAgent (`LitmusAgent/`)

```bash
cd LitmusAgent
npm install
npx playwright install              # install Playwright browsers

npm run build                       # tsc -> dist/
npm start                           # node dist/index.js
# or, for development:
npm run dev                         # ts-node src/index.ts
npm test                            # jest
```

The agent is normally launched by the backend as a containerized process, but it can be run directly. It is a CLI that starts a WebSocket server (default port `8080`, override with `WS_PORT`) for live screencast streaming and takes **10 positional arguments**:

```
node dist/index.js \
  <playwright_instructions> <instructions> <mode> <run_id> <browser> \
  <browserbase_session_id> <cdp_url> <playwright_config> <variables_dict> <blob_url>
```

`<mode>` is one of `script`, `compose`, `triage`, or `heal` (see [How the agent works](#how-the-agent-works)).

### 3. GatewayService (`GatewayService/`)

The gateway is a Node.js WebSocket proxy intended to run **inside Kubernetes**. It authenticates each connection with a Bearer token, finds the target agent pod, and pipes the WebSocket through.

```bash
cd GatewayService
node gateway_logic.js               # listens on :8080
```

It requires `NAMESPACE` and `AUTH_API_URL` environment variables, loads Kubernetes config from the in-cluster service account, and locates the target pod by the `run_id` label. The manifests in `GatewayService/` (`gateway-rbac.yaml`, `gateway-service.yaml`, `lb_service.yaml`) provision the ServiceAccount/RBAC, Deployment, and LoadBalancer.

### 4. Docker (agent + Redis)

Build the agent image:

```bash
cd LitmusAgent
docker build -t litmus-test-runner .
```

Or bring up the agent together with Redis for local development:

```bash
cd LitmusAgent
docker-compose up                   # starts litmus-agent + redis:7-alpine
```

`docker-compose` reads variables from a `LitmusAgent/.env` file.

---

## Configuration

There is no committed `.env` template — each service reads its own environment file (all git-ignored). Create them locally with the keys below.

### Backend — `app.env`

| Key | Purpose |
|---|---|
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | PostgreSQL connection |
| `REDIS_URL` | Redis (shared run state + Celery broker + RedBeat store) |
| `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_KEY`, `AZURE_OPENAI_DEPLOYMENT_NAME`, `AZURE_OPENAI_MODEL_NAME` | Azure OpenAI (LLM triage / test-plan generation) |
| `STORAGE_ACCOUNT_NAME`, `STORAGE_ACCOUNT_KEY` | Azure Blob & Queue Storage (traces, GIFs, run queue) |
| `JWT_SECRET_KEY`, `JWT_EXPIRY_HOURS` | Authentication (JWT) |
| `ENVIRONMENT` | Deployment environment: `local`, `uat`, or `prod` |
| `ENCRYPTION_PASSWORD`, `ENCRYPTION_SALT` | Secret encryption for stored credentials/variables |
| `SENTRY_URL`, `SENTRY_ENV` | _Optional_ — Sentry monitoring (only initialized when set) |
| `KUBERNETES_NAMESPACE`, `AZURE_CONTAINER_REGISTRY_URL` | _Optional_ — cloud test-runner orchestration |
| `SLACK_WEBHOOK_URL`, `BREVO_API_KEY`, `SENDER_EMAIL` | _Optional_ — notifications |

### LitmusAgent — `LitmusAgent/.env`

| Key | Purpose |
|---|---|
| `REDIS_URL` | Shared session state with the backend |
| `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_KEY`, `AZURE_OPENAI_DEPLOYMENT_NAME`, `AZURE_OPENAI_MODEL_NAME`, `AZURE_OPENAI_INSTANCE_NAME` | Azure OpenAI (browser action & goal reasoning) |
| `WS_PORT` | WebSocket screencast port (default `8080`) |
| `STORAGE_ACCOUNT_NAME`, `STORAGE_ACCOUNT_KEY` | Azure Blob Storage (artifacts) |
| `GMAIL_ACCOUNT`, `GMAIL_APP_PASSWORD` | _Optional_ — IMAP inbox for `verify_email` sign-up flows |

> The `docker-compose.yml` passes `REDIS_URL` and `OPENAI_API_KEY` into the container, but the agent's LLM calls use the `AZURE_OPENAI_*` variables above.

### GatewayService — `GatewayService/.env`

| Key | Purpose |
|---|---|
| `NAMESPACE` | Kubernetes namespace to search for agent pods |
| `AUTH_API_URL` | Endpoint that validates the Bearer token (HTTP 200 = valid) |

_(The gateway listens on port `8080`.)_

---

## How the agent works

`LitmusAgent` runs one of four modes per invocation, each a distinct flow in `LitmusAgent.run()`:

| Mode | Purpose |
|---|---|
| `script` | **Automated execution.** Runs instructions sequentially — pre-generated Playwright scripts, or the AI path for steps marked `always_ai`. On completion it stops tracing, builds a GIF from trace screenshots, uploads artifacts, stores the result in Redis, and exits. |
| `compose` | **Interactive/live building.** Polls a Redis compose session, executing instructions one at a time as the user adds them and streaming a live screencast. Supports free-form natural-language **Goal** steps. |
| `triage` | **Failure analysis.** Re-runs the test to locate the failure, then asks the LLM to classify it — `raise_bug`, `update_script`, `cannot_conclude`, `retry_without_changes`, or `successful_on_retry`. |
| `heal` | **Automated repair.** Reads the prior triage result and applies the fix (add/remove/replace a step, or regenerate a script), producing a suggested test with a per-step `edit_type`. |

**Instruction model.** Steps are either **AI actions** (the LLM identifies the target element or generates code — e.g. `ai_click`, `ai_input`, `ai_select`, `ai_verify`, `ai_assert`, `ai_hover`, `ai_file_upload`, `ai_goal`, `ai_script`) or **deterministic Non-AI actions** (e.g. `go_to_url`, `go_back`, `wait_time`, `open_tab`, `run_script`, `scroll`, `switch_tab`, `page_reload`, `key_press`, `verify`, `api_intercept`/`api_mock`). System prompts live as Markdown files in `LitmusAgent/src/LLM/prompts/`.

**Variable system.** Three interpolation syntaxes are supported in instructions, scripts, and assertions:

- `${variableName}` — data-driven variables
- `{{env.variableName}}` — environment variables
- `${state.variableName}` — run-time state, resolved dynamically for cross-step data passing

**Shared state.** A Redis session keyed by `run_id` is the single source of truth shared between the Python backend and the TypeScript agent — it accumulates instructions, generated Playwright code, selectors, logs, and the `test_result` / `triage_result` / `heal_results` payloads.

---

## Tech stack

- **Backend:** Python 3.12, Flask, Flask-SQLAlchemy, Celery + RedBeat, Redis, PyJWT, Sentry (optional)
- **Agent:** TypeScript, Node.js, Playwright, LangChain, Azure OpenAI
- **Data & storage:** PostgreSQL, Redis, Azure Blob & Queue Storage
- **Infrastructure:** Docker, Kubernetes (agent pods + gateway), Azure

---

## Testing

The agent uses [Jest](https://jestjs.io/) with `ts-jest`:

```bash
cd LitmusAgent
npm test
```

Test suites live under `src/__tests__/`, `src/browser/__tests__/`, `src/LLM/__tests__/`, and `src/utils/__tests__/`.

---

## License

The `LitmusAgent` module is published under the MIT License (see `LitmusAgent/README.md`). A repository-wide `LICENSE` file will be added.
