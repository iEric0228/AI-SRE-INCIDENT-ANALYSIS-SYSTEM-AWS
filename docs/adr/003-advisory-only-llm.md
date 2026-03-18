# ADR-003: Advisory-Only LLM with Explicit IAM Denies

**Status**: Accepted
**Date**: 2026-03-18
**Decision Makers**: Project Team

## Context

The LLM Analyzer Lambda invokes Amazon Bedrock (Claude 3 Haiku) to generate root cause hypotheses for incidents. LLMs can produce hallucinated or incorrect outputs. In an SRE context, an LLM that can take autonomous remediation actions (restart instances, scale resources, modify configurations) poses a significant risk.

## Decision

The LLM is **advisory only** — it can read data and produce analysis, but **cannot modify any AWS resources**. This is enforced at the IAM level with explicit deny statements.

### IAM Denies on the LLM Analyzer Role

```hcl
statement {
  sid    = "DenyDangerousActions"
  effect = "Deny"
  actions = [
    "ec2:*", "rds:*", "iam:*",
    "lambda:Update*", "lambda:Delete*",
    "dynamodb:Delete*",
    "cloudformation:*", "s3:Delete*"
  ]
  resources = ["*"]
}
```

## Consequences

### Positive
- **Zero blast radius** from LLM hallucinations — even if prompt injection occurs, the Lambda cannot take destructive actions
- Explicit deny overrides any allow, so future IAM changes cannot accidentally grant dangerous permissions
- Clear separation of concerns: the LLM analyzes, humans remediate
- Builds trust with SRE teams who can rely on the system for insights without fear of automated damage

### Negative
- No automated remediation capability (e.g., auto-scaling, instance restart)
- Humans must act on recommendations manually

### Future Considerations
- If automated remediation is desired, it should be a separate Lambda with its own IAM role, human approval gates (e.g., Slack interactive buttons), and audit logging
