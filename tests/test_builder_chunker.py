from contextus.builder.chunker import (
    BoundaryCandidate,
    BoundaryElementView,
    BoundaryPreliminaryDecision,
    DocumentChunker,
    RefinedChunkGroup,
    TentativeBlock,
    _RepairGroupState,
)
from contextus.builder.config import BuilderConfig
from contextus.builder.preprocessor import ElementPreprocessor
from contextus.ingestion.models import ExtractedDocument, ExtractedElement, ExtractedPage
from concurrent.futures import ThreadPoolExecutor
import time


class DummyLLM:
    def complete(self, system: str, user: str, temperature: float = 0.0, **kwargs):
        raise AssertionError('LLM should not be called in this test unless explicitly mocked')


class Response:
    def __init__(self, content: str) -> None:
        self.content = content


class QueueLLM:
    def __init__(self, *responses: str) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []
        self.calls: list[dict] = []

    def complete(self, system: str, user: str, temperature: float = 0.0, **kwargs):
        self.prompts.append(user)
        self.calls.append({'system': system, 'user': user, 'temperature': temperature, **kwargs})
        if not self.responses:
            raise AssertionError('No queued LLM response')
        return Response(self.responses.pop(0))


class SlowJsonLLM:
    def __init__(self, delay: float = 0.15):
        self.delay = delay

    def complete(self, system: str, user: str, temperature: float = 0.0, **kwargs):
        time.sleep(self.delay)
        return Response(
            '{"decision":"continue","confidence":0.9,"reasons":["same local concept"],'
            '"needs_more_context":false,"context_request":{}}'
        )


class SlowAuditLLM:
    def __init__(self, delay: float = 0.15):
        self.delay = delay
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.prompts: list[str] = []

    def complete(self, system: str, user: str, temperature: float = 0.0, **kwargs):
        time.sleep(self.delay)
        self.prompts.append(user)
        return Response('{"action":"keep","confidence":0.95,"reason":"acceptable as-is","element_ids":[]}')

    def submit(self, system: str, user: str, temperature: float = 0.0, **kwargs):
        return self.executor.submit(self.complete, system, user, temperature, **kwargs)


def make_element(element_type: str, order: int, **kwargs) -> ExtractedElement:
    return ExtractedElement(
        id=kwargs.pop('id', f'{element_type}-{order}'),
        type=element_type,
        page_number=kwargs.pop('page_number', 1),
        order=order,
        bbox=kwargs.pop('bbox', (0.0, 0.0, 1.0, 1.0)),
        confidence=kwargs.pop('confidence', 0.9),
        content=kwargs.pop('content', f'{element_type}-{order}'),
        raw_text=kwargs.pop('raw_text', ''),
        source=kwargs.pop('source', 'test'),
        metadata=kwargs.pop('metadata', {}),
        asset_path=kwargs.pop('asset_path', None),
    )


def make_document(elements: list[ExtractedElement]) -> ExtractedDocument:
    return ExtractedDocument(
        source_name='doc.pdf',
        source_path='doc.pdf',
        source_type='pdf',
        pages=[ExtractedPage(page_number=1, width=10.0, height=10.0, elements=elements)],
    )


def make_chunker(llm_client=None, **kwargs) -> DocumentChunker:
    chunker = DocumentChunker(llm_client=llm_client or DummyLLM(), preprocessor=ElementPreprocessor(), **kwargs)
    chunker._summary_similarity = lambda left, right: 0.5
    chunker._score_cross_encoder = lambda left, right: 0.5
    return chunker


def make_boundary_view(element_id: str, text: str, index: int) -> BoundaryElementView:
    return BoundaryElementView(
        element_id=element_id,
        element_type="text",
        page_number=1,
        order=index + 1,
        bbox=(0.0, 0.0, 1.0, 1.0),
        confidence=0.9,
        text=text,
        raw_text="",
        source="test",
        asset_path=None,
        metadata={},
    )


def make_llm_refinement_block(block_id: str, start_index: int) -> TentativeBlock:
    left = make_boundary_view(f"{block_id}-a", f"{block_id} first idea", start_index)
    right = make_boundary_view(f"{block_id}-b", f"{block_id} continuation", start_index + 1)
    boundary = BoundaryCandidate(
        boundary_id=f"{block_id}::boundary",
        boundary_index=start_index,
        left=left,
        right=right,
        same_page=True,
        preliminary_decision=BoundaryPreliminaryDecision(
            decision="continue",
            split_probability=0.5,
            confidence=0.5,
            reasons=["ambiguous"],
        ),
    )
    return TentativeBlock(
        block_id=block_id,
        block_index=start_index // 2,
        elements=[left, right],
        start_element_index=start_index,
        end_element_index=start_index + 1,
        internal_boundaries=[boundary],
        stability="ambiguous",
    )


def make_block_with_texts(block_id: str, texts: list[str]) -> TentativeBlock:
    elements = [
        make_boundary_view(f"{block_id}-{offset}", text, offset)
        for offset, text in enumerate(texts)
    ]
    boundaries = [
        BoundaryCandidate(
            boundary_id=f"{block_id}::boundary::{offset}",
            boundary_index=offset,
            left=elements[offset],
            right=elements[offset + 1],
            same_page=True,
            preliminary_decision=BoundaryPreliminaryDecision(
                decision="unknown",
                split_probability=0.5,
                confidence=0.5,
                reasons=["ambiguous"],
            ),
        )
        for offset in range(len(elements) - 1)
    ]
    return TentativeBlock(
        block_id=block_id,
        block_index=0,
        elements=elements,
        start_element_index=0,
        end_element_index=len(elements) - 1,
        internal_boundaries=boundaries,
        stability="ambiguous",
    )


def test_chunker_splits_before_title():
    elements = [make_element('text', 1, content='Alpha'), make_element('title', 2, content='Heading')]
    chunker = make_chunker()
    chunker._compute_similarity_stats = lambda texts: ([0.5], 0.5, 0.0)

    chunks = chunker.chunk(make_document(elements))

    assert len(chunks) == 2
    assert chunker.boundary_log[0].tier_used == '0'
    assert chunker.boundary_log[0].decision == 'split'


def test_chunker_splits_on_low_confidence():
    elements = [make_element('text', 1, confidence=0.2, content='A'), make_element('text', 2, content='B')]
    chunker = make_chunker()
    chunker._compute_similarity_stats = lambda texts: ([0.9], 0.9, 0.0)

    chunks = chunker.chunk(make_document(elements))

    assert len(chunks) == 2
    assert 'low confidence' in chunker.boundary_log[0].notes


def test_chunker_free_merges_on_high_prior_without_model_call():
    elements = [make_element('text', 1, content='A'), make_element('text', 2, content='B')]
    chunker = make_chunker(type_priors={('text', 'text'): 0.9})
    chunker._compute_similarity_stats = lambda texts: ([0.1], 0.1, 0.0)
    chunker._summary_similarity = lambda left, right: (_ for _ in ()).throw(AssertionError('should not use summary similarity'))

    chunks = chunker.chunk(make_document(elements))

    assert len(chunks) == 1
    assert chunker.boundary_log[0].decision == 'merge'
    assert 'free merge' in chunker.boundary_log[0].notes


