"""System logging for SmartQuota Manager."""

import logging
from datetime import datetime
from src.constants import DEFAULT_SYSTEM_LOG, ensure_config_dir

def setup_logger():
    """Configure the system logger."""
    ensure_config_dir()
    
    # Configure logging to file and console
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(DEFAULT_SYSTEM_LOG),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger("papi-q")

# Initialize logger instance
logger = setup_logger()

def log_info(message: str):
    logger.info(message)

def log_error(message: str, error: Exception = None):
    if error:
        logger.error(f"{message}: {error}", exc_info=True)
    else:
        logger.error(message)

def log_warning(message: str):
    logger.warning(message)
