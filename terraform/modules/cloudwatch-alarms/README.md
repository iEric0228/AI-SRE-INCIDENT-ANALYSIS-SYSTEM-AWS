# CloudWatch Alarms Module

This module creates CloudWatch alarms and a dashboard to monitor the AI-Assisted SRE Incident Analysis System itself. It provides comprehensive observability for the incident analysis workflow, ensuring the system is healthy and operational.

## Features

- **SNS Topic for Operational Alerts**: Central notification point for system health issues
- **Step Functions Monitoring**: Alarms for workflow failures and timeouts
- **LLM Analyzer Monitoring**: Alarms for errors, timeouts, and throttling
- **Notification Service Monitoring**: Alarms for delivery failures
- **Data Collector Monitoring**: Alarms for collector failures
- **DynamoDB Monitoring**: Alarms for throttling and capacity issues
- **Correlation Engine Monitoring**: Alarms for data processing errors
- **Custom Metric Filters**: Extract specific failure patterns from logs
- **CloudWatch Dashboard**: Visual overview of system health
- **Email Notifications**: Optional email alerts for ops team

## Architecture

```
CloudWatch Alarms
    ↓
SNS Topic (Ops Alerts)
    ↓
Email Subscription (Ops Team)

Monitored Components:
- Step Functions Orchestrator
- LLM Analyzer Lambda
- Notification Service Lambda
- Correlation Engine Lambda
- Data Collectors (Metrics, Logs, Deploy Context)
- DynamoDB Incident Store
```

## Alarms

### 1. Workflow Failures Alarm

Monitors Step Functions workflow execution failures.

- **Metric**: `ExecutionsFailed` (AWS/States)
- **Threshold**: > 0 failures in 5 minutes
- **Severity**: High
- **Action**: Publish to ops alerts topic

**Triggers when**: The incident analysis workflow fails due to unhandled errors.

### 2. Workflow Timeouts Alarm

Monitors Step Functions workflow timeouts.

- **Metric**: `ExecutionsTimedOut` (AWS/States)
- **Threshold**: > 0 timeouts in 5 minutes
- **Severity**: High
- **Action**: Publish to ops alerts topic

**Triggers when**: The workflow exceeds the 120-second timeout threshold.

### 3. LLM Analyzer Errors Alarm

Monitors LLM analyzer Lambda function errors.

- **Metric**: `Errors` (AWS/Lambda)
- **Threshold**: > 2 errors in 10 minutes (2 evaluation periods)
- **Severity**: Medium
- **Action**: Publish to ops alerts topic

**Triggers when**: The LLM analyzer encounters multiple errors (Bedrock failures, parsing errors, etc.).

### 4. LLM Analyzer Timeouts Alarm

Monitors LLM analyzer Lambda function duration approaching timeout.

- **Metric**: `Duration` (AWS/Lambda)
- **Threshold**: > 35 seconds (approaching 40-second timeout)
- **Severity**: Medium
- **Action**: Publish to ops alerts topic

**Triggers when**: LLM invocations are taking too long, risking timeout.

### 5. LLM Analyzer Throttles Alarm

Monitors LLM analyzer Lambda function throttling.

- **Metric**: `Throttles` (AWS/Lambda)
- **Threshold**: > 0 throttles in 5 minutes
- **Severity**: High
- **Action**: Publish to ops alerts topic

**Triggers when**: Lambda concurrency limits are reached or Bedrock rate limits are hit.

### 6. Notification Service Errors Alarm

Monitors notification service Lambda function errors.

- **Metric**: `Errors` (AWS/Lambda)
- **Threshold**: > 2 errors in 10 minutes (2 evaluation periods)
- **Severity**: Medium
- **Action**: Publish to ops alerts topic

**Triggers when**: The notification service encounters multiple errors.

### 7. Notification Delivery Failures Alarm

Monitors complete notification delivery failures (both Slack and email).

- **Metric**: `NotificationDeliveryFailures` (Custom)
- **Threshold**: > 0 failures in 5 minutes
- **Severity**: High
- **Action**: Publish to ops alerts topic

