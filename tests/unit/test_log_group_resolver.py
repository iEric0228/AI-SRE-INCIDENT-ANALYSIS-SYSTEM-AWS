"""Unit tests for logs_collector.log_group_resolver built-in ARN mapping."""

from unittest.mock import MagicMock

import pytest
from log_group_resolver import LogGroupResolver


@pytest.fixture
def resolver():
    return LogGroupResolver(ssm_client=MagicMock(), parameter_name="/incident/log-mapping")


class TestBuiltinLogGroups:
    """Cover every service branch of _get_builtin_log_groups."""

    def test_malformed_arn_returns_unknown(self, resolver):
        assert resolver._get_builtin_log_groups("arn:aws:ec2:r") == ["/aws/unknown/arn:aws:ec2:r"]

    def test_ec2(self, resolver):
        result = resolver._get_builtin_log_groups("arn:aws:ec2:us-east-1:123:instance/i-0abc")
        assert result == ["/aws/ec2/instance/i-0abc"]

    def test_rds(self, resolver):
        result = resolver._get_builtin_log_groups("arn:aws:rds:us-east-1:123:db:mydb")
        assert result[0].startswith("/aws/rds/")

    def test_ecs_full_path(self, resolver):
        result = resolver._get_builtin_log_groups("arn:aws:ecs:us-east-1:123:service/cluster/svc")
        assert result == ["/ecs/cluster/svc"]

    def test_ecs_short_path(self, resolver):
        result = resolver._get_builtin_log_groups("arn:aws:ecs:us-east-1:123:cluster")
        assert result == ["/ecs/cluster"]

    def test_apigateway(self, resolver):
        result = resolver._get_builtin_log_groups("arn:aws:apigateway:us-east-1:123:/restapis/abc")
        assert result == ["/aws/apigateway/abc"]

    def test_nlb(self, resolver):
        result = resolver._get_builtin_log_groups(
            "arn:aws:elasticloadbalancing:us-east-1:123:loadbalancer/net/mynlb/abc"
        )
        assert result == ["/aws/nlb/mynlb"]

    def test_alb(self, resolver):
        result = resolver._get_builtin_log_groups(
            "arn:aws:elasticloadbalancing:us-east-1:123:loadbalancer/app/myalb/abc"
        )
        assert result == ["/aws/alb/myalb"]

    def test_elb_short_path(self, resolver):
        result = resolver._get_builtin_log_groups(
            "arn:aws:elasticloadbalancing:us-east-1:123:loadbalancer"
        )
        assert result == ["/aws/elb/loadbalancer"]

    def test_eks(self, resolver):
        result = resolver._get_builtin_log_groups("arn:aws:eks:us-east-1:123:cluster/mycluster")
        assert result == ["/aws/eks/mycluster/cluster"]

    def test_elasticache(self, resolver):
        result = resolver._get_builtin_log_groups(
            "arn:aws:elasticache:us-east-1:123:cluster/myredis"
        )
        assert result == ["/aws/elasticache/myredis"]

    def test_opensearch(self, resolver):
        result = resolver._get_builtin_log_groups("arn:aws:es:us-east-1:123:domain/mydomain")
        assert result == ["/aws/opensearch/domains/mydomain"]

    def test_unknown_service_falls_back(self, resolver):
        result = resolver._get_builtin_log_groups("arn:aws:sqs:us-east-1:123:myqueue")
        assert result == ["/aws/sqs/myqueue"]
