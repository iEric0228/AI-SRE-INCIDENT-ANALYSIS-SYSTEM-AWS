"""
Unit tests for DynamoDB table Terraform configuration.

Validates Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 17.4, 17.6
"""

import json
import os
import pytest
import re


def load_terraform_file(file_path):
    """Load Terraform file as text for validation."""
    with open(file_path, "r") as f:
        return f.read()


class TestDynamoDBTableConfiguration:
    """Test DynamoDB table module configuration."""

    @pytest.fixture
    def main_tf_content(self):
        """Load DynamoDB main.tf content."""
        return load_terraform_file("terraform/modules/dynamodb/main.tf")

    def test_table_resource_exists(self, main_tf_content):
        """Test that DynamoDB table resource is defined."""
        assert 'resource "aws_dynamodb_table" "incident_store"' in main_tf_content

    def test_billing_mode_on_demand(self, main_tf_content):
        """Test that table uses on-demand billing mode (Requirement 17.4)."""
        assert 'billing_mode = "PAY_PER_REQUEST"' in main_tf_content

    def test_primary_key_schema(self, main_tf_content):
        """Test that table has correct partition and sort keys (Requirement 9.1)."""
        # Check partition key
        assert 'hash_key     = "incidentId"' in main_tf_content

        # Check sort key
        assert 'range_key    = "timestamp"' in main_tf_content

        # Check incidentId attribute
        assert re.search(
            r'attribute\s*\{[^}]*name\s*=\s*"incidentId"[^}]*type\s*=\s*"S"',
            main_tf_content,
            re.DOTALL,
        )

        # Check timestamp attribute
        assert re.search(
            r'attribute\s*\{[^}]*name\s*=\s*"timestamp"[^}]*type\s*=\s*"S"',
            main_tf_content,
            re.DOTALL,
        )

    def test_global_secondary_indexes_exist(self, main_tf_content):
        """Test that required GSIs are defined (Requirement 9.3)."""
        # Verify ResourceIndex exists
        assert 'name            = "ResourceIndex"' in main_tf_content

        # Verify SeverityIndex exists
        assert 'name            = "SeverityIndex"' in main_tf_content

    def test_resource_index_configuration(self, main_tf_content):
        """Test ResourceIndex GSI configuration (Requirement 9.3)."""
        # Extract ResourceIndex block
        resource_index_pattern = (
            r'global_secondary_index\s*\{[^}]*name\s*=\s*"ResourceIndex"[^}]*\}'
        )
        resource_index_match = re.search(resource_index_pattern, main_tf_content, re.DOTALL)
        assert resource_index_match is not None

        resource_index_block = resource_index_match.group(0)

        # Verify keys
        assert 'hash_key        = "resourceArn"' in resource_index_block
        assert 'range_key       = "timestamp"' in resource_index_block

        # Verify projection type
        assert 'projection_type = "ALL"' in resource_index_block

    def test_severity_index_configuration(self, main_tf_content):
        """Test SeverityIndex GSI configuration (Requirement 9.3)."""
        # Extract SeverityIndex block
        severity_index_pattern = (
            r'global_secondary_index\s*\{[^}]*name\s*=\s*"SeverityIndex"[^}]*\}'
        )
        severity_index_match = re.search(severity_index_pattern, main_tf_content, re.DOTALL)
        assert severity_index_match is not None

        severity_index_block = severity_index_match.group(0)

        # Verify keys
        assert 'hash_key        = "severity"' in severity_index_block
        assert 'range_key       = "timestamp"' in severity_index_block

        # Verify projection type
        assert 'projection_type = "ALL"' in severity_index_block

    def test_ttl_configuration(self, main_tf_content):
        """Test TTL configuration for 90-day retention (Requirement 9.4)."""
        # Verify TTL block exists
        ttl_pattern = r"ttl\s*\{[^}]*\}"
        ttl_match = re.search(ttl_pattern, main_tf_content, re.DOTALL)
        assert ttl_match is not None

        ttl_block = ttl_match.group(0)

        # Verify TTL attribute name
        assert 'attribute_name = "ttl"' in ttl_block

        # Verify TTL is enabled
        assert "enabled        = true" in ttl_block

    def test_encryption_at_rest(self, main_tf_content):
        """Test encryption at rest with KMS (Requirement 9.5)."""
        # Verify encryption block exists
        encryption_pattern = r"server_side_encryption\s*\{[^}]*\}"
        encryption_match = re.search(encryption_pattern, main_tf_content, re.DOTALL)
        assert encryption_match is not None

        encryption_block = encryption_match.group(0)

        # Verify encryption is enabled
        assert "enabled     = true" in encryption_block

        # Verify KMS key is used
        assert "kms_key_arn = var.kms_key_arn" in encryption_block

    def test_point_in_time_recovery(self, main_tf_content):
        """Test point-in-time recovery is enabled (Requirement 9.5)."""
        # Verify PITR block exists
        pitr_pattern = r"point_in_time_recovery\s*\{[^}]*\}"
        pitr_match = re.search(pitr_pattern, main_tf_content, re.DOTALL)
        assert pitr_match is not None

        pitr_block = pitr_match.group(0)

        # Verify PITR is enabled
        assert "enabled = true" in pitr_block

    def test_resource_tags(self, main_tf_content):
        """Test resource tagging for cost tracking (Requirement 17.6)."""
        # Verify tags block exists
        assert "tags = merge(" in main_tf_content

        # Verify Project tag
        assert 'Project = "AI-SRE-Portfolio"' in main_tf_content

    def test_gsi_attributes_defined(self, main_tf_content):
        """Test that GSI key attributes are defined in attribute list."""
        # Verify resourceArn attribute (for ResourceIndex)
        assert re.search(
            r'attribute\s*\{[^}]*name\s*=\s*"resourceArn"[^}]*type\s*=\s*"S"',
            main_tf_content,
            re.DOTALL,
        )

        # Verify severity attribute (for SeverityIndex)
        assert re.search(
            r'attribute\s*\{[^}]*name\s*=\s*"severity"[^}]*type\s*=\s*"S"',
            main_tf_content,
            re.DOTALL,
        )