**Triggers when**: Both Slack and email notification delivery fail for an incident.

**Note**: This alarm uses a custom metric filter that parses notification service logs for the pattern:
```json
{ "deliveryStatus": { "slack": "failed", "email": "failed" } }
```

### 8. Collector Failures Alarm

Monitors data collector failures across all three collectors.

- **Metric**: `CollectorFailures` (Custom)
- **Threshold**: > 3 failures in 10 minutes (2 evaluation periods)
- **Severity**: Medium
- **Action**: Publish to ops alerts topic

**Triggers when**: Multiple data collectors (metrics, logs, deploy context) fail.

**Note**: This alarm uses a custom metric filter that parses Step Functions logs for TaskFailed events.

### 9. DynamoDB Throttles Alarm

Monitors DynamoDB incident store throttling.

- **Metric**: `UserErrors` (AWS/DynamoDB)
- **Threshold**: > 5 errors in 5 minutes
- **Severity**: Medium
- **Action**: Publish to ops alerts topic

**Triggers when**: DynamoDB write capacity is exceeded, causing throttling.

### 10. Correlation Engine Errors Alarm

Monitors correlation engine Lambda function errors.

- **Metric**: `Errors` (AWS/Lambda)
- **Threshold**: > 2 errors in 10 minutes (2 evaluation periods)
- **Severity**: High
- **Action**: Publish to ops alerts topic

**Triggers when**: The correlation engine fails to merge and normalize collector data.

## CloudWatch Dashboard

The module creates a comprehensive dashboard with the following widgets:

1. **Step Functions Workflow Health**
   - Workflows Started
   - Workflows Succeeded
   - Workflows Failed
   - Workflows Timed Out

2. **LLM Analyzer Health**
   - Invocations
   - Errors
   - Average Duration
   - Throttles

3. **Notification Service Health**
   - Invocations
   - Errors
   - Delivery Failures

4. **Data Collector Health**
   - Collector Failures

5. **DynamoDB Incident Store Health**
   - Read Capacity Consumed
   - Write Capacity Consumed
   - User Errors

## Usage

```hcl
module "cloudwatch_alarms" {
  source = "./modules/cloudwatch-alarms"

  project_name                         = "ai-sre-incident-analysis"
  aws_region                           = "us-east-1"
  state_machine_arn                    = module.step_functions.state_machine_arn
  state_machine_log_group_name         = module.step_functions.log_group_name
  llm_analyzer_function_name           = module.lambda_llm_analyzer.function_name
  notification_service_function_name   = module.lambda_notification.function_name
  notification_service_log_group_name  = module.lambda_notification.log_group_name
  correlation_engine_function_name     = module.lambda_correlation.function_name
  dynamodb_table_name                  = module.dynamodb.table_name
  kms_key_id                           = aws_kms_key.incident_store.id

  tags = {
    Environment = "production"
    Project     = "AI-SRE-Portfolio"
  }
}
```

## Inputs

| Name | Description | Type | Required |
|------|-------------|------|----------|
| project_name | Name of the project, used for resource naming | string | yes |
| aws_region | AWS region for CloudWatch dashboard | string | yes |
| state_machine_arn | ARN of the Step Functions state machine to monitor | string | yes |
| state_machine_log_group_name | CloudWatch log group name for Step Functions state machine | string | yes |
| llm_analyzer_function_name | Name of the LLM analyzer Lambda function | string | yes |
| notification_service_function_name | Name of the notification service Lambda function | string | yes |
| notification_service_log_group_name | CloudWatch log group name for notification service Lambda | string | yes |
| correlation_engine_function_name | Name of the correlation engine Lambda function | string | yes |
| dynamodb_table_name | Name of the DynamoDB incident store table | string | yes |
| kms_key_id | KMS key ID for encrypting SNS topic | string | yes |
| tags | Tags to apply to all resources | map(string) | no |

## Outputs

