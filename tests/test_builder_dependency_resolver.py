import pytest

from contextus.builder.dependency_resolver import (
    CandidateSupport,
    ConstraintCandidate,
    DependencyResolver,
    DocumentTerm,
    DocumentTermIndex,
    FrameCandidate,
    FrameCandidateProjector,
    TermCandidate,
    TermMention,
    normalize_term_text,
    FactFrame,
    FrameConstraint,
    FrameSlot,
    Need,
    NeedBuilder,
    ResolutionTraceStep,
    SlotCandidate,
    SourceRef,
)


def _term_candidate(
    element_id: str,
    source_text: str,
    term_text: str,
    source_signal: str = "syntax_noun_chunk",
) -> TermCandidate:
    start = source_text.index(term_text)
    return TermCandidate(
        element_id=element_id,
        text=term_text,
        char_start=start,
        char_end=start + len(term_text),
        source_signal=source_signal,
        head=term_text.split()[-1].lower(),
        modifiers=tuple(part.lower() for part in term_text.split()[:-1]),
    )


def _slot_candidate(
    name: str,
    source_text: str,
    term_text: str,
    *,
    grounding_state: str = "unsupported",
) -> SlotCandidate:
    start = source_text.lower().index(term_text.lower())
    return SlotCandidate(
        name=name,
        text=term_text,
        char_start=start,
        char_end=start + len(term_text),
        grounding_state=grounding_state,
    )


def _candidate_points_term_index() -> DocumentTermIndex:
    core_text = "The strip has a constant number of candidate points."
    source_text = "The strip contains at most seven candidate points."
    row_text = "The strip contains at most seven rows."
    return DocumentTermIndex.from_candidates(
        [
            _term_candidate("core", core_text, "strip"),
            _term_candidate("core", core_text, "candidate points"),
            _term_candidate("source", source_text, "strip"),
            _term_candidate("source", source_text, "candidate points"),
            _term_candidate("row-source", row_text, "rows"),
        ]
    )


