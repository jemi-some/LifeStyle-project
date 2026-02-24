import logging
from app.main import app

# Setup basic logging to capture errors in Vercel Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info("Vercel api/index.py initialized")

# This is the entry point for Vercel Serverless Functions
# It exports the FastAPI app instance

