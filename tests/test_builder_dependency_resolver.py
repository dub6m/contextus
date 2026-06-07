import pytest

from contextus.builder.dependency_resolver import (
    CandidateSupport,
    DocumentTermIndex,
    normalize_term_text,
    FactFrame,
    FrameConstraint,
    FrameSlot,
    Need,
    ResolutionTraceStep,
    SourceRef,
)


def test_frame_slot_separates_fill_and_grounding_state():
    slot = FrameSlot(
        name="object",
        value="candidate points",
        term_id="term:candidate_point",
        fill_state="filled",
        grounding_state="unsupported",
        source_text="candidate points",
        char_start=12,
        char_end=28,
    )

    assert slot.fill_state == "filled"
    assert slot.grounding_state == "unsupported"
    assert slot.requires_support is True


def test_frame_slot_requires_support_for_missing_and_ambiguous_fill():
    missing_slot = FrameSlot(name="object", fill_state="missing")
    ambiguous_slot = FrameSlot(name="object", fill_state="ambiguous")

    assert missing_slot.requires_support is True
    assert ambiguous_slot.requires_support is True


def test_frame_slot_does_not_require_support_by_default():
    slot = FrameSlot(name="object")

    assert slot.requires_support is False


def test_frame_slot_converts_evidence_refs_to_tuple():
    slot = FrameSlot(name="object", evidence_refs=["e1"])

    assert slot.evidence_refs == ("e1",)


def test_frame_constraint_requires_support_until_grounded():
    unsupported_constraint = FrameConstraint(target_slot="object", operator="=", value="candidate points")
    grounded_constraint = FrameConstraint(
        target_slot="object",
        operator="=",
        value="candidate points",
        grounding_state="grounded",
    )

    assert unsupported_constraint.requires_support is True
    assert grounded_constraint.requires_support is False


def test_frame_constraint_converts_evidence_refs_to_tuple():
    constraint = FrameConstraint(target_slot="object", operator="=", value="candidate points", evidence_refs=["e1"])

    assert constraint.evidence_refs == ("e1",)


def test_need_points_to_exact_frame_part():
    need = Need(
        need_id="need:frame:1:slots.object",
        frame_id="frame:1",
        target_path="slots.object",
        value="candidate points",
        reason="filled_but_unsupported",
    )

    assert need.status == "open"
    assert need.target_path == "slots.object"


def test_candidate_support_records_matched_and_rejected_parts():
    support = CandidateSupport(
        need_id="need:1",
        candidate_frame_ids=["frame:source:1"],
        matched_parts=["target term"],
        rejected_parts=["operator mismatch"],
        status="candidate",
        reason="same target term but incompatible operator",
    )

    assert support.status == "candidate"
    assert support.matched_parts == ("target term",)
    assert support.rejected_parts == ("operator mismatch",)


def test_candidate_support_converts_list_inputs_to_tuples():
    support = CandidateSupport(
        need_id="need:1",
        candidate_frame_ids=["frame:source:1"],
        matched_parts=["target term"],
        rejected_parts=["operator mismatch"],
    )

    assert support.candidate_frame_ids == ("frame:source:1",)
    assert support.matched_parts == ("target term",)
    assert support.rejected_parts == ("operator mismatch",)


def test_fact_frame_keeps_source_reference():
    frame = FactFrame(
        frame_id="frame:e1:0",
        source=SourceRef(element_id="e1", text="The strip contains candidate points."),
        predicate="contains",
        slots={
            "subject": FrameSlot(name="subject", value="strip", term_id="term:strip"),
            "object": FrameSlot(name="object", value="candidate points", term_id="term:candidate_point"),
        },
    )

    assert frame.source.element_id == "e1"
    assert frame.slots["subject"].value == "strip"


def test_fact_frame_converts_constraints_and_links_to_tuples():
    constraint = FrameConstraint(target_slot="object", operator="=", value="candidate points")
    frame = FactFrame(
        frame_id="frame:e1:0",
        source=SourceRef(element_id="e1"),
        predicate="contains",
        constraints=[constraint],
        links=["frame:other"],
    )

    assert frame.constraints == (constraint,)
    assert frame.links == ("frame:other",)


def test_fact_frame_slots_are_not_externally_mutable():
    frame = FactFrame(
        frame_id="frame:e1:0",
        source=SourceRef(element_id="e1"),
        predicate="contains",
        slots={"subject": FrameSlot(name="subject", value="strip", term_id="term:strip")},
    )

    with pytest.raises(TypeError):
        frame.slots["x"] = FrameSlot(name="x")


