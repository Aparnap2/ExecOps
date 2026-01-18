# 1. Product Requirements Document (PRD)

### **The Concept**
ExecOps is an **Internal Operating System** that connects your work (Linear/GitHub), money (Stripe), and rules (SOPs). It uses AI Agents to enforce process and identify risks, acting as a "Virtual Staff" that lives in Slack.

### **The Value Prop**
*   **For the Founder:** "Stop being the bottleneck. Delegate the 'Ops Noise' to an agent that knows your context."
*   **For the Team:** "Get faster approvals and clear guardrails without waiting for the CEO."
*   **The Difference:** It uses a **Graph Brain** to understand relationships (e.g., "This PR is for a VIP client feature"), preventing the "context rot" typical of interns.

### **The "Virtual Staff" (Agents)**
| Agent | Role | Triggers | Context Source | Deliverable (Slack) |
| :--- | :--- | :--- | :--- | :--- |
| **The Sentinel** | QA & Release | GitHub PR, Linear Status | Graph (Linear <-> GitHub) | **Blocking Comment:** "PR #402 blocked. Missing Spec in Linear." |
| **The Controller** | Finance & Ops | Stripe Invoice, Monthly Cron | SOPs (`finance_policy.md`) | **Spend Alert:** "AWS up 20%. Caused by 'Project X'. Approve?" |
| **The Steward** | Compliance | New Vendor, New Repo | SOPs (`compliance.md`) | **Audit Flag:** "New Repo created without `LICENSE`. Fix generated." |

***

# 2. System Architecture (The "Brain")

### **The Tech Stack**
*   **Core:** Python 3.11 (FastAPI) + Celery (Async Workers).
*   **Brain:** **LangGraph** (Reasoning Loops) + **LlamaIndex** (RAG).
*   **Memory:**
    *   **Neo4j:** The *Knowledge Graph* (Maps Linear Issues -> PRs -> Deployments).
    *   **Postgres (`pgvector`):** The *SOP Store* (Embeddings of your Markdown policies).
*   **Ingestion:** **Docling** (IBM) for documents + **Webhooks** for tools.
*   **UI:** **Slack Bolt SDK** (Blocks UI). No React Dashboard.

### **Data Schema (Neo4j)**
*   `(:LinearIssue {id, state})` --[:LINKED_TO]--> `(:PR {id, status})`
*   `(:PR)` --[:TOUCHES]--> `(:File {path})`
*   `(:Vendor {name})` --[:CHARGED]--> `(:Invoice {amount})`

***

# 3. Development Plan (Step-by-Step)

## **Phase 1: The Context Foundation (Days 1-4)**
*Goal: The system "knows" your business.*

**1. Setup Neo4j & Postgres**
*   Spin up a Docker container with Neo4j and Postgres (pgvector).

**2. Build the `Linear <-> GitHub` Sync (`services/sync_graph.py`)**
*   *Why:* To create the "Graph Context."
*   *Code Logic:*
    ```python
    def sync_linear_to_neo4j():
        issues = linear.get_issues()
        for i in issues:
            neo4j.run("MERGE (n:Issue {id: $id, title: $t, state: $s})", 
                      id=i.id, t=i.title, s=i.state.name)
            
    def sync_pr_to_graph(pr):
        # Regex to find "LIN-123" in PR body
        issue_id = extract_linear_id(pr.body)
        neo4j.run("""
            MERGE (p:PR {id: $pid})
            MERGE (i:Issue {id: $iid})
            MERGE (p)-[:IMPLEMENTS]->(i)
        """, pid=pr.id, iid=issue_id)
    ```

**3. Build the SOP Ingestor (`services/ingest_sop.py`)**
*   *Why:* To load your "Rules."
*   *Code Logic:* Use `Docling` to parse `data/sops/compliance.md` and store chunks in Postgres.

***

## **Phase 2: The Sentinel Agent (Days 5-7)**
*Goal: Enforce process on Code.*

