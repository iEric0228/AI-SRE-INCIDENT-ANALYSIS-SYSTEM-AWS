# CloudWatch Alarms Module
# This module creates CloudWatch alarms to monitor the incident analysis system itself

# SNS Topic for Operational Alerts
resource "aws_sns_topic" "ops_alerts" {
  name              = "${var.project_name}-ops-alerts"
  display_name      = "AI-SRE System Operational Alerts"
  kms_master_key_id = var.kms_key_id

  tags = merge(
    var.tags,
    {
      Purpose = "Operational alerts for incident analysis system"
    }
  )
}

# SNS Topic Policy - Allow CloudWatch to publish
resource "aws_sns_topic_policy" "ops_alerts" {
  arn = aws_sns_topic.ops_alerts.arn

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCloudWatchPublish"
        Effect = "Allow"
        Principal = {
          Service = "cloudwatch.amazonaws.com"
        }
        Action   = "SNS:Publish"
        Resource = aws_sns_topic.ops_alerts.arn
      }
    ]
  })
}

# Alarm 1: Step Functions Workflow Failures
resource "aws_cloudwatch_metric_alarm" "workflow_failures" {
  alarm_name          = "${var.project_name}-workflow-failures"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ExecutionsFailed"
  namespace           = "AWS/States"
  period              = 300 # 5 minutes
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "Alert when Step Functions incident analysis workflow fails"
  treat_missing_data  = "notBreaching"

  dimensions = {
    StateMachineArn = var.state_machine_arn
  }

  alarm_actions = [aws_sns_topic.ops_alerts.arn]

  tags = merge(
    var.tags,
    {
      Component = "Orchestrator"
      Severity  = "High"
    }
  )
}

# Alarm 2: Step Functions Workflow Timeouts
resource "aws_cloudwatch_metric_alarm" "workflow_timeouts" {
  alarm_name          = "${var.project_name}-workflow-timeouts"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ExecutionsTimedOut"
  namespace           = "AWS/States"
  period              = 300 # 5 minutes
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "Alert when Step Functions workflow exceeds 120 second timeout"
  treat_missing_data  = "notBreaching"

  dimensions = {
    StateMachineArn = var.state_machine_arn
  }

  alarm_actions = [aws_sns_topic.ops_alerts.arn]

  tags = merge(
    var.tags,
    {
      Component = "Orchestrator"
      Severity  = "High"
    }
  )
}

# Alarm 3: LLM Analyzer Errors
resource "aws_cloudwatch_metric_alarm" "llm_analyzer_errors" {
  alarm_name          = "${var.project_name}-llm-analyzer-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300 # 5 minutes
  statistic           = "Sum"
  threshold           = 2
  alarm_description   = "Alert when LLM analyzer Lambda function has multiple errors"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = var.llm_analyzer_function_name
  }

  alarm_actions = [aws_sns_topic.ops_alerts.arn]

  tags = merge(
    var.tags,
    {
      Component = "LLM Analyzer"
      Severity  = "Medium"
    }
  )
}

# Alarm 4: LLM Analyzer Timeouts
resource "aws_cloudwatch_metric_alarm" "llm_analyzer_timeouts" {
  alarm_name          = "${var.project_name}-llm-analyzer-timeouts"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Duration"
  namespace           = "AWS/Lambda"
  period              = 300 # 5 minutes
  statistic           = "Maximum"
  threshold           = 35000 # 35 seconds (close to 40 second timeout)
  alarm_description   = "Alert when LLM analyzer approaches timeout threshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = var.llm_analyzer_function_name
  }

  alarm_actions = [aws_sns_topic.ops_alerts.arn]

  tags = merge(
    var.tags,
    {
      Component = "LLM Analyzer"
      Severity  = "Medium"
    }
  )
}

# Alarm 5: LLM Analyzer Throttles
resource "aws_cloudwatch_metric_alarm" "llm_analyzer_throttles" {
  alarm_name          = "${var.project_name}-llm-analyzer-throttles"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Throttles"
  namespace           = "AWS/Lambda"
  period              = 300 # 5 minutes
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "Alert when LLM analyzer Lambda function is throttled"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = var.llm_analyzer_function_name
  }

  alarm_actions = [aws_sns_topic.ops_alerts.arn]

  tags = merge(
    var.tags,
    {
      Component = "LLM Analyzer"
      Severity  = "High"
    }
  )
}

# Alarm 6: Notification Service Errors
resource "aws_cloudwatch_metric_alarm" "notification_errors" {
  alarm_name          = "${var.project_name}-notification-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300 # 5 minutes
  statistic           = "Sum"
  threshold           = 2
  alarm_description   = "Alert when notification service has multiple errors"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = var.notification_service_function_name
  }

  alarm_actions = [aws_sns_topic.ops_alerts.arn]

  tags = merge(
    var.tags,
    {
      Component = "Notification Service"
      Severity  = "Medium"
    }
  )
}

