# ExecOps v1.0 Implementation Instructions

## Context
We are pivoting "FounderOS" to "ExecOps" (Event-Driven Ops).
We are NOT building a chatty AI. We are building a "Push" system (Inbox) and "Pull" system (Canvas).
The codebase currently contains legacy "SRE/CTO/Tech Debt" agents. These should be archived or refactored into the new "Vertical Graph" structure.

## Core Architecture
- **Ingestion (Push):** Webhook -> `events` table (Postgres).
- **Processing (Async):** Celery Worker -> `Router` -> `LangGraph` -> `ActionProposal`.
- **Approval (Human):** Next.js `/inbox` -> Approve/Reject -> `ExecutionAdapter`.
- **Canvas (Pull):** Next.js `/canvas` -> CopilotKit -> Read-only Analytics.

## File Structure Alignment
Use this map to place new code. Do not create new top-level folders.

- `apps/web` (Move `fullstack` content here or alias it):
  - `components/inbox/ActionCard.tsx` (The approval UI)
  - `app/api/ingest/stripe/route.ts` (Webhook handler)
- `services/ai` (Your `ai-service` folder):
  - `src/ai_service/graphs/money_graph.py` (The new "Money" vertical)
  - `src/ai_service/router.py` (The entry point for events)
  - `src/ai_service/infrastructure/checkpointer.py` (Ensure this uses PostgresSaver)
- `packages/db` (Shared logic, mostly your Prisma/Drizzle schemas):
  - `schema.prisma` (Update to include `ActionProposal`, `Event`, `Execution`)

## Phase 1: Database & Ingestion (Sprint 1)
1.  **Schema Migration:**
    Update `fullstack/prisma/schema.prisma`:
    - `model Event`: id, source, type, payload (Json), dedupeKey, status.
    - `model ActionProposal`: id, status (pending/approved), urgency, vertical, reasoning, payload.
    - `model Execution`: id, proposalId, status, result.

2.  **Webhook Handler:**
    Create `fullstack/app/api/ingest/stripe/route.ts`:
    - Verify Stripe signature.
    - Upsert into `Event` table (dedupe by Stripe Event ID).
    - Trigger Celery task `process_event_task.delay(event.id)`.

## Phase 2: The Money Graph (Sprint 2)
1.  **Refactor Graphs:**
    - Delete/Archive `ai-service/src/ai_service/agent/tech_debt.py`.
    - Create `ai-service/src/ai_service/graphs/money_graph.py`.
    - Logic:
      - Node 1: `check_runway` (Read Stripe/Bank balance).
      - Node 2: `analyze_spend` (Is this > 10% variance?).
      - Node 3: `draft_proposal` (Create ActionProposal in DB).

2.  **Router:**
    Update `ai-service/src/ai_service/main.py`:
    - Implement `process_event(event_id)` entry point.
    - Route `source: stripe` -> `money_graph`.

## Phase 3: The Inbox & Execution (Sprint 3)
1.  **Inbox UI:**
    Update `fullstack/components/inbox/Inbox.tsx`:
    - Fetch `ActionProposal` where `status = 'pending'`.
    - Render cards with `Reasoning` and `Urgency`.

2.  **Execution Adapter:**
    Create `ai-service/src/ai_service/integrations/executor.py`:
    - `execute_proposal(proposal_id)`:
      - If `action_type == 'email'`: Call Gmail API (or mock).
      - If `action_type == 'slack'`: Call Slack API.
      - Update `Execution` table.

## Hard Constraints
- **NO Cron Jobs:** The system only wakes up on Webhook Events or User Canvas Queries.
- **NO Autonomous Writes:** Never execute an external API call without a Human Approval record in the DB.
- **Persistence:** Use the `postgres` checkpointer for LangGraph. Do not use memory-only checkpointers.

## Cleanup Tasks (Immediate)
- Remove `ai-service/src/ai_service/memory/graphiti_client.py` (We are using standard Postgres now).
- Rename `test_cto_agent.py` to `test_money_agent.py` and update logic.

---

## Hard scope decisions (non-negotiable)
- Kill anything that looks like "daily briefs / summaries." Your own ExecOps doc already says "no cron/summaries," so don't reintroduce it via "canvas reports."
- Don't ship 4 vertical agents in v1; it's fake breadth and you'll drown in edge cases and integrations. Ship **Money** first (Stripe + invoices) and optionally **Customer Fire** second (Intercom), because they have the clearest ROI and simplest "approve/execute" loop.
- Pick one persistence strategy: your FounderOS doc leans into Neo4j/Graphiti "Hive Memory," while ExecOps is built around Postgres for events/proposals and LangGraph persistence. Mixing both now will slow you down and add failure modes.

## Final PRD (ExecOps v1.0)
**Name:** ExecOps
**Positioning:** Event-driven, vertical agentic ops system that intercepts survival signals and drafts executable actions for founder approval—no passive reporting.

### Problem
Founders lose time firefighting across tools, and dashboards get ignored; the system must interrupt only on high-urgency events and produce an *action draft* that is one click from execution.

### Core UX surfaces
1) **Approval Inbox (Push / interrupt-only)**: A queue of ActionProposals with Approve/Reject and full context + reasoning.
2) **Command Canvas (Pull / AG-UI)**: Natural language queries over the same underlying events/transactions to render tables/metrics/charts *on-demand*, not scheduled summaries. (This must be read-only until v1 is stable.)

### Personas
- Primary: Seed SaaS Founder/CTO.
- Secondary: Ops Lead (optional delegated approvals).

### Success metrics (v1)
- 100% human-in-the-loop for any external side-effect execution.
- Median approval time < 5s once the card is opened.
- Action accuracy target 95% is aspirational; in v1 you should measure **precision** per action type and simply disable low-precision actions.