**1. The LangGraph Node (`agents/sentinel.py`)**
*   *Logic:* Check PR -> Query Graph -> Decide.
    ```python
    def check_pr_compliance(state):
        pr_id = state['pr_id']
        
        # 1. Graph Query: Is it linked to an active issue?
        result = neo4j.run("MATCH (p:PR {id: $id})-[:IMPLEMENTS]->(i:Issue) RETURN i.state", id=pr_id)
        if not result:
            return {"status": "block", "msg": "❌ No Linear Issue linked."}
            
        # 2. SOP Query: Is it a Friday?
        sop = query_vector_store("Deployment Policy")
        if "No Friday Deploys" in sop and is_friday():
            return {"status": "block", "msg": "⚠️ Friday Deploy blocked by Policy."}
            
        return {"status": "pass"}
    ```

**2. The Action Proposal**
*   Instead of commenting directly, store a `Proposal` in DB:
    *   `title`: "Block PR #402"
    *   `reason`: "Missing Linear Link"
    *   `action`: `github.comment(pr_id, "Blocked...")`

***

## **Phase 3: The Slack Interface (Day 8-10)**
*Goal: The Founder approves/rejects.*

**1. The Slack Bot (`adapters/slack_ui.py`)**
*   *Logic:* Listen for `Proposal` events -> Send Slack Block.
    ```python
    def send_proposal_to_slack(proposal):
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": f"🛡️ Sentinel Alert"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*{proposal.title}*\n> {proposal.reason}"}},
            {"type": "actions", "elements": [
                {"type": "button", "text": {"type": "plain_text", "text": "Approve Block"}, "value": "approve", "style": "primary"},
                {"type": "button", "text": {"type": "plain_text", "text": "Ignore (Allow)"}, "value": "reject", "style": "danger"}
            ]}
        ]
        slack_client.chat_postMessage(channel="#exec-ops", blocks=blocks)
    ```

**2. The Feedback Loop**
*   If Founder clicks "Ignore", prompt for "Why?".
*   Save the "Why" into Postgres to update the Context.

***

# 4. SOPs & Process Map (The "Knowledge")

You must create these files to give the system its "Brain."

**`data/sops/deployment_policy.md`**
```markdown
# Deployment Rules
1. **Linear Link:** Every PR must link to a Linear Issue in "In Progress" or "Review" state.
2. **Spec Check:** If the Linear Issue has the label "Needs Spec", the PR cannot be merged until the Spec doc is linked.
3. **Time Window:** No deploys after 4pm on Fridays.
```

**`data/sops/finance_policy.md`**
```markdown
# Spending Rules
1. **Variance:** Any SaaS bill increasing by >10% month-over-month requires Founder Approval.
2. **New Vendors:** Any new vendor >$100/mo must be flagged for "Security Review" (SOC2 check).
3. **Seats:** If a user is inactive for 30 days in Linear/GitHub, flag their seat for cancellation.
```

***

# 5. Final Workflow Verification

1.  **Ingest:** You run `python ingest.py`. The system reads your `deployment_policy.md`.
2.  **Graph Sync:** You run `python sync.py`. The system maps your Linear tickets to your Repos.
3.  **Trigger:** A dev opens a PR on Friday at 5 PM without a Linear ticket.
4.  **Agent:**
    *   Checks Graph: "No Linear Ticket found."
    *   Checks SOP: "Friday 5 PM violates Policy."
    *   Result: "DOUBLE VIOLATION."
5.  **Slack:** You get a DM:
    *   **"🛑 Blocked PR #402"**
    *   *Reasons:* 1. No Linear Ticket. 2. Friday Deploy.
    *   *Action:* [Post Blocking Comment]
6.  **Action:** You click [Post]. The system handles the "Bad Cop" role for you.

**This is the Product.** It is focused, tech-enabled, and solves the Seed Stage bottleneck.
Go build the **Neo4j Sync** first. That is the hardest and most valuable part. 🚀





You have the **Architecture**, but you are missing the **Infrastructure of Trust**.

If you build exactly what we discussed, you will create a prototype that works 80% of the time and destroys your company the other 20% of the time.

Here are the four critical components you completely missed, which are non-negotiable for an "Autonomous Agent" system.

