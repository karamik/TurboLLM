# turbo-llm/turbollm/proof_package.py

from typing import Any, Dict


class InspectionManifest:
    def __init__(self, model_id: str, inspector_version: str):
        self.model_id = model_id
        self.inspector_version = inspector_version
        self.inference_id = None  # будет передан из hardware-манифеста
        self.gs_metrics = {}
        self.decision = None
        self.confidence = None
        self.reflection_triggered = False
        self.proof_of_inspection = None
        self.inspector_log = None

    def set_inference_id(self, inference_id: str):
        self.inference_id = inference_id

    def set_gs_metrics(self, metrics: Dict):
        self.gs_metrics = metrics

    def set_decision(self, decision: str, confidence: float, reflection: bool = False):
        self.decision = decision
        self.confidence = confidence
        self.reflection_triggered = reflection

    def set_proof_of_inspection(self, signature: str):
        self.proof_of_inspection = signature

    def set_inspector_log(self, log_uri: str):
        self.inspector_log = log_uri

    def to_dict(self) -> Dict[str, Any]:
        return {
            "inspector_version": self.inspector_version,
            "model_id": self.model_id,
            "inference_id": self.inference_id,
            "gs_metrics": self.gs_metrics,
            "decision": self.decision,
            "confidence": self.confidence,
            "reflection_triggered": self.reflection_triggered,
            "proof_of_inspection": self.proof_of_inspection,
            "inspector_log": self.inspector_log,
        }
