# Outputs for Lambda module

# Lambda Function ARNs
output "metrics_collector_arn" {
  description = "ARN of the Metrics Collector Lambda function"
  value       = aws_lambda_function.metrics_collector.arn
}

output "metrics_collector_name" {
  description = "Name of the Metrics Collector Lambda function"
  value       = aws_lambda_function.metrics_collector.function_name
}

output "logs_collector_arn" {
  description = "ARN of the Logs Collector Lambda function"
  value       = aws_lambda_function.logs_collector.arn
}

output "logs_collector_name" {
  description = "Name of the Logs Collector Lambda function"
  value       = aws_lambda_function.logs_collector.function_name
}

output "deploy_context_collector_arn" {
  description = "ARN of the Deploy Context Collector Lambda function"
  value       = aws_lambda_function.deploy_context_collector.arn
}

output "deploy_context_collector_name" {
  description = "Name of the Deploy Context Collector Lambda function"
  value       = aws_lambda_function.deploy_context_collector.function_name
}

output "correlation_engine_arn" {
  description = "ARN of the Correlation Engine Lambda function"
  value       = aws_lambda_function.correlation_engine.arn
}

output "correlation_engine_name" {
  description = "Name of the Correlation Engine Lambda function"
  value       = aws_lambda_function.correlation_engine.function_name
}

output "llm_analyzer_arn" {
  description = "ARN of the LLM Analyzer Lambda function"
  value       = aws_lambda_function.llm_analyzer.arn
}

output "llm_analyzer_name" {
  description = "Name of the LLM Analyzer Lambda function"
  value       = aws_lambda_function.llm_analyzer.function_name
}

output "notification_service_arn" {
  description = "ARN of the Notification Service Lambda function"
  value       = aws_lambda_function.notification_service.arn
}

output "notification_service_name" {
  description = "Name of the Notification Service Lambda function"
  value       = aws_lambda_function.notification_service.function_name
}

output "event_transformer_arn" {
  description = "ARN of the Event Transformer Lambda function"
  value       = aws_lambda_function.event_transformer.arn
}

output "event_transformer_name" {
  description = "Name of the Event Transformer Lambda function"
  value       = aws_lambda_function.event_transformer.function_name
}

# All Lambda Function ARNs (for convenience)
output "lambda_function_arns" {
  description = "Map of all Lambda function ARNs"
  value = {
    metrics_collector        = aws_lambda_function.metrics_collector.arn
    logs_collector           = aws_lambda_function.logs_collector.arn
    deploy_context_collector = aws_lambda_function.deploy_context_collector.arn
    correlation_engine       = aws_lambda_function.correlation_engine.arn
    llm_analyzer             = aws_lambda_function.llm_analyzer.arn
    notification_service     = aws_lambda_function.notification_service.arn
    event_transformer        = aws_lambda_function.event_transformer.arn
  }
}

# All Lambda Function Names (for convenience)
output "lambda_function_names" {
  description = "Map of all Lambda function names"
  value = {
    metrics_collector        = aws_lambda_function.metrics_collector.function_name
    logs_collector           = aws_lambda_function.logs_collector.function_name
    deploy_context_collector = aws_lambda_function.deploy_context_collector.function_name
    correlation_engine       = aws_lambda_function.correlation_engine.function_name
    llm_analyzer             = aws_lambda_function.llm_analyzer.function_name
    notification_service     = aws_lambda_function.notification_service.function_name
    event_transformer        = aws_lambda_function.event_transformer.function_name
  }
}

# CloudWatch Log Group ARNs
output "log_group_arns" {
  description = "Map of CloudWatch Log Group ARNs for Lambda functions"
  value = {
    metrics_collector        = aws_cloudwatch_log_group.metrics_collector.arn
    logs_collector           = aws_cloudwatch_log_group.logs_collector.arn
    deploy_context_collector = aws_cloudwatch_log_group.deploy_context_collector.arn
    correlation_engine       = aws_cloudwatch_log_group.correlation_engine.arn
    llm_analyzer             = aws_cloudwatch_log_group.llm_analyzer.arn
    notification_service     = aws_cloudwatch_log_group.notification_service.arn
    event_transformer        = aws_cloudwatch_log_group.event_transformer.arn
  }
}
