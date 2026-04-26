from __future__ import annotations

import os
import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import tensorflow as tf

from app.services.ai_service.preprocessor import preprocess_image

logger = logging.getLogger(__name__)

# ✅ 4 classes only — must match the exact alphabetical order used during training
# (flow_from_directory sorts classes alphabetically: Acne, Eczema, Milia, Rosacea)
CONDITION_LABELS = [
    "Acne",
    "Eczema",
    "Milia",
    "Rosacea",
]

SEVERITY_MAP = {
    "Acne":    "medium",
    "Eczema":  "medium",
    "Milia":   "low",
    "Rosacea": "medium",
}


@dataclass
class PredictionResult:
    predicted_condition: str
    confidence_score: float
    severity: str
    requires_consultation: bool
    all_predictions: list[dict] = field(default_factory=list)
    error: Optional[str] = None


_model = None


def _load_model(model_path: str):
    global _model

    if _model is not None:
        return _model

    # Resolve path relative to this file's location if not absolute.
    # This fixes the bug where a relative path like
    # "app/services/ai_service/model/skin_model.keras" was being resolved
    # from the CWD (wherever Flask was launched), not from the project root.
    if not os.path.isabs(model_path):
        # __file__ = backend/app/services/ai_service/predictor.py
        # Go up 4 levels to reach backend/, then join the relative path
        backend_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..")
        )
        model_path = os.path.join(backend_root, model_path)

    model_path = os.path.normpath(model_path)

    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"AI model file not found at: {model_path}\n"
            f"Place skin_model.keras at: backend/app/services/ai_service/model/skin_model.keras"
        )

    logger.info("Loading AI model from '%s' ...", model_path)
    _model = tf.keras.models.load_model(model_path)
    logger.info("AI model loaded successfully.")
    return _model


def predict(image_path: str, model_path: str, confidence_threshold: float = 0.70) -> PredictionResult:
    try:
        model = _load_model(model_path)
    except FileNotFoundError as exc:
        logger.error("Model load failed: %s", exc)
        return PredictionResult(
            predicted_condition="Unknown",
            confidence_score=0.0,
            severity="medium",
            requires_consultation=True,
            all_predictions=[],
            error=str(exc),
        )

    try:
        img_array = preprocess_image(image_path)
        raw_output = model.predict(img_array, verbose=0)
        probs = raw_output[0]

        logger.info("Raw model probabilities: %s", probs.tolist())
        logger.info("Condition labels: %s", CONDITION_LABELS)

        # ✅ Guard: model output size must match our label count
        if len(probs) != len(CONDITION_LABELS):
            raise ValueError(
                f"Model output has {len(probs)} classes but CONDITION_LABELS has "
                f"{len(CONDITION_LABELS)}. Update CONDITION_LABELS to match training."
            )

        top_idx  = int(np.argmax(probs))
        top_conf = float(probs[top_idx])
        cond     = CONDITION_LABELS[top_idx]

        sorted_idx = np.argsort(probs)[::-1]
        top_k = [
            {
                "condition": CONDITION_LABELS[i],
                "score":     round(float(probs[i]), 4),
            }
            for i in sorted_idx
        ]

        severity = SEVERITY_MAP.get(cond, "medium")
        requires = top_conf < confidence_threshold

        return PredictionResult(
            predicted_condition=cond,
            confidence_score=round(top_conf, 4),
            severity=severity,
            requires_consultation=requires,
            all_predictions=top_k,
        )

    except Exception as exc:
        logger.error("Inference error for '%s': %s", image_path, exc)
        return PredictionResult(
            predicted_condition="Unknown",
            confidence_score=0.0,
            severity="medium",
            requires_consultation=True,
            all_predictions=[],
            error=str(exc),
        )
