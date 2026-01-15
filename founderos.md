

------

# **FounderOS: The Technical Founder's Autopilot**

## Complete Execution Blueprint (PRD, Architecture, Plan)

------

## **1. FINAL REVISED PRD (Safe & Focused)**

## **1.1 Product Overview**

- **Name:** FounderOS
- **Tagline:** The Virtual Head Office for Technical Founders.
- **Core Concept:** A swarm of context-aware agents that act as "Guardrails" for your Code, Budget, and Tech Debt. They don't just chat; they intercept webhooks to stop mistakes *before* they happen.
- **Target User:** Series A/Seed CTOs/Founders who are drowning in operational noise.

## **1.2 The "Guardrails" Staff (Agent Roster)**

*Replaced "Ops Agent" (Legal) with "Tech Debt Agent" (Quality).*

| Agent Name          | Role                 | Trigger                | Action               | Key Graph Rules                                              |
| :------------------ | :------------------- | :--------------------- | :------------------- | :----------------------------------------------------------- |
| **SRE Agent**       | **Production Guard** | GitHub PR Opened       | Block risky PRs      | *"No Friday Deploys"*, *"No direct SQL in controllers"*      |
| **CFO Agent**       | **Runway Guard**     | Stripe Invoice / Slack | Deny duplicate spend | *"Budget < $500"*, *"Vendor 'Vercel' exists? Deny duplicate"* |
| **Tech Debt Agent** | **Quality Guard**    | GitHub Merge           | Track & Nudge        | *"Alert if > 50 TODOs"*, *"Warn on deprecated lib 'moment.js'"* |

------

## **2. SYSTEM ARCHITECTURE & DESIGN**

## **2.1 High-Level Diagram**

```
text┌─────────────────────────────────────────────────────────────┐
│                    FounderOS Platform                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [Triggers]          [API Gateway]         [The Brain]      │
│  GitHub Webhook ───▶ FastAPI       ──────▶ LangGraph        │
│  Stripe Webhook      (Async)               Supervisor       │
│  Slack Event                                    │           │
│                                                 │           │
│                                       ┌─────────┴─────────┐ │
│                                       │                   │ │
│                             ┌─────────▼────────┐  ┌───────▼────────┐
│                             │    SRE Agent     │  │   CFO Agent    │
│                             │ (Code Analysis)  │  │ (Spend Audit)  │
│                             └─────────┬────────┘  └───────┬────────┘
│                                       │                   │
│  [Hive Memory]                        │                   │
│  ┌─────────────────────────┐          │                   │
│  │ Neo4j + Graphiti        │◄─────────┘                   │
│  │ (Temporal Knowledge)    │                              │
│  └─────────────────────────┘                              │
│                                                           │
│                                       ┌───────────────────▼─┐
│                                       │    Slack Block Kit  │
│                                       │   (Staged Action)   │
│                                       └──────────┬──────────┘
│                                                  │
│                                           [Human Click]
│                                                  │
│                                           [Execute API]
│                                    (Block PR / Deny Invoice)
└─────────────────────────────────────────────────────────────┘
```

## **2.2 Data Models (SOPs)**

*These are the "Brains" you ingest into the Graph.*

**`data/sops/deployment_policy.md`**

```
text# Deployment Policy
- Effective: 2026-01-01
- Status: Active

Rules:
1. Friday Deploy Freeze: No deployments allowed on Fridays between 14:00 UTC and 23:59 UTC.
2. Architecture Lock: All changes to 'payment-service' must use gRPC.
```

**`data/sops/tech_health.md`** (New!)

```
text# Tech Health Policy
- Effective: 2026-01-01

Rules:
1. Deprecation Watch: Any PR adding 'moment.js' must be warned (Use 'date-fns').
2. Debt Cap: If a Service has > 50 "TODO" comments, block new feature PRs until 10% are resolved.
```

------

## **3. DEVELOPMENT PLAN (21 Days)**

