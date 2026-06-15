from types import SimpleNamespace

from contextus.builder.claim_frames import (
    ParsedClaimFrameBuilder,
    SignalClaimFrameProducer,
)
from contextus.builder.dependency_resolver import normalize_term_text
from contextus.builder.syntax_frames import ParsedSentence, ParsedToken


def token(
    index: int,
    text: str,
    *,
    lemma: str | None = None,
    upos: str = "NOUN",
    head: int | None = None,
    dep: str = "",
    start: int = 0,
) -> ParsedToken:
    return ParsedToken(
        index=index,
        text=text,
        lemma=lemma or text.lower(),
        upos=upos,
        head=head,
        dep=dep,
        start=start,
        end=start + len(text),
    )


def test_claim_frame_builder_extracts_basic_verb_claim():
    text = "The strip contains candidate points."
    sentence = ParsedSentence(
        element_id="e1",
        proposition_id="e1::p00",
        sentence_index=0,
        text=text,
        tokens=(
            token(0, "The", upos="DET", head=1, dep="det", start=0),
            token(1, "strip", head=2, dep="nsubj", start=4),
            token(2, "contains", lemma="contain", upos="VERB", head=None, dep="root", start=10),
            token(3, "candidate", head=4, dep="compound", start=19),
            token(4, "points", head=2, dep="obj", start=29),
        ),
    )

    frame = ParsedClaimFrameBuilder().build(sentences=[sentence])[0]

    assert normalize_term_text(frame.subject.text) == "strip"
    assert frame.relation.text == "contains"
    assert frame.relation.lemma == "contain"
    assert frame.relation.role == "verb"
    assert normalize_term_text(frame.object.text) == "candidate points"
    assert frame.frame_kind == "proof"


def test_claim_frame_builder_extracts_copular_claim():
    text = "The input is a list of n points."
    sentence = ParsedSentence(
        element_id="e2",
        proposition_id="e2::p00",
        sentence_index=0,
        text=text,
        tokens=(
            token(0, "The", upos="DET", head=1, dep="det", start=0),
            token(1, "input", head=4, dep="nsubj", start=4),
            token(2, "is", lemma="be", upos="AUX", head=4, dep="cop", start=10),
            token(3, "a", upos="DET", head=4, dep="det", start=13),
            token(4, "list", head=None, dep="root", start=15),
            token(5, "of", upos="ADP", head=7, dep="case", start=20),
            token(6, "n", head=7, dep="compound", start=23),
            token(7, "points", head=4, dep="nmod", start=25),
        ),
    )

    frame = ParsedClaimFrameBuilder().build(sentences=[sentence])[0]

    assert normalize_term_text(frame.subject.text) == "input"
    assert frame.relation.text == "is"
    assert frame.relation.lemma == "be"
    assert frame.relation.role == "copula"
    assert normalize_term_text(frame.object.text) == "a list of n points"


def test_claim_frame_builder_does_not_swallow_excluded_tokens_in_copular_object():
    text = "In this problem, the input is a list of n points."
    sentence = ParsedSentence(
        element_id="e2",
        proposition_id="e2::p00",
        sentence_index=0,
        text=text,
        tokens=(
            token(0, "In", upos="ADP", head=2, dep="case", start=0),
            token(1, "this", upos="DET", head=2, dep="det", start=3),
            token(2, "problem", head=7, dep="obl", start=8),
            token(3, "the", upos="DET", head=4, dep="det", start=17),
            token(4, "input", head=7, dep="nsubj", start=21),
            token(5, "is", lemma="be", upos="AUX", head=7, dep="cop", start=27),
            token(6, "a", upos="DET", head=7, dep="det", start=30),
            token(7, "list", head=None, dep="root", start=32),
            token(8, "of", upos="ADP", head=10, dep="case", start=37),
            token(9, "n", head=10, dep="compound", start=40),
            token(10, "points", head=7, dep="nmod", start=42),
        ),
    )

    frame = ParsedClaimFrameBuilder().build(sentences=[sentence])[0]

    assert normalize_term_text(frame.object.text) == "a list of n points"