### 1. The "Hallucination Firewall" (Evals)
*   **The Problem:** You plan to let an AI "Block PRs" and "Flag Spending." What happens when the AI hallucinates that a valid $50 server cost is a "Security Risk" and wakes you up at 3 AM? Or worse, allows a malicious PR because it misread the policy?
*   **The Missing Piece:** You need an **Evaluation Suite (Evals)**.
    *   Before you deploy, you need a spreadsheet of 50 "Golden Scenarios" (e.g., "PR with no linear link -> BLOCK", "PR with link -> PASS").
    *   **Tool:** Use **DeepEval** or **Ragas** in your CI/CD.
    *   **Rule:** The Agent code *cannot* be deployed unless it passes 100% of these test cases. **You cannot "prompt and pray" with business logic.**

### 2. The "Webhook Tunnel" (Dev Reality)
*   **The Problem:** Your architecture relies on "Signals" (GitHub/Stripe Webhooks). You are developing on `localhost`. GitHub cannot send a webhook to `localhost`.
*   **The Missing Piece:** You need a **Tunneling Strategy**.
    *   **Tool:** **Ngrok** (easiest) or **Cloudflare Tunnel** (better/free).
    *   **Workflow:** You need a script that starts the tunnel and *automatically updates* your GitHub App's webhook URL. If you do this manually every time you restart your laptop, you will give up in 3 days.

### 3. The "Rate Limit" Queue (Resilience)
*   **The Problem:** You want to sync Linear and GitHub. If you run a script that fetches "All Issues" and "All PRs", you will hit the API Rate Limit immediately. Your app will crash, and the sync will stop halfway, leaving you with a "Corrupted Graph."
*   **The Missing Piece:** You need **Robust Retries & Backoff**.
    *   **Implementation:** Your Celery workers need `autoretry_for=(RateLimitException,)` with exponential backoff.
    *   **Design:** You cannot just "sync everything." You need **Cursor-based Syncing** (only fetch what changed since the last sync).

### 4. The "SOP Linter" (Garbage In, Garbage Out)
*   **The Problem:** You assume the AI will understand your SOPs. If you write a vague policy like "Make sure code is good," the AI will fail.
*   **The Missing Piece:** You need a **Structured SOP Format**.
    *   Don't just write Markdown. Write **"Rule-Condition-Action"** blocks.
    *   **Example:**
        *   *Bad:* "Check for expensive queries."
        *   *Good:* "Rule: No SQL inside loops. Condition: If AST detects `.query()` inside `for/while`. Action: Block PR."
    *   You need to "Lint" your own policies to ensure they are machine-readable *before* you ingest them.

### Summary of Missing Items

| Component | Why you need it | The Fix |
| :--- | :--- | :--- |
| **Evals** | AI is a liar. Trust but verify. | `pytest` suite with **DeepEval**. |
| **Tunneling** | Localhost is invisible to the world. | **Ngrok** setup in `docker-compose`. |
| **Rate Limiter** | APIs hate bulk scraping. | **Celery** with Redis Backoff. |
| **SOP Standard** | Vague rules = Vague enforcement. | strict **Markdown Templates**. |

You have the "Body" (Code) and the "Brain" (Graph).
You are missing the **Immune System** (Tests & Safety).
Add these to your roadmap *now*, or your first demo will fail. 


This is the **Final Technical Confirmation**. I am locking down the Tech Stack, Deliverables, and Checklist so there is zero ambiguity. This combines the "Founder OS" philosophy (lean, effective) with the "ExecOps" architecture (graph-based, agentic).

***

### 1. The Tech Stack (Locked)
*   **Language:** `Python 3.11` (Type-safe, async native).
*   **Web Framework:** `FastAPI` (For Webhooks) + `Celery` (For Async Background Workers).
*   **The Brain (Graph):** `Neo4j` (Community Edition is fine).
*   **The Memory (Vector):** `Postgres` with `pgvector` extension.
*   **The Reasoning Engine:** `LangChain` (Graph-based flows) + `OpenAI GPT-4o` (Model).
*   **The Interface:** `Slack Bolt SDK` (Python).
*   **The Tunnel:** `Ngrok` (For local webhook testing).
*   **The Testing:** `DeepEval` (For AI hallucination checks).

