"""
Image Preprocessing module.
Provides modular image enhancement pipelines for scanned PDF pages
to improve OCR accuracy for Kannada, English, and structured tables.
"""

import io
import math
from typing import Union, Tuple, Optional
import cv2
import numpy as np
from PIL import Image
import pymupdf

from app.config import setup_logger

logger = setup_logger("image_preprocessor")


def render_page_to_image(page: pymupdf.Page, dpi: int = 300) -> Image.Image:
    """
    Renders a PyMuPDF page to a high-resolution PIL Image at 300 DPI.
    Higher DPI is essential for resolving intricate Kannada vowel signs (ottu/matras).
    """
    pixmap = page.get_pixmap(dpi=dpi)
    img_bytes = pixmap.tobytes("png")
    return Image.open(io.BytesIO(img_bytes))


def to_cv2(image: Image.Image) -> np.ndarray:
    """Converts a PIL Image to an OpenCV BGR numpy array."""
    np_img = np.array(image.convert("RGB"))
    return cv2.cvtColor(np_img, cv2.COLOR_RGB2BGR)


def to_pil(cv_img: np.ndarray) -> Image.Image:
    """Converts an OpenCV image (grayscale or BGR) to a PIL Image."""
    if len(cv_img.shape) == 2:
        return Image.fromarray(cv_img)
    rgb = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


def deskew_image(cv_img: np.ndarray) -> Tuple[np.ndarray, float]:
    """
    Detects skew angle from lines/text in scanned documents and rotates the image straight.
    Returns (deskewed_image, detected_angle).
    """
    gray = cv_img if len(cv_img.shape) == 2 else cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
    # Invert image: background becomes black, foreground text becomes white
    thresh = cv2.bitwise_not(gray)
    coords = np.column_stack(np.where(thresh > 0))

    if len(coords) < 100:
        return cv_img, 0.0

    # minAreaRect gives the rotated rectangle enclosing all white pixels
    rect = cv2.minAreaRect(coords)
    angle = rect[-1]

    # Adjust angle for OpenCV conventions
    if angle < -45:
        angle = -(90 + angle)
    elif angle > 45:
        angle = 90 - angle

    # Only deskew if angle is significant (between 0.5 and 15 degrees)
    if abs(angle) > 0.5 and abs(angle) < 15.0:
        (h, w) = cv_img.shape[:2]
        center = (w // 2, h // 2)
        m = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(cv_img, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        return rotated, angle

    return cv_img, 0.0


def preprocess_standard(cv_img: np.ndarray) -> np.ndarray:
    """
    Standard preprocessing:
    1. Grayscale
    2. CLAHE (Contrast Limited Adaptive Histogram Equalization)
    3. Bilateral filter for noise reduction without blurring edges
    4. Otsu binarization
    """
    gray = cv_img if len(cv_img.shape) == 2 else cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)

    # 1. CLAHE for balancing uneven shadows/scans
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # 2. Denoise with edge preservation
    denoised = cv2.bilateralFilter(enhanced, d=9, sigmaColor=75, sigmaSpace=75)

    # 3. Otsu thresholding
    _, thresh = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return thresh


def preprocess_for_kannada(cv_img: np.ndarray) -> np.ndarray:
    """
    Specialized preprocessing for Kannada text:
    Kannada contains delicate diacritics, loops, and subscript consonants (ottu).
    Aggressive binarization or erosion destroys these glyphs.
    Uses mild unsharp masking followed by adaptive Gaussian thresholding.
    """
    gray = cv_img if len(cv_img.shape) == 2 else cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)

    # 1. Unsharp masking to sharpen Kannada loops and curves
    gaussian = cv2.GaussianBlur(gray, (0, 0), 2.0)
    sharpened = cv2.addWeighted(gray, 1.5, gaussian, -0.5, 0)

    # 2. Adaptive thresholding with larger window size to maintain delicate strokes
    binary = cv2.adaptiveThreshold(
        sharpened,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=25,
        C=10,
    )
    return binary


def preprocess_for_table(cv_img: np.ndarray) -> np.ndarray:
    """
    Specialized preprocessing for table detection:
    Emphasizes straight horizontal and vertical lines while suppressing background texture.
    """
    gray = cv_img if len(cv_img.shape) == 2 else cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
    # Contrast enhancement
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    # Simple Otsu threshold
    _, thresh = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return thresh


def preprocess_image(
    image: Union[Image.Image, np.ndarray],
    method: str = "kannada",
    auto_deskew: bool = True,
) -> Image.Image:
    """
    Modular image preprocessor dispatcher.
    Methods available: 'kannada', 'standard', 'table'
    Returns preprocessed PIL Image.
    """
    # Convert input to cv2
    cv_img = to_cv2(image) if isinstance(image, Image.Image) else image

    # Deskew if requested
    if auto_deskew:
        cv_img, _ = deskew_image(cv_img)

    # Apply selected method
    if method == "kannada":
        processed_cv = preprocess_for_kannada(cv_img)
    elif method == "table":
        processed_cv = preprocess_for_table(cv_img)
    else:
        processed_cv = preprocess_standard(cv_img)

    return to_pil(processed_cv)
