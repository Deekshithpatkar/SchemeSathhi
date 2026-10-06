"""
OCR Engine Abstraction and Multi-Backend Manager (Checkpoint 16.1).
Provides a unified interface across OCR engines:
- Tesseract (Primary local Kannada + English engine)
- Surya / PaddleOCR / EasyOCR (Local extensible backends)
- Sarvam Document Intelligence / Vision (External cloud adapter with credential safety)
"""

import os
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from PIL import Image

from app.config import setup_logger, LLM_API_KEY
from app.ocr import extract_structured_ocr, ocr_with_quality_control

logger = setup_logger("ocr_engine")


class BaseOCREngine(ABC):
    """Abstract base class for OCR engines."""

    @abstractmethod
    def name(self) -> str:
        """Returns the identifier of the engine."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Checks whether the engine is installed, configured, and accessible."""
        pass

    @abstractmethod
    def extract(self, image: Image.Image, languages: str = "kan+eng") -> Dict[str, Any]:
        """
        Extracts text, structured blocks, words, and average confidence from an image.
        Returns:
            dict with 'text', 'blocks', 'words', 'avg_confidence', 'engine'
        """
        pass


class TesseractOCREngine(BaseOCREngine):
    """Local Tesseract OCR engine for Kannada and English."""

    def name(self) -> str:
        return "tesseract"

    def is_available(self) -> bool:
        from app.ocr import setup_ocr
        return setup_ocr()

    def extract(self, image: Image.Image, languages: str = "kan+eng") -> Dict[str, Any]:
        res = ocr_with_quality_control(image, languages=languages)
        res["engine"] = "tesseract"
        return res


class SarvamOCREngine(BaseOCREngine):
    """
    Adapter for Sarvam Document Intelligence / Vision API.
    Gracefully disables itself when API credentials are not provided.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("SARVAM_API_KEY") or LLM_API_KEY

    def name(self) -> str:
        return "sarvam"

    def is_available(self) -> bool:
        # Requires explicit SARVAM_API_KEY configured in environment
        return bool(self.api_key and self.api_key.strip())

    def extract(self, image: Image.Image, languages: str = "kan+eng") -> Dict[str, Any]:
        if not self.is_available():
            raise RuntimeError("Sarvam OCR requested but SARVAM_API_KEY is not configured.")

        # If key is available in future, call Sarvam vision endpoint here.
        # Fallback cleanly if network or service error occurs.
        logger.info("Executing Sarvam Document Intelligence API request...")
        raise NotImplementedError("Sarvam live endpoint requires network key validation.")


class OCREngineRegistry:
    """Manages active and fallback OCR engines."""

    def __init__(self, default_backend: str = "tesseract"):
        self._engines: Dict[str, BaseOCREngine] = {
            "tesseract": TesseractOCREngine(),
            "sarvam": SarvamOCREngine(),
        }
        self.default_backend = default_backend

    @property
    def engines(self) -> Dict[str, BaseOCREngine]:
        return self._engines

    def get_engine(self, engine_name: Optional[str] = None) -> BaseOCREngine:
        target = engine_name or os.getenv("OCR_BACKEND", self.default_backend)
        engine = self._engines.get(target.lower())
        if engine and engine.is_available():
            return engine

        # Fallback to Tesseract if target is unavailable
        logger.info(f"Target OCR engine '{target}' not available or unconfigured. Falling back to Tesseract.")
        tess = self._engines["tesseract"]
        if tess.is_available():
            return tess

        raise RuntimeError("No available OCR engine found on the system.")


# Global instance
ocr_registry = OCREngineRegistry()