| Name | Description |
|------|-------------|
| ops_alerts_topic_arn | ARN of the SNS topic for operational alerts |
| ops_alerts_topic_name | Name of the SNS topic for operational alerts |
| workflow_failures_alarm_arn | ARN of the workflow failures alarm |
| workflow_timeouts_alarm_arn | ARN of the workflow timeouts alarm |
| llm_analyzer_errors_alarm_arn | ARN of the LLM analyzer errors alarm |
| llm_analyzer_timeouts_alarm_arn | ARN of the LLM analyzer timeouts alarm |
| notification_errors_alarm_arn | ARN of the notification service errors alarm |
| notification_delivery_failures_alarm_arn | ARN of the notification delivery failures alarm |
| collector_failures_alarm_arn | ARN of the collector failures alarm |
| dynamodb_throttles_alarm_arn | ARN of the DynamoDB throttles alarm |
| correlation_engine_errors_alarm_arn | ARN of the correlation engine errors alarm |
| dashboard_name | Name of the CloudWatch dashboard for system health |
| dashboard_arn | ARN of the CloudWatch dashboard for system health |

## Custom Metric Filters

### Notification Delivery Failures Filter

Extracts notification delivery failures from Lambda logs:

```json
{
  "$.deliveryStatus.slack": "failed",
  "$.deliveryStatus.email": "failed"
}
```

This pattern matches structured JSON logs where both Slack and email delivery failed.

### Collector Failures Filter

Extracts collector failures from Step Functions logs:

```json
{
  "$.type": "TaskFailed",
  "$.resource": "*metrics-collector*" || "*logs-collector*" || "*deploy-context-collector*"
}
```

This pattern matches Step Functions execution history events where collector tasks failed.

## Alarm Thresholds

The alarm thresholds are configured based on the following principles:

- **Zero-tolerance for critical failures**: Workflow failures, timeouts, and complete notification failures trigger immediately
- **Multiple occurrences for transient errors**: Lambda errors require 2+ occurrences to avoid false positives
- **Capacity-based thresholds**: DynamoDB throttles allow up to 5 errors before alerting
- **Duration-based warnings**: LLM analyzer duration alarm triggers at 35s (87.5% of 40s timeout)

## Monitoring Best Practices

### Alarm Response Procedures

1. **Workflow Failures**:
   - Check Step Functions execution history
   - Review Lambda function logs for errors
   - Verify IAM permissions
   - Check AWS service health dashboard

2. **LLM Analyzer Timeouts**:
   - Review Bedrock service quotas
   - Check prompt size and complexity
   - Consider increasing Lambda timeout
   - Investigate Bedrock API latency

3. **Notification Delivery Failures**:
   - Verify Slack webhook URL in Secrets Manager
   - Check SNS topic subscription status
   - Test Slack webhook manually
   - Review notification service logs

4. **Collector Failures**:
   - Check CloudWatch API quotas
   - Verify IAM permissions for collectors
   - Review resource ARN parsing logic
   - Check for missing log groups or metrics

5. **DynamoDB Throttles**:
   - Review DynamoDB capacity mode (on-demand should auto-scale)
   - Check for hot partition keys
   - Consider enabling auto-scaling for provisioned capacity
   - Review write patterns

### Dashboard Usage

The CloudWatch dashboard provides real-time visibility into system health:

1. **Normal Operation**: All metrics show successful executions with minimal errors
2. **Degraded Performance**: Increased error rates or durations indicate issues
3. **System Failure**: Multiple alarms firing simultaneously indicate critical issues

Access the dashboard:
```bash
aws cloudwatch get-dashboard \
  --dashboard-name ai-sre-incident-analysis-system-health \
  --region us-east-1
```

## Security

- **Encryption**: SNS topic is encrypted with customer-managed KMS key
- **IAM Policies**: Least-privilege policy for CloudWatch to publish to SNS
- **Topic Policy**: Only CloudWatch can publish to the ops alerts topic
- **Email Subscription**: Requires confirmation before receiving alerts

## Cost Optimization