### Functional requirements (v1 scope)
**Ingestion**
- Webhook ingestion via Hono for Stripe + (optional) Intercom; GitHub/Sentry can be stubbed behind feature flags.
- Normalize all inbound payloads into a single `events` table.

**Agent routing + proposal generation**
- A Router selects a vertical graph (Money / Customer Fire / etc.).
- Graph must run: Context Check → Reasoning (LLM + rules) → Draft Proposal → Persist as `pending`.

**Approval + execution**
- Inbox UI + Slack DM for high urgency proposals.
- Approve triggers execution adapters; Reject archives + optionally stores feedback.
- "Read-only integrations initially" applies to everything except actions you explicitly allow (e.g., sending a drafted email can still be an execution).

**AG-UI canvas (v1 read-only)**
- NL query → safe analytics functions → render chart/table.
- No "agent decides to run arbitrary SQL." Only allow predefined analytics queries (spend by vendor, runway estimate, failed payments list, etc.).

### Non-functional requirements (v1)
- LangGraph state persistence using Postgres checkpointer (don't invent your own).
- Async task execution via Celery + Redis (Hono API must never block on LLM calls).
- Full audit log of every proposal state transition and every execution attempt.

## Final architecture + data contracts
### Services
- **apps/web (Next.js)**: `/inbox`, `/canvas`, auth, API client.
- **apps/ingest (Hono)**: webhook endpoints, event normalization, writes to Postgres, enqueues Celery tasks.
- **services/ai (FastAPI + LangGraph)**: router + graphs, proposal creation, decision endpoints.
- **worker (Celery)**: executes "generate proposal" jobs and (after approval) "execute action" jobs.

### Postgres tables
- `events`: id, source, type, occurred_at, payload_json, org_id, dedupe_key, processed_at.
- `action_proposals`: id, status, urgency, action_type, payload, reasoning, vertical.
- `executions`: id, proposal_id, status, started_at, finished_at, result_json, error, idempotency_key.
- `audit_log`: id, actor_type (system/user), actor_id, proposal_id, from_status, to_status, ts, metadata_json.

### API contracts
- `POST /ingest/stripe` (Hono): validate signature → write `events` → enqueue `process_event(event_id)`.
- `POST /ai/propose` (FastAPI): given `event_id`, run router+graph, persist proposal, return proposal_id.
- `POST /ai/decide` (FastAPI): `{proposal_id, decision: approve|reject, actor}` → transition + enqueue execute if approved.
- `GET /api/inbox?status=pending` (Next.js backend or direct DB via API): returns proposals for UI.

### LangGraph persistence
Use the Postgres checkpointer pattern so graph state survives retries and "human approval" pauses.

## Dev plan
### Sprint 0 (1–2 days): repo alignment
- Delete/disable "Daily Briefs" code paths entirely.
- Ensure all existing "guardrails" actions from FounderOS map to **ActionProposal** objects.

### Sprint 1 (Week 1): database + inbox loop
- Implement `events`, `action_proposals`, `audit_log`, `executions` migrations.
- Build `/inbox` page rendering proposals; Approve/Reject buttons call `/ai/decide`.
- Stub a "proposal generator" that creates a fake proposal from an event (no LLM).

### Sprint 2 (Week 2): Money vertical
- Stripe webhook ingestion + normalization.
- Money graph: Context → Drafts ("Send card update email", "Slack DM account owner").
- Execution adapters (Slack DM + email draft).

### Sprint 3 (Week 3): LangGraph productionization
- Add Postgres checkpointer to graphs.
- Add dedupe keys to prevent duplicate proposals.
- Add Celery task routing + exponential backoff.

### Sprint 4 (Week 4): AG-UI Canvas (read-only)
- Implement `/canvas` with "ask a question" → approved analytics function calls.
- Only expose safe metrics first: runway, burn rate, spend by vendor, failed payments count.

---

## Claude Code instructions

**Goal:** Implement ExecOps v1.0 as defined above: ingest → event store → async processing → ActionProposal → approval inbox → execution adapters → audit log, with optional read-only AG-UI canvas.

**Hard rules**
- Never implement autonomous execution without an explicit "approved" status check.
- Do not add new product surfaces beyond `/inbox` and `/canvas`.
- Do not introduce Neo4j/Graphiti or any second DB unless explicitly requested; Postgres is the system of record.

**Refactor plan**
1) Locate any "daily brief/summary" modules and delete/feature-flag them off.
2) Ensure `action_proposals` table matches ExecOps schema and is used everywhere.
3) Build/confirm these endpoints exist and are wired end-to-end:
   - Hono: webhook → `events` insert → Celery enqueue.
   - FastAPI: `/propose` and `/decide`.
   - Next.js: `/inbox` reading proposals + calling decide.

**Implementation tasks (do in order)**
- Task A: Generate Prisma migrations for `events`, `action_proposals`, `executions`, `audit_log`; add indexes.
- Task B: Implement Hono webhook handler for Stripe with signature verification; normalize payload into `events`.
- Task C: Implement Celery job `process_event(event_id)` → calls FastAPI `/propose`.
- Task D: Implement LangGraph Money graph with deterministic rules first, then LLM reasoning second; persist proposals with `pending` status.
- Task E: Implement Inbox UI + Approve/Reject; Approve enqueues `execute_proposal(proposal_id)`.
- Task F: Implement execution adapters with idempotency and audit logging.
- Task G: Add LangGraph Postgres checkpointer for any graph that can pause or retry.
- Task H: Implement `/canvas` with **whitelisted analytics** only (no arbitrary SQL), rendering components for table + time-series chart.