## **Week 1: The Hive Memory (Infrastructure)**

- **Day 1:** Setup `docker-compose.yml` (Neo4j, Postgres, Redis).
- **Day 2:** Implement `graphiti_client.py`. Ingest the markdown SOPs.
- **Day 3:** Verify Temporal Queries (*"Can I deploy?"* returns different answers on Thursday vs Friday).
- **Day 4:** Build the **FastAPI** skeleton with `Mangum` for Lambda.

## **Week 2: The Agents (Logic)**

- **Day 5:** Build `SRE_Agent` (LangGraph node). Parse GitHub PR diffs.
- **Day 6:** Connect `SRE_Agent` to Graphiti. Implement "SQL Detection" logic.
- **Day 7:** Build `CFO_Agent`. Implement "Vendor Entity Resolution" (match "Vercel Inc" to "Vercel").
- **Day 8:** Implement **Supervisor Node** (Router) to direct webhooks to the right agent.

## **Week 3: The Interface & Demo**

- **Day 9:** Set up Slack App. Build **Block Kit** JSON for "Approve/Deny" buttons.
- **Day 10:** Implement `human_approval` node in LangGraph (Pause workflow until button click).
- **Day 11:** **Integration Testing.** (Simulate GitHub Webhook -> Slack Alert -> Click -> GitHub Comment).
- **Day 12:** **Demo Recording.** (Split screen: Code vs. Slack).

------

## **4. CODE SNIPPETS**

## **A. Tech Debt Agent (Regex Logic)**

```
python# agent/debt_agent.py
import re

def check_tech_debt(state):
    pr_diff = state['pr_context']['diff']
    
    # Rule 1: Count TODOs
    todo_count = len(re.findall(r'# TODO:', pr_diff))
    
    # Rule 2: Check Deprecated Libs
    has_moment = "import moment" in pr_diff
    
    if todo_count > 5:
        return {
            "decision": "WARN",
            "message": f"⚠️ Tech Debt Alert: You added {todo_count} TODOs. Please resolve some."
        }
    
    if has_moment:
        return {
            "decision": "BLOCK",
            "message": "🚫 Policy Violation: 'moment.js' is deprecated. Use 'date-fns'."
        }
        
    return {"decision": "PASS"}
```

## **B. Slack "Block Kit" (Approval UI)**

```
python# integrations/slack.py
def build_block_alert(title, reason, action_id):
    return [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"🚨 *FounderOS Alert* \n{title}"}
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"> {reason}"}
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "🚫 Block Action"},
                    "style": "danger",
                    "value": f"deny_{action_id}"
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✅ Allow (Override)"},
                    "value": f"approve_{action_id}"
                }
            ]
        }
    ]
```

------

## **5. VALIDATION CHECKLIST**

-  **Docker:** Neo4j & Postgres running.
-  **Ingestion:** `python seed_graph.py` runs without error.
-  **Query Test:** "Is it Friday?" query returns correct Boolean based on mock time.
-  **Webhook:** `curl` to FastAPI endpoint triggers the correct Agent log.
-  **Slack:** Bot sends a message with a button.
-  **End-to-End:** Clicking "Block" on Slack actually posts a comment on GitHub.

------

## **6. FINAL DELIVERABLES**

1. **Codebase:** `founder-os` Repo (FastAPI + LangGraph + Neo4j).
2. **Demo Video:** 2 Minutes.
   - *Scene 1:* "It's Friday 4 PM." (Show clock).
   - *Scene 2:* Junior Dev opens PR.
   - *Scene 3:* **FounderOS** instantly comments: "Blocked: Friday Freeze Policy."
   - *Scene 4:* Founder gets Slack alert.
3. **Submission Text:** Use the "Virtual Head Office" narrative.

This is a rock-solid plan. It minimizes risk (no legal stuff), maximizes your skills (coding/devops), and delivers a flashy "AI Sentinel" demo that judges love. Go build it.

