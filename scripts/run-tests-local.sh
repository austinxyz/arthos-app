#!/bin/bash
# Script to run tests locally using Docker (mimics GitHub Actions CI)

set -e

echo "=========================================="
echo "Running Tests Locally (Docker)"
echo "=========================================="

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "Error: Docker is not running. Please start Docker and try again."
    exit 1
fi

# Parse command line arguments
TEST_TYPE=${1:-all}  # all, unit, browser, or specific test file

echo -e "${YELLOW}Test type: ${TEST_TYPE}${NC}"

# Start PostgreSQL
echo -e "\n${GREEN}Starting PostgreSQL...${NC}"
docker-compose -f docker-compose.test.yml up -d postgres

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL to be ready..."
for i in {1..30}; do
    if docker-compose -f docker-compose.test.yml exec -T postgres pg_isready -U test_user -d test_db > /dev/null 2>&1; then
        echo -e "${GREEN}PostgreSQL is ready!${NC}"
        break
    fi
    sleep 1
done

# Run tests based on type
case $TEST_TYPE in
    unit)
        echo -e "\n${GREEN}Running unit tests...${NC}"
        docker-compose -f docker-compose.test.yml run --rm test-runner \
            pytest tests/ -v --tb=short -k "not browser and not e2e"
        ;;
    browser)
        echo -e "\n${GREEN}Starting server for browser tests...${NC}"
        # Start server in background
        docker-compose -f docker-compose.test.yml up -d test-server
        
        # Wait for server to be ready
        echo "Waiting for server to start..."
        for i in {1..30}; do
            if curl -f http://localhost:8000/ > /dev/null 2>&1; then
                echo -e "${GREEN}Server is ready!${NC}"
                break
            fi
            sleep 1
        done
        
        # Run browser tests (use host network to access localhost:8000)
        echo -e "\n${GREEN}Running browser tests...${NC}"
        docker-compose -f docker-compose.test.yml run --rm --network host test-runner \
            pytest tests/ -v --tb=short -k "browser or e2e"
        
        # Stop server
        docker-compose -f docker-compose.test.yml stop test-server || true
        ;;
    all)
        echo -e "\n${GREEN}Running all tests...${NC}"
        # Run unit tests
        echo -e "\n${YELLOW}--- Unit Tests ---${NC}"
        docker-compose -f docker-compose.test.yml run --rm test-runner \
            pytest tests/ -v --tb=short -k "not browser and not e2e"
        
        # Run browser tests
        echo -e "\n${YELLOW}--- Browser Tests ---${NC}"
        # Start server in background
        docker-compose -f docker-compose.test.yml up -d test-server
        
        # Wait for server
        echo "Waiting for server to start..."
        for i in {1..30}; do
            if curl -f http://localhost:8000/ > /dev/null 2>&1; then
                echo -e "${GREEN}Server is ready!${NC}"
                break
            fi
            sleep 1
        done
        
        # Run browser tests (use host network to access localhost:8000)
        docker-compose -f docker-compose.test.yml run --rm --network host test-runner \
            pytest tests/ -v --tb=short -k "browser or e2e"
        
        # Stop server
        docker-compose -f docker-compose.test.yml stop test-server || true
        ;;
    *)
        # Run specific test file or pattern
        echo -e "\n${GREEN}Running specific test: ${TEST_TYPE}${NC}"
        docker-compose -f docker-compose.test.yml run --rm test-runner \
            pytest tests/ -v --tb=short "${TEST_TYPE}"
        ;;
esac

echo -e "\n${GREEN}Tests completed!${NC}"

# Cleanup (optional - comment out if you want to keep containers running)
# echo -e "\n${YELLOW}Cleaning up...${NC}"
# docker-compose -f docker-compose.test.yml down

