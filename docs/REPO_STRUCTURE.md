# Repository Structure

This document describes the organization of the Arthos-App repository.

```
arthos-app/
├── app/                        # Application source code
│   ├── models/                 # SQLModel database models
│   ├── providers/              # Data providers (yfinance, MarketData)
│   ├── services/               # Business logic services
│   ├── static/                 # CSS, JS, images
│   ├── templates/              # Jinja2 HTML templates
│   └── main.py                 # FastAPI application
│
├── docs/                       # Documentation
│   ├── deployment/             # Railway, GitHub, secrets setup guides
│   ├── development/            # Local dev, testing, quick start guides
│   ├── learnings/              # Post-incident learnings
│   ├── specs/                  # Feature specifications
│   └── screenshots/            # UI screenshots
│
├── scripts/                    # Utility scripts
│   ├── db/                     # Database management scripts
│   ├── debug/                  # Debugging utilities
│   └── test/                   # Test running scripts
│
├── tests/                      # Pytest test files
├── static/                     # Root static assets
├── .agent/workflows/           # Agent workflows (e.g., pre-push)
│
├── README.md                   # Project overview
├── requirements.txt            # Python dependencies
├── Procfile                    # Railway process file
├── docker-compose.test.yml     # Docker test configuration
├── pytest.ini                  # Pytest configuration
└── run.py                      # Local development entry point
```

## Key Directories

### `/app` - Application Code
All Python application code lives here. Follow the existing patterns for:
- **models/**: Database models using SQLModel
- **providers/**: External data sources (yfinance, MarketData)
- **services/**: Business logic (keep API routes thin)

### `/docs` - Documentation
All documentation except README.md should be here:
- **deployment/**: How to deploy to Railway, set up secrets
- **development/**: How to develop locally, run tests
- **learnings/**: Post-incident documentation (what went wrong, how to avoid)
- **specs/**: Feature specifications and designs

### `/scripts` - Utility Scripts
Helper scripts organized by purpose:
- **db/**: Database operations (clear, fix, migrate)
- **debug/**: One-off debugging scripts
- **test/**: Test execution scripts

### `/tests` - Test Files
All pytest test files. Follow naming convention: `test_*.py`

## What Goes Where

| Content Type | Location |
|--------------|----------|
| Application code | `/app` |
| Database models | `/app/models` |
| Business logic | `/app/services` |
| HTML templates | `/app/templates` |
| Deployment docs | `/docs/deployment` |
| Dev guides | `/docs/development` |
| Post-mortems | `/docs/learnings` |
| Feature specs | `/docs/specs` |
| Debug scripts | `/scripts/debug` |
| DB scripts | `/scripts/db` |
| Test scripts | `/scripts/test` |
| Test files | `/tests` |

## Conventions

1. **Only README.md in root** - All other docs go in `/docs`
2. **No scripts in root** - Use `/scripts` subdirectories
3. **Pre-push testing** - Run `/pre-push` workflow before pushing to main
4. **Learnings after incidents** - Document in `/docs/learnings`
