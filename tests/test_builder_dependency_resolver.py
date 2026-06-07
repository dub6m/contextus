import pytest

from contextus.builder.dependency_resolver import (
    CandidateSupport,
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
