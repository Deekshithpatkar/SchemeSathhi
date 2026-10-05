"""
Configuration module.
Reads settings from the .env file and sets up basic paths and logging.
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Base project directory (where this file's parent directory is)
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file
load_dotenv(BASE_DIR / ".env")

# Database URL
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/scheme_agent"
)

# LLM Settings (Ollama / Local or API)
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:7b-instruct")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# Storage folders
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
STRUCTURED_DIR = DATA_DIR / "structured"
EXTRACTED_RULES_DIR = DATA_DIR / "extracted_rules"
COMPARISONS_DIR = DATA_DIR / "comparisons"
IMAGES_DIR = DATA_DIR / "images"
LOGS_DIR = DATA_DIR / "logs"

# Ensure all data directories exist
RAW_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
STRUCTURED_DIR.mkdir(parents=True, exist_ok=True)
EXTRACTED_RULES_DIR.mkdir(parents=True, exist_ok=True)
COMPARISONS_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)


def setup_logger(name: str = "scheme_agent") -> logging.Logger:
    """
    Sets up a simple logger that writes messages both
    to the terminal and to data/logs/app.log.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Avoid adding duplicate handlers if setup_logger is called multiple times
    if not logger.handlers:
        # Formatter: Timestamp - Name - Level - Message
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

        # 1. Console Handler (prints to terminal)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # 2. File Handler (saves to data/logs/app.log)
        log_file = LOGS_DIR / "app.log"
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
