from __future__ import annotations

import json
import re

from contextus.llm import LLMClient

from .base import ElementHandler, HandlerOutput


class FormulaHandler(ElementHandler):
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client

    def handle(self, page, bbox, scale_x: float, scale_y: float) -> HandlerOutput:
        prepared = self.prepare_inputs(page, bbox, scale_x, scale_y)
        return self.handle_prepared(**prepared)

    def prepare_inputs(self, page, bbox, scale_x: float, scale_y: float) -> dict[str, object]:
        raw_text = self.extract_text(page, bbox, scale_x, scale_y)
        image_bytes = self.render_crop(page, bbox, scale_x, scale_y)
        return {
            "raw_text": raw_text,
            "image_bytes": image_bytes,
        }

    def handle_prepared(self, *, raw_text: str, image_bytes: bytes) -> HandlerOutput:
        llm_output = self.build_llm_output(raw_text=raw_text, image_bytes=image_bytes)
        if llm_output is not None:
            return llm_output
        return self.build_fallback_output(raw_text=raw_text, image_bytes=image_bytes)

    def build_llm_output(self, *, raw_text: str, image_bytes: bytes) -> HandlerOutput | None:
        if self.llm_client is None:
            return None
        llm_result = self._transcribe_with_llm(image_bytes, raw_text=raw_text)
        if llm_result is None:
            return None
        return HandlerOutput(
            content=llm_result["content"],
            raw_text=str(llm_result["raw_text"]),
            source="openai_formula_vision",
            metadata={
                "needs_review": bool(llm_result["needs_review"]),
                "transcription_method": type(self.llm_client).__name__,
                "extraction_rationale": llm_result["rationale"],
            },
            asset_bytes=image_bytes,
            asset_extension=".png",
        )

    def build_fallback_output(self, *, raw_text: str, image_bytes: bytes) -> HandlerOutput:
        latex = self.simple_text_to_latex(raw_text) or (raw_text if raw_text else None)
        content = self.build_non_text_payload(
            format="formula",
            figure_type="formula",
            raw_text=raw_text,
            structured_content={
                "latex": latex,
                "mathml": None,
            },
            literal_description=None,
            source_confidence=0.25 if latex else 0.0,
        )
        return HandlerOutput(
            content=content,
            raw_text=raw_text,
            source="pymupdf_formula_text",
            metadata={"needs_review": latex is None},
            asset_bytes=image_bytes,
            asset_extension=".png",
        )

    def simple_text_to_latex(self, text: str) -> str | None:
        if not text:
            return None
        value = str(text)
        strong_signals = (
            "=",
            "<=",
            ">=",
            "!=",
            "~",
            "^",
            "/",
            "sqrt",
            "sum",
            "int",
            "\\u221a",
            "\\u2211",
            "\\u222b",
            "\\u2264",
            "\\u2265",
            "\\u2248",
            "\\u2260",
        )
        expanded_value = value.encode('unicode_escape').decode('ascii')
        if not any(token in value or token in expanded_value for token in strong_signals):
            return None
        replacements = {
            "\u2212": "-",
            "\u2013": "-",
            "\u00d7": "*",
            "\u00b7": "\\cdot ",
            "\u00f7": "/",
            "\u2264": "\\leq ",
            "\u2265": "\\geq ",
            "\u2260": "\\neq ",
            "\u2248": "\\approx ",
            "\u2192": "\\to ",
            "\u2190": "\\leftarrow ",
            "\u221e": "\\infty ",
        }
        for source, target in replacements.items():
            value = value.replace(source, target)
        return value.strip()

    def _transcribe_with_llm(self, image_bytes: bytes, *, raw_text: str) -> dict[str, object] | None:
        try:
            response = self.llm_client.complete_with_image(
                system=(
                    "You transcribe a single mathematical expression crop into faithful LaTeX. "
                    "Return strict JSON only using this schema: "
                    '{"format":"formula","figure_type":"formula","raw_text":"...","structured_content":{"latex":"...","mathml":null},"literal_description":null,"source_confidence":0.0,"needs_review":false,"rationale":"..."} '
                    "Use standard LaTeX without surrounding dollar signs. "
                    "If the crop includes surrounding text that is visually part of the displayed expression, preserve it faithfully. "
                    "Set needs_review to true when any symbol, subscript, superscript, prime, delimiter, or layout detail is uncertain."
                ),
                user="Transcribe this formula image exactly and return JSON only.",
                image_bytes=image_bytes,
                mime_type="image/png",
                temperature=0.0,
            ).content
        except NotImplementedError:
            return None
        except Exception:
            return None

        payload = self._parse_json_payload(response)
        if payload is None:
            text = response.strip()
            latex = text or None
            content = self.build_non_text_payload(
                format="formula",
                figure_type="formula",
                raw_text=raw_text,
                structured_content={"latex": latex, "mathml": None},
                literal_description=None,
                source_confidence=0.0,
            )
            return {
                "content": content,
                "raw_text": raw_text,
                "needs_review": True,
                "rationale": "unparsed_llm_output",
            }
        structured = payload.get("structured_content")
        if not isinstance(structured, dict):
            structured = {}
        latex = str(structured.get("latex") or payload.get("latex") or "").strip() or None
        model_raw_text = self.normalize_text(payload.get("raw_text")) or raw_text
        content = self.build_non_text_payload(
            format="formula",
            figure_type="formula",
            raw_text=model_raw_text,
            structured_content={
                "latex": latex,
                "mathml": structured.get("mathml"),
            },
            literal_description=None,
            source_confidence=self._coerce_confidence(payload.get("source_confidence")),
        )
        return {
            "content": content,
            "raw_text": model_raw_text,
            "needs_review": bool(payload.get("needs_review", latex is None)),
            "rationale": str(payload.get("rationale") or ""),
        }

    def _parse_json_payload(self, text: str) -> dict[str, object] | None:
        payload = self.parse_json_payload(text)
        if isinstance(payload, dict):
            return payload

        candidate = (text or "").strip()
        latex_match = re.search(r'"latex"\s*:\s*"([^"]*)"', candidate)
        needs_review_match = re.search(r'"needs_review"\s*:\s*(true|false)', candidate, re.IGNORECASE)
        rationale_match = re.search(r'"rationale"\s*:\s*"([^"]*)"', candidate)
        if latex_match is None:
            return None
        return {
            "latex": latex_match.group(1),
            "needs_review": (needs_review_match.group(1).lower() == "true") if needs_review_match else True,
            "rationale": rationale_match.group(1) if rationale_match else "",
        }