# Custom Metric Filter for Notification Delivery Failures
resource "aws_cloudwatch_log_metric_filter" "notification_delivery_failures" {
  name           = "${var.project_name}-notification-delivery-failures"
  log_group_name = var.notification_service_log_group_name
  pattern        = "{ $.deliveryStatus.slack = \"failed\" && $.deliveryStatus.email = \"failed\" }"

  metric_transformation {
    name      = "NotificationDeliveryFailures"
    namespace = "${var.project_name}/Notifications"
    value     = "1"
    unit      = "Count"
  }
}

# Alarm 7: Notification Delivery Failures (both Slack and Email failed)
resource "aws_cloudwatch_metric_alarm" "notification_delivery_failures" {
  alarm_name          = "${var.project_name}-notification-delivery-failures"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "NotificationDeliveryFailures"
  namespace           = "${var.project_name}/Notifications"
  period              = 300 # 5 minutes
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "Alert when both Slack and email notification delivery fail"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.ops_alerts.arn]

  tags = merge(
    var.tags,
    {
      Component = "Notification Service"
      Severity  = "High"
    }
  )
}

# Custom Metric Filter for Collector Failures
resource "aws_cloudwatch_log_metric_filter" "collector_failures" {
  name           = "${var.project_name}-collector-failures"
  log_group_name = var.state_machine_log_group_name
  pattern        = "{ $.type = \"TaskFailed\" && ($.resource = \"*metrics-collector*\" || $.resource = \"*logs-collector*\" || $.resource = \"*deploy-context-collector*\") }"

  metric_transformation {
    name      = "CollectorFailures"
    namespace = "${var.project_name}/Collectors"
    value     = "1"
    unit      = "Count"
  }
}

# Alarm 8: High Collector Failure Rate
resource "aws_cloudwatch_metric_alarm" "collector_failures" {
  alarm_name          = "${var.project_name}-collector-failures"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CollectorFailures"
  namespace           = "${var.project_name}/Collectors"
  period              = 300 # 5 minutes
  statistic           = "Sum"
  threshold           = 3
  alarm_description   = "Alert when multiple data collectors fail"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.ops_alerts.arn]

  tags = merge(
    var.tags,
    {
      Component = "Data Collectors"
      Severity  = "Medium"
    }
  )
}

# Alarm 9: DynamoDB Write Throttles
resource "aws_cloudwatch_metric_alarm" "dynamodb_throttles" {
  alarm_name          = "${var.project_name}-dynamodb-throttles"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "UserErrors"
  namespace           = "AWS/DynamoDB"
  period              = 300 # 5 minutes
  statistic           = "Sum"
  threshold           = 5
  alarm_description   = "Alert when DynamoDB incident store has throttling errors"
  treat_missing_data  = "notBreaching"

  dimensions = {
    TableName = var.dynamodb_table_name
  }

  alarm_actions = [aws_sns_topic.ops_alerts.arn]

  tags = merge(
    var.tags,
    {
      Component = "Incident Store"
      Severity  = "Medium"
    }
  )
}

# Alarm 10: Correlation Engine Errors
resource "aws_cloudwatch_metric_alarm" "correlation_engine_errors" {
  alarm_name          = "${var.project_name}-correlation-engine-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300 # 5 minutes
  statistic           = "Sum"
  threshold           = 2
  alarm_description   = "Alert when correlation engine has multiple errors"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = var.correlation_engine_function_name
  }

  alarm_actions = [aws_sns_topic.ops_alerts.arn]

  tags = merge(
    var.tags,
    {
      Component = "Correlation Engine"
      Severity  = "High"
    }
  )
}

# Alarm 11: DynamoDB Consumed Write Capacity Anomaly
# Detects unexpected spikes in write activity that could indicate runaway costs
resource "aws_cloudwatch_metric_alarm" "dynamodb_write_spike" {
  alarm_name          = "${var.project_name}-dynamodb-write-spike"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "ConsumedWriteCapacityUnits"
  namespace           = "AWS/DynamoDB"
  period              = 300 # 5 minutes
  statistic           = "Sum"
  threshold           = 500 # ~100 writes/min sustained is abnormal for incident store
  alarm_description   = "Alert when DynamoDB write activity spikes unexpectedly (potential runaway cost)"
  treat_missing_data  = "notBreaching"

  dimensions = {
    TableName = var.dynamodb_table_name
  }

  alarm_actions = [aws_sns_topic.ops_alerts.arn]

  tags = merge(
    var.tags,
    {
      Component = "Incident Store"
      Severity  = "High"
    }
  )
}

# Alarm 12: DynamoDB Consumed Read Capacity Anomaly
resource "aws_cloudwatch_metric_alarm" "dynamodb_read_spike" {
  alarm_name          = "${var.project_name}-dynamodb-read-spike"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "ConsumedReadCapacityUnits"
  namespace           = "AWS/DynamoDB"
  period              = 300 # 5 minutes
  statistic           = "Sum"
  threshold           = 1000
  alarm_description   = "Alert when DynamoDB read activity spikes unexpectedly (potential runaway cost)"
  treat_missing_data  = "notBreaching"

  dimensions = {
    TableName = var.dynamodb_table_name
  }

  alarm_actions = [aws_sns_topic.ops_alerts.arn]

  tags = merge(
    var.tags,
    {
      Component = "Incident Store"
      Severity  = "High"
    }
  )
}

