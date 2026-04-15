"""Run the Arthos FastAPI application."""
import uvicorn
import logging
import os
import sys
import json
import datetime

# Ensure Unicode output works on Windows (cp1252 terminals don't support ✓/⚠)
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


class JSONFormatter(logging.Formatter):
    """JSON formatter for Railway production logging."""

    def format(self, record):
        log_entry = {
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


# Check if running in Railway
is_railway = os.getenv('RAILWAY_ENVIRONMENT') or os.getenv('RAILWAY_SERVICE_NAME')

if is_railway:
    # Production (Railway): Use JSON format for proper log parsing
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logging.basicConfig(
        level=logging.INFO,
        handlers=[handler],
        force=True
    )
else:
    # Local development: Use human-readable format
    handlers = [logging.StreamHandler()]

    # Add file handler if LOG_FILE is set
    log_file = os.getenv('LOG_FILE')
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(name)s - %(message)s'
        ))
        handlers.append(file_handler)

    logging.basicConfig(
        level=logging.DEBUG if os.getenv('LOG_LEVEL') == 'DEBUG' else logging.INFO,
        format='%(levelname)s: %(name)s - %(message)s',
        handlers=handlers
    )

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