def test_fact_frame_slots_are_copied_before_wrapping():
    slots = {"subject": FrameSlot(name="subject", value="strip", term_id="term:strip")}
    frame = FactFrame(
        frame_id="frame:e1:0",
        source=SourceRef(element_id="e1"),
        predicate="contains",
        slots=slots,
    )

    slots["subject"] = FrameSlot(name="subject", value="changed", term_id="term:changed")
    slots["object"] = FrameSlot(name="object")

    assert frame.slots["subject"].value == "strip"
    assert "object" not in frame.slots


def test_trace_step_records_action_reason_and_frames():
    step = ResolutionTraceStep(
        action="need_resolved",
        need_id="need:1",
        frame_ids=["frame:e2:0"],
        reason="candidate frame covers the unsupported quantity",
    )

    assert step.action == "need_resolved"
    assert step.reason == "candidate frame covers the unsupported quantity"
    assert step.frame_ids == ("frame:e2:0",)


def test_trace_step_converts_list_inputs_to_tuples():
    step = ResolutionTraceStep(action="need_resolved", frame_ids=["frame:e2:0"])

    assert step.frame_ids == ("frame:e2:0",)


def test_normalize_term_text_is_conservative():
    assert normalize_term_text("The strip.") == "strip"
    assert normalize_term_text("candidate points") == "candidate point"
    assert normalize_term_text("median line") == "median line"
    assert normalize_term_text("line") == "line"
    assert normalize_term_text("Q_x") == "q_x"


def test_normalize_term_text_preserves_singular_s_endings():
    assert normalize_term_text("axis") == "axis"
    assert normalize_term_text("bias") == "bias"
    assert normalize_term_text("analysis") == "analysis"
    assert normalize_term_text("status") == "status"
    assert normalize_term_text("points") == "point"


def test_normalize_term_text_does_not_corrupt_common_s_endings():
    assert normalize_term_text("lines") == "line"
    assert normalize_term_text("sides") == "side"
    assert normalize_term_text("series") == "series"
    assert normalize_term_text("axis") == "axis"


def test_document_term_index_keeps_specific_terms_separate():
    index = DocumentTermIndex.from_texts(
        [
            ("e1", "The median line splits the points."),
            ("e2", "The line is drawn vertically."),
        ]
    )

    assert "term:median_line" in index.terms
    assert "term:line" in index.terms
    assert index.terms["term:median_line"].canonical == "median line"
    assert index.terms["term:line"].canonical == "line"


def test_document_term_index_records_mentions_with_source():
    index = DocumentTermIndex.from_texts([("e1", "The vertical strip contains candidate points.")])

    strip = index.terms["term:vertical_strip"]
    assert strip.canonical == "vertical strip"
    assert strip.mentions[0].element_id == "e1"
    assert strip.mentions[0].source_signal == "nounish_span"


def test_document_term_index_does_not_cross_verbs_or_stopwords():
    index = DocumentTermIndex.from_texts([("e1", "The median line splits the points.")])

    assert "term:median_line" in index.terms
    assert "term:line" in index.terms
    assert "term:line_split" not in index.terms
    assert "term:median_line_split" not in index.terms
    assert "term:split_the" not in index.terms
    assert "term:split_the_point" not in index.terms


def test_document_term_index_does_not_cross_intersect_verb():
    index = DocumentTermIndex.from_texts([("e1", "The x axis intersects the y axis.")])

    assert "term:x_axis" in index.terms
    assert "term:y_axis" in index.terms
    assert "term:axis_intersect" not in index.terms
    assert "term:x_axis_intersect" not in index.terms
    assert "term:intersect_the" not in index.terms
    assert "term:intersect_the_y" not in index.terms


def test_document_term_index_does_not_cross_punctuation_boundaries():
    index = DocumentTermIndex.from_texts([("e1", "Line. Median line.")])

    assert "term:line" in index.terms
    assert "term:median_line" in index.terms
    assert "term:line_median" not in index.terms


def test_document_term_index_mappings_are_immutable():
    index = DocumentTermIndex.from_texts([("e1", "The median line.")])

    with pytest.raises(TypeError):
        index.terms["term:x"] = index.terms["term:median_line"]

    with pytest.raises(TypeError):
        index.mentions_by_element_id["e2"] = ()
