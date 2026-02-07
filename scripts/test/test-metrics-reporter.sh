#!/bin/bash
# Test Metrics Reporter
# Analyzes test changes and reports metrics before/after running tests
#
# Usage: ./scripts/test/test-metrics-reporter.sh <test-command>
# Example: ./scripts/test/test-metrics-reporter.sh "./scripts/test/smart-test-runner.sh"

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Temporary files
BEFORE_TESTS="/tmp/tests_before_$$"
AFTER_TESTS="/tmp/tests_after_$$"
TEST_OUTPUT="/tmp/test_output_$$"

echo -e "${BOLD}${BLUE}═══════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}${BLUE}         TEST METRICS REPORTER${NC}"
echo -e "${BOLD}${BLUE}═══════════════════════════════════════════════════════${NC}"
echo ""

# Function to count tests in a file
count_tests_in_file() {
    local file=$1
    if [ -f "$file" ]; then
        grep -c "^\s*def test_" "$file" 2>/dev/null || echo "0"
    else
        echo "0"
    fi
}

# Function to get all test functions from git
get_all_tests() {
    local ref=$1
    local output=$2

    # Get all test files at the ref
    git ls-tree -r --name-only "$ref" tests/ 2>/dev/null | grep "test_.*\.py$" | while read file; do
        # Get test functions from each file
        git show "$ref:$file" 2>/dev/null | grep "^\s*def test_" | sed "s/^\s*def \(test_[^(]*\).*/\1/" | while read test; do
            echo "${file}::${test}"
        done
    done | sort
}

# Analyze git changes
echo -e "${BLUE}📊 Analyzing Changes Since Last Commit...${NC}"
CHANGED_FILES=$(git diff --name-only HEAD~1 2>/dev/null || git diff --name-only origin/main 2>/dev/null || echo "")

if [ -z "$CHANGED_FILES" ]; then
    echo -e "${YELLOW}⚠️  No changes detected (comparing to HEAD~1)${NC}"
    COMPARE_TO="origin/main"
else
    COMPARE_TO="HEAD~1"
fi

# Get tests before and after
echo "  Collecting test inventory..."
get_all_tests "$COMPARE_TO" > "$BEFORE_TESTS"
get_all_tests "HEAD" > "$AFTER_TESTS"

# Calculate metrics
TESTS_ADDED=$(comm -13 "$BEFORE_TESTS" "$AFTER_TESTS" | wc -l | tr -d ' ')
TESTS_REMOVED=$(comm -23 "$BEFORE_TESTS" "$AFTER_TESTS" | wc -l | tr -d ' ')
TESTS_COMMON=$(comm -12 "$BEFORE_TESTS" "$AFTER_TESTS" | wc -l | tr -d ' ')

# Detect updated tests (tests that exist in both but file changed)
TESTS_UPDATED=0
CHANGED_TEST_FILES=$(echo "$CHANGED_FILES" | grep "^tests/test_.*\.py$" || echo "")
if [ -n "$CHANGED_TEST_FILES" ]; then
    for file in $CHANGED_TEST_FILES; do
        if [ -f "$file" ]; then
            # Count tests that existed before
            TESTS_IN_FILE=$(count_tests_in_file "$file")
            TESTS_BEFORE=$(git show "$COMPARE_TO:$file" 2>/dev/null | grep -c "^\s*def test_" || echo "0")

            # Tests updated = tests that exist in both versions of this file
            if [ "$TESTS_IN_FILE" -gt 0 ] && [ "$TESTS_BEFORE" -gt 0 ]; then
                # Conservative estimate: min of before/after (actual updates could be more)
                UPDATED_IN_FILE=$((TESTS_IN_FILE < TESTS_BEFORE ? TESTS_IN_FILE : TESTS_BEFORE))
                TESTS_UPDATED=$((TESTS_UPDATED + UPDATED_IN_FILE))
            fi
        fi
    done
fi

