#!/usr/bin/env bash
# Package Lambda functions for deployment.
# Creates deployment.zip for each Lambda function containing:
#   - The function's lambda_function.py
#   - The shared/ directory (models, metrics, structured_logger, log_metadata)
#   - Per-function pip dependencies (only notification_service needs 'requests')
#
# Usage: ./scripts/package-lambdas.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SRC_DIR="${PROJECT_ROOT}/src"

echo "================================================"
echo "Packaging Lambda functions"
echo "================================================"
echo "Project root: ${PROJECT_ROOT}"
echo "Source dir:    ${SRC_DIR}"
echo ""

package_function() {
  local func="$1"
  local FUNC_DIR="${SRC_DIR}/${func}"
  local BUILD_DIR="${FUNC_DIR}/build"

  echo "=== Packaging ${func} ==="

  # Verify source exists
  if [ ! -f "${FUNC_DIR}/lambda_function.py" ]; then
    echo "ERROR: ${FUNC_DIR}/lambda_function.py not found!"
    return 1
  fi

  # Clean previous build
  rm -rf "${BUILD_DIR}" "${FUNC_DIR}/deployment.zip"
  mkdir -p "${BUILD_DIR}"

  # Copy function code (lambda_function.py + any sibling .py modules like circuit_breaker.py)
  for pyfile in "${FUNC_DIR}"/*.py; do
    [ -f "$pyfile" ] && cp "$pyfile" "${BUILD_DIR}/"
  done
  echo "  Copied function .py files"

  # Copy shared modules to build root so imports like 'from metrics import ...' work
  # in Lambda (where sys.path includes /var/task/ but not /var/task/shared/)
  if [ -d "${SRC_DIR}/shared" ]; then
    cp "${SRC_DIR}/shared"/*.py "${BUILD_DIR}/"
    # Remove __pycache__
    find "${BUILD_DIR}" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    echo "  Copied shared/ modules to build root"
  else
    echo "ERROR: ${SRC_DIR}/shared directory not found!"
    return 1
  fi

  # Install pip dependencies for notification_service only (requests)
  # All other functions only need boto3 which is pre-installed in Lambda runtime
  if [ "${func}" = "notification_service" ]; then
    echo "  Installing requests package (with dependencies)..."
    python3 -m pip install requests -t "${BUILD_DIR}" --quiet 2>&1 || {
      echo "  WARNING: pip install failed, retrying without cache..."
      python3 -m pip install requests -t "${BUILD_DIR}" --quiet --no-cache-dir 2>&1 || true
    }
  fi

  # Remove unnecessary files from build
  find "${BUILD_DIR}" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
  find "${BUILD_DIR}" -name "*.pyc" -delete 2>/dev/null || true
  find "${BUILD_DIR}" -name "*.dist-info" -type d -exec rm -rf {} + 2>/dev/null || true

  # Create deployment.zip
  (cd "${BUILD_DIR}" && zip -r9q "${FUNC_DIR}/deployment.zip" .)

  # Verify zip was created
  if [ ! -f "${FUNC_DIR}/deployment.zip" ]; then
    echo "ERROR: Failed to create deployment.zip for ${func}!"
    return 1
  fi

  # Clean build directory
  rm -rf "${BUILD_DIR}"

  # Report
  local ZIP_SIZE
  ZIP_SIZE=$(du -h "${FUNC_DIR}/deployment.zip" | cut -f1)
  echo "  Created: deployment.zip (${ZIP_SIZE})"
  echo ""
}

# Package all functions
FUNCTIONS="event_transformer metrics_collector logs_collector deploy_context_collector correlation_engine llm_analyzer notification_service"
FAILED=0

for func in $FUNCTIONS; do
  if ! package_function "$func"; then
    echo "FAILED to package ${func}"
    FAILED=$((FAILED + 1))
  fi
done

echo "================================================"
if [ $FAILED -gt 0 ]; then
  echo "ERROR: ${FAILED} function(s) failed to package!"
  exit 1
fi

echo "All Lambda packages created successfully."
echo ""
echo "Verification:"
for func in $FUNCTIONS; do
  if [ -f "${SRC_DIR}/${func}/deployment.zip" ]; then
    SIZE=$(du -h "${SRC_DIR}/${func}/deployment.zip" | cut -f1)
    CONTENTS=$(zipinfo -1 "${SRC_DIR}/${func}/deployment.zip" 2>/dev/null | wc -l | tr -d ' ')
    echo "  OK: ${func}/deployment.zip (${SIZE}, ${CONTENTS} files)"
  else
    echo "  MISSING: ${func}/deployment.zip"
    exit 1
  fi
done