def test_chunker_populates_boundary_log():
    elements = [
        make_element('text', 1, content='A'),
        make_element('text', 2, content='B'),
        make_element('title', 3, content='C'),
    ]
    chunker = make_chunker()
    chunker._compute_similarity_stats = lambda texts: ([0.9, 0.9], 0.9, 0.0)
    chunker._summary_similarity = lambda left, right: 0.95
    chunker._score_cross_encoder = lambda left, right: 0.8

    chunker.chunk(make_document(elements))

    assert len(chunker.boundary_log) == 2


def test_refined_groups_refines_independent_tentative_blocks_concurrently():
    chunker = make_chunker(llm_client=SlowJsonLLM(delay=0.15))
    blocks = [
        make_llm_refinement_block("block-a", 0),
        make_llm_refinement_block("block-b", 2),
    ]

    started = time.perf_counter()
    groups = chunker._build_refined_groups(document_id="doc", tentative_blocks=blocks, allow_llm=True)
    elapsed = time.perf_counter() - started

    assert len(groups) == 2
    assert chunker.llm_calls == 2
    assert elapsed < 0.25


def test_block_segmentation_refines_tentative_block_from_batched_boundary_decisions():
    llm = QueueLLM(
        '{"decisions":['
        '{"left_element_id":"block-a-0","right_element_id":"block-a-1","decision":"continue","confidence":0.91,"reason":"same topic"},'
        '{"left_element_id":"block-a-1","right_element_id":"block-a-2","decision":"split","confidence":0.88,"reason":"new topic"},'
        '{"left_element_id":"block-a-2","right_element_id":"block-a-3","decision":"continue","confidence":0.9,"reason":"same topic"}'
        '],"confidence":0.9,"reason":"all decisions are clear"}'
    )
    chunker = make_chunker(llm_client=llm)
    block = make_block_with_texts(
        "block-a",
        [
            "Alpha is the first topic.",
            "Alpha has a direct supporting detail.",
            "Beta begins a different topic.",
            "Beta has a direct supporting detail.",
        ],
    )

    groups = chunker._build_refined_groups(
        document_id="doc",
        tentative_blocks=[block],
        allow_llm=True,
        refinement_strategy="block",
    )

    assert [group.element_ids for group in groups] == [
        ["block-a-0", "block-a-1"],
        ["block-a-2", "block-a-3"],
    ]
    assert chunker.llm_calls == 1
    assert groups[0].search_strategy == "block_segmentation"
    assert llm.calls[0]["response_format"]["json_schema"]["name"] == "block_concept_segmentation"
    assert "decisions" in llm.calls[0]["response_format"]["json_schema"]["schema"]["properties"]
    decision_schema = llm.calls[0]["response_format"]["json_schema"]["schema"]["properties"]["decisions"]["items"]
    assert "left_element_id" in decision_schema["properties"]
    assert "right_element_id" in decision_schema["properties"]
    assert "id=block-a-2" in llm.prompts[0]
    assert "Boundaries to decide:" in llm.prompts[0]
    assert "Process boundaries in order" in llm.prompts[0]
    assert "Return one decision object for every boundary pair" in llm.prompts[0]


def test_block_segmentation_does_not_fall_back_to_galloping_when_confidence_is_low():
    llm = QueueLLM(
        '{"decisions":['
        '{"left_element_id":"block-a-0","right_element_id":"block-a-1","decision":"continue","confidence":0.91,"reason":"same topic"},'
        '{"left_element_id":"block-a-1","right_element_id":"block-a-2","decision":"split","confidence":0.88,"reason":"new topic"},'
        '{"left_element_id":"block-a-2","right_element_id":"block-a-3","decision":"continue","confidence":0.9,"reason":"same topic"}'
        '],"confidence":0.2,"reason":"too uncertain"}',
    )
    chunker = make_chunker(llm_client=llm)
    block = make_block_with_texts(
        "block-a",
        [
            "Alpha is the first topic.",
            "Alpha has a direct supporting detail.",
            "Beta begins a different topic.",
            "Beta has a direct supporting detail.",
        ],
    )

    groups = chunker._build_refined_groups(
        document_id="doc",
        tentative_blocks=[block],
        allow_llm=True,
        refinement_strategy="block",
    )

    assert [group.element_ids for group in groups] == [
        ["block-a-0", "block-a-1", "block-a-2", "block-a-3"],
    ]
    assert chunker.llm_calls == 1
    assert groups[0].search_strategy == "block_segmentation_rejected"
    assert "confidence=0.20" in groups[0].reason_summary


def test_semantic_walk_refinement_splits_on_embedding_distance_outlier():
    elements = [
        make_element("text", 1, id="a", content="Alpha setup."),
        make_element("text", 2, id="b", content="Alpha detail."),
        make_element("text", 3, id="c", content="Alpha conclusion."),
        make_element("text", 4, id="d", content="Beta setup."),
        make_element("text", 5, id="e", content="Beta detail."),
    ]
    config = BuilderConfig(
        SEMANTIC_WALK_BREAKPOINT_PERCENTILE=75,
        SEMANTIC_WALK_MIN_BOUNDARIES=2,
    )
    chunker = make_chunker(llm_client=DummyLLM(), config=config, type_priors={("text", "text"): 0.5})
    chunker._compute_similarity_stats = lambda texts: ([0.5] * 4, 0.5, 0.0)
    chunker._embed_texts = lambda texts: __import__("numpy").array([
        [1.0, 0.0],
        [1.0, 0.0],
        [1.0, 0.0],
        [0.0, 1.0],
        [0.0, 1.0],
    ])

    groups = chunker.build_refined_groups(
        make_document(elements),
        allow_llm=True,
        refinement_strategy="semantic_walk",
    )

    assert [group.element_ids for group in groups] == [["a", "b", "c"], ["d", "e"]]
    assert {group.search_strategy for group in groups} == {"semantic_walk"}
    assert chunker.llm_calls == 0


def test_semantic_walk_refinement_keeps_small_blocks_unsplit():
    elements = [
        make_element("text", 1, id="a", content="Alpha setup."),
        make_element("text", 2, id="b", content="Beta setup."),
    ]
    config = BuilderConfig(SEMANTIC_WALK_MIN_BOUNDARIES=3)
    chunker = make_chunker(llm_client=DummyLLM(), config=config, type_priors={("text", "text"): 0.5})
    chunker._compute_similarity_stats = lambda texts: ([0.5], 0.5, 0.0)
    chunker._embed_texts = lambda texts: __import__("numpy").array([
        [1.0, 0.0],
        [0.0, 1.0],
    ])

    groups = chunker.build_refined_groups(
        make_document(elements),
        allow_llm=True,
        refinement_strategy="level4",
    )

    assert [group.element_ids for group in groups] == [["a", "b"]]
    assert groups[0].search_strategy == "semantic_walk"
    assert "no breakpoint outliers" in groups[0].reason_summary
    assert chunker.llm_calls == 0


