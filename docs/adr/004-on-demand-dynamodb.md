# ADR-004: On-Demand DynamoDB Billing

**Status**: Accepted
**Date**: 2026-03-18
**Decision Makers**: Project Team

## Context

DynamoDB offers two capacity modes:

- **Provisioned**: Pre-allocate read/write capacity units. Predictable cost, but requires capacity planning and risks throttling if underprovisioned.
- **On-Demand (PAY_PER_REQUEST)**: Auto-scales transparently. Higher per-request cost, but zero capacity planning needed.

The incident analysis system stores incidents sporadically — traffic is bursty (0 writes for hours, then a burst of writes during an incident). Average volume: ~100 incidents/month.

## Decision

Use **On-Demand (PAY_PER_REQUEST)** billing mode.

## Consequences

### Positive
- **Zero throttling risk** — DynamoDB auto-scales to any traffic pattern
- **No capacity planning** needed — ideal for unpredictable incident-driven workloads
- **Cost-effective at low volume**: ~$0.25/month at 100 incidents vs minimum ~$0.58/month for provisioned (1 RCU + 1 WCU)
- No autoscaling policies to manage or tune

### Negative
- Higher per-request cost than optimally provisioned capacity ($1.25/million writes vs $0.00065/WCU-hour)
- No cost ceiling — a runaway loop could generate unbounded writes
- At very high volume (10,000+ incidents/month), provisioned with autoscaling would be cheaper

### Mitigations
- **CloudWatch alarms** monitor write capacity spikes (Alarm 11: `dynamodb-write-spike`)
- **90-day TTL** prevents unbounded table growth
- **Lambda concurrency limits** (10 per function) cap the maximum write rate
- At current volume, on-demand costs are negligible (<$1/month)
