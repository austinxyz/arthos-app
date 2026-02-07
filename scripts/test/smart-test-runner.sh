#!/bin/bash
# Smart test runner - intelligently selects tests based on git changes
# Usage: ./scripts/test/smart-test-runner.sh [--since <commit>]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse arguments
COMPARE_TO="HEAD~1"
if [ "$1" = "--since" ] && [ -n "$2" ]; then
    COMPARE_TO="$2"
fi

echo -e "${BLUE}🔍 Smart Test Runner${NC}"
echo "Comparing changes since: $COMPARE_TO"
echo ""

# Get changed files
CHANGED_FILES=$(git diff --name-only $COMPARE_TO 2>/dev/null || git diff --name-only origin/main 2>/dev/null || echo "")

if [ -z "$CHANGED_FILES" ]; then
    echo -e "${YELLOW}⚠️  No changes detected, running full suite${NC}"
    ./scripts/test/run-tests-local.sh all
    exit $?
fi

echo -e "${BLUE}Changed files:${NC}"
echo "$CHANGED_FILES" | sed 's/^/  /'
echo ""

# Initialize test selection variables
RUN_ALL=false
RUN_BROWSER=false
RUN_UNIT=false
RUN_INTEGRATION=false
TEST_PATTERNS=""

# Critical files that require full suite
CRITICAL_PATTERNS=(
    "^app/models/"
    "^app/database.py"
    "^requirements.txt"
    "^docker-compose"
    "^railway_deploy.py"
)

# Check for critical changes
for pattern in "${CRITICAL_PATTERNS[@]}"; do
    if echo "$CHANGED_FILES" | grep -qE "$pattern"; then
        echo -e "${RED}🔴 Critical files changed: $(echo "$CHANGED_FILES" | grep -E "$pattern" | head -1)${NC}"
        echo -e "${RED}   → Running FULL test suite${NC}"
        RUN_ALL=true
        break
    fi
done

if [ "$RUN_ALL" = false ]; then
    # UI changes → browser tests
    if echo "$CHANGED_FILES" | grep -qE "^app/templates/|^app/static/"; then
        echo -e "${BLUE}🎨 UI changes detected → Including browser tests${NC}"
        RUN_BROWSER=true

        # Determine which browser tests based on template
        if echo "$CHANGED_FILES" | grep -q "stock_detail.html"; then
            TEST_PATTERNS="$TEST_PATTERNS tests/test_stock_detail_browser.py"
        fi
        if echo "$CHANGED_FILES" | grep -qE "watchlist|create_watchlist"; then
            TEST_PATTERNS="$TEST_PATTERNS tests/test_watchlist_browser.py"
        fi
    fi

    # Service layer changes → related tests
    if echo "$CHANGED_FILES" | grep -q "app/services/watchlist"; then
        echo -e "${GREEN}📋 Watchlist service changed → Including watchlist tests${NC}"
        TEST_PATTERNS="$TEST_PATTERNS tests/test_watchlist*.py"
        RUN_INTEGRATION=true
    fi

    if echo "$CHANGED_FILES" | grep -qE "app/services/stock_service|app/services/stock_price"; then
        echo -e "${GREEN}📊 Stock service changed → Including stock tests${NC}"
        TEST_PATTERNS="$TEST_PATTERNS tests/test_stock*.py"
        RUN_INTEGRATION=true
    fi

    if echo "$CHANGED_FILES" | grep -qE "app/services/options|app/services/rr_watchlist"; then
        echo -e "${GREEN}📈 Options service changed → Including options tests${NC}"
        TEST_PATTERNS="$TEST_PATTERNS tests/test_options*.py tests/test_rr*.py"
        RUN_INTEGRATION=true
    fi

    if echo "$CHANGED_FILES" | grep -q "app/services/llm"; then
        echo -e "${GREEN}🤖 LLM service changed → Including LLM tests${NC}"
        TEST_PATTERNS="$TEST_PATTERNS tests/test_llm*.py tests/test_openrouter*.py"
        RUN_INTEGRATION=true
    fi

    # API endpoint changes → API tests
    if echo "$CHANGED_FILES" | grep -q "app/main.py"; then
        echo -e "${GREEN}🌐 API endpoints changed → Including API tests${NC}"
        TEST_PATTERNS="$TEST_PATTERNS tests/test_api.py tests/test_*_api.py"
        RUN_INTEGRATION=true
    fi

    # Provider changes → provider tests
    if echo "$CHANGED_FILES" | grep -q "app/providers/"; then
        echo -e "${GREEN}🔌 Provider changed → Including provider tests${NC}"
        TEST_PATTERNS="$TEST_PATTERNS tests/test_providers*.py"
        RUN_UNIT=true
    fi

    # Helper/utility changes → unit tests
    if echo "$CHANGED_FILES" | grep -qE "app/helpers/|app/utils/"; then
        echo -e "${GREEN}🛠️  Helpers/utils changed → Including helper tests${NC}"
        TEST_PATTERNS="$TEST_PATTERNS tests/test_*_helpers.py tests/test_converters.py tests/test_type_helpers.py"
        RUN_UNIT=true
    fi

    # Test-only changes → run modified tests
    if echo "$CHANGED_FILES" | grep -qE "^tests/"; then
        echo -e "${GREEN}🧪 Test files changed → Running modified tests${NC}"
        MODIFIED_TESTS=$(echo "$CHANGED_FILES" | grep "^tests/test_.*\.py$" || echo "")
        if [ -n "$MODIFIED_TESTS" ]; then
            TEST_PATTERNS="$TEST_PATTERNS $MODIFIED_TESTS"
        fi
    fi
fi

# Execute tests
echo ""
if [ "$RUN_ALL" = true ]; then
    echo -e "${RED}🚀 Running FULL test suite${NC}"
    ./scripts/test/run-tests-local.sh all
    exit $?
fi

# If no specific patterns matched, run unit + integration (skip browser for speed)
if [ -z "$TEST_PATTERNS" ]; then
    echo -e "${YELLOW}⚠️  No specific test patterns matched${NC}"
    echo -e "${BLUE}🏃 Running: Unit + Integration tests (skipping browser)${NC}"
    docker-compose -f docker-compose.test.yml up test-runner --abort-on-container-exit
    EXIT_CODE=$?
else
    # Remove duplicates from TEST_PATTERNS
    TEST_PATTERNS=$(echo $TEST_PATTERNS | tr ' ' '\n' | sort -u | tr '\n' ' ')

    echo -e "${BLUE}🏃 Running selected tests:${NC}"
    echo "$TEST_PATTERNS" | tr ' ' '\n' | sed 's/^/  /'
    echo ""

    # Run in Docker
    docker-compose -f docker-compose.test.yml run --rm test-runner pytest $TEST_PATTERNS -v
    EXIT_CODE=$?
fi

# Always run smoke test
echo ""
echo -e "${BLUE}💨 Running smoke test...${NC}"
docker-compose -f docker-compose.test.yml run --rm test-runner \
    pytest tests/test_e2e_user_flows.py::TestE2EUserFlows::test_home_page_loads_and_navigation -v

SMOKE_EXIT=$?

if [ $EXIT_CODE -eq 0 ] && [ $SMOKE_EXIT -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✅ All selected tests passed!${NC}"
    echo -e "${YELLOW}⚠️  Remember to run full suite before pushing:${NC}"
    echo -e "   ./scripts/test/run-tests-local.sh all"
    exit 0
else
    echo ""
    echo -e "${RED}❌ Tests failed!${NC}"
    exit 1
fi