# CloudWatch Dashboard for System Health
resource "aws_cloudwatch_dashboard" "system_health" {
  dashboard_name = "${var.project_name}-system-health"

  dashboard_body = jsonencode({
    widgets = [
      {
        type = "metric"
        properties = {
          metrics = [
            ["AWS/States", "ExecutionsStarted", { stat = "Sum", label = "Workflows Started" }],
            [".", "ExecutionsSucceeded", { stat = "Sum", label = "Workflows Succeeded" }],
            [".", "ExecutionsFailed", { stat = "Sum", label = "Workflows Failed" }],
            [".", "ExecutionsTimedOut", { stat = "Sum", label = "Workflows Timed Out" }]
          ]
          period = 300
          stat   = "Sum"
          region = var.aws_region
          title  = "Step Functions Workflow Health"
          dimensions = {
            StateMachineArn = [var.state_machine_arn]
          }
        }
      },
      {
        type = "metric"
        properties = {
          metrics = [
            ["AWS/Lambda", "Invocations", { stat = "Sum", label = "LLM Invocations" }],
            [".", "Errors", { stat = "Sum", label = "LLM Errors" }],
            [".", "Duration", { stat = "Average", label = "Avg Duration (ms)" }],
            [".", "Throttles", { stat = "Sum", label = "Throttles" }]
          ]
          period = 300
          stat   = "Sum"
          region = var.aws_region
          title  = "LLM Analyzer Health"
          dimensions = {
            FunctionName = [var.llm_analyzer_function_name]
          }
        }
      },
      {
        type = "metric"
        properties = {
          metrics = [
            ["AWS/Lambda", "Invocations", { stat = "Sum", label = "Notification Invocations" }],
            [".", "Errors", { stat = "Sum", label = "Notification Errors" }],
            ["${var.project_name}/Notifications", "NotificationDeliveryFailures", { stat = "Sum", label = "Delivery Failures" }]
          ]
          period = 300
          stat   = "Sum"
          region = var.aws_region
          title  = "Notification Service Health"
          dimensions = {
            FunctionName = [var.notification_service_function_name]
          }
        }
      },
      {
        type = "metric"
        properties = {
          metrics = [
            ["${var.project_name}/Collectors", "CollectorFailures", { stat = "Sum", label = "Collector Failures" }]
          ]
          period = 300
          stat   = "Sum"
          region = var.aws_region
          title  = "Data Collector Health"
        }
      },
      {
        type = "metric"
        properties = {
          metrics = [
            ["AWS/DynamoDB", "ConsumedReadCapacityUnits", { stat = "Sum", label = "Read Capacity" }],
            [".", "ConsumedWriteCapacityUnits", { stat = "Sum", label = "Write Capacity" }],
            [".", "UserErrors", { stat = "Sum", label = "User Errors" }]
          ]
          period = 300
          stat   = "Sum"
          region = var.aws_region
          title  = "DynamoDB Incident Store Health"
          dimensions = {
            TableName = [var.dynamodb_table_name]
          }
        }
      },
      # Widget 6: LLM Response Parse Quality
      # Tracks which fallback level the response parser used each invocation.
      # Level 1 = JSON parsed cleanly (ideal), Level 2 = text extraction fallback,
      # Level 3 = minimal report (Bedrock output was unparseable — investigate promptly).
      # A rising Level 2/3 count signals prompt drift or Bedrock model changes.
      {
        type = "metric"
        properties = {
          metrics = [
            ["${var.metric_namespace}", "LLMParseLevel", "Level", "1", { stat = "Sum", label = "Level 1 — JSON parse (ideal)" }],
            [".", ".", "Level", "2", { stat = "Sum", label = "Level 2 — text extraction (fallback)" }],
            [".", ".", "Level", "3", { stat = "Sum", label = "Level 3 — minimal report (degraded)" }]
          ]
          period = 300
          region = var.aws_region
          title  = "LLM Response Parse Quality"
          view   = "timeSeries"
        }
      },
      # Widget 7: Context Truncation
      # Fires whenever the correlation engine had to truncate data to stay within
      # the 50 KB LLM context limit. SampleCount = number of truncation events;
      # Maximum = largest payload seen before trimming.
      # Sustained truncations indicate high-cardinality incidents and may degrade
      # analysis quality — consider tightening collector window parameters.
      {
        type = "metric"
        properties = {
          metrics = [
            ["${var.metric_namespace}", "ContextTruncatedOriginalSizeBytes", { stat = "SampleCount", label = "Truncation Events (count)", id = "m1" }],
            [".", ".", { stat = "Maximum", label = "Max Payload Before Trim (Bytes)", yAxis = "right", id = "m2" }]
          ]
          period = 300
          region = var.aws_region
          title  = "Context Truncation"
        }
      }
    ]
  })
}
