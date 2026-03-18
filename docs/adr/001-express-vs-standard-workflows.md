# ADR-001: Express vs Standard Step Functions Workflows

**Status**: Accepted
**Date**: 2026-03-18
**Decision Makers**: Project Team

## Context

The incident analysis orchestrator needs a workflow engine to coordinate 7 Lambda functions (event transformer, 3 parallel collectors, correlation engine, LLM analyzer, notification service). AWS Step Functions offers two workflow types:

- **Standard Workflows**: Durable, exactly-once execution, up to 1 year duration, execution history queryable via API
- **Express Workflows**: At-most-once execution, up to 5 minutes duration, no execution history API, 5x cheaper

Our workflow completes in under 60 seconds (collectors ~1s, LLM ~5s, total ~10s with overhead).

## Decision

Use **Express Workflows**.

## Consequences

### Positive
- **5x cost reduction** vs Standard ($0.000001/transition vs $0.000025/transition)
- Workflow completes well within 5-minute Express limit (typical: 10-15 seconds)
- Higher throughput capacity (Express supports 100,000+ concurrent executions)
- Sufficient for event-driven, short-lived incident analysis

### Negative
- Cannot query execution history via `ListExecutions` API — must use CloudWatch Logs for debugging
- At-most-once semantics: a failed execution may not retry automatically (mitigated by Lambda-level retries and DLQ)
- 5-minute hard limit could be hit if Bedrock is extremely slow (mitigated by 40-second Lambda timeout)

### Mitigations
- CloudWatch Logs enabled on the state machine for full execution tracing
- Dead letter queue captures events that fail all retries
- CloudWatch alarms monitor execution failures and timeouts
