-- CreateTable
CREATE TABLE "Event" (
    "id" TEXT NOT NULL,
    "source" TEXT NOT NULL,
    "source_type" TEXT,
    "occurred_at" TIMESTAMP(3) NOT NULL,
    "external_id" TEXT,
    "payload" JSONB NOT NULL,
    "processed" BOOLEAN NOT NULL DEFAULT false,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Event_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ActionProposal" (
    "id" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'pending',
    "urgency" TEXT NOT NULL,
    "vertical" TEXT NOT NULL,
    "action_type" TEXT NOT NULL,
    "payload" JSONB NOT NULL,
    "reasoning" TEXT NOT NULL,
    "context_summary" TEXT NOT NULL,
    "confidence" DOUBLE PRECISION NOT NULL DEFAULT 0.8,
    "event_id" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "approved_at" TIMESTAMP(3),
    "executed_at" TIMESTAMP(3),
    "approver_id" TEXT,
    "rejection_reason" TEXT,

    CONSTRAINT "ActionProposal_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Decision" (
    "id" TEXT NOT NULL,
    "request_id" TEXT NOT NULL,
    "objective" TEXT NOT NULL,
    "state" TEXT NOT NULL,
    "summary" TEXT NOT NULL,
    "confidence" DOUBLE PRECISION NOT NULL,
    "confidence_breakdown" JSONB,
    "recommendations" JSONB,
    "escalations" JSONB,
    "executed_sops" TEXT[],
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Decision_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Escalation" (
    "id" TEXT NOT NULL,
    "decision_id" TEXT NOT NULL,
    "reason" TEXT NOT NULL,
    "severity" TEXT NOT NULL,
    "context" JSONB NOT NULL,
    "state" TEXT NOT NULL DEFAULT 'pending',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Escalation_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "DailyBrief" (
    "id" TEXT NOT NULL,
    "date" DATE NOT NULL,
    "summary" TEXT NOT NULL,
    "decisions" JSONB NOT NULL,
    "state" TEXT NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "DailyBrief_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Execution" (
    "id" TEXT NOT NULL,
    "proposal_id" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'pending',
    "started_at" TIMESTAMP(3),
    "finished_at" TIMESTAMP(3),
    "result" JSONB,
    "error" TEXT,
    "idempotency_key" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Execution_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "AuditLog" (
    "id" TEXT NOT NULL,
    "action" TEXT NOT NULL,
    "entity_type" TEXT NOT NULL,
    "entity_id" TEXT NOT NULL,
    "payload" JSONB NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "AuditLog_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "Event_source_source_type_occurred_at_idx" ON "Event"("source", "source_type", "occurred_at");

-- CreateIndex
CREATE INDEX "Event_processed_occurred_at_idx" ON "Event"("processed", "occurred_at");

-- CreateIndex
CREATE INDEX "ActionProposal_status_urgency_idx" ON "ActionProposal"("status", "urgency");

-- CreateIndex
CREATE INDEX "ActionProposal_vertical_created_at_idx" ON "ActionProposal"("vertical", "created_at");

-- CreateIndex
CREATE INDEX "ActionProposal_event_id_idx" ON "ActionProposal"("event_id");

-- CreateIndex
CREATE UNIQUE INDEX "Decision_request_id_key" ON "Decision"("request_id");

-- CreateIndex
CREATE INDEX "Decision_objective_state_idx" ON "Decision"("objective", "state");

-- CreateIndex
CREATE INDEX "Escalation_state_severity_idx" ON "Escalation"("state", "severity");

-- CreateIndex
CREATE UNIQUE INDEX "DailyBrief_date_key" ON "DailyBrief"("date");

-- CreateIndex
CREATE UNIQUE INDEX "Execution_idempotency_key_key" ON "Execution"("idempotency_key");

-- CreateIndex
CREATE INDEX "Execution_proposal_id_status_idx" ON "Execution"("proposal_id", "status");

-- CreateIndex
CREATE INDEX "Execution_idempotency_key_idx" ON "Execution"("idempotency_key");

-- CreateIndex
CREATE INDEX "AuditLog_entity_type_action_idx" ON "AuditLog"("entity_type", "action");

-- CreateIndex
CREATE INDEX "AuditLog_entity_id_idx" ON "AuditLog"("entity_id");

-- AddForeignKey
ALTER TABLE "ActionProposal" ADD CONSTRAINT "ActionProposal_event_id_fkey" FOREIGN KEY ("event_id") REFERENCES "Event"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Execution" ADD CONSTRAINT "Execution_proposal_id_fkey" FOREIGN KEY ("proposal_id") REFERENCES "ActionProposal"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