def test_frame_slot_separates_fill_and_grounding_state():
    slot = FrameSlot(
        name="object",
        value="candidate points",
        term_id="term:candidate_points",
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
            "object": FrameSlot(name="object", value="candidate points", term_id="term:candidate_points"),
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
    assert normalize_term_text(" Strip. ") == "strip"
    assert normalize_term_text("candidate points") == "candidate points"
    assert normalize_term_text("median line") == "median line"
    assert normalize_term_text("line") == "line"
    assert normalize_term_text("Q_x") == "q_x"


def test_normalize_term_text_preserves_source_morphology():
    assert normalize_term_text("axis") == "axis"
    assert normalize_term_text("bias") == "bias"
    assert normalize_term_text("analysis") == "analysis"
    assert normalize_term_text("status") == "status"
    assert normalize_term_text("points") == "points"
    assert normalize_term_text("lines") == "lines"
    assert normalize_term_text("sides") == "sides"
    assert normalize_term_text("series") == "series"
    assert normalize_term_text("lens") == "lens"
    assert normalize_term_text("canvas") == "canvas"
    assert normalize_term_text("chaos") == "chaos"


def test_document_term_index_keeps_specific_terms_separate():
    text1 = "The median line splits the points."
    text2 = "The line is drawn vertically."
    index = DocumentTermIndex.from_candidates(
        [
            _term_candidate("e1", text1, "median line"),
            _term_candidate("e2", text2, "line"),
        ]
    )

    assert "term:median_line" in index.terms
    assert "term:line" in index.terms
    assert index.terms["term:median_line"].canonical == "median line"
    assert index.terms["term:line"].canonical == "line"


def test_document_term_index_records_mentions_with_source():
    text = "The vertical strip contains candidate points."
    index = DocumentTermIndex.from_candidates([_term_candidate("e1", text, "vertical strip")])

    strip = index.terms["term:vertical_strip"]
    assert strip.canonical == "vertical strip"
    assert strip.mentions[0].element_id == "e1"
    assert strip.mentions[0].source_signal == "syntax_noun_chunk"


def test_document_term_index_rejects_raw_text_extraction():
    with pytest.raises(ValueError, match="TermCandidate"):
        DocumentTermIndex.from_texts([("e1", "The median line splits the points near Q_x.")])

    assert DocumentTermIndex.from_texts([]).terms == {}


def test_document_term_index_keeps_extractor_boundaries():
    text = "The x axis intersects the y axis."
    index = DocumentTermIndex.from_candidates(
        [
            _term_candidate("e1", text, "x axis"),
            _term_candidate("e1", text, "y axis"),
        ]
    )

    assert "term:x_axis" in index.terms
    assert "term:y_axis" in index.terms
    assert "term:axis_intersect" not in index.terms


def test_document_term_index_keeps_colliding_slugs_separate():
    index = DocumentTermIndex.from_candidates(
        [
            TermCandidate(
                element_id="e1",
                text="Q_x",
                char_start=0,
                char_end=3,
                source_signal="symbol",
                head="Q_x",
            ),
            TermCandidate(
                element_id="e2",
                text="Q x",
                char_start=0,
                char_end=3,
                source_signal="syntax_noun_chunk",
                head="x",
                modifiers=("q",),
            ),
        ]
    )

    q_x_id = index.term_id_for_text("Q_x")
    q_space_x_id = index.term_id_for_text("Q x")

    assert q_x_id
    assert q_space_x_id
    assert q_x_id != q_space_x_id
    assert index.terms[q_x_id].canonical == "q_x"
    assert index.terms[q_space_x_id].canonical == "q x"


def test_document_term_index_keeps_punctuation_separated_when_spans_are_separate():
    text = "Line. Median line."
    index = DocumentTermIndex.from_candidates(
        [
            _term_candidate("e1", text, "Line"),
            _term_candidate("e1", text, "Median line"),
        ]
    )

    assert "term:line" in index.terms
    assert "term:median_line" in index.terms
    assert "term:line_median" not in index.terms


def test_document_term_index_mappings_are_immutable():
    text = "The median line."
    index = DocumentTermIndex.from_candidates([_term_candidate("e1", text, "median line")])

    with pytest.raises(TypeError):
        index.terms["term:x"] = index.terms["term:median_line"]

    with pytest.raises(TypeError):
        index.mentions_by_element_id["e2"] = ()


def test_document_term_index_preserves_dash_or_slash_separated_spans():
    text = "Line - median line / candidate points"
    index = DocumentTermIndex.from_candidates(
        [
            _term_candidate("e1", text, "Line"),
            _term_candidate("e1", text, "median line"),
            _term_candidate("e1", text, "candidate points"),
        ]
    )

    assert "term:line" in index.terms
    assert "term:median_line" in index.terms
    assert "term:candidate_points" in index.terms
    assert "term:line_median" not in index.terms
    assert "term:line_candidate" not in index.terms


def test_term_mentions_preserve_exact_source_span_text():
    text = "The vertical strip contains candidate points."
    index = DocumentTermIndex.from_candidates(
        [
            _term_candidate("e1", text, "vertical strip"),
            _term_candidate("e1", text, "candidate points"),
        ]
    )

    for term in index.terms.values():
        for mention in term.mentions:
            assert mention.text == text[mention.char_start : mention.char_end]


def test_term_models_normalize_nested_collections_from_direct_constructors():
    mention = TermMention(
        text="candidate points",
        normalized="candidate points",
        element_id="e1",
        char_start=0,
        char_end=16,
        source_signal="syntax_noun_chunk",
        modifiers=["candidate"],
    )
    term = DocumentTerm(term_id="term:candidate_points", canonical="candidate points", mentions=[mention])
    index = DocumentTermIndex(terms={"term:candidate_points": term}, mentions_by_element_id={"e1": [mention]})

    assert mention.modifiers == ("candidate",)
    assert term.mentions == (mention,)
    assert index.mentions_by_element_id["e1"] == (mention,)


def test_document_term_index_uses_upstream_head_and_modifiers():
    text = "The candidate points are bounded."
    candidate = TermCandidate(
        element_id="e1",
        text="candidate points",
        char_start=text.index("candidate points"),
        char_end=text.index("candidate points") + len("candidate points"),
        source_signal="syntax_noun_chunk",
        head="points",
        modifiers=("candidate",),
    )

    index = DocumentTermIndex.from_candidates([candidate])
    mention = index.terms["term:candidate_points"].mentions[0]

    assert mention.head == "points"
    assert mention.modifiers == ("candidate",)


def test_frame_candidate_projector_materializes_explicit_frames_with_term_ids():
    text = "The strip contains at most seven candidate points."
    term_index = _candidate_points_term_index()
    projector = FrameCandidateProjector(term_index)
    candidate = FrameCandidate(
        frame_id="frame:source:bound",
        element_id="source",
        proposition_id="source::p00",
        predicate="bound",
        text=text,
        char_start=0,
        char_end=len(text),
        slots={"target": _slot_candidate("target", text, "candidate points")},
        constraints=(
            ConstraintCandidate(
                target_slot="target",
                operator="<=",
                value="seven",
                normalized_value="7",
                source_text="at most seven candidate points",
                char_start=text.index("at most"),
                char_end=text.index("candidate points") + len("candidate points"),
            ),
        ),
    )

    frames = projector.project([candidate])

    assert len(frames) == 1
    frame = frames[0]
    assert frame.frame_id == "frame:source:bound"
    assert frame.source.proposition_id == "source::p00"
    assert frame.predicate == "bound"
    assert frame.slots["target"].value == "candidate points"
    assert frame.slots["target"].term_id == "term:candidate_points"
    assert frame.constraints[0].normalized_value == "7"


def test_frame_candidate_projector_does_not_infer_frames_from_raw_text():
    import contextus.builder.dependency_resolver as resolver

    assert not hasattr(resolver, "SimpleFrameExtractor")


def test_need_builder_creates_needs_from_unsupported_slots_and_constraints():
    frame = FactFrame(
        frame_id="frame:core:bound",
        source=SourceRef(element_id="core"),
        predicate="bound",
        slots={
            "target": FrameSlot(
                name="target",
                value="candidate points",
                term_id="term:candidate_points",
                grounding_state="unsupported",
            )
        },
        constraints=(
            FrameConstraint(
                target_slot="target",
                operator="constant_bound",
                value="constant",
                normalized_value="constant",
                grounding_state="unsupported",
            ),
        ),
    )

    needs = NeedBuilder().needs_for_frame(frame)

    assert [need.target_path for need in needs] == ["slots.target", "constraints.0"]
    assert [need.reason for need in needs] == ["filled_but_unsupported", "filled_but_unsupported"]


def test_need_builder_ignores_grounded_frame_parts():
    frame = FactFrame(
        frame_id="frame:core:bound",
        source=SourceRef(element_id="core"),
        predicate="bound",
        slots={"target": FrameSlot(name="target", value="candidate points", grounding_state="grounded")},
        constraints=(
            FrameConstraint(
                target_slot="target",
                operator="<=",
                value="seven",
                normalized_value="7",
                grounding_state="grounded",
            ),
        ),
    )

    assert NeedBuilder().needs_for_frame(frame) == []


def _projected_bound_frame(
    *,
    frame_id: str,
    element_id: str,
    text: str,
    target: str,
    operator: str,
    value: str,
    normalized_value: str,
    term_index: DocumentTermIndex,
    value_kind: str = "",
) -> FactFrame:
    return FrameCandidateProjector(term_index).project(
        [
            FrameCandidate(
                frame_id=frame_id,
                element_id=element_id,
                proposition_id=f"{element_id}::p00",
                predicate="bound",
                text=text,
                char_start=0,
                char_end=len(text),
                slots={"target": _slot_candidate("target", text, target)},
                constraints=(
                    ConstraintCandidate(
                        target_slot="target",
                        operator=operator,
                        value=value,
                        normalized_value=normalized_value,
                        value_kind=value_kind,
                        source_text=text,
                        char_start=0,
                        char_end=len(text),
                    ),
                ),
            )
        ]
    )[0]


def test_resolver_closes_constant_need_with_fixed_upper_bound():
    term_index = _candidate_points_term_index()
    core_frame = _projected_bound_frame(
        frame_id="frame:core:bound",
        element_id="core",
        text="The strip has a constant number of candidate points.",
        target="candidate points",
        operator="constant_bound",
        value="constant",
        normalized_value="constant",
        term_index=term_index,
    )
    source_frame = _projected_bound_frame(
        frame_id="frame:source:bound",
        element_id="source",
        text="The strip contains at most seven candidate points.",
        target="candidate points",
        operator="<=",
        value="seven",
        normalized_value="7",
        value_kind="constant",
        term_index=term_index,
    )

    result = DependencyResolver().resolve(core_frames=[core_frame], document_frames=[source_frame])

    assert [need.status for need in result.resolved_needs] == ["resolved", "resolved"]
    assert not result.unresolved_needs
    assert result.selected_elements == ("source",)
    assert any(step.action == "need_resolved" for step in result.resolution_trace)


def test_resolver_does_not_close_with_target_mismatch():
    term_index = _candidate_points_term_index()
    core_frame = _projected_bound_frame(
        frame_id="frame:core:bound",
        element_id="core",
        text="Candidate points have a constant bound.",
        target="candidate points",
        operator="constant_bound",
        value="constant",
        normalized_value="constant",
        term_index=term_index,
    )
    row_frame = _projected_bound_frame(
        frame_id="frame:row-source:bound",
        element_id="row-source",
        text="The strip contains at most seven rows.",
        target="rows",
        operator="<=",
        value="seven",
        normalized_value="7",
        value_kind="constant",
        term_index=term_index,
    )

    result = DependencyResolver().resolve(core_frames=[core_frame], document_frames=[row_frame])

    assert not result.resolved_needs
    assert result.unresolved_needs
    assert any(step.action == "candidate_rejected" for step in result.resolution_trace)


def test_resolver_does_not_close_constant_need_with_variable_bound():
    term_index = _candidate_points_term_index()
    core_frame = _projected_bound_frame(
        frame_id="frame:core:bound",
        element_id="core",
        text="Candidate points have a constant bound.",
        target="candidate points",
        operator="constant_bound",
        value="constant",
        normalized_value="constant",
        term_index=term_index,
    )
    variable_frame = _projected_bound_frame(
        frame_id="frame:source:bound",
        element_id="source",
        text="The strip contains at most n candidate points.",
        target="candidate points",
        operator="<=",
        value="n",
        normalized_value="n",
        value_kind="variable",
        term_index=term_index,
    )

    result = DependencyResolver().resolve(core_frames=[core_frame], document_frames=[variable_frame])

    assert any(need.target_path == "slots.target" for need in result.resolved_needs)
    assert any(need.target_path == "constraints.0" for need in result.unresolved_needs)


def test_resolver_traces_rejected_candidate_before_later_acceptance():
    term_index = _candidate_points_term_index()
    core_frame = _projected_bound_frame(
        frame_id="frame:core:bound",
        element_id="core",
        text="Candidate points have a constant bound.",
        target="candidate points",
        operator="constant_bound",
        value="constant",
        normalized_value="constant",
        term_index=term_index,
    )
    rejected_frame = _projected_bound_frame(
        frame_id="frame:rejected:bound",
        element_id="rejected",
        text="The strip contains at least n candidate points.",
        target="candidate points",
        operator=">=",
        value="n",
        normalized_value="n",
        value_kind="variable",
        term_index=term_index,
    )
    accepted_frame = _projected_bound_frame(
        frame_id="frame:source:bound",
        element_id="source",
        text="The strip contains at most seven candidate points.",
        target="candidate points",
        operator="<=",
        value="seven",
        normalized_value="7",
        value_kind="constant",
        term_index=term_index,
    )

    result = DependencyResolver().resolve(
        core_frames=[core_frame],
        document_frames=[rejected_frame, accepted_frame],
    )

    rejected_steps = [step for step in result.resolution_trace if step.action == "candidate_rejected"]
    assert any(step.frame_ids == ("frame:rejected:bound",) for step in rejected_steps)
    assert result.resolved_needs


def test_resolver_records_cycle_without_expanding_forever():
    frame_a = FactFrame(
        frame_id="frame:a",
        source=SourceRef(element_id="a", text="A depends on B."),
        predicate="depends_on",
        links=("frame:b",),
    )
    frame_b = FactFrame(
        frame_id="frame:b",
        source=SourceRef(element_id="b", text="B depends on A."),
        predicate="depends_on",
        links=("frame:a",),
    )

    result = DependencyResolver().record_cycles([frame_a, frame_b])

    assert result == (("frame:a", "frame:b", "frame:a"),)


def test_resolver_records_cycle_once_with_long_entry_path():
    frames = [
        FactFrame(frame_id="frame:start", source=SourceRef(element_id="start"), predicate="depends_on", links=("frame:a",)),
        FactFrame(frame_id="frame:a", source=SourceRef(element_id="a"), predicate="depends_on", links=("frame:b",)),
        FactFrame(frame_id="frame:b", source=SourceRef(element_id="b"), predicate="depends_on", links=("frame:c",)),
        FactFrame(frame_id="frame:c", source=SourceRef(element_id="c"), predicate="depends_on", links=("frame:a",)),
    ]

    result = DependencyResolver().record_cycles(frames)

    assert result == (("frame:a", "frame:b", "frame:c", "frame:a"),)


def test_dependency_resolver_is_public_builder_export():
    from contextus.builder import DependencyResolver as PublicDependencyResolver

    assert PublicDependencyResolver is DependencyResolver


def test_query_adapter_uses_supplied_candidates_not_text_extraction():
    from contextus.builder.query_assembly import QueryEvidenceProposition

    core = QueryEvidenceProposition(
        proposition_id="core::p00",
        element_id="core",
        element_index=0,
        text="Candidate points have a constant bound.",
    )
    source = QueryEvidenceProposition(
        proposition_id="source::p00",
        element_id="source",
        element_index=1,
        text="The strip contains at most seven candidate points.",
    )
    term_index = _candidate_points_term_index()
    frame_candidates = [
        FrameCandidate(
            frame_id="frame:core:bound",
            element_id="core",
            proposition_id="core::p00",
            predicate="bound",
            text=core.text,
            char_start=0,
            char_end=len(core.text),
            slots={"target": SlotCandidate(name="target", text="candidate points", char_start=0, char_end=16)},
            constraints=(
                ConstraintCandidate(
                    target_slot="target",
                    operator="constant_bound",
                    value="constant",
                    normalized_value="constant",
                ),
            ),
        ),
        FrameCandidate(
            frame_id="frame:source:bound",
            element_id="source",
            proposition_id="source::p00",
            predicate="bound",
            text=source.text,
            char_start=0,
            char_end=len(source.text),
            slots={"target": _slot_candidate("target", source.text, "candidate points")},
            constraints=(
                ConstraintCandidate(
                    target_slot="target",
                    operator="<=",
                    value="seven",
                    normalized_value="7",
                    value_kind="constant",
                ),
            ),
        ),
    ]

    result = DependencyResolver().resolve_query_propositions(
        core=core,
        propositions=[core, source],
        term_index=term_index,
        frame_candidates=frame_candidates,
    )

    assert result.resolved_needs
    assert result.selected_elements == ("source",)


def test_query_adapter_includes_core_when_core_is_not_in_propositions():
    from contextus.builder.query_assembly import QueryEvidenceProposition

    core = QueryEvidenceProposition(
        proposition_id="core::p00",
        element_id="core",
        element_index=0,
        text="Candidate points have a constant bound.",
    )
    source = QueryEvidenceProposition(
        proposition_id="source::p00",
        element_id="source",
        element_index=1,
        text="The strip contains at most seven candidate points.",
    )
    term_index = _candidate_points_term_index()
    frame_candidates = [
        FrameCandidate(
            frame_id="frame:core:bound",
            element_id="core",
            proposition_id="core::p00",
            predicate="bound",
            text=core.text,
            slots={"target": SlotCandidate(name="target", text="candidate points")},
            constraints=(
                ConstraintCandidate(
                    target_slot="target",
                    operator="constant_bound",
                    value="constant",
                    normalized_value="constant",
                ),
            ),
        ),
        FrameCandidate(
            frame_id="frame:source:bound",
            element_id="source",
            proposition_id="source::p00",
            predicate="bound",
            text=source.text,
            slots={"target": _slot_candidate("target", source.text, "candidate points")},
            constraints=(
                ConstraintCandidate(
                    target_slot="target",
                    operator="<=",
                    value="seven",
                    normalized_value="7",
                    value_kind="constant",
                ),
            ),
        ),
    ]

    result = DependencyResolver().resolve_query_propositions(
        core=core,
        propositions=[source],
        term_index=term_index,
        frame_candidates=frame_candidates,
    )

    assert result.resolved_needs
    assert result.selected_elements == ("source",)


def test_query_adapter_rejects_unscoped_frame_candidates():
    from contextus.builder.query_assembly import QueryEvidenceProposition

    core = QueryEvidenceProposition(
        proposition_id="core::p00",
        element_id="core",
        element_index=0,
        text="Candidate points have a constant bound.",
    )

    with pytest.raises(ValueError, match="proposition_id"):
        DependencyResolver().resolve_query_propositions(
            core=core,
            propositions=[core],
            term_index=_candidate_points_term_index(),
            frame_candidates=[
                FrameCandidate(
                    frame_id="frame:unscoped",
                    element_id="source",
                    predicate="bound",
                )
            ],
        )


def test_query_adapter_rejects_missing_frame_candidates():
    from contextus.builder.query_assembly import QueryEvidenceProposition

    core = QueryEvidenceProposition(
        proposition_id="core::p00",
        element_id="core",
        element_index=0,
        text="Candidate points have a constant bound.",
    )

    with pytest.raises(ValueError, match="frame_candidates"):
        DependencyResolver().resolve_query_propositions(core=core, propositions=[core])
