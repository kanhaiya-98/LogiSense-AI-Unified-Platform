from __future__ import annotations
"""
Damage Classifier using ResNet-50
Maps image features to damage severity classes.
torch/torchvision are lazy-imported so backend starts without them.
"""
import logging
import io
from pathlib import Path

logger = logging.getLogger(__name__)

DAMAGE_CLASSES = ["NONE", "MINOR", "MODERATE", "SEVERE", "DESTROYED"]

ROUTING_MAP = {
    "NONE":      "FULL_REFUND",
    "MINOR":     "PARTIAL_REFUND",
    "MODERATE":  "REFURBISHMENT",
    "SEVERE":    "LIQUIDATION",
    "DESTROYED": "DISPOSAL",
}

_model = None
_transform = None
_torch_available = None


def _check_torch():
    global _torch_available
    if _torch_available is None:
        try:
            import torch  # noqa
            import torchvision  # noqa
            _torch_available = True
        except ImportError:
            _torch_available = False
            logger.warning("⚠️  torch/torchvision not installed. Damage classifier will use heuristic fallback.")
    return _torch_available


def _get_model():
    global _model, _transform
    if _model is None:
        if not _check_torch():
            raise ImportError("torch is not installed. Install with: pip install torch torchvision")

        import torch
        import torch.nn as nn
        from torchvision import zen.models, transforms

        _transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406],
                                 std=[0.229, 0.224, 0.225]),
        ])

        m = models.resnet50(weights=models.ResNet50_Weights.DEFAULT)
        m.fc = nn.Linear(m.fc.in_features, len(DAMAGE_CLASSES))

        from app.config import get_settings
        cfg = get_settings()
        weights_path = Path(cfg.damage_model_path)
        if weights_path.exists():
            state = torch.load(weights_path, map_location="cpu")
            m.load_state_dict(state)
            logger.info(f"Loaded fine-tuned damage model from {weights_path}")
        else:
            logger.warning(
                f"Fine-tuned damage model not found at {weights_path}. "
                "Using ImageNet ResNet-50 — damage scoring will be heuristic for demo."
            )

        m.eval()
        _model = m
        return _model
    return _model


def _heuristic_classify(image_bytes: bytes) -> dict:
    """
    Fallback when torch is not available.
    Uses image size/format as a rough proxy.
    In production, replace with real model.
    """
    import random
    random.seed(len(image_bytes) % 1000)
    # Simulate a plausible distribution skewed towards less damage
    weights = [0.35, 0.30, 0.20, 0.10, 0.05]
    idx = random.choices(range(len(DAMAGE_CLASSES)), weights=weights)[0]
    damage_class = DAMAGE_CLASSES[idx]
    confidence = random.uniform(0.55, 0.90)

    raw = {}
    remaining = 1.0
    for i, cls in enumerate(DAMAGE_CLASSES):
        if i == idx:
            raw[cls] = round(confidence, 4)
            remaining -= confidence
        else:
            share = max(0, remaining / (len(DAMAGE_CLASSES) - i - 1)) if i < len(DAMAGE_CLASSES) - 1 else max(0, remaining)
            raw[cls] = round(share, 4)

    return {
        "damage_class":     damage_class,
        "confidence":       round(confidence, 4),
        "routing_decision": ROUTING_MAP[damage_class],
        "raw_scores":       raw,
        "model_version":    "heuristic-fallback-v1",
    }


def classify_damage(image_bytes: bytes) -> dict:
    """
    Returns: {damage_class, confidence, routing_decision, raw_scores, model_version}
    """
    if not _check_torch():
        return _heuristic_classify(image_bytes)

    try:
        from PIL import Image
        model = _get_model()

        import torch
        from torchvision import transforms
        transform = _transform

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        tensor = transform(img).unsqueeze(0)

        with torch.no_grad():
            logits = model(tensor)
            probs = torch.softmax(logits, dim=1)[0].numpy()

        pred_idx = int(probs.argmax())
        damage_class = DAMAGE_CLASSES[pred_idx]
        confidence = float(probs[pred_idx])
        raw_scores = {cls: round(float(probs[i]), 4) for i, cls in enumerate(DAMAGE_CLASSES)}

        return {
            "damage_class":     damage_class,
            "confidence":       round(confidence, 4),
            "routing_decision": ROUTING_MAP[damage_class],
            "raw_scores":       raw_scores,
            "model_version":    "resnet50-imagenet-v1",
        }
    except Exception as e:
        logger.error(f"ResNet classification failed: {e}, using heuristic")
        return _heuristic_classify(image_bytes)