def test_local_audit_audits_non_overlapping_suspicious_chunks_concurrently():
    llm = SlowAuditLLM(delay=0.15)
    chunker = make_chunker(llm_client=llm)
    elements = [
        *[
            make_element("text", order + 1, id=f"a-{order}", content=f"First group complete idea number {order}.")
            for order in range(6)
        ],
        make_element("text", 7, id="middle-a", content="The middle bridge is complete."),
        make_element("text", 8, id="middle-a-detail", content="It has enough detail to avoid singleton audit."),
        make_element("text", 9, id="middle-b", content="Another middle chunk is complete."),
        make_element("text", 10, id="middle-b-detail", content="It also has enough detail to avoid singleton audit."),
        *[
            make_element("text", order + 11, id=f"b-{order}", content=f"Second group complete idea number {order}.")
            for order in range(6)
        ],
    ]
    views = [
        chunker._element_view(element, chunker.preprocessor.to_text(element))
        for element in elements
    ]
    groups = [
        RefinedChunkGroup(
            group_id="group-0",
            group_index=0,
            source_block_id="block-0",
            elements=views[:6],
            start_element_index=0,
            end_element_index=5,
            stability="likely_good",
            reason_summary="test",
        ),
        RefinedChunkGroup(
            group_id="group-1",
            group_index=1,
            source_block_id="block-1",
            elements=views[6:8],
            start_element_index=6,
            end_element_index=7,
            stability="likely_good",
            reason_summary="test",
        ),
        RefinedChunkGroup(
            group_id="group-2",
            group_index=2,
            source_block_id="block-2",
            elements=views[8:10],
            start_element_index=8,
            end_element_index=9,
            stability="likely_good",
            reason_summary="test",
        ),
        RefinedChunkGroup(
            group_id="group-3",
            group_index=3,
            source_block_id="block-3",
            elements=views[10:],
            start_element_index=10,
            end_element_index=15,
            stability="likely_good",
            reason_summary="test",
        ),
    ]

    started = time.perf_counter()
    repaired = chunker._llm_audit_repaired_groups(document_id="doc", groups=groups)
    elapsed = time.perf_counter() - started

    assert [group.element_ids for group in repaired] == [group.element_ids for group in groups]
    assert chunker.llm_calls == 2
    assert elapsed < 0.25


def test_chunker_computes_dynamic_depth_scores():
    chunker = make_chunker()
    chunker._embed_texts = lambda texts: __import__('numpy').array([
        [1.0, 0.0],
        [1.0, 0.0],
        [0.0, 1.0],
    ])

    scores, mu, sigma = chunker._compute_similarity_stats(['a', 'b', 'c'])

    assert scores == [1.0, 0.0]
    assert mu == 0.5
    assert sigma > 0.0


def test_build_boundary_candidates_covers_adjacent_pairs_in_order():
    first = make_element('title', 1, id='first', content='First heading')
    second = make_element('text', 2, id='second', content='Second body')
    third = make_element('formula', 1, id='third', page_number=2, content={'latex': 'n = 2'})
    document = ExtractedDocument(
        source_name='doc.pdf',
        source_path='doc.pdf',
        source_type='pdf',
        pages=[
            ExtractedPage(page_number=1, width=10.0, height=10.0, elements=[second, first]),
            ExtractedPage(page_number=2, width=10.0, height=10.0, elements=[third]),
        ],
        id='doc-1',
    )
    chunker = make_chunker()
    chunker._compute_similarity_stats = lambda texts: ([0.2, 0.4], 0.3, 0.1)

    candidates = chunker.build_boundary_candidates(document, context_window=1)

    assert [candidate.boundary_index for candidate in candidates] == [0, 1]
    assert [(candidate.left_element_id, candidate.right_element_id) for candidate in candidates] == [
        ('first', 'second'),
        ('second', 'third'),
    ]
    assert candidates[0].boundary_id == 'doc-1::boundary::00000'
    assert candidates[1].left.text == 'Second body'
    assert candidates[1].right.text == 'Formula: n = 2'
    assert candidates[1].same_page is False
    assert candidates[1].page_gap == 1


def test_boundary_candidates_include_local_context_and_metadata():
    elements = [
        make_element('text', 1, id='e1', content='One'),
        make_element('text', 2, id='e2', content='Two'),
        make_element('figure', 3, id='e3', content={'figure_type': 'diagram', 'raw_text': 'Flow'}, raw_text='raw-flow', asset_path='fig.png'),
        make_element('text', 4, id='e4', content='Four', metadata={'role': 'body'}),
        make_element('text', 5, id='e5', content='Five'),
    ]
    chunker = make_chunker()
    chunker._compute_similarity_stats = lambda texts: ([0.1, 0.2, 0.3, 0.4], 0.25, 0.11)

    candidate = chunker.build_boundary_candidates(make_document(elements), context_window=2)[2]

    assert candidate.left_element_id == 'e3'
    assert candidate.right_element_id == 'e4'
    assert [item.element_id for item in candidate.left_context] == ['e1', 'e2']
    assert [item.element_id for item in candidate.right_context] == ['e5']
    assert candidate.left.asset_path == 'fig.png'
    assert candidate.left.raw_text == 'raw-flow'
    assert candidate.right.metadata == {'role': 'body'}
    assert candidate.same_page is True
    assert candidate.order_gap == 1


def test_boundary_signals_include_factual_scores_and_hard_flags():
    left = make_element('text', 1, id='left', page_number=1, confidence=0.2, content='Prior body')
    right = make_element('title', 1, id='right', page_number=3, content='Major Section')
    document = ExtractedDocument(
        source_name='doc.pdf',
        source_path='doc.pdf',
        source_type='pdf',
        pages=[
            ExtractedPage(page_number=1, width=10.0, height=10.0, elements=[left]),
            ExtractedPage(page_number=3, width=10.0, height=10.0, elements=[right]),
        ],
        id='doc-2',
    )
    chunker = make_chunker()
    chunker._compute_similarity_stats = lambda texts: ([0.37], 0.37, 0.0)

    signals = chunker.build_boundary_candidates(document)[0].signals

    assert signals is not None
    assert signals.page_gap == 2
    assert signals.order_gap == 0
    assert signals.left_confidence == 0.2
    assert signals.right_confidence == 0.9
    assert signals.adjacent_embedding_similarity == 0.37
    assert signals.type_prior == 0.0
    assert signals.right_heading_like_score == 1.0
    assert signals.hard_rule_flags["right_is_title"] is True
    assert signals.hard_rule_flags["left_low_confidence"] is True
    assert signals.hard_rule_flags["type_prior_forces_split"] is True
    assert signals.hard_rule_flags["cross_page_gap_large"] is True


