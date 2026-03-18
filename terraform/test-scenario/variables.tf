# Variables for Test Scenario Infrastructure

variable "aws_region" {
  description = "AWS region for test infrastructure"
  type        = string
  default     = "us-east-1"
}

variable "instance_type" {
  description = "EC2 instance type for test instance"
  type        = string
  default     = "t2.micro"

  validation {
    condition     = can(regex("^t2\\.(micro|small)", var.instance_type))
    error_message = "Instance type must be t2.micro or t2.small for cost efficiency."
  }
}

variable "key_pair_name" {
  description = "Name of the SSH key pair for EC2 access (must already exist in AWS)"
  type        = string

  validation {
    condition     = length(var.key_pair_name) > 0
    error_message = "Key pair name cannot be empty. Create a key pair in AWS EC2 console first."
  }
}

variable "allowed_ssh_cidr_blocks" {
  description = "CIDR blocks allowed to SSH into the test instance (restrict to your IP for security)"
  type        = list(string)
  default     = ["0.0.0.0/0"] # WARNING: This allows SSH from anywhere. Restrict in production!

  validation {
    condition     = length(var.allowed_ssh_cidr_blocks) > 0
    error_message = "At least one CIDR block must be specified."
  }
}

variable "cpu_threshold" {
  description = "CPU utilization threshold (%) that triggers the alarm"
  type        = number
  default     = 50

  validation {
    condition     = var.cpu_threshold > 0 && var.cpu_threshold <= 100
    error_message = "CPU threshold must be between 1 and 100."
  }
}

variable "alarm_period" {
  description = "Period (in seconds) over which the alarm statistic is applied"
  type        = number
  default     = 60

  validation {
    condition     = contains([60, 300, 900, 3600], var.alarm_period)
    error_message = "Alarm period must be 60, 300, 900, or 3600 seconds."
  }
}

variable "sns_topic_arn" {
  description = "SNS topic ARN for alarm actions (incident notification topic)"
  type        = string
}

variable "evaluation_periods" {
  description = "Number of periods over which data is compared to the threshold"
  type        = number
  default     = 1

  validation {
    condition     = var.evaluation_periods >= 1 && var.evaluation_periods <= 5
    error_message = "Evaluation periods must be between 1 and 5."
  }
}
