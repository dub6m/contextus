from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json
import pickle
import re

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .labeler import ChunkAuditLabeler


TYPE_FEATURES = ("text", "title", "table", "formula", "figure", "image", "chart", "diagram", "flowchart")
BOOL_FEATURES = ("contains_title", "contains_non_text", "singleton_chunk")
NUMERIC_FEATURES = (
    "chunk_size",
    "token_count",
    "content_token_count",
    "sentence_count",
    "left_similarity",
    "right_similarity",
    "left_context_similarity",
    "right_context_similarity",
    "previous_substantive_distance",
    "next_substantive_distance",
    "previous_substantive_similarity",
    "next_substantive_similarity",
    "max_previous_similarity",
    "token_substance",
    "lexical_density",
    "type_richness",
    "left_independence",
    "right_independence",
    "novelty",
    "rhetorical_penalty",
    "duplicate_penalty",
    "heading_score",
    "proposition_score",
    "admin_score",
    "toc_score",
    "artifact_score",
    "list_item_score",
    "heuristic_viability",
)
DIRECTIONAL_NUMERIC_FEATURES = (
    "chunk_size",
    "token_count",
    "content_token_count",
    "sentence_count",
    "left_similarity",
    "right_similarity",
    "left_context_similarity",
    "right_context_similarity",
    "previous_substantive_similarity",
    "next_substantive_similarity",
    "previous_substantive_distance",
    "next_substantive_distance",
    "heading_score",
    "proposition_score",
    "admin_score",
    "toc_score",
    "artifact_score",
    "list_item_score",
    "duplicate_penalty",
    "rhetorical_penalty",
    "heuristic_viability",
)
DIRECTIONAL_DERIVED_FEATURES = (
    "similarity_delta",
    "context_similarity_delta",
    "substantive_similarity_delta",
    "anchor_delta",
    "left_fit",
    "right_fit",
    "fit_delta",
)
DIRECTIONAL_BOOL_FEATURES = (
    "has_left_chunk",
    "has_right_chunk",
    "has_previous_substantive",
    "has_next_substantive",
    "is_closer_like",
    "is_introductory_like",
    "is_formula_like",
    "is_heading_like",
    "is_list_item_like",
    "is_admin_like",
)

CLOSING_PATTERNS = (
    re.compile(r"\brespectfully submitted\b", re.IGNORECASE),
    re.compile(r"\ble tout respectueusement soumis\b", re.IGNORECASE),
    re.compile(r"\bsincerely\b", re.IGNORECASE),
    re.compile(r"\bregards\b", re.IGNORECASE),
    re.compile(r"\bsubmitted\b", re.IGNORECASE),
)
INTRODUCTORY_LABEL_PATTERNS = (
    re.compile(r"^proof\b", re.IGNORECASE),
    re.compile(r"^original signed by\b", re.IGNORECASE),
    re.compile(r"^original sign.? par\b", re.IGNORECASE),
    re.compile(r"^(?:figure|table|formula)\b", re.IGNORECASE),
)
BARE_RIGHT_MARKER_PATTERNS = (
    re.compile(r"^(?:proof|claim|example|remark|lemma|theorem|corollary)\b", re.IGNORECASE),
)


@dataclass
class StageMetrics:
    """Evaluation summary for one stage of the two-stage chunk model."""

    name: str
    train_rows: int
    test_rows: int
    labels: list[str]
    accuracy: float
    macro_f1: float
    weighted_f1: float
    classification_report: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe metrics payload."""
        return {
            "name": self.name,
            "train_rows": self.train_rows,
            "test_rows": self.test_rows,
            "labels": self.labels,
            "accuracy": self.accuracy,
            "macro_f1": self.macro_f1,
            "weighted_f1": self.weighted_f1,
            "classification_report": self.classification_report,
        }


@dataclass
class DirectionalResolution:
    """One resolved attachment-direction decision."""

    action: str | None
    confidence: float
    rule_name: str | None
    left_fit: float
    right_fit: float
    promotable: bool


@dataclass
class TrainingResult:
    """Summary of one clean-split two-stage model training run."""

    total_clean_rows: int
    stage2_training_rows: int
    stage2_promoted_review_rows: int
    stage1: StageMetrics
    stage2: StageMetrics | None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe training summary."""
        return {
            "total_clean_rows": self.total_clean_rows,
            "stage2_training_rows": self.stage2_training_rows,
            "stage2_promoted_review_rows": self.stage2_promoted_review_rows,
            "stage1": self.stage1.to_dict(),
            "stage2": None if self.stage2 is None else self.stage2.to_dict(),
        }