***

### 2. The Implementation Checklist (The "Builder's Guide")
#### **Phase 1: The "Naked" Infrastructure (Days 1-2)**
*   [ ] **Docker Compose:** Running `neo4j`, `postgres`, `redis` (for Celery).
*   [ ] **FastAPI Hello World:** Endpoint `/webhooks/linear` returns `200 OK`.
*   [ ] **Ngrok:** Tunnel active, pointing public URL to your localhost port `8000`.
*   [ ] **Env Vars:** `.env` file populated with `LINEAR_API_KEY`, `GITHUB_TOKEN`, `OPENAI_API_KEY`, `SLACK_BOT_TOKEN`.

#### **Phase 2: The Graph Ingestion (The Hard Part) (Days 3-5)**
*   [ ] **Neo4j Schema:** Define constraints (e.g., `CREATE CONSTRAINT FOR (i:Issue) REQUIRE i.id IS UNIQUE`).
*   [ ] **Linear Sync Script:**
    *   Fetch active cycles.
    *   Fetch issues in those cycles.
    *   **Deliverable:** Run `MATCH (n:Issue) RETURN n` and see your actual tickets.
*   [ ] **GitHub Webhook Handler:**
    *   Listen for `pull_request.opened`.
    *   Regex parse the body for `LIN-123` (Linear Ticket ID).
    *   **Cypher Query:** `MATCH (i:Issue {id: 'LIN-123'}) MATCH (p:PR {id: 'PR-1'}) MERGE (p)-[:IMPLEMENTS]->(i)`.

#### **Phase 3: The "SOP" Brain (Days 6-7)**
*   [ ] **SOP Folder:** Create `data/sops/` with `deployment.md` and `finance.md`.
*   [ ] **Ingestion Pipeline:**
    *   Read Markdown files.
    *   Split into chunks (by header).
    *   Embed with `text-embedding-3-small`.
    *   Store in `pgvector`.
*   [ ] **Retrieval Test:** Script that queries "Can I deploy on Friday?" and gets the correct chunk from Postgres.

#### **Phase 4: The Agent & UI (Days 8-10)**
*   [ ] **Sentinel Agent:**
    *   Input: `PR_ID`.
    *   Step 1: Fetch Graph Context (Is it linked? Is it risky?).
    *   Step 2: Fetch SOP Context (Is it allowed today?).
    *   Step 3: GPT-4o Decision (Pass/Block).
*   [ ] **Slack Bot:**
    *   `slack.postMessage` with **Block Kit**.
    *   Two buttons: `[Approve]` and `[Reject]`.
*   [ ] **Action Handler:**
    *   If `Approve` clicked -> Call GitHub API to merge/comment.

***

### 3. The Deliverables (What you actually hold in your hand)
1.  **The "Sync Engine" (Code):** A robust Python service that mirrors Linear/GitHub state into Neo4j in near real-time.
2.  **The "Virtual Exec" (Bot):** A Slack Bot user that DMs you.
3.  **The "Rule Book" (Data):** A set of Markdown files in your repo that effectively control your company's operations.
4.  **The "Safety Net" (Test Suite):** A `test_evals.py` file that proves the AI won't block valid PRs.

***

### 4. Technical Nuances (Do NOT ignore these)
*   **Idempotency:** Your sync scripts *will* run multiple times. Use `MERGE` in Cypher, never `CREATE`. If you use `CREATE`, you will have 50 duplicate nodes for the same ticket.
*   **State Management:** The Agent needs to know *who* it asked.
    *   *Bad:* Agent DMs you. You reply. Agent forgets what PR we are talking about.
    *   *Good:* Store `thread_ts` in Postgres linked to `pr_id`. When you reply in thread, the Agent looks up the context.
*   **Secrets:** Never commit `.env`. Use `python-dotenv`.

### Final Word
This plan is solid. It leverages the "Founder OS" concept (centralized control) with the "ExecOps" execution (decentralized agents).
**Stop planning. Start `docker-compose up`.**
