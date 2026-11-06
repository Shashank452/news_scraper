"""
Database initialization script.
Creates tables and verifies database connectivity.
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import init_db
from utils import logger


def main():
    logger.info("Running database initialization...")
    init_db()
    logger.info("Database initialized successfully.")


if __name__ == "__main__":
    main()
