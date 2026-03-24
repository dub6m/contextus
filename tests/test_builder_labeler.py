from pathlib import Path
import json

from contextus.builder.labeler import ChunkAuditLabeler, LLMChunkAuditLabeler
from contextus.llm import LLMResponse


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)

    def complete(self, system: str, user: str, temperature: float = 0.0):
        return LLMResponse(content=self.responses.pop(0))


class FlakyLLM:
    def __init__(self, responses):
        self.responses = list(responses)

    def complete(self, system: str, user: str, temperature: float = 0.0):
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return LLMResponse(content=response)


class FactoryLLM:
    def __init__(self, responses_by_instance):
        self._responses_by_instance = [list(item) for item in responses_by_instance]

    def __call__(self):
        return FakeLLM(self._responses_by_instance.pop(0))


def make_row(**kwargs):
    row = {
        "document_id": "doc-1",
        "source_name": "example.pdf",
        "source_path": "C:/example.pdf",
        "chunk_index": 0,
        "chunk_text": "Proof",
        "left_chunk_text": "Claim 5.1",
        "right_chunk_text": "If the pair is closer than delta then both points lie in the strip.",
        "left_context_text": "Closest pair in the plane",
        "right_context_text": "If the pair is closer than delta then both points lie in the strip. Therefore ...",
        "previous_substantive_text": "Claim 5.1 If the pair is closer than delta then both points lie in the strip.",
        "next_substantive_text": "If the pair is closer than delta then both points lie in the strip.",
        "previous_substantive_distance": 1,
        "next_substantive_distance": 1,
        "chunk_size": 1,
        "token_count": 1,
        "content_token_count": 1,
        "sentence_count": 1,
        "element_ids": ["e-1"],
        "element_types": ["text"],
        "page_numbers": [1],
        "type_histogram": {"text": 1},
        "contains_title": False,
        "contains_non_text": False,
        "singleton_chunk": True,
        "left_similarity": 0.0,
        "right_similarity": 0.4,
        "left_context_similarity": 0.0,
        "right_context_similarity": 0.35,
        "previous_substantive_similarity": 0.0,
        "next_substantive_similarity": 0.18,
        "max_previous_similarity": 0.0,
        "token_substance": 0.05,
        "lexical_density": 1.0,
        "type_richness": 0.33,
        "left_independence": 1.0,
        "right_independence": 0.6,
        "novelty": 1.0,
        "rhetorical_penalty": 0.9,
        "duplicate_penalty": 0.0,
        "heading_score": 0.9,
        "proposition_score": 0.2,
        "admin_score": 0.0,
        "toc_score": 0.0,
        "artifact_score": 0.0,
        "list_item_score": 0.0,
        "docling_section_header_score": 0.0,
        "docling_apparatus_score": 0.0,
        "docling_repeated_header_score": 0.0,
        "docling_caption_score": 0.0,
        "docling_footnote_score": 0.0,
        "docling_table_score": 0.0,
        "docling_picture_score": 0.0,
        "docling_labels": [],
        "docling_matched_texts": [],
        "heuristic_viability": 0.12,
        "rhetorical_markers": ["proof"],
        "suggested_action": "attach_right",
        "gold_action": None,
        "notes": "",
    }
    row.update(kwargs)
    return row


def test_policy_labels_bare_proof_as_support_only():
    labeler = ChunkAuditLabeler()

    labeled = labeler.label_row(make_row())

    assert labeled["weak_action"] == "support_only"
    assert labeled["weak_needs_review"] is False
    assert "structural evidence" in labeled["weak_rationale"].lower()


def test_policy_labels_substantive_title_chunk_as_standalone():
    labeler = ChunkAuditLabeler()

    labeled = labeler.label_row(
        make_row(
            chunk_text="Biocultural Model\nThe biocultural model explains how social and biological forces interact to shape health outcomes.",
            left_chunk_text="",
            right_chunk_text="Case study examples follow.",
            left_context_text="",
            right_context_text="Case study examples follow. More evidence follows.",
            next_substantive_text="Case study examples follow.",
            previous_substantive_text="",
            previous_substantive_distance=None,
            next_substantive_distance=1,
            chunk_size=3,
            token_count=18,
            content_token_count=14,
            sentence_count=2,
            element_ids=["e-1", "e-2", "e-3"],
            contains_title=True,
            contains_non_text=True,
            singleton_chunk=False,
            type_histogram={"title": 1, "text": 1, "figure": 1},
            element_types=["title", "text", "figure"],
            type_richness=1.0,
            rhetorical_penalty=0.0,
            heading_score=0.38,
            proposition_score=0.9,
            artifact_score=0.4,
            heuristic_viability=0.74,
            rhetorical_markers=[],
            suggested_action="standalone",
        )
    )

    assert labeled["weak_action"] == "standalone"
    assert labeled["weak_needs_review"] is False
    assert "self-contained" in labeled["weak_rationale"].lower()


