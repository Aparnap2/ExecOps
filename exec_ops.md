ExecOps is an event-driven, vertical agentic system that intercepts critical startup survival signals and drafts executable actions for founder approval, eliminating passive reporting.

It refactors FounderOS by replacing "Daily Briefs" with a proactive "Approval Inbox," preserving the stack while pivoting to interrupt-only workflows. [docs.langchain](https://docs.langchain.com/oss/python/langgraph/persistence)

## Product Requirements Document (PRD)

### Product Overview
**Vision:** Offload founder headaches by proactively detecting survival threats (prod breaks, churn risks, cash flow issues, team attrition) and drafting obedient actions (e.g., "Rollback command ready"). Founders approve with one click; the system executes.

**Problem:** Founders waste 40% of time on reactive ops firefighting across tools. Passive dashboards get ignored; ExecOps interrupts only for high-urgency events.

**Value:** Reclaims 10+ hours/week by automating coordination, not summarization. YC-caliber: Protects $100k+ assets (customers, runway, team).

### Objectives & Metrics
- **Objectives:** 95% action accuracy; <5s approval time; zero unapproved executions.
- **Metrics:** DAU >70% (approvals opened); Retention 50% at 60 days; Time saved ≥8 hrs/week (survey); Escalation accuracy 90%. [sparkco](https://sparkco.ai/blog/mastering-langgraph-checkpointing-best-practices-for-2025)

### Personas
- **Primary: Seed SaaS Founder/CTO** – Needs survival signals actioned, not reported.
- **Secondary: Ops Lead** – Approves low-urgency drafts.

### Functional Requirements
- FR1: Ingest webhooks (GitHub, Sentry, Stripe, Intercom).
- FR2: Route to vertical agents (LangGraph graphs).
- FR3: Generate ActionProposal (draft + reasoning).
- FR4: Approval Inbox UI with one-click execution.
- FR5: Obedient execution (API calls post-approval).
**Acceptance:** 100% HITL for executions; urgency-based Slack DMs.

### Non-Functional
- NFR1: Postgres persistence for LangGraph state. [langchain-ai.github](https://langchain-ai.github.io/langgraphjs/how-tos/persistence-postgres/)
- NFR2: Async via Celery (no blocking).
- NFR3: Read-only integrations initially.

## System Design & Architecture

```
[Webhooks: GitHub/Sentry/Stripe/Intercom/Slack]
         ↓ (Hono API)
Event Normalization → Postgres (Events table)
         ↓ (Celery Trigger)
Vertical Agent Router → LangGraph Graphs (4 Agents)
         ↓
ActionProposal → Postgres
         ↓
Approval Inbox (Next.js UI + Slack DM)
         ↓ (Approve)
Execution Adapter → CRM/Stripe/Slack APIs
         ↓
Audit Log (Postgres)
```

**Stack (Preserved from FounderOS):** Next.js/Hono (UI/Ingestion), FastAPI/LangGraph (Agents), Drizzle/Postgres (State), Celery/Redis (Async). [zestminds](https://www.zestminds.com/blog/build-ai-workflows-fastapi-langgraph/)

**Key Pivot:** Event → Agent Graph → Proposal (no cron/summaries).

## Workflows & Process Map

### Core Workflow: Event-to-Action
1. Webhook hits Hono → Normalize → Store Event.
2. Celery detects trigger → Invoke matching Agent Graph.
3. Graph: Context Check → Reasoning → Draft ActionProposal → Persist (status: pending).
4. Push to Inbox UI + Slack DM (if urgency=high).
5. Founder: Approve → Execute → Update status/executed.
6. Reject → Archive + optional feedback.

**Process Map (Text UML):**
```
Event In → [Router: Match Vertical?] → No: Ignore
                  ↓ Yes
Agent Graph:
  Node1: Gather Context
  Node2: Reasoning (LLM + Rules)
  Node3: Draft Proposal
  Node4: human_approval (Persist)
↓
Inbox Card: [Context][Draft][Approve/Reject]
↓ Approve → Execute API → Log Success
```

**SOPs (4 Vertical Agents):**

| SOP | Trigger | Context Check | Drafted Action | Escalation |
|----|---------|---------------|----------------|------------|
| **Release Hygiene** | Deploy/Sentry spike | Error rate >2%, tickets surge | Rollback command or postmortem DM to dev | Prod down >15min |
| **Customer Fire** | VIP ticket | Churn score >0.6, high-value | Apology email + senior assign | Unresolved >4h |
| **Runway/Money** | Stripe failure | Top 10% customer, renewal soon | Card update email + pause downgrade | Failure >24h |
| **Team Pulse** | Git commits drop 50% | PTO spike + sentiment low | 1:1 calendar invite to founder | Multiple engineers at risk  [datacamp](https://www.datacamp.com/tutorial/langgraph-agents) |

## Data Model & Code Snippets

**Drizzle Schema (Pivot from FounderOS):**
```ts
// schema.ts (Replace summaries/escalations)
export const actionProposals = pgTable('action_proposals', {
  id: uuid('id').primaryKey(),
  status: text('status').$type<'pending' | 'approved' | 'rejected' | 'executed'>(),
  urgency: text('urgency').$type<'low' | 'high' | 'critical'>(),
  actionType: text('action_type'), // 'email' | 'api_call' | 'slack_dm'
  payload: jsonb('payload'), // {to: '...', body: '...'}
  reasoning: text('reasoning'),
  vertical: text('vertical'), // 'release' | 'customer_fire' etc.
});
export const events = pgTable('events', { /* Keep existing */ });
```

**LangGraph Snippet (New: graphs/release_hygiene.py):**
```python
from langgraph.graph import StateGraph
class AgentState(dict): pass

def gather_context(state): state['error_rate'] = 0.03; return state
def draft_action(state):
    state['proposal'] = {'type': 'rollback', 'payload': {'command': 'git revert HEAD'}}
    return state
def human_approval(state): state['status'] = 'pending'; return state  # Persist here

graph = StateGraph(AgentState)
graph.add_node("gather", gather_context).add_node("draft", draft_action).add_node("approve", human_approval)
graph.set_entry_point("gather"); graph.add_edge("gather", "draft"); graph.add_edge("draft", "approve")
app = graph.compile(checkpointer=PostgresSaver(...))  # [web:229]
```

**FastAPI Endpoint (Updated /decide):**
```python
@app.post("/propose")
async def propose(req: EventRequest) -> ActionProposalResponse:
    result = release_graph.invoke({"events": req.events})  # Route by vertical
    return ActionProposalResponse(id=..., payload=result['proposal'], status='pending')
```

**UI Snippet (Next.js ActionCard):**
```tsx
// components/ActionCard.tsx
function ActionCard({ proposal }: { proposal: ActionProposal }) {
  return (
    <div className="p-4 border rounded">
      <h3>{proposal.reasoning}</h3>
      <pre>{JSON.stringify(proposal.payload, null, 2)}</pre>  {/* Email preview */}
      <div>
        <button onClick={() => approve(proposal.id)}>Approve & Execute</button>
        <button onClick={() => reject(proposal.id)}>Reject</button>
      </div>
    </div>
  );
}
```

## File Structure & Refactoring Plan

**Refactored Structure (90% Preserved):**
```
/apps/web          # Keep: Add /inbox page
/packages/db       # Update schema.ts (action_proposals)
/packages/contracts # Update ai.json (ActionProposal)
/services/ai       # Delete old graphs/*; Add graphs/release_hygiene.py etc.
                  # Update main.py (/propose endpoint)
```

**Week-by-Week Refactor (Leverage Existing):**
- **Week 1:** DB Migration (action_proposals table); Test ingestion.
- **Week 2:** 2 Agents (Release + Runway); LangGraph graphs.
- **Week 3:** Inbox UI + Execution Adapter; Test end-to-end.
- **Week 4:** Remaining Agents + Slack DMs; Deploy.

**Business Plan:** ICP: Seed SaaS Founders. Pricing: $299/mo (Pro), $99 trial. GTM: HN/YC forums. MRR Goal: $10k (34 customers). [atalupadhyay.wordpress](https://atalupadhyay.wordpress.com/2026/01/02/fastapi-langgraph-building-production-ready-ai-apis/)