def test_boundary_signals_score_formula_admin_artifact_and_continuation():
    elements = [
        make_element('text', 1, id='setup', content='The recurrence is:'),
        make_element('formula', 2, id='formula', content={'latex': 'T(n) = 2T(n/2) + n'}),
        make_element('text', 3, id='admin', content='Received 02 January 2025 Accepted 07 April 2025'),
    ]
    chunker = make_chunker()
    chunker._compute_similarity_stats = lambda texts: ([0.64, 0.12], 0.38, 0.26)

    candidates = chunker.build_boundary_candidates(make_document(elements))
    setup_to_formula = candidates[0].signals
    formula_to_admin = candidates[1].signals

    assert setup_to_formula is not None
    assert setup_to_formula.right_formula_or_table_score == 1.0
    assert setup_to_formula.formula_or_table_score == 1.0
    assert setup_to_formula.caption_or_artifact_score >= 0.65
    assert setup_to_formula.text_continuation_score >= 0.78
    assert formula_to_admin is not None
    assert formula_to_admin.right_admin_front_matter_score >= 0.78
    assert formula_to_admin.admin_front_matter_score >= 0.78


def test_preliminary_decision_splits_obvious_title_boundary():
    elements = [
        make_element('text', 1, id='body', content='A complete paragraph.'),
        make_element('title', 2, id='heading', content='New Section'),
    ]
    chunker = make_chunker()
    chunker._compute_similarity_stats = lambda texts: ([0.8], 0.8, 0.0)

    decision = chunker.build_boundary_candidates(make_document(elements))[0].preliminary_decision

    assert decision is not None
    assert decision.decision == 'split'
    assert decision.split_probability >= 0.95
    assert decision.confidence >= 0.9
    assert 'right element is a title' in decision.reasons
    assert decision.hard_rule_flags['right_is_title'] is True


def test_preliminary_decision_continues_obvious_free_merge_boundary():
    elements = [
        make_element('text', 1, id='left', content='The running time is'),
        make_element('text', 2, id='right', content='O(n log n).'),
    ]
    chunker = make_chunker(type_priors={('text', 'text'): 0.9})
    chunker._compute_similarity_stats = lambda texts: ([0.1], 0.1, 0.0)

    decision = chunker.build_boundary_candidates(make_document(elements))[0].preliminary_decision

    assert decision is not None
    assert decision.decision == 'continue'
    assert decision.split_probability <= 0.1
    assert decision.confidence >= 0.85
    assert 'type prior strongly favors continuation' in decision.reasons
    assert decision.hard_rule_flags['type_prior_free_merge'] is True


def test_preliminary_decision_keeps_mixed_tier0_evidence_unknown():
    elements = [
        make_element('text', 1, id='left', content='This statement is complete.'),
        make_element('text', 2, id='right', content='Another statement is also complete.'),
    ]
    chunker = make_chunker(type_priors={('text', 'text'): 0.5})
    chunker._compute_similarity_stats = lambda texts: ([0.5], 0.5, 0.0)

    decision = chunker.build_boundary_candidates(make_document(elements))[0].preliminary_decision

    assert decision is not None
    assert decision.decision == 'unknown'
    assert 0.35 <= decision.split_probability <= 0.65
    assert decision.confidence <= 0.55
    assert decision.reasons


def test_tentative_blocks_split_on_high_confidence_preliminary_boundaries():
    elements = [
        make_element('text', 1, id='intro', content='Intro paragraph.'),
        make_element('text', 2, id='body', content='Continuation paragraph.'),
        make_element('title', 3, id='heading', content='New Section'),
        make_element('text', 4, id='after', content='Section body.'),
    ]
    chunker = make_chunker(type_priors={('text', 'text'): 0.5})
    chunker._compute_similarity_stats = lambda texts: ([0.5, 0.9, 0.5], 0.63, 0.19)

    blocks = chunker.build_tentative_blocks(make_document(elements))

    assert [block.element_ids for block in blocks] == [['intro', 'body'], ['heading', 'after']]
    assert blocks[0].end_boundary is not None
    assert blocks[0].end_boundary.right_element_id == 'heading'
    assert blocks[1].start_boundary is blocks[0].end_boundary
    assert blocks[0].stability == 'ambiguous'
    assert 'ends_at=' in blocks[0].reason_summary


def test_tentative_blocks_keep_high_confidence_continue_run_together():
    elements = [
        make_element('text', 1, id='a', content='The running time is'),
        make_element('text', 2, id='b', content='O(n log n)'),
        make_element('text', 3, id='c', content='for the divide and conquer algorithm.'),
    ]
    chunker = make_chunker(type_priors={('text', 'text'): 0.9})
    chunker._compute_similarity_stats = lambda texts: ([0.1, 0.1], 0.1, 0.0)

    blocks = chunker.build_tentative_blocks(make_document(elements))

    assert len(blocks) == 1
    assert blocks[0].element_ids == ['a', 'b', 'c']
    assert [boundary.preliminary_decision.decision for boundary in blocks[0].internal_boundaries] == ['continue', 'continue']
    assert blocks[0].stability == 'likely_good'
    assert 'continues=2' in blocks[0].reason_summary


def test_tentative_blocks_keep_unknown_boundaries_inside_ambiguous_block():
    elements = [
        make_element('text', 1, id='a', content='First complete statement.'),
        make_element('text', 2, id='b', content='Second complete statement.'),
        make_element('text', 3, id='c', content='Third complete statement.'),
    ]
    chunker = make_chunker(type_priors={('text', 'text'): 0.5})
    chunker._compute_similarity_stats = lambda texts: ([0.5, 0.5], 0.5, 0.0)

    blocks = chunker.build_tentative_blocks(make_document(elements))

    assert len(blocks) == 1
    assert blocks[0].element_ids == ['a', 'b', 'c']
    assert [boundary.preliminary_decision.decision for boundary in blocks[0].internal_boundaries] == ['unknown', 'unknown']
    assert blocks[0].stability == 'ambiguous'
    assert 'unknown=2' in blocks[0].reason_summary


def test_tentative_blocks_handle_single_element_document():
    element = make_element('text', 1, id='only', content='Only element.')
    chunker = make_chunker()

    blocks = chunker.build_tentative_blocks(make_document([element]))

    assert len(blocks) == 1
    assert blocks[0].element_ids == ['only']
    assert blocks[0].stability == 'locked'
    assert blocks[0].reason_summary == 'single element document'