def test_policy_labels_closing_language_as_support_only():
    labeler = ChunkAuditLabeler()

    labeled = labeler.label_row(
        make_row(
            chunk_text="Respectfully submitted,\nCounsel for the applicant",
            left_chunk_text="Final order and signature block",
            right_chunk_text="",
            token_count=5,
            content_token_count=3,
            sentence_count=1,
            rhetorical_markers=[],
            rhetorical_penalty=0.0,
            heading_score=0.1,
            proposition_score=0.2,
            heuristic_viability=0.2,
            suggested_action="attach_left",
        )
    )

    assert labeled["weak_action"] == "support_only"
    assert labeled["weak_needs_review"] is False


def test_policy_labels_duplicate_chunk_as_duplicate_drop():
    labeler = ChunkAuditLabeler()

    labeled = labeler.label_row(
        make_row(
            chunk_text="Closest Pair of Points Problem",
            token_count=5,
            content_token_count=4,
            rhetorical_markers=[],
            rhetorical_penalty=0.0,
            duplicate_penalty=0.96,
            heading_score=0.8,
            proposition_score=0.3,
            heuristic_viability=0.18,
            suggested_action="duplicate_drop",
        )
    )

    assert labeled["weak_action"] == "duplicate_drop"
    assert labeled["weak_needs_review"] is False


def test_policy_labels_admin_chunk_as_support_only():
    labeler = ChunkAuditLabeler()

    labeled = labeler.label_row(
        make_row(
            chunk_text="Funding and disclosure information for the publication.",
            left_chunk_text="Main results discussion",
            right_chunk_text="Acknowledgments",
            token_count=6,
            content_token_count=5,
            sentence_count=1,
            rhetorical_markers=[],
            rhetorical_penalty=0.0,
            heading_score=0.18,
            proposition_score=0.2,
            admin_score=0.92,
            heuristic_viability=0.2,
            suggested_action="support_only",
        )
    )

    assert labeled["weak_action"] == "support_only"
    assert "publication-record" in labeled["weak_rationale"].lower()


def test_policy_labels_numbered_heading_as_support_only():
    labeler = ChunkAuditLabeler()

    labeled = labeler.label_row(
        make_row(
            chunk_text="1.1 Basic arithmetic",
            left_chunk_text="Algorithms with numbers",
            right_chunk_text="We now study addition and multiplication in detail.",
            left_context_text="Algorithms with numbers",
            right_context_text="We now study addition and multiplication in detail. The section introduces standard operations.",
            previous_substantive_text="Algorithms with numbers",
            next_substantive_text="We now study addition and multiplication in detail.",
            token_count=4,
            content_token_count=2,
            heading_score=0.9,
            proposition_score=0.35,
            next_substantive_distance=1,
            previous_substantive_distance=1,
            right_similarity=0.08,
            right_context_similarity=0.12,
            suggested_action="attach_right",
            rhetorical_markers=[],
            rhetorical_penalty=0.0,
        )
    )

    assert labeled["weak_action"] == "support_only"


def test_policy_labels_shallow_list_item_as_attach_left():
    labeler = ChunkAuditLabeler()

    labeled = labeler.label_row(
        make_row(
            chunk_text="2. Make life better for Manitobans.",
            left_chunk_text="Strategic priorities",
            right_chunk_text="3. Deliver on commitments in a fiscally responsible way.",
            left_context_text="Strategic priorities\n1. Protect communities.",
            right_context_text="3. Deliver on commitments in a fiscally responsible way.",
            previous_substantive_text="Strategic priorities",
            next_substantive_text="3. Deliver on commitments in a fiscally responsible way.",
            token_count=6,
            content_token_count=4,
            sentence_count=1,
            list_item_score=0.82,
            proposition_score=0.66,
            heading_score=0.24,
            previous_substantive_distance=1,
            next_substantive_distance=1,
            suggested_action="attach_left",
            rhetorical_markers=[],
            rhetorical_penalty=0.0,
        )
    )

    assert labeled["weak_action"] == "attach_left"
    assert labeled["weak_needs_review"] is False


