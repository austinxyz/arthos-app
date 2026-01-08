# PowerShell script to run tests locally using Docker (mimics GitHub Actions CI)

param(
    [string]$TestType = "all"  # all, unit, browser, or specific test file
)

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Running Tests Locally (Docker)" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# Check if Docker is running
try {
    docker info | Out-Null
} catch {
    Write-Host "Error: Docker is not running. Please start Docker and try again." -ForegroundColor Red
    exit 1
}

Write-Host "Test type: $TestType" -ForegroundColor Yellow

# Start PostgreSQL
Write-Host "`nStarting PostgreSQL..." -ForegroundColor Green
docker-compose -f docker-compose.test.yml up -d postgres

# Wait for PostgreSQL to be ready
Write-Host "Waiting for PostgreSQL to be ready..."
$maxAttempts = 30
$attempt = 0
do {
    Start-Sleep -Seconds 1
    $attempt++
    $ready = docker-compose -f docker-compose.test.yml exec -T postgres pg_isready -U test_user -d test_db 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "PostgreSQL is ready!" -ForegroundColor Green
        break
    }
} while ($attempt -lt $maxAttempts)

if ($attempt -eq $maxAttempts) {
    Write-Host "PostgreSQL failed to start!" -ForegroundColor Red
    exit 1
}

# Run tests based on type
switch ($TestType) {
    "unit" {
        Write-Host "`nRunning unit tests..." -ForegroundColor Green
        docker-compose -f docker-compose.test.yml run --rm test-runner `
            pytest tests/ -v --tb=short -k "not browser and not e2e"
    }
    "browser" {
        Write-Host "`nStarting server for browser tests..." -ForegroundColor Green
        # Start server in background
        docker-compose -f docker-compose.test.yml run -d --rm --name test-server test-runner `
            uvicorn app.main:app --host 0.0.0.0 --port 8000
        
        # Wait for server
        Write-Host "Waiting for server to start..."
        $maxAttempts = 30
        $attempt = 0
        do {
            Start-Sleep -Seconds 1
            $attempt++
            try {
                $response = docker-compose -f docker-compose.test.yml exec -T test-server curl -f http://localhost:8000/ 2>&1
                if ($LASTEXITCODE -eq 0) {
                    Write-Host "Server is ready!" -ForegroundColor Green
                    break
                }
            } catch {
                # Continue waiting
            }
        } while ($attempt -lt $maxAttempts)
        
        # Run browser tests
        Write-Host "`nRunning browser tests..." -ForegroundColor Green
        docker-compose -f docker-compose.test.yml run --rm test-runner `
            pytest tests/ -v --tb=short -k "browser or e2e"
        
        # Stop server
        docker-compose -f docker-compose.test.yml stop test-server 2>&1 | Out-Null
        docker-compose -f docker-compose.test.yml rm -f test-server 2>&1 | Out-Null
    }
    "all" {
        Write-Host "`nRunning all tests..." -ForegroundColor Green
        # Run unit tests
        Write-Host "`n--- Unit Tests ---" -ForegroundColor Yellow
        docker-compose -f docker-compose.test.yml run --rm test-runner `
            pytest tests/ -v --tb=short -k "not browser and not e2e"
        
        # Run browser tests
        Write-Host "`n--- Browser Tests ---" -ForegroundColor Yellow
        # Start server in background
        docker-compose -f docker-compose.test.yml run -d --rm --name test-server test-runner `
            uvicorn app.main:app --host 0.0.0.0 --port 8000
        
        # Wait for server
        Write-Host "Waiting for server to start..."
        $maxAttempts = 30
        $attempt = 0
        do {
            Start-Sleep -Seconds 1
            $attempt++
            try {
                $response = docker-compose -f docker-compose.test.yml exec -T test-server curl -f http://localhost:8000/ 2>&1
                if ($LASTEXITCODE -eq 0) {
                    Write-Host "Server is ready!" -ForegroundColor Green
                    break
                }
            } catch {
                # Continue waiting
            }
        } while ($attempt -lt $maxAttempts)
        
        # Run browser tests
        docker-compose -f docker-compose.test.yml run --rm test-runner `
            pytest tests/ -v --tb=short -k "browser or e2e"
        
        # Stop server
        docker-compose -f docker-compose.test.yml stop test-server 2>&1 | Out-Null
        docker-compose -f docker-compose.test.yml rm -f test-server 2>&1 | Out-Null
    }
    default {
        # Run specific test file or pattern
        Write-Host "`nRunning specific test: $TestType" -ForegroundColor Green
        docker-compose -f docker-compose.test.yml run --rm test-runner `
            pytest tests/ -v --tb=short $TestType
    }
}

Write-Host "`nTests completed!" -ForegroundColor Green

