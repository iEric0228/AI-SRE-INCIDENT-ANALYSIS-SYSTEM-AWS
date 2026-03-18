# Operational Runbooks

Procedures for diagnosing and resolving common operational issues with the AI-SRE Incident Analysis System.

**Naming convention**: Resources use the prefix `ai-sre-incident-analysis-` (configurable via `project_name`).

---

## 1. DLQ Processing

Failed events land in the SQS dead letter queue (`ai-sre-incident-analysis-incident-dlq`).

### Inspect messages

```bash
# Check how many messages are in the DLQ
aws sqs get-queue-attributes \
  --queue-url "$(aws sqs get-queue-url --queue-name ai-sre-incident-analysis-incident-dlq --query QueueUrl --output text)" \
  --attribute-names ApproximateNumberOfMessages \
  --query 'Attributes.ApproximateNumberOfMessages' --output text

# Receive and inspect a message (does NOT delete it)
aws sqs receive-message \
  --queue-url "$(aws sqs get-queue-url --queue-name ai-sre-incident-analysis-incident-dlq --query QueueUrl --output text)" \
  --max-number-of-messages 1 \
  --output json | python3 -m json.tool
```

### Replay messages

```bash
# Replay a single message by re-publishing to the incident notifications topic
TOPIC_ARN="arn:aws:sns:us-east-1:<ACCOUNT_ID>:ai-sre-incident-analysis-incident-notifications"
MESSAGE_BODY='<paste message body from receive-message>'

aws sns publish --topic-arn "$TOPIC_ARN" --message "$MESSAGE_BODY"
```

### Purge DLQ (destructive — use only after investigation)

```bash
aws sqs purge-queue \
  --queue-url "$(aws sqs get-queue-url --queue-name ai-sre-incident-analysis-incident-dlq --query QueueUrl --output text)"
```

---

## 2. Lambda Debugging

### Find recent errors

```bash
# Replace <function-name> with one of:
#   ai-sre-incident-analysis-event-transformer
#   ai-sre-incident-analysis-metrics-collector
#   ai-sre-incident-analysis-logs-collector
#   ai-sre-incident-analysis-deploy-context-collector
#   ai-sre-incident-analysis-correlation-engine
#   ai-sre-incident-analysis-llm-analyzer
#   ai-sre-incident-analysis-notification-service

aws logs filter-log-events \
  --log-group-name "/aws/lambda/<function-name>" \
  --start-time "$(python3 -c "import time; print(int((time.time()-3600)*1000))")" \
  --filter-pattern "ERROR" \
  --query 'events[*].message' --output text
```

### Common errors and fixes

| Error | Lambda | Fix |
|-------|--------|-----|
| `No module named 'models'` | Any | Re-run `scripts/package-lambdas.sh` and redeploy |
| `AccessDeniedException` (SSM) | llm-analyzer | Check `PROMPT_TEMPLATE_PARAM` env var matches SSM parameter name |
| `AccessDeniedException` (Bedrock) | llm-analyzer | Verify Bedrock model access is enabled in your account/region |
| `AccessDeniedException` (KMS) | Any publishing to SNS | Ensure IAM role has `kms:Decrypt` + `kms:GenerateDataKey` |
| `ResourceNotFoundException` (DynamoDB) | correlation-engine | Check `DYNAMODB_TABLE` env var matches actual table name |
| `No module named 'idna'` | notification-service | Re-package with `--no-deps` removed from pip install |

### Invoke a Lambda manually

```bash
aws lambda invoke \
  --function-name ai-sre-incident-analysis-metrics-collector \
  --payload '{"incidentId":"test-123","resourceArn":"arn:aws:ec2:us-east-1:123456789:instance/i-abc","timestamp":"2026-01-01T00:00:00Z","metricName":"CPUUtilization","namespace":"AWS/EC2"}' \
  --cli-binary-format raw-in-base64-out \
  /dev/stdout
```

---

## 3. Step Functions Failures

### Check recent executions (Standard workflows only)

Express workflows don't support `list-executions`. Use CloudWatch Logs instead.

```bash
# View Step Functions log group for errors
aws logs filter-log-events \
  --log-group-name "/aws/states/ai-sre-incident-analysis-orchestrator" \
  --start-time "$(python3 -c "import time; print(int((time.time()-3600)*1000))")" \
  --filter-pattern "TaskFailed" \
  --query 'events[*].message' --output text
```

### Common failure patterns