def test_policy_keeps_substantive_table_chunk_standalone():
    labeler = ChunkAuditLabeler()

    labeled = labeler.label_row(
        make_row(
            chunk_text="Table with columns Stage and Outcome. First rows show: Planning=Budget alignment; Delivery=Bridge rehabilitation.",
            left_chunk_text="Capital program overview",
            right_chunk_text="The capital program continues next year.",
            contains_non_text=True,
            element_types=["table"],
            token_count=16,
            content_token_count=12,
            sentence_count=2,
            artifact_score=0.72,
            proposition_score=0.84,
            heading_score=0.28,
            heuristic_viability=0.72,
            rhetorical_markers=[],
            rhetorical_penalty=0.0,
            suggested_action="standalone",
        )
    )

    assert labeled["weak_action"] == "standalone"


def test_policy_label_file_respects_offset_and_limit(tmp_path):
    input_path = tmp_path / "rows.jsonl"
    rows = [
        make_row(chunk_text="Proof"),
        make_row(
            chunk_text="Closest pair definition\nThe closest-pair problem asks for the minimum Euclidean distance between two points.",
            rhetorical_markers=[],
            rhetorical_penalty=0.0,
            token_count=16,
            content_token_count=12,
            sentence_count=2,
            chunk_size=2,
            singleton_chunk=False,
            contains_title=True,
            heading_score=0.32,
            proposition_score=0.88,
            heuristic_viability=0.72,
            suggested_action="standalone",
        ),
        make_row(
            chunk_text="Repeated definition",
            rhetorical_markers=[],
            rhetorical_penalty=0.0,
            duplicate_penalty=0.9,
            heading_score=0.75,
            proposition_score=0.28,
            heuristic_viability=0.1,
            suggested_action="duplicate_drop",
        ),
    ]
    input_path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    output_path = tmp_path / "labeled.jsonl"

    labeler = ChunkAuditLabeler()

    saved_path = labeler.label_file(input_path=input_path, output_path=output_path, limit=1, offset=1)

    lines = saved_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["chunk_text"].startswith("Closest pair definition")
    assert payload["weak_action"] == "standalone"


def test_llm_labeler_parses_valid_json_response():
    labeler = LLMChunkAuditLabeler(
        FakeLLM([
            '{"action":"attach_right","confidence":0.92,"needs_review":false,"rationale":"Proof marker introduces the following content."}'
        ])
    )

    labeled = labeler.label_row(make_row())

    assert labeled["weak_action"] == "support_only"
    assert labeled["weak_confidence"] == 0.97
    assert labeled["weak_needs_review"] is False


def test_llm_labeler_falls_back_to_heuristic_on_bad_responses():
    labeler = LLMChunkAuditLabeler(FakeLLM(["not json", "still not json"]))

    labeled = labeler.label_row(make_row())

    assert labeled["weak_action"] == "support_only"
    assert labeled["weak_confidence"] == 0.97
    assert labeled["weak_needs_review"] is False
    assert "structural evidence" in labeled["weak_rationale"]


def test_llm_labeler_retries_retryable_errors_then_succeeds(monkeypatch):
    monkeypatch.setattr("contextus.builder.labeler.time.sleep", lambda _: None)
    labeler = LLMChunkAuditLabeler(
        FlakyLLM([
            RuntimeError("queue_exceeded"),
            '{"action":"attach_right","confidence":0.7,"needs_review":true,"rationale":"Retry succeeded."}',
        ])
    )

    labeled = labeler.label_row(make_row())

    assert labeled["weak_action"] == "support_only"
    assert labeled["weak_confidence"] == 0.97
    assert labeled["weak_needs_review"] is False


def test_llm_parallel_label_rows_preserves_order_and_counts_calls():
    factory = FactoryLLM([
        ['{"action":"attach_right","confidence":0.8,"needs_review":false,"rationale":"Heading."}'],
        ['{"action":"standalone","confidence":0.9,"needs_review":false,"rationale":"Self-contained."}'],
    ])
    labeler = LLMChunkAuditLabeler(FakeLLM([]), llm_client_factory=factory)

    rows = [
        make_row(chunk_text="Proof", suggested_action="attach_right"),
        make_row(
            chunk_text="Closest pair definition\nThe closest-pair problem asks for the minimum Euclidean distance between two points.",
            suggested_action="standalone",
            rhetorical_markers=[],
            rhetorical_penalty=0.0,
            token_count=16,
            content_token_count=12,
            sentence_count=2,
            chunk_size=2,
            singleton_chunk=False,
            contains_title=True,
            heading_score=0.32,
            proposition_score=0.88,
            heuristic_viability=0.72,
        ),
    ]
    labeled = labeler.label_rows(rows, workers=2)

    assert [row["chunk_text"] for row in labeled] == ["Proof", "Closest pair definition\nThe closest-pair problem asks for the minimum Euclidean distance between two points."]
    assert [row["weak_action"] for row in labeled] == ["support_only", "standalone"]
    assert labeler.llm_calls == 2


