"""Run the Arthos FastAPI application."""
import uvicorn
import logging

# Configure logging to see DEBUG level logs from scheduler
logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s:     %(name)s - %(message)s'
)

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
