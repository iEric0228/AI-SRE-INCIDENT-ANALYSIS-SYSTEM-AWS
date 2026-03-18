# Test Scenario: EC2 High CPU Alarm
# This creates a simple EC2 instance with a CloudWatch Alarm for testing the incident analysis system

terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "AI-SRE-Portfolio"
      Environment = "test"
      ManagedBy   = "Terraform"
      Purpose     = "Test-Scenario"
    }
  }
}

# Data source for latest Amazon Linux 2 AMI
data "aws_ami" "amazon_linux_2" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["amzn2-ami-hvm-*-x86_64-gp2"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# Data source for current AWS account
data "aws_caller_identity" "current" {}

# Data source for default VPC (for simplicity)
data "aws_vpc" "default" {
  default = true
}

# Data source for default subnet
data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# Security Group - Allow SSH from your IP
resource "aws_security_group" "test_instance" {
  name        = "test-incident-instance-sg"
  description = "Security group for test incident EC2 instance"
  vpc_id      = data.aws_vpc.default.id

  # SSH access (you should restrict this to your IP)
  ingress {
    description = "SSH from anywhere (restrict this in production!)"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = var.allowed_ssh_cidr_blocks
  }

  # Allow all outbound traffic
  egress {
    description = "Allow all outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "test-incident-instance-sg"
  }
}

# IAM Role for EC2 instance (CloudWatch Agent permissions)
resource "aws_iam_role" "test_instance" {
  name = "test-incident-instance-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "test-incident-instance-role"
  }
}

# Attach CloudWatch Agent policy
resource "aws_iam_role_policy_attachment" "cloudwatch_agent" {
  role       = aws_iam_role.test_instance.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
}

# Instance profile
resource "aws_iam_instance_profile" "test_instance" {
  name = "test-incident-instance-profile"
  role = aws_iam_role.test_instance.name

  tags = {
    Name = "test-incident-instance-profile"
  }
}

# CloudWatch Log Group for instance logs
resource "aws_cloudwatch_log_group" "test_instance" {
  name              = "/aws/ec2/test-incident-instance"
  retention_in_days = 7

  tags = {
    Name = "test-incident-instance-logs"
  }
}

# EC2 Instance
resource "aws_instance" "test_instance" {
  ami                    = data.aws_ami.amazon_linux_2.id
  instance_type          = var.instance_type
  key_name               = var.key_pair_name
  vpc_security_group_ids = [aws_security_group.test_instance.id]
  iam_instance_profile   = aws_iam_instance_profile.test_instance.name
  subnet_id              = data.aws_subnets.default.ids[0]

  # User data to install CloudWatch Agent (optional)
  user_data = <<-EOF
              #!/bin/bash
              # Update system
              yum update -y
              
              # Install CloudWatch Agent
              wget https://s3.amazonaws.com/amazoncloudwatch-agent/amazon_linux/amd64/latest/amazon-cloudwatch-agent.rpm
              rpm -U ./amazon-cloudwatch-agent.rpm
              
              # Create CloudWatch Agent config
              cat > /opt/aws/amazon-cloudwatch-agent/etc/config.json <<'CWCONFIG'
              {
                "logs": {
                  "logs_collected": {
                    "files": {
                      "collect_list": [
                        {
                          "file_path": "/var/log/messages",
                          "log_group_name": "${aws_cloudwatch_log_group.test_instance.name}",
                          "log_stream_name": "{instance_id}/messages"
                        }
                      ]
                    }
                  }
                },
                "metrics": {
                  "namespace": "TestIncident",
                  "metrics_collected": {
                    "cpu": {
                      "measurement": [
                        {"name": "cpu_usage_idle", "rename": "CPU_IDLE", "unit": "Percent"},
                        {"name": "cpu_usage_iowait", "rename": "CPU_IOWAIT", "unit": "Percent"}
                      ],
                      "metrics_collection_interval": 60
                    },
                    "disk": {
                      "measurement": [
                        {"name": "used_percent", "rename": "DISK_USED", "unit": "Percent"}
                      ],
                      "metrics_collection_interval": 60,
                      "resources": ["*"]
                    },
                    "mem": {
                      "measurement": [
                        {"name": "mem_used_percent", "rename": "MEM_USED", "unit": "Percent"}
                      ],
                      "metrics_collection_interval": 60
                    }
                  }
                }
              }
              CWCONFIG
              
              # Start CloudWatch Agent
              /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
                -a fetch-config \
                -m ec2 \
                -s \
                -c file:/opt/aws/amazon-cloudwatch-agent/etc/config.json
              
              # Install stress-ng for CPU testing
              amazon-linux-extras install epel -y
              yum install -y stress-ng
              
              echo "Test instance setup complete" > /var/log/test-instance-setup.log
              EOF

  tags = {
    Name = "test-incident-instance"
  }
}

# CloudWatch Alarm - High CPU
resource "aws_cloudwatch_metric_alarm" "high_cpu" {
  alarm_name          = "test-incident-high-cpu"
  alarm_description   = "Test alarm for incident analysis system - triggers when CPU > ${var.cpu_threshold}%"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = var.evaluation_periods
  metric_name         = "CPUUtilization"
  namespace           = "AWS/EC2"
  period              = var.alarm_period
  statistic           = "Average"
  threshold           = var.cpu_threshold
  treat_missing_data  = "notBreaching"

  dimensions = {
    InstanceId = aws_instance.test_instance.id
  }

  alarm_actions = [var.sns_topic_arn]
  ok_actions    = [var.sns_topic_arn]

  tags = {
    Name = "test-incident-high-cpu"
  }
}