def test_chunk_populates_boundary_candidates_without_changing_chunks():
    elements = [
        make_element('text', 1, id='a', content='Alpha'),
        make_element('title', 2, id='b', content='Heading'),
    ]
    chunker = make_chunker()
    chunker._compute_similarity_stats = lambda texts: ([0.5], 0.5, 0.0)

    chunks = chunker.chunk(make_document(elements))

    assert [[element.id for element in chunk] for chunk in chunks] == [['a'], ['b']]
    assert len(chunker.boundary_candidates) == 1
    assert [(candidate.left_element_id, candidate.right_element_id) for candidate in chunker.boundary_candidates] == [
        ('a', 'b'),
    ]
    assert chunker.boundary_candidates[0].signals is not None
    assert chunker.boundary_candidates[0].preliminary_decision is not None
    assert [block.element_ids for block in chunker.tentative_blocks] == [['a'], ['b']]
    assert [group.element_ids for group in chunker.refined_groups] == [['a'], ['b']]


def test_refined_groups_use_tier0_continue_without_llm():
    elements = [
        make_element('text', 1, id='a', content='The running time is'),
        make_element('text', 2, id='b', content='O(n log n)'),
        make_element('text', 3, id='c', content='for this recurrence.'),
    ]
    chunker = make_chunker(type_priors={('text', 'text'): 0.9})
    chunker._compute_similarity_stats = lambda texts: ([0.1, 0.1], 0.1, 0.0)

    groups = chunker.build_refined_groups(make_document(elements), allow_llm=False)

    assert [group.element_ids for group in groups] == [['a', 'b', 'c']]
    assert groups[0].stability == 'likely_good'
    assert [decision.source for decision in groups[0].probe_decisions] == ['tier0', 'tier0']
    assert [decision.decision for decision in groups[0].probe_decisions] == ['continue', 'continue']


def test_refined_groups_ask_llm_to_split_ambiguous_boundary():
    elements = [
        make_element('text', 1, id='a', content='First complete statement.'),
        make_element('text', 2, id='b', content='Second complete statement.'),
    ]
    llm = QueueLLM(
        '{"decision":"split","confidence":0.91,"reasons":["new concept"],"needs_more_context":false}'
    )
    chunker = make_chunker(llm_client=llm, type_priors={('text', 'text'): 0.5})
    chunker._compute_similarity_stats = lambda texts: ([0.5], 0.5, 0.0)

    groups = chunker.build_refined_groups(make_document(elements), allow_llm=True)

    assert [group.element_ids for group in groups] == [['a'], ['b']]
    assert chunker.llm_calls == 1
    assert groups[0].probe_decisions[0].source == 'llm'
    assert groups[0].probe_decisions[0].decision == 'split'
    assert llm.calls[0]['response_format']['type'] == 'json_schema'
    assert llm.calls[0]['response_format']['json_schema']['name'] == 'concept_boundary_refinement'


def test_refined_groups_support_bounded_context_expansion():
    elements = [
        make_element('text', 1, id='before', content='Background setup.'),
        make_element('text', 2, id='a', content='The method keeps a working frontier.'),
        make_element('text', 3, id='b', content='It expands only when evidence is uncertain.'),
        make_element('text', 4, id='after', content='Later discussion.'),
    ]
    llm = QueueLLM(
        '{"decision":"continue","confidence":0.87,"reasons":["same setup"],"needs_more_context":false}',
        (
            '{"decision":"unsure","confidence":0.4,"reasons":["need neighbors"],'
            '"needs_more_context":true,'
            '"context_request":{"expand_left_elements":2,"expand_right_elements":2,"reason":"need local neighbors"}}'
        ),
        '{"decision":"continue","confidence":0.88,"reasons":["expanded context continues the same idea"],"needs_more_context":false}',
        '{"decision":"continue","confidence":0.87,"reasons":["same discussion"],"needs_more_context":false}',
    )
    config = BuilderConfig(CONTEXT_EXPANSION_MAX_REQUESTS=1, CONTEXT_EXPANSION_MAX_ELEMENTS=2)
    chunker = make_chunker(llm_client=llm, config=config, type_priors={('text', 'text'): 0.5})
    chunker._compute_similarity_stats = lambda texts: ([0.5, 0.5, 0.5], 0.5, 0.0)

    groups = chunker.build_refined_groups(make_document(elements), allow_llm=True)

    assert [group.element_ids for group in groups] == [['before', 'a', 'b', 'after']]
    assert chunker.llm_calls == 4
    assert groups[0].probe_decisions[1].decision == 'continue'
    assert groups[0].probe_decisions[1].context_expansions == 1
    assert 'A. [text, page 1] Background setup.' in llm.prompts[2]
    assert 'D. [text, page 1] Later discussion.' in llm.prompts[2]


def test_repaired_groups_merge_heading_with_body():
    elements = [
        make_element('title', 1, id='heading', content='Closest Pair'),
        make_element('text', 2, id='body', content='The closest pair problem asks for the nearest two points.'),
    ]
    chunker = make_chunker()
    chunker._compute_similarity_stats = lambda texts: ([0.5], 0.5, 0.0)

    groups = chunker.build_repaired_groups(make_document(elements), allow_llm=False)

    assert [group.element_ids for group in groups] == [['heading', 'body']]
    assert [decision.action for decision in chunker.repair_decisions] == ['merge_heading_with_next']
    assert groups[0].stability == 'repaired'


def test_repaired_groups_attach_orphan_support_to_next_heading_body():
    elements = [
        make_element('text', 1, id='prior', content='The previous topic is complete.'),
        make_element('figure', 2, id='figure', content={'raw_text': 'A DNA helix diagram'}),
        make_element('title', 3, id='heading', content='DNA'),
        make_element('text', 4, id='body', content='DNA stores inherited information.'),
    ]
    chunker = make_chunker()
    chunker._compute_similarity_stats = lambda texts: ([0.5, 0.5, 0.5], 0.5, 0.0)

    groups = chunker.build_repaired_groups(make_document(elements), allow_llm=False)

    assert [group.element_ids for group in groups] == [['prior'], ['figure', 'heading', 'body']]
    assert [decision.action for decision in chunker.repair_decisions] == [
        'merge_orphan_support_with_next',
        'merge_repaired_scaffold_with_body',
    ]


def test_repaired_groups_keep_owned_formula_with_previous_text():
    elements = [
        make_element('text', 1, id='setup', content='The recurrence is:'),
        make_element('formula', 2, id='formula', content={'latex': 'T(n) = 2T(n/2) + n'}),
        make_element('title', 3, id='heading', content='Next Section'),
        make_element('text', 4, id='body', content='This section introduces the next topic.'),
    ]
    chunker = make_chunker(type_priors={('text', 'formula'): 0.0})
    chunker._compute_similarity_stats = lambda texts: ([0.5, 0.5, 0.5], 0.5, 0.0)

    groups = chunker.build_repaired_groups(make_document(elements), allow_llm=False)

    assert [group.element_ids for group in groups] == [['setup', 'formula'], ['heading', 'body']]
    assert [decision.action for decision in chunker.repair_decisions] == [
        'merge_orphan_support_with_previous',
        'merge_heading_with_next',
    ]


