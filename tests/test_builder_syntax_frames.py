from contextus.builder.dependency_resolver import normalize_term_text
from types import SimpleNamespace

from contextus.builder.syntax_frames import (
    ParsedSentence,
    ParsedSyntaxFrameProducer,
    ParsedToken,
    SignalSyntaxFrameProducer,
    StanzaSentenceParser,
)


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


def test_parsed_syntax_frame_producer_emits_definition_frame_from_copular_parse():
    text = "Closest pair problem is finding closest points."
    sentence = ParsedSentence(
        element_id="definition",
        proposition_id="definition::p00",
        sentence_index=0,
        text=text,
        tokens=(
            token(0, "Closest", upos="ADJ", head=2, dep="amod", start=0),
            token(1, "pair", upos="NOUN", head=2, dep="compound", start=8),
            token(2, "problem", upos="NOUN", head=4, dep="nsubj", start=13),
            token(3, "is", lemma="be", upos="AUX", head=4, dep="cop", start=21),
            token(4, "finding", lemma="find", upos="VERB", head=None, dep="root", start=24),
            token(5, "closest", upos="ADJ", head=6, dep="amod", start=32),
            token(6, "points", upos="NOUN", head=4, dep="obj", start=40),
        ),
    )

    result = ParsedSyntaxFrameProducer().produce(sentences=[sentence])

    assert [frame.predicate for frame in result.proof_frame_candidates] == ["definition"]
    frame = result.proof_frame_candidates[0]
    assert normalize_term_text(frame.slots["target"].text) == "closest pair problem"
    assert normalize_term_text(frame.slots["value"].text) == "finding closest points"
    assert {normalize_term_text(term.text) for term in result.term_candidates} >= {
        "closest pair problem",
        "finding closest points",
    }


def test_parsed_syntax_frame_producer_emits_bound_frame_from_numeric_modifier():
    text = "The strip contains at most seven candidate points."
    sentence = ParsedSentence(
        element_id="bound",
        proposition_id="bound::p00",
        sentence_index=0,
        text=text,
        tokens=(
            token(0, "The", upos="DET", head=1, dep="det", start=0),
            token(1, "strip", upos="NOUN", head=2, dep="nsubj", start=4),
            token(2, "contains", lemma="contain", upos="VERB", head=None, dep="root", start=10),
            token(3, "at", upos="ADP", head=5, dep="case", start=19),
            token(4, "most", upos="ADV", head=5, dep="advmod", start=22),
            token(5, "seven", lemma="7", upos="NUM", head=7, dep="nummod", start=27),
            token(6, "candidate", upos="NOUN", head=7, dep="compound", start=33),
            token(7, "points", upos="NOUN", head=2, dep="obj", start=43),
        ),
    )

    result = ParsedSyntaxFrameProducer().produce(sentences=[sentence])

    frame = result.proof_frame_candidates[0]
    assert frame.predicate == "bound"
    assert normalize_term_text(frame.slots["target"].text) == "candidate points"
    assert frame.constraints[0].operator == "<="
    assert frame.constraints[0].normalized_value == "7"
    assert frame.constraints[0].value_kind == "constant"


def test_parsed_syntax_frame_producer_keeps_route_frames_out_of_proof_frames():
    sentence = ParsedSentence(
        element_id="body",
        proposition_id="body::p00",
        sentence_index=0,
        text="This paragraph is under the closest pair heading.",
        tokens=(token(0, "paragraph", head=None, dep="root"),),
        route_links=("heading:closest-pair",),
    )

    result = ParsedSyntaxFrameProducer().produce(sentences=[sentence])

    assert result.proof_frame_candidates == ()
    assert [frame.predicate for frame in result.route_frame_candidates] == ["heading_of"]


def test_signal_syntax_frame_producer_caches_parsed_proposition_sentences():
    class FakeParser:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def parse(self, *, element_id, proposition_id, text):
            self.calls.append(text)
            return (
                ParsedSentence(
                    element_id=element_id,
                    proposition_id=proposition_id,
                    sentence_index=0,
                    text=text,
                    tokens=(
                        token(0, "Beta", upos="NOUN", head=1, dep="compound", start=0),
                        token(1, "concept", upos="NOUN", head=3, dep="nsubj", start=5),
                        token(2, "is", lemma="be", upos="AUX", head=3, dep="cop", start=13),
                        token(3, "defined", lemma="define", upos="VERB", head=None, dep="root", start=16),
                    ),
                ),
            )

    parser = FakeParser()
    producer = SignalSyntaxFrameProducer(parser=parser)
    proposition = SimpleNamespace(
        proposition_id="p0",
        element_id="e0",
        text="Beta concept is defined.",
    )

    first = producer.produce(signals=[], propositions=[proposition])
    second = producer.produce(signals=[], propositions=[proposition])

    assert len(parser.calls) == 1
    assert [frame.predicate for frame in first.proof_frame_candidates] == ["definition"]
    assert [frame.predicate for frame in second.proof_frame_candidates] == ["definition"]


def test_stanza_sentence_parser_converts_stanza_words_to_parsed_tokens():
    class FakeWord:
        def __init__(self, word_id, text, lemma, upos, head, deprel, start_char, end_char):
            self.id = word_id
            self.text = text
            self.lemma = lemma
            self.upos = upos
            self.head = head
            self.deprel = deprel
            self.start_char = start_char
            self.end_char = end_char

    class FakeSentence:
        words = (
            FakeWord(1, "Beta", "beta", "NOUN", 2, "compound", 0, 4),
            FakeWord(2, "concept", "concept", "NOUN", 4, "nsubj", 5, 12),
            FakeWord(3, "is", "be", "AUX", 4, "cop", 13, 15),
            FakeWord(4, "defined", "define", "VERB", 0, "root", 16, 23),
        )

    class FakeDoc:
        sentences = (FakeSentence(),)

    class FakePipeline:
        def __call__(self, text):
            return FakeDoc()

    parser = StanzaSentenceParser(pipeline=FakePipeline())

    sentences = parser.parse(element_id="e0", proposition_id="p0", text="Beta concept is defined.")

    assert sentences[0].tokens[0].index == 0
    assert sentences[0].tokens[0].head == 1
    assert sentences[0].tokens[3].head is None
    assert sentences[0].tokens[3].dep == "root"
