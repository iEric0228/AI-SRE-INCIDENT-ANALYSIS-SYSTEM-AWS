"""
Log group resolver with SSM-based configuration.

Resolves resource ARNs to CloudWatch Log Group names.
Priority: SSM overrides > built-in patterns > SSM additional (appended)
"""

import json
import logging
import time
from typing import Any, Dict, List

logger = logging.getLogger()

# Cache TTL in seconds
_CACHE_TTL_SECONDS = 300  # 5 minutes


class LogGroupResolver:
    """Resolves resource ARNs to CloudWatch Log Group names using SSM config with built-in fallback."""

    def __init__(self, ssm_client: Any, parameter_name: str) -> None:
        self._ssm = ssm_client
        self._parameter_name = parameter_name
        self._cache: Dict[str, Any] = {}
        self._cache_timestamp: float = 0.0

    def resolve(self, resource_arn: str) -> List[str]:
        """
        Resolve a resource ARN to a list of log group names.

        Args:
            resource_arn: AWS resource ARN

        Returns:
            List of log group names to query
        """
        config = self._load_config()

        # Check for overrides first (completely replaces built-in)
        overrides = config.get("overrides", {})
        if resource_arn in overrides:
            return list(overrides[resource_arn])

        # Get built-in log groups
        log_groups = self._get_builtin_log_groups(resource_arn)

        # Append additional log groups if configured
        additional = config.get("additional", {})
        if resource_arn in additional:
            log_groups = log_groups + list(additional[resource_arn])

        return log_groups

    def _load_config(self) -> Dict[str, Any]:
        """Load SSM config with caching. Returns empty dict on failure."""
        now = time.monotonic()
        if self._cache and (now - self._cache_timestamp) < _CACHE_TTL_SECONDS:
            return self._cache

        try:
            response = self._ssm.get_parameter(
                Name=self._parameter_name,
                WithDecryption=False,
            )
            value = response.get("Parameter", {}).get("Value", "{}")
            self._cache = json.loads(value)
            self._cache_timestamp = now

        except self._ssm.exceptions.ParameterNotFound:
            logger.info(
                json.dumps(
                    {
                        "message": "Log group mapping parameter not found; using built-in patterns",
                        "parameterName": self._parameter_name,
                    }
                )
            )
            self._cache = {}
            self._cache_timestamp = now

        except Exception as exc:
            logger.warning(
                json.dumps(
                    {
                        "message": "Failed to load log group mapping from SSM; using built-in patterns",
                        "parameterName": self._parameter_name,
                        "error": str(exc),
                    }
                )
            )
            # Keep stale cache if available, otherwise empty
            if not self._cache:
                self._cache = {}
            self._cache_timestamp = now

        return self._cache

    def _get_builtin_log_groups(self, resource_arn: str) -> List[str]:
        """
        Get built-in log group names based on resource ARN patterns.

        Args:
            resource_arn: AWS resource ARN

        Returns:
            List containing the single derived log group name
        """
        parts = resource_arn.split(":")

        if len(parts) < 6:
            return [f"/aws/unknown/{resource_arn}"]

        service = parts[2]
        # Rejoin everything after the account so colon-separated resources survive
        # (e.g. "function:my-function"); parts[5] alone would be just "function".
        resource_part = ":".join(parts[5:])

        if service == "lambda":
            # arn:aws:lambda:region:account:function:NAME[:version-or-alias]
            function_name = parts[6] if len(parts) > 6 else resource_part.split("/")[-1]
            return [f"/aws/lambda/{function_name}"]

        if service == "ec2":
            instance_id = resource_part.split("/")[-1]
            return [f"/aws/ec2/instance/{instance_id}"]

        if service == "rds":
            db_instance_id = resource_part.split(":")[-1]
            return [f"/aws/rds/instance/{db_instance_id}/error"]

        if service == "ecs":
            parts_split = resource_part.split("/")
            if len(parts_split) >= 3:
                cluster_name = parts_split[1]
                service_name = parts_split[2]
                return [f"/ecs/{cluster_name}/{service_name}"]
            return [f"/ecs/{resource_part}"]

        if service == "apigateway":
            api_id = resource_part.split("/")[-1]
            return [f"/aws/apigateway/{api_id}"]

        if service == "elasticloadbalancing":
            lb_parts = resource_part.split("/")
            if len(lb_parts) >= 3:
                lb_type = lb_parts[1]
                lb_name = lb_parts[2]
                if lb_type == "net":
                    return [f"/aws/nlb/{lb_name}"]
                return [f"/aws/alb/{lb_name}"]
            return [f"/aws/elb/{resource_part}"]

        if service == "eks":
            cluster_name = resource_part.split("/")[-1]
            return [f"/aws/eks/{cluster_name}/cluster"]

        if service == "elasticache":
            cluster_id = (
                resource_part.split(":")[-1]
                if ":" in resource_part
                else resource_part.split("/")[-1]
            )
            return [f"/aws/elasticache/{cluster_id}"]

        if service == "es":
            domain_name = resource_part.split("/")[-1]
            return [f"/aws/opensearch/domains/{domain_name}"]

        return [f"/aws/{service}/{resource_part}"]
