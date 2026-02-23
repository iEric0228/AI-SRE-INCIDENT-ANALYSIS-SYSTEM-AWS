resource "aws_dynamodb_table" "incident_store" {
  name         = var.table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "incidentId"
  range_key    = "timestamp"

  attribute {
    name = "incidentId"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "S"
  }

  attribute {
    name = "resourceArn"
    type = "S"
  }

  attribute {
    name = "severity"
    type = "S"
  }

  global_secondary_index {
    name            = "ResourceIndex"
    hash_key        = "resourceArn"
    range_key       = "timestamp"
    projection_type = "ALL"
  }

  global_secondary_index {
    name            = "SeverityIndex"
    hash_key        = "severity"
    range_key       = "timestamp"
    projection_type = "ALL"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = var.kms_key_arn
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = merge(
    var.tags,
    {
      Name    = var.table_name
      Project = "AI-SRE-Portfolio"
    }
  )
}
