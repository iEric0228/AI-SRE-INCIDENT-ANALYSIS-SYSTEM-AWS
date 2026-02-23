# Step Functions State Machine Module
# This module creates the Express Workflow orchestrator for incident analysis

# CloudWatch Log Group for Step Functions
resource "aws_cloudwatch_log_group" "state_machine" {
  name              = "/aws/vendedlogs/states/${var.project_name}-orchestrator"
  retention_in_days = 7

  tags = var.tags
}

# Step Functions State Machine
resource "aws_sfn_state_machine" "incident_orchestrator" {
  name     = "${var.project_name}-orchestrator"
  role_arn = var.state_machine_role_arn
  type     = "EXPRESS"

  definition = jsonencode({
    Comment = "AI-Assisted Incident Analysis Workflow"
    StartAt = "ParallelDataCollection"
    States = {
      # Parallel data collection from three collectors
      ParallelDataCollection = {
        Type = "Parallel"
        Branches = [
          # Branch 1: Metrics Collector
          {
            StartAt = "CollectMetrics"
            States = {
              CollectMetrics = {
                Type           = "Task"
                Resource       = var.lambda_function_arns.metrics_collector
                TimeoutSeconds = 20
                Retry = [
                  {
                    ErrorEquals     = ["ThrottlingException", "ServiceException", "TooManyRequestsException"]
                    IntervalSeconds = 2
                    MaxAttempts     = 3
                    BackoffRate     = 2.0
                  }
                ]
                Catch = [
                  {
                    ErrorEquals = ["States.ALL"]
                    ResultPath  = "$.metricsError"
                    Next        = "MetricsCollectionFailed"
                  }
                ]
                End = true
              }
              MetricsCollectionFailed = {
                Type = "Pass"
                Result = {
                  status = "failed"
                  error  = "Metrics collection failed"
                }
                End = true
              }
            }
          },
          # Branch 2: Logs Collector
          {
            StartAt = "CollectLogs"
            States = {
              CollectLogs = {
                Type           = "Task"
                Resource       = var.lambda_function_arns.logs_collector
                TimeoutSeconds = 20
                Retry = [
                  {
                    ErrorEquals     = ["ThrottlingException", "ServiceException", "TooManyRequestsException"]
                    IntervalSeconds = 2
                    MaxAttempts     = 3
                    BackoffRate     = 2.0
                  }
                ]
                Catch = [
                  {
                    ErrorEquals = ["States.ALL"]
                    ResultPath  = "$.logsError"
                    Next        = "LogsCollectionFailed"
                  }
                ]
                End = true
              }
              LogsCollectionFailed = {
                Type = "Pass"
                Result = {
                  status = "failed"
                  error  = "Logs collection failed"
                }
                End = true
              }
            }
          },
          # Branch 3: Deploy Context Collector
          {
            StartAt = "CollectDeployContext"
            States = {
              CollectDeployContext = {
                Type           = "Task"
                Resource       = var.lambda_function_arns.deploy_context_collector
                TimeoutSeconds = 20
                Retry = [
                  {
                    ErrorEquals     = ["ThrottlingException", "ServiceException", "TooManyRequestsException"]
                    IntervalSeconds = 2
                    MaxAttempts     = 3
                    BackoffRate     = 2.0
                  }
                ]
                Catch = [
                  {
                    ErrorEquals = ["States.ALL"]
                    ResultPath  = "$.changesError"
                    Next        = "DeployContextCollectionFailed"
                  }
                ]
                End = true
              }
              DeployContextCollectionFailed = {
                Type = "Pass"
                Result = {
                  status = "failed"
                  error  = "Deploy context collection failed"
                }
                End = true
              }
            }
          }
        ]
        ResultPath = "$.collectorResults"
        Next       = "CorrelateData"
      }

      # Correlation Engine - merges collector outputs
      CorrelateData = {
        Type           = "Task"
        Resource       = var.lambda_function_arns.correlation_engine
        TimeoutSeconds = 10
        Retry = [
          {
            ErrorEquals     = ["ThrottlingException", "ServiceException", "TooManyRequestsException"]
            IntervalSeconds = 2
            MaxAttempts     = 3
            BackoffRate     = 2.0
          }
        ]
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            ResultPath  = "$.correlationError"
            Next        = "CorrelationFailed"
          }
        ]
        ResultPath = "$.structuredContext"
        Next       = "AnalyzeWithLLM"
      }

      # Correlation failure handler
      CorrelationFailed = {
        Type  = "Fail"
        Error = "CorrelationEngineFailure"
        Cause = "Failed to correlate collector data"
      }

      # LLM Analyzer - generates root cause hypothesis
      AnalyzeWithLLM = {
        Type           = "Task"
        Resource       = var.lambda_function_arns.llm_analyzer
        TimeoutSeconds = 40
        Retry = [
          {
            ErrorEquals     = ["ThrottlingException", "TooManyRequestsException"]
            IntervalSeconds = 2
            MaxAttempts     = 3
            BackoffRate     = 2.0
          }
        ]
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            ResultPath  = "$.analysisError"
            Next        = "NotifyAndStore"
          }
        ]
        ResultPath = "$.analysisReport"
        Next       = "NotifyAndStore"
      }

      # Parallel notification and storage
      NotifyAndStore = {
        Type = "Parallel"
        Branches = [
          # Branch 1: Send Notification
          {
            StartAt = "SendNotification"
            States = {
              SendNotification = {
                Type           = "Task"
                Resource       = var.lambda_function_arns.notification_service
                TimeoutSeconds = 15
                Retry = [
                  {
                    ErrorEquals     = ["ThrottlingException", "ServiceException"]
                    IntervalSeconds = 1
                    MaxAttempts     = 2
                    BackoffRate     = 2.0
                  }
                ]
                Catch = [
                  {
                    ErrorEquals = ["States.ALL"]
                    ResultPath  = "$.notificationError"
                    Next        = "NotificationFailed"
                  }
                ]
                End = true
              }
              NotificationFailed = {
                Type = "Pass"
                Result = {
                  status = "failed"
                  error  = "Notification delivery failed"
                }
                End = true
              }
            }
          },
          # Branch 2: Store Incident
          {
            StartAt = "StoreIncident"
            States = {
              StoreIncident = {
                Type     = "Task"
                Resource = "arn:aws:states:::dynamodb:putItem"
                Parameters = {
                  TableName = var.dynamodb_table_name
                  Item = {
                    incidentId = {
                      "S.$" = "$.incident.incidentId"
                    }
                    timestamp = {
                      "S.$" = "$.incident.timestamp"
                    }
                    resourceArn = {
                      "S.$" = "$.incident.resourceArn"
                    }
                    resourceType = {
                      "S.$" = "$.structuredContext.resource.type"
                    }
                    alarmName = {
                      "S.$" = "$.incident.alarmName"
                    }
                    severity = {
                      S = "high"
                    }
                    structuredContext = {
                      "S.$" = "States.JsonToString($.structuredContext)"
                    }
                    analysisReport = {
                      "S.$" = "States.JsonToString($.analysisReport)"
                    }
                    notificationStatus = {
                      "S.$" = "States.JsonToString($.notificationResults[0])"
                    }
                    ttl = {
                      "N.$" = "States.Format('{}', $.incident.ttl)"
                    }
                  }
                }
                Retry = [
                  {
                    ErrorEquals     = ["ThrottlingException", "ProvisionedThroughputExceededException"]
                    IntervalSeconds = 2
                    MaxAttempts     = 3
                    BackoffRate     = 2.0
                  }
                ]
                Catch = [
                  {
                    ErrorEquals = ["States.ALL"]
                    ResultPath  = "$.storageError"
                    Next        = "StorageFailed"
                  }
                ]
                End = true
              }
              StorageFailed = {
                Type = "Pass"
                Result = {
                  status = "failed"
                  error  = "Incident storage failed"
                }
                End = true
              }
            }
          }
        ]
        End = true
      }
    }
  })

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.state_machine.arn}:*"
    include_execution_data = true
    level                  = "ALL"
  }

  tracing_configuration {
    enabled = true
  }

  tags = var.tags
}

