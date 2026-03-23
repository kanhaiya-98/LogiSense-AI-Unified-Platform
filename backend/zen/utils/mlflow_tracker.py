from __future__ import annotations
"""MLflow tracker stub — no-op if mlflow not installed."""
import logging
logger = logging.getLogger(__name__)

class MLflowTracker:
    def __init__(self, tracking_uri: str = "mlruns"):
        self.tracking_uri = tracking_uri
        try:
            import mlflow
            mlflow.set_tracking_uri(tracking_uri)
        except ImportError:
            pass

    def log_metric(self, key, value):
        try:
            import mlflow
            mlflow.log_metric(key, value)
        except Exception:
            pass