# Adjust for added/removed (don't double-count)
# Updated = common tests in changed files
TOTAL_BEFORE=$(wc -l < "$BEFORE_TESTS" | tr -d ' ')
TOTAL_AFTER=$(wc -l < "$AFTER_TESTS" | tr -d ' ')

echo ""
echo -e "${BOLD}${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}${GREEN}  TEST CHANGE SUMMARY${NC}"
echo -e "${BOLD}${GREEN}═══════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${GREEN}✨ New tests added:${NC}           ${BOLD}$TESTS_ADDED${NC}"
echo -e "${YELLOW}📝 Existing tests updated:${NC}    ${BOLD}$TESTS_UPDATED${NC}"
echo -e "${RED}🗑️  Tests removed:${NC}             ${BOLD}$TESTS_REMOVED${NC}"
echo -e "${BLUE}📦 Total tests (before):${NC}      $TOTAL_BEFORE"
echo -e "${BLUE}📦 Total tests (after):${NC}       $TOTAL_AFTER"
echo ""

# Show details of added tests
if [ "$TESTS_ADDED" -gt 0 ]; then
    echo -e "${GREEN}New tests added:${NC}"
    comm -13 "$BEFORE_TESTS" "$AFTER_TESTS" | head -10 | sed 's/^/  ✨ /'
    if [ "$TESTS_ADDED" -gt 10 ]; then
        echo -e "  ... and $((TESTS_ADDED - 10)) more"
    fi
    echo ""
fi

# Show details of removed tests
if [ "$TESTS_REMOVED" -gt 0 ]; then
    echo -e "${RED}Tests removed:${NC}"
    comm -23 "$BEFORE_TESTS" "$AFTER_TESTS" | head -5 | sed 's/^/  🗑️  /'
    if [ "$TESTS_REMOVED" -gt 5 ]; then
        echo -e "  ... and $((TESTS_REMOVED - 5)) more"
    fi
    echo ""
fi

# Determine which tests will run
echo -e "${BOLD}${BLUE}═══════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}${BLUE}  TEST SELECTION${NC}"
echo -e "${BOLD}${BLUE}═══════════════════════════════════════════════════════${NC}"
echo ""

# Run the test command if provided, otherwise use smart runner
TEST_COMMAND="${1:-./scripts/test/smart-test-runner.sh}"

if [ "$TEST_COMMAND" = "all" ] || [ "$TEST_COMMAND" = "full" ]; then
    TEST_COMMAND="./scripts/test/run-tests-local.sh all"
fi

echo -e "${BLUE}🎯 Test Strategy:${NC} Smart Selection"
echo -e "${BLUE}🚀 Test Command:${NC} $TEST_COMMAND"
echo ""

# Estimate selected tests (before running)
if echo "$TEST_COMMAND" | grep -q "smart-test-runner"; then
    # Smart runner - estimate based on changes
    SELECTED_TESTS="~50-150 tests (subset based on changes)"

    if echo "$CHANGED_FILES" | grep -qE "^app/models/|^app/database.py|^requirements.txt"; then
        SELECTED_TESTS="ALL $TOTAL_AFTER tests (critical files changed)"
    elif echo "$CHANGED_FILES" | grep -qE "^tests/"; then
        SELECTED_TESTS="~20-50 tests (test files changed)"
    fi
elif echo "$TEST_COMMAND" | grep -q "run-tests-local.sh all"; then
    SELECTED_TESTS="ALL $TOTAL_AFTER tests (full suite)"
else
    SELECTED_TESTS="Varies based on command"
fi

echo -e "${BLUE}📋 Estimated tests to run:${NC} $SELECTED_TESTS"
echo ""
echo -e "${BOLD}${BLUE}═══════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}${BLUE}  RUNNING TESTS${NC}"
echo -e "${BOLD}${BLUE}═══════════════════════════════════════════════════════${NC}"
echo ""

# Run tests and capture output
START_TIME=$(date +%s)

if eval "$TEST_COMMAND" 2>&1 | tee "$TEST_OUTPUT"; then
    TEST_EXIT_CODE=0