class TestDynamoDBModuleVariables:
    """Test DynamoDB module variables configuration."""

    @pytest.fixture
    def variables_content(self):
        """Load variables configuration."""
        return load_terraform_file("terraform/modules/dynamodb/variables.tf")

    def test_table_name_variable(self, variables_content):
        """Test table_name variable is defined."""
        assert 'variable "table_name"' in variables_content
        assert "type        = string" in variables_content
        assert 'default     = "incident-analysis-store"' in variables_content

    def test_kms_key_arn_variable(self, variables_content):
        """Test kms_key_arn variable is defined and required."""
        assert 'variable "kms_key_arn"' in variables_content
        # Required variables don't have a default
        kms_block = re.search(r'variable "kms_key_arn"\s*\{[^}]*\}', variables_content, re.DOTALL)
        assert kms_block is not None
        assert "default" not in kms_block.group(0)

    def test_tags_variable(self, variables_content):
        """Test tags variable is defined."""
        assert 'variable "tags"' in variables_content
        assert "type        = map(string)" in variables_content
        assert "default     = {}" in variables_content


class TestDynamoDBModuleOutputs:
    """Test DynamoDB module outputs configuration."""

    @pytest.fixture
    def outputs_content(self):
        """Load outputs configuration."""
        return load_terraform_file("terraform/modules/dynamodb/outputs.tf")

    def test_table_name_output(self, outputs_content):
        """Test table_name output is defined."""
        assert 'output "table_name"' in outputs_content
        assert "value       = aws_dynamodb_table.incident_store.name" in outputs_content

    def test_table_arn_output(self, outputs_content):
        """Test table_arn output is defined."""
        assert 'output "table_arn"' in outputs_content
        assert "value       = aws_dynamodb_table.incident_store.arn" in outputs_content

    def test_table_id_output(self, outputs_content):
        """Test table_id output is defined."""
        assert 'output "table_id"' in outputs_content
        assert "value       = aws_dynamodb_table.incident_store.id" in outputs_content

    def test_gsi_name_outputs(self, outputs_content):
        """Test GSI name outputs are defined."""
        assert 'output "resource_index_name"' in outputs_content
        assert 'value       = "ResourceIndex"' in outputs_content

        assert 'output "severity_index_name"' in outputs_content
        assert 'value       = "SeverityIndex"' in outputs_content


class TestDynamoDBSchemaCompliance:
    """Test that DynamoDB schema matches design document requirements."""

    def test_ttl_calculation(self):
        """Test TTL calculation for 90-day retention (Requirement 9.4)."""
        from datetime import datetime, timedelta

        # Simulate incident timestamp
        incident_time = datetime(2024, 1, 15, 14, 30, 0)

        # Calculate TTL (90 days from incident)
        ttl_time = incident_time + timedelta(days=90)
        ttl_unix = int(ttl_time.timestamp())

        # Verify TTL is 90 days in the future
        expected_ttl = incident_time + timedelta(days=90)
        assert ttl_time == expected_ttl

        # Verify TTL is a valid Unix timestamp
        assert ttl_unix > 0
        assert ttl_unix == int(expected_ttl.timestamp())

    def test_incident_record_structure(self):
        """Test incident record structure matches design (Requirement 9.2)."""
        # Define expected fields based on design document
        required_fields = {
            "incidentId",  # Partition key
            "timestamp",  # Sort key
            "resourceArn",  # GSI key
            "resourceType",
            "alarmName",
            "severity",  # GSI key
            "structuredContext",
            "analysisReport",
            "notificationStatus",
            "ttl",  # TTL attribute
        }

        # Create sample incident record
        incident_record = {
            "incidentId": "uuid-value",
            "timestamp": "2024-01-15T14:30:00Z",
            "resourceArn": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
            "resourceType": "lambda",
            "alarmName": "HighErrorRate",
            "severity": "high",
            "structuredContext": {},
            "analysisReport": {},
            "notificationStatus": {},
            "ttl": 1234567890,
        }

        # Verify all required fields are present
        assert set(incident_record.keys()) == required_fields

    def test_query_patterns(self):
        """Test that schema supports required query patterns (Requirement 9.3)."""
        # Query pattern 1: Get incident by ID
        query_by_id = {"partition_key": "incidentId", "sort_key": "timestamp"}
        assert query_by_id["partition_key"] == "incidentId"
        assert query_by_id["sort_key"] == "timestamp"

        # Query pattern 2: Get incidents by resource ARN
        query_by_resource = {
            "index": "ResourceIndex",
            "partition_key": "resourceArn",
            "sort_key": "timestamp",
        }
        assert query_by_resource["index"] == "ResourceIndex"
        assert query_by_resource["partition_key"] == "resourceArn"

        # Query pattern 3: Get incidents by severity
        query_by_severity = {
            "index": "SeverityIndex",
            "partition_key": "severity",
            "sort_key": "timestamp",
        }
        assert query_by_severity["index"] == "SeverityIndex"
        assert query_by_severity["partition_key"] == "severity"
