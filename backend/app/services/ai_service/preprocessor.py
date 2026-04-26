"""
Image preprocessing pipeline.
This version mirrors the notebook training pipeline as closely as possible.

Notebook pipeline used:
- cv2.imread(...)
- resize to (224, 224)
- unsharp mask
- CLAHE
- no ImageNet mean/std normalization
- model already contains Rescaling(1.0 / 255)
"""

import io
import cv2
import numpy as np

TARGET_SIZE = (224, 224)


def apply_unsharp_mask(image_bgr, sigma=1.0, strength=1.5):
    blurred = cv2.GaussianBlur(image_bgr, (0, 0), sigmaX=sigma, sigmaY=sigma)
    return cv2.addWeighted(image_bgr, 1 + strength, blurred, -strength, 0)


def apply_clahe(image_rgb):
    lab_image = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2LAB)
    l, a, b = cv2.split(lab_image)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l_clahe = clahe.apply(l)

    clahe_lab = cv2.merge((l_clahe, a, b))
    clahe_rgb = cv2.cvtColor(clahe_lab, cv2.COLOR_LAB2RGB)
    return clahe_rgb


def preprocess_array(image_bgr: np.ndarray) -> np.ndarray:
    """
    Mirror the notebook pipeline exactly.

    Important:
    - We keep OpenCV-style loading/array handling.
    - We do NOT divide by 255 here.
    - We do NOT apply ImageNet mean/std normalization.
    - The model itself already does Rescaling(1.0 / 255).
    """
    image_resized = cv2.resize(image_bgr, TARGET_SIZE)
    sharpened = apply_unsharp_mask(image_resized)

    # This intentionally mirrors the notebook behavior exactly.
    # The notebook passes the sharpened OpenCV image into apply_clahe(...)
    # as written there, so we preserve that behavior here for consistency.
    processed = apply_clahe(sharpened)

    input_image = np.expand_dims(processed.astype(np.float32), axis=0)
    return input_image


def preprocess_image(image_path: str) -> np.ndarray:
    image_bgr = cv2.imread(image_path)
    if image_bgr is None:
        raise ValueError(f"Could not load image: {image_path}")
    return preprocess_array(image_bgr)


def preprocess_from_bytes(image_bytes: bytes) -> np.ndarray:
    file_bytes = np.frombuffer(image_bytes, np.uint8)
    image_bgr = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    if image_bgr is None:
        raise ValueError("Could not decode uploaded image bytes")
    return preprocess_array(image_bgr)