def test_policy_labels_publication_metadata_as_support_only():
    labeler = ChunkAuditLabeler()

    labeled = labeler.label_row(
        make_row(
            chunk_text="RECEIVED 02 January 2025 ACCEPTED 07 April 2025 PUBLISHED 15 May 2025",
            left_chunk_text="Climate science for 2050",
            right_chunk_text="Abstract",
            token_count=11,
            content_token_count=8,
            sentence_count=1,
            rhetorical_markers=[],
            rhetorical_penalty=0.0,
            heading_score=0.22,
            proposition_score=0.18,
            admin_score=0.86,
            heuristic_viability=0.14,
            suggested_action="support_only",
        )
    )

    assert labeled["weak_action"] == "support_only"
    assert "publication-record" in labeled["weak_rationale"].lower()


def test_policy_labels_author_list_as_support_only():
    labeler = ChunkAuditLabeler()

    labeled = labeler.label_row(
        make_row(
            chunk_text="Guy Brasseur 1,2, Detlef Stammer 3, Pierre Friedlingstein 4,5, Gabriele Hegerl 6, Tiffany Shaw 7, Kevin Trenberth 2,8, Jadwiga Richter 2",
            left_chunk_text="Climate science for 2050",
            right_chunk_text="Abstract",
            token_count=20,
            content_token_count=14,
            sentence_count=1,
            rhetorical_markers=[],
            rhetorical_penalty=0.0,
            heading_score=0.18,
            proposition_score=0.2,
            admin_score=0.62,
            heuristic_viability=0.18,
            suggested_action="support_only",
        )
    )

    assert labeled["weak_action"] == "support_only"
    assert "publication-record" in labeled["weak_rationale"].lower()


def test_policy_uses_docling_apparatus_signal_for_support_only():
    labeler = ChunkAuditLabeler()

    labeled = labeler.label_row(
        make_row(
            chunk_text="Editorial record for publication",
            left_chunk_text="Climate science for 2050",
            right_chunk_text="© 2025 Brasseur et al.",
            token_count=4,
            content_token_count=3,
            sentence_count=1,
            rhetorical_markers=[],
            rhetorical_penalty=0.0,
            heading_score=0.82,
            proposition_score=0.2,
            admin_score=0.24,
            docling_section_header_score=0.88,
            docling_apparatus_score=0.93,
            heuristic_viability=0.05,
            suggested_action="support_only",
        )
    )

    assert labeled["weak_action"] == "support_only"
    assert "docling" in labeled["weak_rationale"].lower()


def test_policy_labels_abstract_as_support_only():
    labeler = ChunkAuditLabeler()

    labeled = labeler.label_row(
        make_row(
            chunk_text="Abstract",
            left_chunk_text="Author list",
            right_chunk_text="This paper presents a compact benchmark for boundary quality.",
            token_count=1,
            content_token_count=1,
            sentence_count=1,
            chunk_size=1,
            rhetorical_markers=[],
            rhetorical_penalty=0.0,
            heading_score=0.7,
            proposition_score=0.0,
            heuristic_viability=0.2,
            suggested_action="attach_right",
        )
    )

    assert labeled["weak_action"] == "support_only"
    assert "front-matter" in labeled["weak_rationale"].lower()


def test_policy_labels_chapter_heading_as_support_only():
    labeler = ChunkAuditLabeler()

    labeled = labeler.label_row(
        make_row(
            chunk_text="Chapter 0",
            left_chunk_text="Preface text",
            right_chunk_text="Prologue",
            token_count=2,
            content_token_count=1,
            sentence_count=1,
            chunk_size=1,
            rhetorical_markers=[],
            rhetorical_penalty=0.0,
            heading_score=0.98,
            proposition_score=0.0,
            heuristic_viability=0.1,
            suggested_action="attach_left",
        )
    )

    assert labeled["weak_action"] == "support_only"
    assert "front-matter" in labeled["weak_rationale"].lower()