def test_repaired_groups_do_not_guess_trailing_support_owner():
    elements = [
        make_element('text', 1, id='prior', content='The previous topic is complete.'),
        make_element('figure', 2, id='figure', content={'raw_text': 'A DNA double helix diagram'}),
        make_element('title', 3, id='heading', content='DNA'),
        make_element('text', 4, id='body', content='DNA stores inherited information.'),
    ]
    chunker = make_chunker(type_priors={('text', 'figure'): 0.9})
    chunker._compute_similarity_stats = lambda texts: ([0.5, 0.5, 0.5], 0.5, 0.0)

    groups = chunker.build_repaired_groups(make_document(elements), allow_llm=False)

    assert [group.element_ids for group in groups] == [['prior', 'figure'], ['heading', 'body']]
    assert [decision.action for decision in chunker.repair_decisions] == ['merge_heading_with_next']


def test_repaired_groups_llm_audit_moves_trailing_support_to_next_heading():
    elements = [
        make_element('text', 1, id='prior', content='The previous topic is complete.'),
        make_element('figure', 2, id='figure', content={'raw_text': 'A DNA double helix diagram'}),
        make_element('title', 3, id='heading', content='DNA'),
        make_element('text', 4, id='body', content='DNA stores inherited information.'),
    ]
    llm = QueueLLM(
        '{"action":"move_current_suffix_to_next","confidence":0.9,"reason":"the figure illustrates the DNA section","element_ids":["figure"]}'
    )
    config = BuilderConfig(MAX_LLM_CALLS_PER_BOUNDARY=0)
    chunker = make_chunker(llm_client=llm, config=config, type_priors={('text', 'figure'): 0.9})
    chunker._compute_similarity_stats = lambda texts: ([0.5, 0.5, 0.5], 0.5, 0.0)

    groups = chunker.build_repaired_groups(make_document(elements), allow_llm=True)

    assert [group.element_ids for group in groups] == [['prior'], ['figure', 'heading', 'body']]
    assert chunker.llm_calls == 1
    assert chunker.repair_decisions[-1].source == 'llm'
    assert chunker.repair_decisions[-1].action == 'move_current_suffix_to_next'
    assert llm.calls[0]['response_format']['json_schema']['name'] == 'local_chunk_audit'
    assert 'Current chunk under review:' in llm.prompts[0]
    assert 'Risk flags:' in llm.prompts[0]
    assert 'Same broad topic is not enough reason to move or merge elements.' in llm.prompts[0]
    assert 'Do not move edge elements if doing so leaves the current chunk heading-only' in llm.prompts[0]


def test_repaired_groups_llm_audit_expands_context_on_wider_review():
    elements = [
        make_element('text', 1, id='prior-a', content='The previous topic is complete.'),
        make_element('text', 2, id='prior-b', content='It does not mention DNA diagrams.'),
        make_element('figure', 3, id='figure', content={'raw_text': 'A DNA double helix diagram'}),
        make_element('title', 4, id='heading', content='DNA'),
        make_element('text', 5, id='body', content='DNA stores inherited information.'),
    ]
    llm = QueueLLM(
        '{"action":"needs_wider_review","confidence":0.9,"reason":"need the next body text","element_ids":[]}',
        '{"action":"move_current_suffix_to_next","confidence":0.9,"reason":"the figure illustrates the expanded DNA section","element_ids":["figure"]}',
    )
    config = BuilderConfig(
        LOCAL_AUDIT_EDGE_ELEMENTS=1,
        LOCAL_AUDIT_MAX_CALLS=2,
        CONTEXT_EXPANSION_MAX_ELEMENTS=3,
    )
    chunker = make_chunker(llm_client=llm, config=config)
    views = [
        chunker._element_view(element, chunker.preprocessor.to_text(element))
        for element in elements
    ]
    groups = [
        RefinedChunkGroup(
            group_id='group-0',
            group_index=0,
            source_block_id='block-0',
            elements=views[:3],
            start_element_index=0,
            end_element_index=2,
            stability='likely_good',
            reason_summary='test',
        ),
        RefinedChunkGroup(
            group_id='group-1',
            group_index=1,
            source_block_id='block-0',
            elements=views[3:],
            start_element_index=3,
            end_element_index=4,
            stability='likely_good',
            reason_summary='test',
        ),
    ]

    repaired = chunker._llm_audit_repaired_groups(document_id='doc', groups=groups)

    assert [group.element_ids for group in repaired] == [
        ['prior-a', 'prior-b'],
        ['figure', 'heading', 'body'],
    ]
    assert chunker.llm_calls == 2
    assert 'N2. [id=body' not in llm.prompts[0]
    assert 'expanded second-pass review' in llm.prompts[1]
    assert 'N2. [id=body' in llm.prompts[1]


def test_repaired_groups_llm_audit_rejects_low_confidence_action():
    elements = [
        make_element('text', 1, id='prior', content='The previous topic is complete.'),
        make_element('figure', 2, id='figure', content={'raw_text': 'A DNA double helix diagram'}),
        make_element('title', 3, id='heading', content='DNA'),
        make_element('text', 4, id='body', content='DNA stores inherited information.'),
    ]
    llm = QueueLLM(
        '{"action":"move_current_suffix_to_next","confidence":0.2,"reason":"too uncertain","element_ids":["figure"]}'
    )
    config = BuilderConfig(MAX_LLM_CALLS_PER_BOUNDARY=0)
    chunker = make_chunker(llm_client=llm, config=config, type_priors={('text', 'figure'): 0.9})
    chunker._compute_similarity_stats = lambda texts: ([0.5, 0.5, 0.5], 0.5, 0.0)

    groups = chunker.build_repaired_groups(make_document(elements), allow_llm=True)

    assert [group.element_ids for group in groups] == [['prior', 'figure'], ['heading', 'body']]
    assert chunker.llm_calls == 1
    assert [decision.action for decision in chunker.repair_decisions] == ['merge_heading_with_next']


def test_repaired_groups_rejects_non_support_suffix_move_from_normal_chunk():
    elements = [
        make_element('title', 1, id='heading', content='Chromosomes'),
        make_element('text', 2, id='body', content='Somatic cells have 46 chromosomes.'),
        make_element('title', 3, id='next-heading', content='Mitosis'),
        make_element('text', 4, id='next-body', content='Mitosis replicates somatic cells.'),
    ]
    chunker = make_chunker()
    views = [
        chunker._element_view(element, chunker.preprocessor.to_text(element))
        for element in elements
    ]
    states = [
        _RepairGroupState(
            source_group_ids=['current'],
            source_block_ids=['block'],
            elements=views[:2],
            internal_boundaries=[],
            probe_decisions=[],
            repair_decisions=[],
            stability='likely_good',
            reason_summary='test',
        ),
        _RepairGroupState(
            source_group_ids=['next'],
            source_block_ids=['block'],
            elements=views[2:],
            internal_boundaries=[],
            probe_decisions=[],
            repair_decisions=[],
            stability='likely_good',
            reason_summary='test',
        ),
    ]

    moved = chunker._move_current_suffix_to_next(
        states,
        0,
        element_ids=['body'],
        confidence=1.0,
        reason='bad model move',
    )

    assert moved is False
    assert [element.element_id for element in states[0].elements] == ['heading', 'body']
    assert [element.element_id for element in states[1].elements] == ['next-heading', 'next-body']
    assert chunker.repair_decisions == []


