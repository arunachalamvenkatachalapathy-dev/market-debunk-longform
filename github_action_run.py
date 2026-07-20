"""
GitHub Actions entry point for the Longform Podcast Pipeline.
"""
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import logging
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Load local .env if it exists
if os.path.exists(".env"):
    load_dotenv()
    logger.info("Loaded config from .env")

from main import run_pipeline, cleanup_output


def run_production():
    """Production entry point for GitHub Actions."""
    logger.info("🚀 Starting Longform Podcast Pipeline (Production)...")

    cleanup_output()

    try:
        success = run_pipeline()

        if success:
            logger.info("🏁 Production Pipeline completed successfully!")
            sys.exit(0)
        else:
            logger.error("🛑 Production Pipeline FAILED.")
            sys.exit(1)
    finally:
        cleanup_output()


if __name__ == "__main__":
    run_production()
