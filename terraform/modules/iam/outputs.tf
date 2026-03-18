# Outputs for IAM module

# Lambda Function Role ARNs
output "metrics_collector_role_arn" {
  description = "ARN of the Metrics Collector Lambda IAM role"
  value       = aws_iam_role.metrics_collector.arn
}

output "metrics_collector_role_name" {
  description = "Name of the Metrics Collector Lambda IAM role"
  value       = aws_iam_role.metrics_collector.name
}

output "logs_collector_role_arn" {
  description = "ARN of the Logs Collector Lambda IAM role"
  value       = aws_iam_role.logs_collector.arn
}

output "logs_collector_role_name" {
  description = "Name of the Logs Collector Lambda IAM role"
  value       = aws_iam_role.logs_collector.name
}

output "deploy_context_collector_role_arn" {
  description = "ARN of the Deploy Context Collector Lambda IAM role"
  value       = aws_iam_role.deploy_context_collector.arn
}

output "deploy_context_collector_role_name" {
  description = "Name of the Deploy Context Collector Lambda IAM role"
  value       = aws_iam_role.deploy_context_collector.name
}

output "correlation_engine_role_arn" {
  description = "ARN of the Correlation Engine Lambda IAM role"
  value       = aws_iam_role.correlation_engine.arn
}

output "correlation_engine_role_name" {
  description = "Name of the Correlation Engine Lambda IAM role"
  value       = aws_iam_role.correlation_engine.name
}

output "llm_analyzer_role_arn" {
  description = "ARN of the LLM Analyzer Lambda IAM role"
  value       = aws_iam_role.llm_analyzer.arn
}

output "llm_analyzer_role_name" {
  description = "Name of the LLM Analyzer Lambda IAM role"
  value       = aws_iam_role.llm_analyzer.name
}

output "notification_service_role_arn" {
  description = "ARN of the Notification Service Lambda IAM role"
  value       = aws_iam_role.notification_service.arn
}

output "notification_service_role_name" {
  description = "Name of the Notification Service Lambda IAM role"
  value       = aws_iam_role.notification_service.name
}

output "event_transformer_role_arn" {
  description = "ARN of the Event Transformer Lambda IAM role"
  value       = aws_iam_role.event_transformer.arn
}

output "event_transformer_role_name" {
  description = "Name of the Event Transformer Lambda IAM role"
  value       = aws_iam_role.event_transformer.name
}

# Step Functions Orchestrator Role
output "orchestrator_role_arn" {
  description = "ARN of the Step Functions Orchestrator IAM role"
  value       = aws_iam_role.orchestrator.arn
}

output "orchestrator_role_name" {
  description = "Name of the Step Functions Orchestrator IAM role"
  value       = aws_iam_role.orchestrator.name
}

# All Lambda Role ARNs (for convenience)
output "lambda_role_arns" {
  description = "Map of all Lambda function role ARNs"
  value = {
    metrics_collector        = aws_iam_role.metrics_collector.arn
    logs_collector           = aws_iam_role.logs_collector.arn
    deploy_context_collector = aws_iam_role.deploy_context_collector.arn
    correlation_engine       = aws_iam_role.correlation_engine.arn
    llm_analyzer             = aws_iam_role.llm_analyzer.arn
    notification_service     = aws_iam_role.notification_service.arn
    event_transformer        = aws_iam_role.event_transformer.arn
  }
}