def test_claim_frame_builder_uses_verbal_root_for_is_to_claims():
    text = "The problem is to find a pair of points."
    sentence = ParsedSentence(
        element_id="e4",
        proposition_id="e4::p00",
        sentence_index=0,
        text=text,
        tokens=(
            token(0, "The", upos="DET", head=1, dep="det", start=0),
            token(1, "problem", head=4, dep="nsubj:outer", start=4),
            token(2, "is", lemma="be", upos="AUX", head=4, dep="cop", start=12),
            token(3, "to", upos="PART", head=4, dep="mark", start=15),
            token(4, "find", lemma="find", upos="VERB", head=None, dep="root", start=18),
            token(5, "a", upos="DET", head=6, dep="det", start=23),
            token(6, "pair", head=4, dep="obj", start=25),
            token(7, "of", upos="ADP", head=8, dep="case", start=30),
            token(8, "points", head=6, dep="nmod", start=33),
        ),
    )

    frame = ParsedClaimFrameBuilder().build(sentences=[sentence])[0]

    assert normalize_term_text(frame.subject.text) == "problem"
    assert frame.relation.text == "find"
    assert frame.relation.lemma == "find"
    assert normalize_term_text(frame.object.text) == "a pair of points"


def test_claim_frame_builder_splits_qualifier_and_condition_by_attachment():
    text = "The strip contains at most seven candidate points if the merge step succeeds."
    sentence = ParsedSentence(
        element_id="e3",
        proposition_id="e3::p00",
        sentence_index=0,
        text=text,
        tokens=(
            token(0, "The", upos="DET", head=1, dep="det", start=0),
            token(1, "strip", head=2, dep="nsubj", start=4),
            token(2, "contains", lemma="contain", upos="VERB", head=None, dep="root", start=10),
            token(3, "at", upos="ADP", head=5, dep="case", start=19),
            token(4, "most", upos="ADV", head=5, dep="advmod", start=22),
            token(5, "seven", lemma="7", upos="NUM", head=7, dep="nummod", start=27),
            token(6, "candidate", head=7, dep="compound", start=33),
            token(7, "points", head=2, dep="obj", start=43),
            token(8, "if", upos="SCONJ", head=12, dep="mark", start=50),
            token(9, "the", upos="DET", head=11, dep="det", start=53),
            token(10, "merge", head=11, dep="compound", start=57),
            token(11, "step", head=12, dep="nsubj", start=63),
            token(12, "succeeds", lemma="succeed", upos="VERB", head=2, dep="advcl", start=68),
        ),
    )

    frame = ParsedClaimFrameBuilder().build(sentences=[sentence])[0]

    assert [normalize_term_text(item.text) for item in frame.qualifiers] == ["at most seven"]
    assert frame.qualifiers[0].target == "object"
    assert [normalize_term_text(item.text) for item in frame.conditions] == ["if the merge step succeeds"]
    assert frame.conditions[0].has_own_predicate is True


def test_claim_frame_builder_extracts_polarity_and_modality():
    text = "Candidate points may not be bounded."
    sentence = ParsedSentence(
        element_id="e4",
        proposition_id="e4::p00",
        sentence_index=0,
        text=text,
        tokens=(
            token(0, "Candidate", head=1, dep="compound", start=0),
            token(1, "points", head=5, dep="nsubj:pass", start=10),
            token(2, "may", lemma="may", upos="AUX", head=5, dep="aux", start=17),
            token(3, "not", lemma="not", upos="PART", head=5, dep="neg", start=21),
            token(4, "be", lemma="be", upos="AUX", head=5, dep="aux:pass", start=25),
            token(5, "bounded", lemma="bound", upos="VERB", head=None, dep="root", start=28),
        ),
    )

    frame = ParsedClaimFrameBuilder().build(sentences=[sentence])[0]

    assert normalize_term_text(frame.subject.text) == "candidate points"
    assert frame.object is None
    assert frame.polarity == "negative"
    assert frame.modality == "possible"


def test_signal_claim_frame_producer_sets_route_and_artifact_kinds_from_signals():
    class FakeParser:
        def parse(self, *, element_id, proposition_id, text):
            return (
                ParsedSentence(
                    element_id=element_id,
                    proposition_id=proposition_id,
                    sentence_index=0,
                    text=text,
                    tokens=(token(0, text, head=None, dep="root", start=0),),
                ),
            )

    propositions = [
        SimpleNamespace(proposition_id="h::p00", element_id="h", text="Closest Pair"),
        SimpleNamespace(proposition_id="f::p00", element_id="f", text="Figure shows a split."),
        SimpleNamespace(proposition_id="b::p00", element_id="b", text="Body claim."),
    ]
    signals = [
        SimpleNamespace(element_id="h", element_type="title", is_heading=True),
        SimpleNamespace(element_id="f", element_type="figure", is_heading=False),
        SimpleNamespace(element_id="b", element_type="text", is_heading=False),
    ]

    frames = SignalClaimFrameProducer(parser=FakeParser()).produce(signals=signals, propositions=propositions)

    assert [frame.frame_kind for frame in frames] == ["route", "artifact", "proof"]
