"""
Property-based tests for change event classification.

This module tests the change event classification property: for any CloudTrail event,
classification must be deployment, configuration, or infrastructure.

Validates Requirements 5.2
"""

from hypothesis import given, strategies as st
from hypothesis.strategies import composite
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from deploy_context_collector.lambda_function import classify_change_type

# Strategy generators


@composite
def cloudtrail_event_name_strategy(draw):
    """
    Generate arbitrary CloudTrail event names.

    Generates a mix of:
    - Real AWS CloudTrail event names
    - Synthetic event names with common prefixes
    - Edge cases (empty, special characters)
    """
    # Real CloudTrail event names from various AWS services
    real_event_names = [
        # Lambda events
        "UpdateFunctionCode",
        "UpdateFunctionConfiguration",
        "CreateFunction",
        "DeleteFunction",
        "PublishVersion",
        "PublishLayerVersion",
        # EC2 events
        "RunInstances",
        "TerminateInstances",
        "StartInstances",
        "StopInstances",
        "RebootInstances",
        "ModifyInstanceAttribute",
        "CreateSecurityGroup",
        "DeleteSecurityGroup",
        # ECS events
        "CreateService",
        "UpdateService",
        "DeleteService",
        "CreateDeployment",
        "UpdateTaskDefinition",
        # RDS events
        "CreateDBInstance",
        "ModifyDBInstance",
        "DeleteDBInstance",
        "RebootDBInstance",
        # CloudFormation events
        "CreateStack",
        "UpdateStack",
        "DeleteStack",
        # Parameter Store events
        "PutParameter",
        "UpdateParameter",
        "DeleteParameter",
        # CloudWatch events
        "PutMetricAlarm",
        "UpdateAlarm",
        "DeleteAlarms",
        "PutMetricFilter",
        "UpdateLogGroup",
        # IAM events
        "CreateRole",
        "UpdateRole",
        "DeleteRole",
        "AttachRolePolicy",
        "DetachRolePolicy",
        # S3 events
        "CreateBucket",
        "DeleteBucket",
        "PutBucketPolicy",
        # DynamoDB events
        "CreateTable",
        "UpdateTable",
        "DeleteTable",
        # Read-only events (should not be classified as changes)
        "GetFunction",
        "DescribeInstances",
        "ListFunctions",
        "GetParameter",
        "DescribeDBInstances",
    ]

    # Mutating operation prefixes
    mutating_prefixes = [
        "Create",
        "Update",
        "Delete",
        "Put",
        "Modify",
        "Deploy",
        "Publish",
        "Start",
        "Stop",
        "Reboot",
        "Terminate",
        "Launch",
        "Register",
        "Deregister",
        "Attach",
        "Detach",
        "Associate",
        "Disassociate",
        "Enable",
        "Disable",
        "Set",
        "Add",
        "Remove",
    ]

    # Resource types
    resource_types = [
        "Function",
        "Instance",
        "Service",
        "DBInstance",
        "Stack",
        "Parameter",
        "Alarm",
        "Rule",
        "Policy",
        "Bucket",
        "Table",
        "LogGroup",
        "Role",
        "User",
        "Group",
        "SecurityGroup",
    ]

    # Choose strategy
    strategy_choice = draw(st.integers(min_value=0, max_value=2))

    if strategy_choice == 0:
        # Use real event name
        return draw(st.sampled_from(real_event_names))
    elif strategy_choice == 1:
        # Generate synthetic event name with mutating prefix
        prefix = draw(st.sampled_from(mutating_prefixes))
        resource = draw(st.sampled_from(resource_types))
        return f"{prefix}{resource}"
    else:
        # Generate arbitrary text (edge cases)
        return draw(
            st.text(
                min_size=1,
                max_size=100,
                alphabet=st.characters(
                    whitelist_categories=("Lu", "Ll"),  # Uppercase and lowercase letters
                    min_codepoint=65,
                    max_codepoint=122,
                ),
            )
        )


# Property Tests


@given(cloudtrail_event_name_strategy())
def test_change_event_classification_is_valid(event_name):
    """
    Property 12: Change Event Classification

    **Validates: Requirements 5.2**

    For any CloudTrail event, classification must be deployment, configuration, or infrastructure.

    This property ensures that:
    1. The classification function always returns one of the three valid types
    2. The classification is deterministic (same input always produces same output)
    3. The classification never returns None, empty string, or invalid values
    """
    # Classify the event
    change_type = classify_change_type(event_name)

    # Property 1: Classification must be one of the three valid types
    valid_types = {"deployment", "configuration", "infrastructure"}
    assert change_type in valid_types, (
        f"Change type must be one of {valid_types}. " f"Got: {change_type} for event: {event_name}"
    )

    # Property 2: Classification must not be None or empty
    assert change_type is not None, f"Change type must not be None for event: {event_name}"
    assert change_type != "", f"Change type must not be empty string for event: {event_name}"

    # Property 3: Classification must be a string
    assert isinstance(
        change_type, str
    ), f"Change type must be a string. Got type: {type(change_type)} for event: {event_name}"