class ChunkActionDataset:
    """Build clean training matrices for the chunk-action model."""

    def load_rows(self, path: str | Path) -> list[dict[str, Any]]:
        """Load labeled chunk-audit rows from a JSONL file."""
        rows = []
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows

    def select_clean_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        min_confidence: float = 0.78,
    ) -> list[dict[str, Any]]:
        """Keep only cleaner, high-confidence weak labels for training."""
        clean_rows = []
        for row in rows:
            action = str(row.get("weak_action") or "").strip()
            confidence = self._coerce_float(row.get("weak_confidence"))
            needs_review = bool(row.get("weak_needs_review"))
            if action and not needs_review and confidence >= min_confidence:
                clean_rows.append(row)
        return clean_rows

    def select_stage2_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        min_confidence: float = 0.78,
        resolver: "AttachmentDirectionResolver | None" = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Return clean attachment rows plus high-confidence promoted review rows."""
        clean_rows = self.select_clean_rows(rows, min_confidence=min_confidence)
        stage2_rows: list[dict[str, Any]] = []
        for row in clean_rows:
            action = str(row.get("weak_action") or "")
            if action in {"attach_left", "attach_right"}:
                labeled = dict(row)
                labeled["direction_training_source"] = "clean_attach"
                stage2_rows.append(labeled)

        promoted_count = 0
        if resolver is None:
            return stage2_rows, promoted_count

        for row in rows:
            promoted = resolver.promote_review_row(row)
            if promoted is not None:
                stage2_rows.append(promoted)
                promoted_count += 1
        return stage2_rows, promoted_count

    def coarse_action(self, action: str) -> str:
        """Collapse non-standalone structural actions into a single coarse attach label."""
        if action in {"attach_left", "attach_right", "support_only"}:
            return "attach"
        return action

    def build_matrix(self, rows: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray, list[str]]:
        """Convert labeled rows into a numeric feature matrix and full action targets."""
        feature_names = list(NUMERIC_FEATURES)
        feature_names.extend(BOOL_FEATURES)
        feature_names.extend(f"type_count__{feature}" for feature in TYPE_FEATURES)
        matrix = np.array([self._row_to_general_features(row) for row in rows], dtype=float)
        labels = np.array([str(row.get("weak_action") or "") for row in rows])
        return matrix, labels, feature_names

    def build_stage1_matrix(self, rows: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray, list[str]]:
        """Build the coarse-action matrix for stage 1."""
        feature_names = list(NUMERIC_FEATURES)
        feature_names.extend(BOOL_FEATURES)
        feature_names.extend(f"type_count__{feature}" for feature in TYPE_FEATURES)
        matrix = np.array([self._row_to_general_features(row) for row in rows], dtype=float)
        labels = np.array([self.coarse_action(str(row.get("weak_action") or "")) for row in rows])
        return matrix, labels, feature_names

    def build_stage2_matrix(self, rows: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray, list[str]]:
        """Build the directional attachment matrix for stage 2."""
        feature_names = list(DIRECTIONAL_NUMERIC_FEATURES)
        feature_names.extend(DIRECTIONAL_DERIVED_FEATURES)
        feature_names.extend(DIRECTIONAL_BOOL_FEATURES)
        feature_names.extend(f"type_count__{feature}" for feature in TYPE_FEATURES)
        matrix = np.array([self._row_to_directional_features(row) for row in rows], dtype=float)
        labels = np.array([str(row.get("weak_action") or "") for row in rows])
        return matrix, labels, feature_names

    def _row_to_general_features(self, row: dict[str, Any]) -> list[float]:
        features = [self._coerce_float(row.get(name)) for name in NUMERIC_FEATURES]
        features.extend(1.0 if bool(row.get(name)) else 0.0 for name in BOOL_FEATURES)
        type_histogram = row.get("type_histogram") or {}
        features.extend(float(type_histogram.get(name, 0)) for name in TYPE_FEATURES)
        return features

    def _row_to_directional_features(self, row: dict[str, Any]) -> list[float]:
        features = [self._coerce_float(row.get(name)) for name in DIRECTIONAL_NUMERIC_FEATURES]

        left_similarity = self._coerce_float(row.get("left_similarity"))
        right_similarity = self._coerce_float(row.get("right_similarity"))
        left_context_similarity = self._coerce_float(row.get("left_context_similarity"))
        right_context_similarity = self._coerce_float(row.get("right_context_similarity"))
        previous_substantive_similarity = self._coerce_float(row.get("previous_substantive_similarity"))
        next_substantive_similarity = self._coerce_float(row.get("next_substantive_similarity"))
        previous_substantive_distance = self._optional_int(row.get("previous_substantive_distance"))
        next_substantive_distance = self._optional_int(row.get("next_substantive_distance"))

        left_anchor = self._inverse_distance(previous_substantive_distance)
        right_anchor = self._inverse_distance(next_substantive_distance)
        left_fit = max(left_similarity, left_context_similarity * 0.85, previous_substantive_similarity) + left_anchor
        right_fit = max(right_similarity, right_context_similarity * 0.85, next_substantive_similarity) + right_anchor
        features.extend(
            [
                right_similarity - left_similarity,
                right_context_similarity - left_context_similarity,
                next_substantive_similarity - previous_substantive_similarity,
                right_anchor - left_anchor,
                left_fit,
                right_fit,
                right_fit - left_fit,
            ]
        )

        chunk_text = self._text(row.get("chunk_text"))
        features.extend(
            [
                1.0 if self._text(row.get("left_chunk_text")) else 0.0,
                1.0 if self._text(row.get("right_chunk_text")) else 0.0,
                1.0 if self._text(row.get("previous_substantive_text")) else 0.0,
                1.0 if self._text(row.get("next_substantive_text")) else 0.0,
                1.0 if self._is_closer_like(chunk_text) else 0.0,
                1.0 if self._is_introductory_like(chunk_text) else 0.0,
                1.0 if chunk_text.lower().startswith("formula:") else 0.0,
                1.0 if self._coerce_float(row.get("heading_score")) >= 0.75 else 0.0,
                1.0 if self._coerce_float(row.get("list_item_score")) >= 0.72 else 0.0,
                1.0 if self._coerce_float(row.get("admin_score")) >= 0.78 else 0.0,
            ]
        )

        type_histogram = row.get("type_histogram") or {}
        features.extend(float(type_histogram.get(name, 0)) for name in TYPE_FEATURES)
        return features

    def _text(self, value: Any) -> str:
        return str(value or "").strip()

    def _coerce_float(self, value: Any) -> float:
        if value is None:
            return -1.0
        try:
            return float(value)
        except Exception:
            return -1.0

    def _optional_int(self, value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except Exception:
            return None

    def _inverse_distance(self, value: int | None) -> float:
        if value is None or value < 0:
            return 0.0
        return 1.0 / float(value + 1)

    def _is_closer_like(self, chunk_text: str) -> bool:
        lowered = chunk_text.strip().lower()
        return any(pattern.search(lowered) for pattern in CLOSING_PATTERNS)

    def _is_introductory_like(self, chunk_text: str) -> bool:
        stripped = chunk_text.strip()
        if not stripped:
            return False
        if any(pattern.search(stripped) for pattern in INTRODUCTORY_LABEL_PATTERNS):
            return True
        return any(pattern.search(stripped) for pattern in BARE_RIGHT_MARKER_PATTERNS)


class AttachmentDirectionResolver:
    """Promotes and resolves attachment direction using structural rules and fit deltas."""

    def __init__(
        self,
        dataset: ChunkActionDataset | None = None,
        *,
        promotion_fit_delta: float = 0.18,
        strong_fit_delta: float = 0.24,
    ) -> None:
        """Create a directional resolver for attachment rows."""
        self.dataset = dataset or ChunkActionDataset()
        self.promotion_fit_delta = promotion_fit_delta
        self.strong_fit_delta = strong_fit_delta

    def resolve(self, row: dict[str, Any], *, allow_fallback: bool = False) -> DirectionalResolution:
        """Return the best direction supported by structural rules or fit deltas."""
        chunk_text = str(row.get("chunk_text") or "").strip()
        left_text = str(row.get("left_chunk_text") or "").strip()
        right_text = str(row.get("right_chunk_text") or "").strip()
        heading_score = self.dataset._coerce_float(row.get("heading_score"))
        proposition_score = self.dataset._coerce_float(row.get("proposition_score"))
        artifact_score = self.dataset._coerce_float(row.get("artifact_score"))
        list_item_score = self.dataset._coerce_float(row.get("list_item_score"))
        admin_score = self.dataset._coerce_float(row.get("admin_score"))
        toc_score = self.dataset._coerce_float(row.get("toc_score"))
        left_fit, right_fit = self._fit_scores(row)
        fit_delta = right_fit - left_fit

        if not left_text and right_text:
            return DirectionalResolution("attach_right", 0.92, "edge_right_only", left_fit, right_fit, True)
        if left_text and not right_text:
            return DirectionalResolution("attach_left", 0.92, "edge_left_only", left_fit, right_fit, True)
        if self.dataset._is_closer_like(chunk_text) and left_text:
            return DirectionalResolution("attach_left", 0.96, "closer_like", left_fit, right_fit, True)
        if self.dataset._is_introductory_like(chunk_text) and right_text:
            return DirectionalResolution("attach_right", 0.94, "introductory_like", left_fit, right_fit, True)
        if heading_score >= 0.82 and proposition_score < 0.72 and right_text:
            return DirectionalResolution("attach_right", 0.9, "heading_like", left_fit, right_fit, True)
        if list_item_score >= 0.72 and proposition_score < 0.8 and left_text:
            return DirectionalResolution("attach_left", 0.84, "list_item_parent", left_fit, right_fit, True)
        if chunk_text.lower().startswith("formula:") and left_text and (left_fit - right_fit) >= 0.08:
            return DirectionalResolution("attach_left", 0.84, "formula_left_fit", left_fit, right_fit, True)
        if artifact_score >= 0.84 and left_text and (left_fit - right_fit) >= 0.1:
            return DirectionalResolution("attach_left", 0.82, "artifact_left_fit", left_fit, right_fit, True)
        if artifact_score >= 0.84 and right_text and (right_fit - left_fit) >= 0.1:
            return DirectionalResolution("attach_right", 0.82, "artifact_right_fit", left_fit, right_fit, True)
        if admin_score >= 0.85 and self.dataset._is_closer_like(chunk_text) and left_text:
            return DirectionalResolution("attach_left", 0.9, "admin_closer", left_fit, right_fit, True)
        if toc_score >= 0.78 and proposition_score < 0.7 and abs(fit_delta) >= self.promotion_fit_delta:
            action = "attach_right" if fit_delta > 0 else "attach_left"
            return DirectionalResolution(action, 0.84, "toc_fit_delta", left_fit, right_fit, True)
        if proposition_score < 0.78 and abs(fit_delta) >= self.strong_fit_delta:
            action = "attach_right" if fit_delta > 0 else "attach_left"
            return DirectionalResolution(action, 0.86, "strong_fit_delta", left_fit, right_fit, True)
        if proposition_score < 0.72 and abs(fit_delta) >= self.promotion_fit_delta:
            action = "attach_right" if fit_delta > 0 else "attach_left"
            return DirectionalResolution(action, 0.82, "fit_delta", left_fit, right_fit, True)
        if allow_fallback:
            action = "attach_right" if fit_delta > 0 else "attach_left"
            return DirectionalResolution(action, 0.58, "fit_fallback", left_fit, right_fit, False)
        return DirectionalResolution(None, 0.0, None, left_fit, right_fit, False)

    def promote_review_row(self, row: dict[str, Any]) -> dict[str, Any] | None:
        """Promote a review-stage attach row into clean stage-2 training if direction is strong."""
        action = str(row.get("weak_action") or "")
        if action not in {"attach_left", "attach_right"} or not bool(row.get("weak_needs_review")):
            return None
        resolution = self.resolve(row)
        if resolution.action is None or not resolution.promotable:
            return None
        promoted = dict(row)
        promoted["weak_action"] = resolution.action
        promoted["weak_confidence"] = max(float(row.get("weak_confidence") or 0.0), resolution.confidence)
        promoted["weak_needs_review"] = False
        promoted["weak_label_source"] = "AttachmentDirectionResolver"
        promoted["weak_rationale"] = f"Promoted for stage-2 direction training via {resolution.rule_name or 'resolver'}."
        promoted["direction_training_source"] = "promoted_review"
        promoted["direction_rule_name"] = resolution.rule_name
        promoted["direction_left_fit"] = resolution.left_fit
        promoted["direction_right_fit"] = resolution.right_fit
        return promoted

    def _fit_scores(self, row: dict[str, Any]) -> tuple[float, float]:
        left_similarity = self.dataset._coerce_float(row.get("left_similarity"))
        right_similarity = self.dataset._coerce_float(row.get("right_similarity"))
        left_context_similarity = self.dataset._coerce_float(row.get("left_context_similarity"))
        right_context_similarity = self.dataset._coerce_float(row.get("right_context_similarity"))
        previous_substantive_similarity = self.dataset._coerce_float(row.get("previous_substantive_similarity"))
        next_substantive_similarity = self.dataset._coerce_float(row.get("next_substantive_similarity"))
        previous_substantive_distance = self.dataset._optional_int(row.get("previous_substantive_distance"))
        next_substantive_distance = self.dataset._optional_int(row.get("next_substantive_distance"))
        left_anchor = self.dataset._inverse_distance(previous_substantive_distance)
        right_anchor = self.dataset._inverse_distance(next_substantive_distance)
        left_fit = max(left_similarity, left_context_similarity * 0.85, previous_substantive_similarity) + left_anchor
        right_fit = max(right_similarity, right_context_similarity * 0.85, next_substantive_similarity) + right_anchor
        return left_fit, right_fit


class ChunkActionModel:
    """Two-stage logistic baseline for chunk-action prediction."""

    def __init__(self, *, direction_margin: float = 0.12) -> None:
        """Create an unfitted two-stage chunk-action model."""
        self.stage1_pipeline: Pipeline | None = None
        self.stage2_pipeline: Pipeline | None = None
        self.stage1_feature_names: list[str] = []
        self.stage2_feature_names: list[str] = []
        self.stage1_class_names: list[str] = []
        self.stage2_class_names: list[str] = []
        self.min_confidence: float = 0.78
        self.direction_margin = direction_margin
        self.dataset = ChunkActionDataset()
        self.direction_resolver = AttachmentDirectionResolver(self.dataset)
        self.support_only_labeler = ChunkAuditLabeler()
        self.stage2_training_rows = 0
        self.stage2_promoted_review_rows = 0

    def train(
        self,
        rows: list[dict[str, Any]],
        *,
        min_confidence: float = 0.78,
        holdout_fraction: float = 0.2,
        random_state: int = 42,
    ) -> TrainingResult:
        """Fit the coarse stage-1 model and the attachment-direction stage-2 model."""
        clean_rows = self.dataset.select_clean_rows(rows, min_confidence=min_confidence)
        if len(clean_rows) < 20:
            raise ValueError("Need at least 20 clean labeled rows to train the chunk-action baseline.")

        stage1_matrix, stage1_labels, stage1_feature_names = self.dataset.build_stage1_matrix(clean_rows)
        self.stage1_pipeline, stage1_metrics = self._fit_stage(
            matrix=stage1_matrix,
            labels=stage1_labels,
            feature_names=stage1_feature_names,
            stage_name="stage1",
            holdout_fraction=holdout_fraction,
            random_state=random_state,
        )
        self.stage1_feature_names = stage1_feature_names
        self.stage1_class_names = stage1_metrics.labels

        stage2_rows, promoted_count = self.dataset.select_stage2_rows(
            rows,
            min_confidence=min_confidence,
            resolver=self.direction_resolver,
        )
        self.stage2_training_rows = len(stage2_rows)
        self.stage2_promoted_review_rows = promoted_count
        stage2_metrics: StageMetrics | None = None
        if stage2_rows:
            stage2_matrix, stage2_labels, stage2_feature_names = self.dataset.build_stage2_matrix(stage2_rows)
            if len(set(stage2_labels.tolist())) >= 2:
                self.stage2_pipeline, stage2_metrics = self._fit_stage(
                    matrix=stage2_matrix,
                    labels=stage2_labels,
                    feature_names=stage2_feature_names,
                    stage_name="stage2",
                    holdout_fraction=holdout_fraction,
                    random_state=random_state,
                )
                self.stage2_feature_names = stage2_feature_names
                self.stage2_class_names = stage2_metrics.labels

        self.min_confidence = min_confidence
        return TrainingResult(
            total_clean_rows=len(clean_rows),
            stage2_training_rows=self.stage2_training_rows,
            stage2_promoted_review_rows=self.stage2_promoted_review_rows,
            stage1=stage1_metrics,
            stage2=stage2_metrics,
        )

    def predict_row(self, row: dict[str, Any]) -> dict[str, Any]:
        """Predict a final action with stage-level diagnostics and review flags."""
        if self.stage1_pipeline is None:
            raise ValueError("Model must be trained or loaded before prediction.")

        support_only = self.support_only_labeler.support_only_decision(row)
        if support_only is not None and self.dataset._coerce_float(row.get("duplicate_penalty")) < 0.8:
            probabilities = {
                "standalone": 0.0,
                "duplicate_drop": 0.0,
                "support_only": support_only.confidence,
                "attach_left": 0.0,
                "attach_right": 0.0,
            }
            return {
                "action": support_only.action,
                "confidence": support_only.confidence,
                "probabilities": probabilities,
                "stage1_action": support_only.action,
                "stage1_confidence": support_only.confidence,
                "stage2_action": None,
                "stage2_confidence": None,
                "used_rule": "support_only_role_gate",
                "needs_review": support_only.needs_review,
            }

        stage1 = self._predict_stage(self.stage1_pipeline, self.dataset._row_to_general_features(row))
        stage1_action = str(stage1["action"])
        stage1_probabilities = dict(stage1["probabilities"])

        if stage1_action == "support_only":
            fallback_resolution = self.direction_resolver.resolve(row)
            if fallback_resolution.action is not None:
                attach_confidence = max(float(stage1["confidence"]), fallback_resolution.confidence)
                fallback_stage1 = {
                    "standalone": 0.0,
                    "duplicate_drop": 0.0,
                    "attach": attach_confidence,
                    "support_only": 0.0,
                }
                probabilities = self._combine_probabilities(fallback_stage1, rule_action=fallback_resolution.action)
                return {
                    "action": fallback_resolution.action,
                    "confidence": max(float(probabilities.get(fallback_resolution.action, 0.0)), fallback_resolution.confidence),
                    "probabilities": probabilities,
                    "stage1_action": "attach",
                    "stage1_confidence": attach_confidence,
                    "stage2_action": fallback_resolution.action,
                    "stage2_confidence": fallback_resolution.confidence,
                    "used_rule": "fallback_from_support_only",
                    "needs_review": True,
                }
            fallback_stage1 = {
                "standalone": max(float(stage1["confidence"]), 0.51),
                "duplicate_drop": 0.0,
                "attach": 0.0,
                "support_only": 0.0,
            }
            probabilities = self._combine_probabilities(fallback_stage1)
            return {
                "action": "standalone",
                "confidence": float(probabilities.get("standalone", fallback_stage1["standalone"])),
                "probabilities": probabilities,
                "stage1_action": "standalone",
                "stage1_confidence": fallback_stage1["standalone"],
                "stage2_action": None,
                "stage2_confidence": None,
                "used_rule": "fallback_from_support_only",
                "needs_review": True,
            }

        if stage1_action != "attach":
            probabilities = self._combine_probabilities(stage1_probabilities)
            return {
                "action": stage1_action,
                "confidence": float(probabilities.get(stage1_action, stage1["confidence"])),
                "probabilities": probabilities,
                "stage1_action": stage1_action,
                "stage1_confidence": stage1["confidence"],
                "stage2_action": None,
                "stage2_confidence": None,
                "used_rule": None,
                "needs_review": bool(stage1["confidence"] < 0.62),
            }

        resolution = self.direction_resolver.resolve(row)
        if resolution.action is not None:
            probabilities = self._combine_probabilities(stage1_probabilities, rule_action=resolution.action)
            return {
                "action": resolution.action,
                "confidence": max(float(probabilities.get(resolution.action, 0.0)), resolution.confidence),
                "probabilities": probabilities,
                "stage1_action": stage1_action,
                "stage1_confidence": stage1["confidence"],
                "stage2_action": resolution.action,
                "stage2_confidence": resolution.confidence,
                "used_rule": resolution.rule_name,
                "needs_review": False,
            }

        if self.stage2_pipeline is None:
            fallback = self.direction_resolver.resolve(row, allow_fallback=True)
            probabilities = self._combine_probabilities(stage1_probabilities, rule_action=fallback.action)
            return {
                "action": fallback.action,
                "confidence": float(probabilities.get(fallback.action, 0.0)),
                "probabilities": probabilities,
                "stage1_action": stage1_action,
                "stage1_confidence": stage1["confidence"],
                "stage2_action": fallback.action,
                "stage2_confidence": fallback.confidence,
                "used_rule": fallback.rule_name,
                "needs_review": True,
            }

        stage2 = self._predict_stage(self.stage2_pipeline, self.dataset._row_to_directional_features(row))
        stage2_action = str(stage2["action"])
        stage2_probabilities = stage2["probabilities"]
        probabilities = self._combine_probabilities(stage1_probabilities, stage2_probabilities=stage2_probabilities)
        direction_gap = abs(
            float(stage2_probabilities.get("attach_right", 0.0)) - float(stage2_probabilities.get("attach_left", 0.0))
        )
        return {
            "action": stage2_action,
            "confidence": float(probabilities.get(stage2_action, stage2["confidence"])),
            "probabilities": probabilities,
            "stage1_action": stage1_action,
            "stage1_confidence": stage1["confidence"],
            "stage2_action": stage2_action,
            "stage2_confidence": stage2["confidence"],
            "used_rule": None,
            "needs_review": bool(stage1["confidence"] < 0.62 or stage2["confidence"] < 0.58 or direction_gap < self.direction_margin),
        }

    def save(self, path: str | Path) -> Path:
        """Persist the trained two-stage model and metadata to disk."""
        if self.stage1_pipeline is None:
            raise ValueError("Model must be trained before it can be saved.")
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "stage1_pipeline": self.stage1_pipeline,
            "stage2_pipeline": self.stage2_pipeline,
            "stage1_feature_names": self.stage1_feature_names,
            "stage2_feature_names": self.stage2_feature_names,
            "stage1_class_names": self.stage1_class_names,
            "stage2_class_names": self.stage2_class_names,
            "min_confidence": self.min_confidence,
            "direction_margin": self.direction_margin,
            "stage2_training_rows": self.stage2_training_rows,
            "stage2_promoted_review_rows": self.stage2_promoted_review_rows,
        }
        with target.open("wb") as handle:
            pickle.dump(payload, handle)
        return target

    @classmethod
    def load(cls, path: str | Path) -> "ChunkActionModel":
        """Load a persisted two-stage chunk-action model from disk."""
        with Path(path).open("rb") as handle:
            payload = pickle.load(handle)
        model = cls(direction_margin=float(payload.get("direction_margin", 0.12)))
        model.stage1_pipeline = payload["stage1_pipeline"]
        model.stage2_pipeline = payload.get("stage2_pipeline")
        model.stage1_feature_names = list(payload.get("stage1_feature_names", []))
        model.stage2_feature_names = list(payload.get("stage2_feature_names", []))
        model.stage1_class_names = list(payload.get("stage1_class_names", []))
        model.stage2_class_names = list(payload.get("stage2_class_names", []))
        model.min_confidence = float(payload.get("min_confidence", 0.78))
        model.stage2_training_rows = int(payload.get("stage2_training_rows", 0))
        model.stage2_promoted_review_rows = int(payload.get("stage2_promoted_review_rows", 0))
        return model

    def _fit_stage(
        self,
        *,
        matrix: np.ndarray,
        labels: np.ndarray,
        feature_names: list[str],
        stage_name: str,
        holdout_fraction: float,
        random_state: int,
    ) -> tuple[Pipeline, StageMetrics]:
        if len(set(labels.tolist())) < 2:
            raise ValueError(f"Need at least two label classes to train {stage_name}.")

        train_x, test_x, train_y, test_y = train_test_split(
            matrix,
            labels,
            test_size=holdout_fraction,
            stratify=labels,
            random_state=random_state,
        )
        pipeline = Pipeline(
            steps=[
                ("scaler", StandardScaler()),
                (
                    "classifier",
                    LogisticRegression(
                        max_iter=4000,
                        class_weight="balanced",
                        random_state=random_state,
                    ),
                ),
            ]
        )
        pipeline.fit(train_x, train_y)
        predictions = pipeline.predict(test_x)
        report = classification_report(test_y, predictions, output_dict=True, zero_division=0)
        metrics = StageMetrics(
            name=stage_name,
            train_rows=len(train_x),
            test_rows=len(test_x),
            labels=sorted({str(value) for value in labels.tolist()}),
            accuracy=float(accuracy_score(test_y, predictions)),
            macro_f1=float(f1_score(test_y, predictions, average="macro", zero_division=0)),
            weighted_f1=float(f1_score(test_y, predictions, average="weighted", zero_division=0)),
            classification_report=report,
        )
        return pipeline, metrics

    def _predict_stage(self, pipeline: Pipeline, features: list[float]) -> dict[str, Any]:
        feature_array = np.array([features], dtype=float)
        probabilities = pipeline.predict_proba(feature_array)[0]
        classes = [str(value) for value in pipeline.named_steps["classifier"].classes_]
        best_index = int(np.argmax(probabilities))
        return {
            "action": classes[best_index],
            "confidence": float(probabilities[best_index]),
            "probabilities": {label: float(probability) for label, probability in zip(classes, probabilities)},
        }

    def _combine_probabilities(
        self,
        stage1_probabilities: dict[str, float],
        stage2_probabilities: dict[str, float] | None = None,
        rule_action: str | None = None,
    ) -> dict[str, float]:
        attach_mass = float(stage1_probabilities.get("attach", 0.0))
        probabilities = {
            "standalone": float(stage1_probabilities.get("standalone", 0.0)),
            "duplicate_drop": float(stage1_probabilities.get("duplicate_drop", 0.0)),
            "support_only": float(stage1_probabilities.get("support_only", 0.0)),
            "attach_left": 0.0,
            "attach_right": 0.0,
        }
        if stage2_probabilities is not None:
            probabilities["attach_left"] = attach_mass * float(stage2_probabilities.get("attach_left", 0.0))
            probabilities["attach_right"] = attach_mass * float(stage2_probabilities.get("attach_right", 0.0))
        elif rule_action == "attach_left":
            probabilities["attach_left"] = attach_mass
        elif rule_action == "attach_right":
            probabilities["attach_right"] = attach_mass
        else:
            probabilities["attach_right"] = attach_mass
        return probabilities
