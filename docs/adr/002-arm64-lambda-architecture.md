# ADR-002: ARM64 (Graviton2) Lambda Architecture

**Status**: Accepted
**Date**: 2026-03-18
**Decision Makers**: Project Team

## Context

AWS Lambda supports two CPU architectures:
- **x86_64**: Traditional Intel/AMD processors
- **arm64**: AWS Graviton2 processors

All 7 Lambda functions in this system run pure Python 3.11 with boto3 and the `requests` library. No native C extensions or architecture-specific binaries are used.

## Decision

Use **arm64 (Graviton2)** for all Lambda functions.

## Consequences

### Positive
- **20% lower cost** at the same memory/duration compared to x86_64
- **Up to 34% better price-performance** per AWS benchmarks for compute-bound workloads
- All dependencies are pure Python — no compatibility issues
- Graviton2 is available in all major AWS regions

### Negative
- If a future dependency requires native x86 binaries (e.g., compiled C extensions), the packaging pipeline would need to cross-compile or switch architecture
- Minor: local development on x86 machines doesn't match Lambda runtime architecture (irrelevant for pure Python)

### Notes
- The packaging script (`scripts/package-lambdas.sh`) installs dependencies with `--platform manylinux2014_aarch64` when needed
- Terraform configuration: `architectures = ["arm64"]` on all `aws_lambda_function` resources
