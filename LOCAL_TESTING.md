# Local Testing with Docker

This guide explains how to run tests locally using Docker, mimicking the GitHub Actions CI environment.

## Prerequisites

- Docker Desktop installed and running
- Docker Compose (usually included with Docker Desktop)

## Quick Start

### Run All Tests

**Linux/macOS:**
```bash
chmod +x scripts/run-tests-local.sh
./scripts/run-tests-local.sh all
```

**Windows (PowerShell):**
```powershell
.\scripts\run-tests-local.ps1 -TestType all
```

### Run Only Unit Tests

**Linux/macOS:**
```bash
./scripts/run-tests-local.sh unit
```

**Windows:**
```powershell
.\scripts\run-tests-local.ps1 -TestType unit
```

### Run Only Browser Tests

**Linux/macOS:**
```bash
./scripts/run-tests-local.sh browser
```

**Windows:**
```powershell
.\scripts\run-tests-local.ps1 -TestType browser
```

### Run Specific Test File

**Linux/macOS:**
```bash
./scripts/run-tests-local.sh tests/test_api.py
```

**Windows:**
```powershell
.\scripts\run-tests-local.ps1 -TestType tests/test_api.py
```

## Manual Docker Commands

If you prefer to run Docker commands manually:

### 1. Start PostgreSQL

```bash
docker-compose -f docker-compose.test.yml up -d postgres
```

### 2. Wait for PostgreSQL to be ready

```bash
docker-compose -f docker-compose.test.yml exec postgres pg_isready -U test_user -d test_db
```

### 3. Run Unit Tests

```bash
docker-compose -f docker-compose.test.yml run --rm test-runner \
    pytest tests/ -v --tb=short -k "not browser and not e2e"
```

### 4. Run Browser Tests

First, start the server:

```bash
docker-compose -f docker-compose.test.yml run -d --rm --name test-server test-runner \
    uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Wait for server to be ready, then run tests:

```bash
docker-compose -f docker-compose.test.yml run --rm test-runner \
    pytest tests/ -v --tb=short -k "browser or e2e"
```

Stop the server:

```bash
docker-compose -f docker-compose.test.yml stop test-server
docker-compose -f docker-compose.test.yml rm -f test-server
```

### 5. Cleanup

Stop and remove all containers:

```bash
docker-compose -f docker-compose.test.yml down
```

Remove volumes (clears database):

```bash
docker-compose -f docker-compose.test.yml down -v
```

## Environment

The test environment matches GitHub Actions:

- **Python**: 3.9
- **PostgreSQL**: 15
- **Database**: `test_db` with user `test_user` / password `test_password`
- **DATABASE_URL**: `postgresql://test_user:test_password@postgres:5432/test_db`

## Troubleshooting

### Docker is not running

Make sure Docker Desktop is running before executing test scripts.

### Port 5432 already in use

If you have a local PostgreSQL instance running, you can:
1. Stop your local PostgreSQL, or
2. Change the port mapping in `docker-compose.test.yml`:
   ```yaml
   ports:
     - "5433:5432"  # Use 5433 instead of 5432
   ```

### Tests fail with connection errors

Make sure PostgreSQL container is healthy:
```bash
docker-compose -f docker-compose.test.yml ps
```

Check PostgreSQL logs:
```bash
docker-compose -f docker-compose.test.yml logs postgres
```

### Browser tests fail with connection refused

Make sure the test server container is running:
```bash
docker-compose -f docker-compose.test.yml ps test-server
```

Check server logs:
```bash
docker-compose -f docker-compose.test.yml logs test-server
```

### Rebuild test image

If you change dependencies or Dockerfile:

```bash
docker-compose -f docker-compose.test.yml build --no-cache test-runner
```

## Differences from GitHub Actions

- **Caching**: GitHub Actions caches pip packages, Docker uses a volume
- **Parallel execution**: GitHub Actions runs steps in parallel, Docker runs sequentially
- **Resource limits**: Docker may have different resource limits than GitHub runners

## Tips

1. **First run**: The first time you run tests, Docker will build the image and download dependencies. This may take several minutes.

2. **Subsequent runs**: Docker will reuse the cached image and volumes, making subsequent runs much faster.

3. **Debugging**: You can exec into the test container to debug:
   ```bash
   docker-compose -f docker-compose.test.yml run --rm test-runner bash
   ```

4. **View logs**: Check container logs for debugging:
   ```bash
   docker-compose -f docker-compose.test.yml logs test-runner
   ```