| Pattern | Cause | Fix |
|---------|-------|-----|
| All 3 collectors fail | IAM permission issue or wrong env vars | Check CloudWatch logs for specific error |
| LLM Analyzer timeout | Bedrock latency spike | The circuit breaker returns a fallback report; no action needed unless persistent |
| StoreIncident fails | JSONPath mismatch in state machine definition | Compare Step Functions definition with actual Lambda output shape |
| Notification fails but incident stored | Slack webhook expired or email bounce | Rotate webhook secret (see Section 7) |

---

## 4. Bedrock Throttling / Circuit Breaker

The LLM Analyzer includes a circuit breaker that opens after repeated Bedrock failures.

### Check if circuit breaker is tripping

```bash
aws logs filter-log-events \
  --log-group-name "/aws/lambda/ai-sre-incident-analysis-llm-analyzer" \
  --start-time "$(python3 -c "import time; print(int((time.time()-3600)*1000))")" \
  --filter-pattern "circuit" \
  --query 'events[*].message' --output text
```

### Check Bedrock service quotas

```bash
aws service-quotas get-service-quota \
  --service-code bedrock \
  --quota-code L-XXXXXX  # Replace with your actual quota code
```

### Workaround

When the circuit breaker opens, the LLM Analyzer returns a fallback report with `"confidence": "low"` and `"rootCauseHypothesis": "Analysis unavailable"`. The incident is still stored and notifications still fire — just without AI analysis. The circuit breaker resets automatically after cooldown.

---

## 5. DynamoDB Issues

### Check for throttling

```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/DynamoDB \
  --metric-name UserErrors \
  --dimensions Name=TableName,Value=incident-analysis-store \
  --start-time "$(date -u -v-1H +%Y-%m-%dT%H:%M:%S)" \
  --end-time "$(date -u +%Y-%m-%dT%H:%M:%S)" \
  --period 300 --statistics Sum
```

### TTL not expiring items

DynamoDB TTL deletes are best-effort and can lag up to 48 hours. If items older than 90 days remain:
- Verify TTL is enabled: `aws dynamodb describe-time-to-live --table-name incident-analysis-store`
- Verify items have a numeric `ttl` attribute (Unix epoch seconds)

### Point-in-Time Recovery (PITR) restore

```bash
# Restore table to a specific point in time
aws dynamodb restore-table-to-point-in-time \
  --source-table-name incident-analysis-store \
  --target-table-name incident-analysis-store-restored \
  --restore-date-time "2026-03-18T12:00:00Z"
```

---

## 6. Alarm Noise During Maintenance

To temporarily suppress alarms during planned maintenance:

```bash
# Disable alarm actions (alarms still evaluate, but don't notify)
aws cloudwatch disable-alarm-actions \
  --alarm-names \
    "ai-sre-incident-analysis-workflow-failures" \
    "ai-sre-incident-analysis-llm-analyzer-errors" \
    "ai-sre-incident-analysis-notification-errors"

# Re-enable after maintenance
aws cloudwatch enable-alarm-actions \
  --alarm-names \
    "ai-sre-incident-analysis-workflow-failures" \
    "ai-sre-incident-analysis-llm-analyzer-errors" \
    "ai-sre-incident-analysis-notification-errors"
```

---

## 7. Secret Rotation

### Rotate Slack webhook URL

```bash
# Update the secret value
aws secretsmanager put-secret-value \
  --secret-id "ai-sre-incident-analysis/slack-webhook" \
  --secret-string '{"webhook_url":"https://hooks.slack.com/services/NEW/WEBHOOK/URL"}'
```

No Lambda restart needed — the notification service reads the secret on each invocation.

### KMS key rotation

KMS automatic key rotation is enabled by default in the Terraform config. To manually rotate:

```bash
aws kms enable-key-rotation --key-id <key-id>
```

---

## 8. Full System Recovery

If you need to destroy and redeploy the entire system:

```bash
# 1. Destroy infrastructure
cd terraform && terraform destroy

# 2. Force-delete Secrets Manager secrets (they have a 7-day pending deletion window)
aws secretsmanager delete-secret \
  --secret-id "ai-sre-incident-analysis/slack-webhook" \
  --force-delete-without-recovery

aws secretsmanager delete-secret \
  --secret-id "ai-sre-incident-analysis/email-config" \
  --force-delete-without-recovery

# 3. Wait ~60 seconds for deletion to propagate

# 4. Re-package Lambdas
bash scripts/package-lambdas.sh

# 5. Redeploy
cd terraform && terraform apply

# 6. Recreate SSM prompt template
python scripts/create_prompt_template.py
# Or manually:
aws ssm put-parameter \
  --name "/ai-sre-incident-analysis/prompt-template" \
  --type String \
  --value '<prompt template content>'
```
