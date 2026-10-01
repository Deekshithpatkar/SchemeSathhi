"""
Test Environment and Project Skeleton (CP1).
Verifies that all required packages can be imported and paths are created.
"""

def test_imports():
    """Verify that all core libraries are installed and can be imported."""
    import requests
    import bs4
    import pymupdf
    import psycopg
    import pydantic
    import dotenv

    assert requests.__name__ == "requests"
    assert bs4.__name__ == "bs4"
    assert pymupdf.__name__ == "pymupdf"
    assert psycopg.__name__ == "psycopg"
    assert pydantic.__name__ == "pydantic"
    assert dotenv.__name__ == "dotenv"


def test_config_paths():
    """Verify that project paths and directories exist."""
    from app.config import BASE_DIR, DATA_DIR, RAW_DIR, PROCESSED_DIR, LOGS_DIR

    assert BASE_DIR.exists()
    assert DATA_DIR.exists()
    assert RAW_DIR.exists()
    assert PROCESSED_DIR.exists()
    assert LOGS_DIR.exists()


def test_logger():
    """Verify that the logger works and writes to the log file."""
    from app.config import setup_logger, LOGS_DIR

    logger = setup_logger("test_logger")
    test_message = "Test log entry for Checkpoint 1"
    logger.info(test_message)

    log_file = LOGS_DIR / "app.log"
    assert log_file.exists()

    with open(log_file, "r", encoding="utf-8") as f:
        content = f.read()
        assert test_message in content