def test_repaired_groups_rejects_suffix_move_that_leaves_heading_orphan():
    elements = [
        make_element('title', 1, id='heading', content='Punnett Square'),
        make_element('figure', 2, id='figure', content={'raw_text': 'Punnett square diagram'}),
        make_element('title', 3, id='next-heading', content='Eye Color'),
        make_element('text', 4, id='next-body', content='Eye color is controlled by many genes.'),
    ]
    chunker = make_chunker()
    views = [
        chunker._element_view(element, chunker.preprocessor.to_text(element))
        for element in elements
    ]
    states = [
        _RepairGroupState(
            source_group_ids=['current'],
            source_block_ids=['block'],
            elements=views[:2],
            internal_boundaries=[],
            probe_decisions=[],
            repair_decisions=[],
            stability='likely_good',
            reason_summary='test',
        ),
        _RepairGroupState(
            source_group_ids=['next'],
            source_block_ids=['block'],
            elements=views[2:],
            internal_boundaries=[],
            probe_decisions=[],
            repair_decisions=[],
            stability='likely_good',
            reason_summary='test',
        ),
    ]

    moved = chunker._move_current_suffix_to_next(
        states,
        0,
        element_ids=['figure'],
        confidence=1.0,
        reason='bad orphaning move',
    )

    assert moved is False
    assert [element.element_id for element in states[0].elements] == ['heading', 'figure']
    assert [element.element_id for element in states[1].elements] == ['next-heading', 'next-body']
    assert chunker.repair_decisions == []


def test_repaired_groups_llm_audit_splits_current_chunk_into_three_pieces():
    elements = [
        make_element('text', 1, id='lists', content='The method first constructs four sorted lists.'),
        make_element('text', 2, id='qy', content='Qy contains points in Q sorted by y-coordinate.'),
        make_element('text', 3, id='rx', content='Rx contains points in R sorted by x-coordinate.'),
        make_element('text', 4, id='solve-q', content='Then recursively solve the closest pair in Q.'),
        make_element('text', 5, id='solve-r', content='Similarly, recursively solve the closest pair in R.'),
        make_element('text', 6, id='merge', content='Now compare candidates that cross the partition.'),
    ]
    llm = QueueLLM(
        '{"action":"split_current","confidence":0.9,"reason":"the chunk contains list construction, recursive calls, and merge transition","element_ids":["solve-q","merge"]}'
    )
    config = BuilderConfig(MAX_LLM_CALLS_PER_BOUNDARY=0)
    chunker = make_chunker(llm_client=llm, config=config, type_priors={('text', 'text'): 0.9})
    chunker._compute_similarity_stats = lambda texts: ([0.1] * 5, 0.1, 0.0)

    groups = chunker.build_repaired_groups(make_document(elements), allow_llm=True)

    assert [group.element_ids for group in groups] == [['lists', 'qy', 'rx'], ['solve-q', 'solve-r'], ['merge']]
    assert chunker.llm_calls == 1
    assert chunker.repair_decisions[-1].source == 'llm'
    assert chunker.repair_decisions[-1].action == 'split_current'
    assert 'split_current' in llm.prompts[0]
    assert 'small knowledge unit' in llm.prompts[0]


def test_repaired_groups_llm_audit_rejects_split_into_more_than_three_pieces():
    elements = [
        make_element('text', 1, id='a', content='First complete idea.'),
        make_element('text', 2, id='b', content='Second complete idea.'),
        make_element('text', 3, id='c', content='Third complete idea.'),
        make_element('text', 4, id='d', content='Fourth complete idea.'),
        make_element('text', 5, id='e', content='Fifth complete idea.'),
        make_element('text', 6, id='f', content='Sixth complete idea.'),
    ]
    llm = QueueLLM(
        '{"action":"split_current","confidence":0.9,"reason":"too many independent ideas","element_ids":["b","c","d"]}'
    )
    config = BuilderConfig(MAX_LLM_CALLS_PER_BOUNDARY=0)
    chunker = make_chunker(llm_client=llm, config=config, type_priors={('text', 'text'): 0.9})
    chunker._compute_similarity_stats = lambda texts: ([0.1] * 5, 0.1, 0.0)

    groups = chunker.build_repaired_groups(make_document(elements), allow_llm=True)

    assert [group.element_ids for group in groups] == [['a', 'b', 'c', 'd', 'e', 'f']]
    assert chunker.llm_calls == 1
    assert chunker.repair_decisions == []


def test_local_audit_flags_mixed_visual_support_candidate():
    elements = [
        make_element('title', 1, id='heading', content='Heredity Punnett Square'),
        make_element('figure', 2, id='punnett', content={'raw_text': 'Punnett square with father gametes, mother gametes, brown eyes, and blue eyes'}),
        make_element('text', 3, id='eye-text', content='About 16 genes control eye color in humans.'),
        make_element('figure', 4, id='dihybrid', content={'raw_text': 'Dihybrid Punnett square with AB, Ab, aB, ab gametes and genotype cells'}),
        make_element('figure', 5, id='cell-figure', content={'raw_text': 'Cell anatomy diagram with nucleus, chromosome material, ribosomes, and mitochondrion'}),
        make_element('text', 6, id='next-body', content='Somatic cells contain chromosomes in the nucleus.'),
    ]
    chunker = make_chunker()
    views = [
        chunker._element_view(element, chunker.preprocessor.to_text(element))
        for element in elements
    ]
    current = _RepairGroupState(
        source_group_ids=['current'],
        source_block_ids=['block'],
        elements=views[:5],
        internal_boundaries=[],
        probe_decisions=[],
        repair_decisions=[],
        stability='likely_good',
        reason_summary='test',
    )
    next_state = _RepairGroupState(
        source_group_ids=['next'],
        source_block_ids=['block'],
        elements=views[5:],
        internal_boundaries=[],
        probe_decisions=[],
        repair_decisions=[],
        stability='likely_good',
        reason_summary='test',
    )

    flags = chunker._local_audit_risk_flags([current, next_state], 0)

    assert 'mixed_visual_support_candidate' in flags
    assert 'possible_internal_split' not in flags


