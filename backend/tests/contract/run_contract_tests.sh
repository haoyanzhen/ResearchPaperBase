#!/usr/bin/env bash
# 契约测试执行脚本（qa_design §7）
# 在 CI 中配合 docker-compose 启动 API 服务后运行

set -euo pipefail

API_URL="${API_URL:-http://localhost:8000}"
SCHEMA_URL="${API_URL}/openapi.json"
CONFIG="tests/contract/schemathesis.toml"
REPORT_DIR="${REPORT_DIR:-test-reports/contract}"

mkdir -p "${REPORT_DIR}"

echo "==> Running contract tests against ${SCHEMA_URL}"

# 等待 API 服务就绪（最多 30 秒）
for i in $(seq 1 30); do
    if curl -sf "${API_URL}/health" > /dev/null 2>&1; then
        echo "API ready after ${i}s"
        break
    fi
    if [ "${i}" -eq 30 ]; then
        echo "ERROR: API did not become ready in 30s"
        exit 1
    fi
    sleep 1
done

# 运行契约测试
schemathesis run "${SCHEMA_URL}" \
    --config="${CONFIG}" \
    --checks=all \
    --max-response-time=1000 \
    --junit-xml="${REPORT_DIR}/contract-results.xml" \
    --report="${REPORT_DIR}/contract-report.html" \
    --workers=2 \
    --header "Authorization: Bearer ${TEST_JWT:-}" \
    "$@"

echo "==> Contract tests completed. Reports in ${REPORT_DIR}/"