@given(cloudtrail_event_name_strategy())
def test_change_event_classification_is_deterministic(event_name):
    """
    Property: Change Event Classification is Deterministic

    **Validates: Requirements 5.2**

    Calling classify_change_type multiple times with the same input
    should always produce the same output.
    """
    # Classify the event multiple times
    classification_1 = classify_change_type(event_name)
    classification_2 = classify_change_type(event_name)
    classification_3 = classify_change_type(event_name)

    # All classifications should be identical
    assert classification_1 == classification_2 == classification_3, (
        f"Classification should be deterministic. " f"Got different results for event: {event_name}"
    )


@given(st.text(min_size=1, max_size=100))
def test_change_event_classification_handles_arbitrary_strings(event_name):
    """
    Property: Change Event Classification Handles Arbitrary Strings

    **Validates: Requirements 5.2**

    The classification function should handle any arbitrary string input
    without crashing and always return a valid classification.
    """
    # This should not raise an exception
    change_type = classify_change_type(event_name)

    # Must return a valid type
    valid_types = {"deployment", "configuration", "infrastructure"}
    assert change_type in valid_types, (
        f"Classification must handle arbitrary strings gracefully. "
        f"Got: {change_type} for event: {event_name}"
    )


def test_change_event_classification_deployment_examples():
    """
    Property: Deployment Events are Correctly Classified

    **Validates: Requirements 5.2**

    Known deployment-related events should be classified as "deployment".
    """
    deployment_events = [
        "UpdateFunctionCode",
        "CreateDeployment",
        "PublishVersion",
        "PublishLayerVersion",
        "DeployApplication",
        "PutImage",
    ]

    for event_name in deployment_events:
        change_type = classify_change_type(event_name)
        assert change_type == "deployment", (
            f"Event {event_name} should be classified as 'deployment', " f"but got '{change_type}'"
        )


def test_change_event_classification_configuration_examples():
    """
    Property: Configuration Events are Correctly Classified

    **Validates: Requirements 5.2**

    Known configuration-related events should be classified as "configuration".
    """
    configuration_events = [
        "UpdateFunctionConfiguration",
        "PutParameter",
        "UpdateParameter",
        "ModifyDBInstance",
        "UpdateStack",
        "PutRule",
        "UpdateAlarm",
        "PutMetricFilter",
        "UpdateLogGroup",
    ]

    for event_name in configuration_events:
        change_type = classify_change_type(event_name)
        assert change_type == "configuration", (
            f"Event {event_name} should be classified as 'configuration', "
            f"but got '{change_type}'"
        )


def test_change_event_classification_infrastructure_examples():
    """
    Property: Infrastructure Events are Correctly Classified

    **Validates: Requirements 5.2**

    Events that are neither deployment nor configuration should be
    classified as "infrastructure" (the default category).
    """
    infrastructure_events = [
        "CreateFunction",
        "DeleteFunction",
        "RunInstances",
        "TerminateInstances",
        "StartInstances",
        "StopInstances",
        "RebootInstances",
        "CreateSecurityGroup",
        "DeleteSecurityGroup",
        "CreateTable",
        "DeleteTable",
        "CreateBucket",
        "DeleteBucket",
    ]

    for event_name in infrastructure_events:
        change_type = classify_change_type(event_name)
        assert change_type == "infrastructure", (
            f"Event {event_name} should be classified as 'infrastructure', "
            f"but got '{change_type}'"
        )


@given(cloudtrail_event_name_strategy())
def test_change_event_classification_case_insensitive(event_name):
    """
    Property: Change Event Classification is Case-Insensitive

    **Validates: Requirements 5.2**

    The classification should work correctly regardless of the case
    of the event name (since the implementation uses .lower()).
    """
    # Classify original event name
    original_classification = classify_change_type(event_name)

    # Classify uppercase version
    uppercase_classification = classify_change_type(event_name.upper())

    # Classify lowercase version
    lowercase_classification = classify_change_type(event_name.lower())

    # All should produce the same result
    assert original_classification == uppercase_classification == lowercase_classification, (
        f"Classification should be case-insensitive. "
        f"Original: {original_classification}, "
        f"Uppercase: {uppercase_classification}, "
        f"Lowercase: {lowercase_classification} "
        f"for event: {event_name}"
    )


@given(st.lists(cloudtrail_event_name_strategy(), min_size=1, max_size=100))
def test_change_event_classification_batch_consistency(event_names):
    """
    Property: Change Event Classification is Consistent Across Batches

    **Validates: Requirements 5.2**

    Classifying a batch of events should produce consistent results
    regardless of the order or presence of other events.
    """
    # Classify all events
    classifications = [classify_change_type(event_name) for event_name in event_names]

    # All classifications should be valid
    valid_types = {"deployment", "configuration", "infrastructure"}
    for i, (event_name, change_type) in enumerate(zip(event_names, classifications)):
        assert (
            change_type in valid_types
        ), f"Event {i} ({event_name}) has invalid classification: {change_type}"

    # Re-classify the same events and verify consistency
    reclassifications = [classify_change_type(event_name) for event_name in event_names]

    assert (
        classifications == reclassifications
    ), "Batch classification should be consistent across multiple runs"