else
    TEST_EXIT_CODE=$?
fi

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

# Parse test results from output
TESTS_RAN=$(grep -E "passed|failed" "$TEST_OUTPUT" | tail -1 | grep -oE "[0-9]+ passed" | grep -oE "[0-9]+" || echo "0")
TESTS_FAILED=$(grep -E "passed|failed" "$TEST_OUTPUT" | tail -1 | grep -oE "[0-9]+ failed" | grep -oE "[0-9]+" || echo "0")
TESTS_SKIPPED=$(grep -E "skipped" "$TEST_OUTPUT" | tail -1 | grep -oE "[0-9]+ skipped" | grep -oE "[0-9]+" || echo "0")

# Format duration
if [ "$DURATION" -ge 60 ]; then
    MINUTES=$((DURATION / 60))
    SECONDS=$((DURATION % 60))
    DURATION_STR="${MINUTES}m ${SECONDS}s"
else
    DURATION_STR="${DURATION}s"
fi

# Final Report
echo ""
echo -e "${BOLD}${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}${GREEN}  FINAL TEST METRICS REPORT${NC}"
echo -e "${BOLD}${GREEN}═══════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${BOLD}Test Coverage Changes:${NC}"
echo -e "  ✨ New tests added:          ${BOLD}${GREEN}$TESTS_ADDED${NC}"
echo -e "  📝 Existing tests updated:   ${BOLD}${YELLOW}$TESTS_UPDATED${NC}"
echo -e "  🗑️  Tests removed:            ${BOLD}${RED}$TESTS_REMOVED${NC}"
echo -e "  📊 Net change:               ${BOLD}$((TESTS_ADDED - TESTS_REMOVED))${NC} tests"
echo ""
echo -e "${BOLD}Test Execution:${NC}"
echo -e "  🎯 Tests selected:           ${BOLD}${BLUE}$TESTS_RAN${NC} (subset)"
echo -e "  ⏱️  Time taken:               ${BOLD}${BLUE}$DURATION_STR${NC}"
echo ""
echo -e "${BOLD}Test Results:${NC}"
echo -e "  ✅ Passed:                   ${BOLD}${GREEN}$TESTS_RAN${NC}"

if [ "$TESTS_FAILED" -gt 0 ]; then
    echo -e "  ❌ Failed:                   ${BOLD}${RED}$TESTS_FAILED${NC}"
fi

if [ "$TESTS_SKIPPED" -gt 0 ]; then
    echo -e "  ⏭️  Skipped:                  ${BOLD}${YELLOW}$TESTS_SKIPPED${NC}"
fi

echo ""
echo -e "${BOLD}Performance:${NC}"

# Calculate tests per second
if [ "$DURATION" -gt 0 ]; then
    TESTS_PER_SEC=$((TESTS_RAN * 100 / DURATION))
    TESTS_PER_SEC_FORMATTED="$((TESTS_PER_SEC / 100)).$((TESTS_PER_SEC % 100))"
    echo -e "  ⚡ Test throughput:          ${BOLD}$TESTS_PER_SEC_FORMATTED tests/sec${NC}"
fi

# Compare to full suite baseline
FULL_SUITE_TIME=195  # 3 min 15 sec baseline
if [ "$DURATION" -lt "$FULL_SUITE_TIME" ]; then
    TIME_SAVED=$((FULL_SUITE_TIME - DURATION))
    PERCENT_SAVED=$((TIME_SAVED * 100 / FULL_SUITE_TIME))
    echo -e "  💰 Time saved vs full suite: ${BOLD}${GREEN}${TIME_SAVED}s (${PERCENT_SAVED}%)${NC}"
fi

echo ""
echo -e "${BOLD}${GREEN}═══════════════════════════════════════════════════════${NC}"

# Cleanup
rm -f "$BEFORE_TESTS" "$AFTER_TESTS" "$TEST_OUTPUT"

exit $TEST_EXIT_CODE