def test_local_audit_flags_visual_edge_support_candidate():
    elements = [
        make_element('text', 1, id='eye-text', content='Eye color is controlled by many genes.'),
        make_element('figure', 2, id='cell-figure', content={'raw_text': 'Cell anatomy diagram with nucleus and chromosomes'}),
        make_element('title', 3, id='cells-heading', content='Cells'),
        make_element('text', 4, id='cells-body', content='Somatic cells contain chromosomes in the nucleus.'),
    ]
    chunker = make_chunker()
    views = [
        chunker._element_view(element, chunker.preprocessor.to_text(element))
        for element in elements
    ]
    current = _RepairGroupState(
        source_group_ids=['current'],
        source_block_ids=['block'],
        elements=views[:2],
        internal_boundaries=[],
        probe_decisions=[],
        repair_decisions=[],
        stability='likely_good',
        reason_summary='test',
    )
    next_state = _RepairGroupState(
        source_group_ids=['next'],
        source_block_ids=['block'],
        elements=views[2:],
        internal_boundaries=[],
        probe_decisions=[],
        repair_decisions=[],
        stability='likely_good',
        reason_summary='test',
    )

    flags = chunker._local_audit_risk_flags([current, next_state], 0)

    assert 'visual_edge_support_candidate' in flags
    assert 'mixed_visual_support_candidate' not in flags


def test_local_audit_flags_singleton_text_chunk_for_llm_review():
    elements = [
        make_element('text', 1, id='singleton', content='Now suppose s and t are points in S.'),
        make_element('text', 2, id='next-body', content='Since each row has four boxes, the points must be nearby.'),
    ]
    chunker = make_chunker()
    views = [
        chunker._element_view(element, chunker.preprocessor.to_text(element))
        for element in elements
    ]
    current = _RepairGroupState(
        source_group_ids=['current'],
        source_block_ids=['block'],
        elements=views[:1],
        internal_boundaries=[],
        probe_decisions=[],
        repair_decisions=[],
        stability='likely_good',
        reason_summary='test',
    )
    next_state = _RepairGroupState(
        source_group_ids=['next'],
        source_block_ids=['block'],
        elements=views[1:],
        internal_boundaries=[],
        probe_decisions=[],
        repair_decisions=[],
        stability='likely_good',
        reason_summary='test',
    )

    flags = chunker._local_audit_risk_flags([current, next_state], 0)
    prompt = chunker._local_audit_prompt([current, next_state], 0, flags)

    assert 'singleton_text_chunk' in flags
    assert 'single text-element chunk can be valid' in prompt


def test_repaired_groups_llm_audit_rechecks_new_edge_piece_after_split():
    elements = [
        make_element('title', 1, id='punnett-title', content='Punnett Square'),
        make_element('figure', 2, id='punnett-figure', content={'raw_text': 'Punnett square with dominant and recessive alleles'}),
        make_element('text', 3, id='cell-text', content='Cells contain chromosomes inside the nucleus.'),
        make_element('figure', 4, id='cell-figure', content={'raw_text': 'Cell anatomy diagram with nucleus and chromosomes'}),
        make_element('title', 5, id='cells-heading', content='Cells'),
        make_element('text', 6, id='cells-body', content='Somatic cells contain chromosomes in the nucleus.'),
    ]
    llm = QueueLLM(
        '{"action":"split_current","confidence":0.9,"reason":"the trailing cell material forms a second unit","element_ids":["cell-text"]}',
        '{"action":"move_current_suffix_to_next","confidence":0.88,"reason":"the cell unit belongs with the Cells section","element_ids":["cell-text","cell-figure"]}',
    )
    chunker = make_chunker(llm_client=llm)
    views = [
        chunker._element_view(element, chunker.preprocessor.to_text(element))
        for element in elements
    ]
    groups = [
        RefinedChunkGroup(
            group_id='group-0',
            group_index=0,
            source_block_id='block-0',
            elements=views[:4],
            start_element_index=0,
            end_element_index=3,
            stability='likely_good',
            reason_summary='test',
        ),
        RefinedChunkGroup(
            group_id='group-1',
            group_index=1,
            source_block_id='block-0',
            elements=views[4:],
            start_element_index=4,
            end_element_index=5,
            stability='likely_good',
            reason_summary='test',
        ),
    ]

    repaired = chunker._llm_audit_repaired_groups(document_id='doc', groups=groups)

    assert [group.element_ids for group in repaired] == [
        ['punnett-title', 'punnett-figure'],
        ['cell-text', 'cell-figure', 'cells-heading', 'cells-body'],
    ]
    assert chunker.llm_calls == 2
    assert [decision.action for decision in chunker.repair_decisions[-2:]] == [
        'split_current',
        'move_current_suffix_to_next',
    ]
    assert 'Current chunk under review:' in llm.prompts[1]
    assert 'C1. [id=cell-text' in llm.prompts[1]
    assert 'N1. [id=cells-heading' in llm.prompts[1]


def test_repaired_groups_merge_short_bridge_text_with_next_chunk():
    elements = [
        make_element('text', 1, id='bridge', content='The figure on the next slide shows the construction.'),
        make_element('title', 2, id='heading', content='Claim 5.1'),
        make_element('text', 3, id='body', content='The strip contains at most six candidate points.'),
    ]
    chunker = make_chunker()
    chunker._compute_similarity_stats = lambda texts: ([0.5, 0.5], 0.5, 0.0)

    groups = chunker.build_repaired_groups(make_document(elements), allow_llm=False)

    assert [group.element_ids for group in groups] == [['bridge', 'heading', 'body']]
    assert [decision.action for decision in chunker.repair_decisions] == [
        'merge_bridge_text_with_next',
        'merge_repaired_scaffold_with_body',
    ]


def test_chunker_splits_conservatively_on_llm_budget_exhaustion():
    elements = [make_element('text', 1, content='A'), make_element('table', 2, content={'headers': ['X'], 'rows': [['X'], ['1']]})]
    config = BuilderConfig(MAX_LLM_CALLS_PER_BOUNDARY=0)
    chunker = make_chunker(config=config)
    chunker._compute_similarity_stats = lambda texts: ([0.5], 0.5, 0.1)

    chunks = chunker.chunk(make_document(elements))

    assert len(chunks) == 2
    assert chunker.boundary_log[0].tier_used == '2'
    assert chunker.boundary_log[0].decision == 'split'
    assert 'budget exhausted' in chunker.boundary_log[0].notes


def test_chunker_records_recoverable_error_on_unresolved_boundary():
    elements = [
        make_element('text', 1, content='A'),
        make_element('figure', 2, content={'figure_type': 'image', 'ocr_text': ''}),
    ]
    config = BuilderConfig(
        ANCHOR_MIN_CONFIRMED=1,
        ANCHOR_WARMUP_THRESHOLD=0.0,
        MAX_PROBE_STEPS_PER_GROUP=0,
        MAX_LOCAL_RECOVERY_STEPS=0,
    )
    chunker = make_chunker(config=config)
    chunker._compute_similarity_stats = lambda texts: ([0.55], 0.55, 0.1)

    chunks = chunker.chunk(make_document(elements))

    assert len(chunks) == 2
    assert chunker.recoverable_errors
    assert 'defaulted to split' in chunker.recoverable_errors[0]