- **Alarm Pricing**: $0.10 per alarm per month (10 alarms = $1.00/month)
- **SNS Pricing**: $0.50 per million requests (negligible for alarm notifications)
- **Dashboard Pricing**: $3.00 per dashboard per month
- **Custom Metrics**: $0.30 per metric per month (2 custom metrics = $0.60/month)
- **Total Estimated Cost**: ~$5/month for complete monitoring

## Compliance

This module validates the following requirements:

- **11.4**: CloudWatch Alarms for workflow failures, LLM timeout, and notification delivery failures
- **11.1**: Structured JSON logs for all Lambda functions (monitored via metric filters)
- **11.3**: Custom CloudWatch metrics for workflow duration, collector success rates, LLM invocation latency, and notification delivery status

## Testing

### Test Alarm Triggers

1. **Workflow Failures Alarm**:
```bash
# Trigger a workflow with invalid input to cause failure
aws stepfunctions start-execution \
  --state-machine-arn <state-machine-arn> \
  --input '{"invalid": "data"}'
```

2. **LLM Analyzer Errors Alarm**:
```bash
# Invoke LLM analyzer with invalid context
aws lambda invoke \
  --function-name llm-analyzer \
  --payload '{"invalid": "context"}' \
  response.json
```

3. **Notification Delivery Failures Alarm**:
```bash
# Update Slack webhook secret to invalid URL
aws secretsmanager update-secret \
  --secret-id incident-analysis/slack-webhook \
  --secret-string '{"url": "https://invalid.slack.com/webhook"}'

# Trigger notification
aws lambda invoke \
  --function-name notification-service \
  --payload '{"analysisReport": {...}}' \
  response.json
```

### Verify Alarm State

```bash
# Check alarm state
aws cloudwatch describe-alarms \
  --alarm-names ai-sre-incident-analysis-workflow-failures

# Check alarm history
aws cloudwatch describe-alarm-history \
  --alarm-name ai-sre-incident-analysis-workflow-failures \
  --max-records 10
```

### Test SNS Notifications

```bash
# Publish test message to ops alerts topic
aws sns publish \
  --topic-arn <ops-alerts-topic-arn> \
  --subject "Test Alert" \
  --message "This is a test operational alert"
```

## Troubleshooting

### Alarms Not Triggering

1. Check alarm state: `aws cloudwatch describe-alarms`
2. Verify metric data exists: `aws cloudwatch get-metric-statistics`
3. Check alarm evaluation periods and thresholds
4. Review alarm configuration: `aws cloudwatch describe-alarms --alarm-names <name>`

### SNS Notifications Not Received

1. Verify email subscription is confirmed
2. Check SNS topic policy allows CloudWatch to publish
3. Review SNS delivery logs
4. Check spam folder for email notifications

### Custom Metrics Not Appearing

1. Verify log group names match metric filter configuration
2. Check log events match the filter pattern
3. Wait 5-10 minutes for metric data to appear
4. Test filter pattern: `aws logs test-metric-filter`

### Dashboard Not Loading

1. Verify dashboard exists: `aws cloudwatch list-dashboards`
2. Check dashboard JSON syntax
3. Verify metric namespaces and dimensions
4. Review IAM permissions for CloudWatch dashboard access

## Future Enhancements

- **Anomaly Detection**: Use CloudWatch Anomaly Detection for dynamic thresholds
- **Composite Alarms**: Combine multiple alarms for complex failure scenarios
- **Auto-Remediation**: Trigger Lambda functions to automatically fix common issues
- **Slack Integration**: Send alarm notifications directly to Slack channels
- **PagerDuty Integration**: Integrate with on-call rotation systems
- **Cost Anomaly Detection**: Alert on unexpected cost increases
- **Performance Baselines**: Track and alert on performance degradation over time

## Related Modules

- **eventbridge**: Provides the incident detection and routing infrastructure
- **step-functions**: Orchestrates the incident analysis workflow
- **lambda**: Implements the data collectors, correlation engine, LLM analyzer, and notification service
- **dynamodb**: Stores incident history and analysis results

