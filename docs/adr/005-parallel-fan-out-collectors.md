# ADR-005: Parallel Fan-Out Data Collectors

**Status**: Accepted
**Date**: 2026-03-18
**Decision Makers**: Project Team

## Context

The incident analysis system needs to gather three types of context data for each incident:

1. **CloudWatch Metrics** — CPU, memory, network, disk for the affected resource
2. **CloudWatch Logs** — Error and warning logs around the incident time
3. **CloudTrail Events** — Recent deployments and configuration changes

These three data sources are independent — collecting metrics doesn't depend on logs, and vice versa.

## Decision

Use **Step Functions Parallel state** to fan out all 3 collectors simultaneously, then merge results in the correlation engine.

```
Event Transformer
       |
  ┌────┼────┐
  ▼    ▼    ▼
Metrics Logs Deploy   (parallel)
  └────┼────┘
       ▼
Correlation Engine    (merge)
       ▼
  LLM Analyzer
       ▼
  Notification
```

## Consequences

### Positive
- **3x faster data collection** — collectors run in ~1-2s each; parallel execution means total collection time equals the slowest collector, not the sum
- **Independent failure isolation** — each collector branch has its own Catch block; if one fails, the others still provide partial data
- **Graceful degradation** — the correlation engine and LLM analyzer can work with partial context (1 or 2 collectors succeeding)
- **Simple scaling** — adding a 4th collector (e.g., AWS Config history) requires only adding a branch to the Parallel state

### Negative
- Higher concurrent Lambda invocations per incident (3 instead of 1 sequential call)
- Step Functions Parallel state adds slight orchestration overhead (~100ms)
- Debugging requires checking 3 separate CloudWatch Log groups

### Notes
- Each collector has a 20-second timeout — well within the Express Workflow's 5-minute limit
- Retry policy: 3 attempts with exponential backoff (2s, 4s, 8s) per collector
- The correlation engine tracks `completeness` to indicate which data sources succeeded
