from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Iterable

from .dependency_resolver import ConstraintCandidate, FrameCandidate, SlotCandidate, TermCandidate, normalize_term_text


@dataclass(frozen=True)
class ParsedToken:
    index: int
    text: str
    lemma: str
    upos: str
    head: int | None
    dep: str
    start: int
    end: int


@dataclass(frozen=True)
class ParsedSentence:
    element_id: str
    proposition_id: str
    sentence_index: int
    text: str
    tokens: tuple[ParsedToken, ...] = ()
    route_links: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "tokens", tuple(self.tokens))
        object.__setattr__(self, "route_links", tuple(self.route_links))


@dataclass(frozen=True)
class SyntaxFrameExtractionResult:
    term_candidates: tuple[TermCandidate, ...] = ()
    proof_frame_candidates: tuple[FrameCandidate, ...] = ()
    evidence_frame_candidates: tuple[FrameCandidate, ...] = ()
    route_frame_candidates: tuple[FrameCandidate, ...] = ()
    diagnostics: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "term_candidates", tuple(self.term_candidates))
        object.__setattr__(self, "proof_frame_candidates", tuple(self.proof_frame_candidates))
        object.__setattr__(self, "evidence_frame_candidates", tuple(self.evidence_frame_candidates))
        object.__setattr__(self, "route_frame_candidates", tuple(self.route_frame_candidates))
        object.__setattr__(self, "diagnostics", dict(self.diagnostics))

    @property
    def frame_candidates(self) -> tuple[FrameCandidate, ...]:
        return self.proof_frame_candidates + self.evidence_frame_candidates + self.route_frame_candidates


class ParsedSyntaxFrameProducer:
    def produce(self, *, sentences: Iterable[ParsedSentence]) -> SyntaxFrameExtractionResult:
        term_candidates: list[TermCandidate] = []
        proof_frames: list[FrameCandidate] = []
        route_frames: list[FrameCandidate] = []

        for sentence in sentences:
            for frame in self._definition_frames(sentence):
                proof_frames.append(frame)
                term_candidates.extend(_term_candidates_for_frame(frame))
            for frame in self._bound_frames(sentence):
                proof_frames.append(frame)
                term_candidates.extend(_term_candidates_for_frame(frame))
            for frame in self._route_frames(sentence):
                route_frames.append(frame)
                term_candidates.extend(_term_candidates_for_frame(frame))

        return SyntaxFrameExtractionResult(
            term_candidates=tuple(_dedupe_terms(term_candidates)),
            proof_frame_candidates=tuple(proof_frames),
            route_frame_candidates=tuple(route_frames),
        )

    def _definition_frames(self, sentence: ParsedSentence) -> list[FrameCandidate]:
        root = _root_token(sentence.tokens)
        if root is None:
            return []
        subject = _child_with_dep(sentence.tokens, root.index, {"nsubj", "nsubj:pass"})
        copula = _child_with_dep(sentence.tokens, root.index, {"cop"})
        if subject is None or copula is None:
            return []

        subject_tokens = _subtree_tokens(sentence.tokens, subject.index)
        subject_indexes = {token.index for token in subject_tokens}
        value_tokens = [
            token
            for token in _subtree_tokens(sentence.tokens, root.index)
            if token.index not in subject_indexes and token.dep != "cop" and token.upos != "PUNCT"
        ]
        target_span = _span_from_tokens(sentence, subject_tokens)
        value_span = _span_from_tokens(sentence, value_tokens)
        if target_span is None or value_span is None:
            return []
        target_start, target_end, target_text = target_span
        value_start, value_end, value_text = value_span
        return [
            FrameCandidate(
                frame_id=f"frame:{sentence.proposition_id}:syntax:definition:{sentence.sentence_index:02d}",
                element_id=sentence.element_id,
                proposition_id=sentence.proposition_id,
                sentence_index=sentence.sentence_index,
                predicate="definition",
                slots={
                    "target": SlotCandidate(
                        name="target",
                        text=target_text,
                        char_start=target_start,
                        char_end=target_end,
                        grounding_state="grounded",
                    ),
                    "value": SlotCandidate(
                        name="value",
                        text=value_text,
                        char_start=value_start,
                        char_end=value_end,
                        grounding_state="grounded",
                    ),
                },
                char_start=0,
                char_end=len(sentence.text),
                text=sentence.text,
                extraction_status="syntax_frame",
            )
        ]

    def _bound_frames(self, sentence: ParsedSentence) -> list[FrameCandidate]:
        frames: list[FrameCandidate] = []
        for number in sentence.tokens:
            if number.upos != "NUM" or number.head is None:
                continue
            target_head = _token_by_index(sentence.tokens, number.head)
            if target_head is None:
                continue
            excluded = {token.index for token in _subtree_tokens(sentence.tokens, number.index)}
            target_tokens = [
                token
                for token in _subtree_tokens(sentence.tokens, target_head.index)
                if token.index not in excluded and token.upos != "PUNCT"
            ]
            target_span = _span_from_tokens(sentence, target_tokens)
            if target_span is None:
                continue
            operator = _numeric_operator(sentence.text, number.start)
            if not operator:
                continue
            target_start, target_end, target_text = target_span
            normalized_value = number.lemma if number.lemma and any(char.isdigit() for char in number.lemma) else normalize_term_text(number.text)
            frames.append(
                FrameCandidate(
                    frame_id=f"frame:{sentence.proposition_id}:syntax:bound:{sentence.sentence_index:02d}:{number.index}",
                    element_id=sentence.element_id,
                    proposition_id=sentence.proposition_id,
                    sentence_index=sentence.sentence_index,
                    predicate="bound",
                    slots={
                        "target": SlotCandidate(
                            name="target",
                            text=target_text,
                            char_start=target_start,
                            char_end=target_end,
                            grounding_state="grounded",
                        )
                    },
                    constraints=(
                        ConstraintCandidate(
                            target_slot="target",
                            operator=operator,
                            value=number.text,
                            normalized_value=normalized_value,
                            value_kind="constant" if normalized_value and any(char.isdigit() for char in normalized_value) else "",
                            source_text=number.text,
                            char_start=number.start,
                            char_end=number.end,
                            grounding_state="grounded",
                        ),
                    ),
                    char_start=0,
                    char_end=len(sentence.text),
                    text=sentence.text,
                    extraction_status="syntax_frame",
                )
            )
        return frames

    def _route_frames(self, sentence: ParsedSentence) -> list[FrameCandidate]:
        frames: list[FrameCandidate] = []
        for index, route_link in enumerate(sentence.route_links):
            frames.append(
                FrameCandidate(
                    frame_id=f"frame:{sentence.proposition_id}:syntax:route:{sentence.sentence_index:02d}:{index:02d}",
                    element_id=sentence.element_id,
                    proposition_id=sentence.proposition_id,
                    sentence_index=sentence.sentence_index,
                    predicate="heading_of",
                    slots={
                        "target": SlotCandidate(
                            name="target",
                            text=sentence.text,
                            char_start=0,
                            char_end=len(sentence.text),
                            grounding_state="grounded",
                        ),
                        "route": SlotCandidate(
                            name="route",
                            text=route_link,
                            char_start=0,
                            char_end=0,
                            grounding_state="grounded",
                        ),
                    },
                    links=(route_link,),
                    char_start=0,
                    char_end=len(sentence.text),
                    text=sentence.text,
                    extraction_status="syntax_route",
                )
            )
        return frames


class StanzaSentenceParser:
    def __init__(
        self,
        *,
        pipeline: object | None = None,
        lang: str = "en",
        processors: str = "tokenize,mwt,pos,lemma,depparse",
        **pipeline_kwargs: object,
    ) -> None:
        if pipeline is None:
            import stanza

            pipeline = stanza.Pipeline(lang=lang, processors=processors, **pipeline_kwargs)
        self.pipeline = pipeline

    def parse(self, *, element_id: str, proposition_id: str, text: str) -> tuple[ParsedSentence, ...]:
        document = self.pipeline(text)
        parsed_sentences: list[ParsedSentence] = []
        cursor = 0
        for sentence_index, sentence in enumerate(getattr(document, "sentences", ()) or ()):
            tokens: list[ParsedToken] = []
            words = tuple(getattr(sentence, "words", ()) or ())
            for fallback_index, word in enumerate(words):
                word_text = str(getattr(word, "text", ""))
                start = getattr(word, "start_char", None)
                end = getattr(word, "end_char", None)
                if start is None or end is None:
                    start, end = _fallback_word_span(text, word_text, cursor)
                cursor = max(cursor, int(end))
                tokens.append(
                    ParsedToken(
                        index=_stanza_word_index(getattr(word, "id", fallback_index + 1), fallback_index),
                        text=word_text,
                        lemma=str(getattr(word, "lemma", "") or word_text.lower()),
                        upos=str(getattr(word, "upos", "") or getattr(word, "pos", "")),
                        head=_stanza_head_index(getattr(word, "head", 0)),
                        dep=str(getattr(word, "deprel", "") or getattr(word, "dependency_relation", "")),
                        start=int(start),
                        end=int(end),
                    )
                )
            parsed_sentences.append(
                ParsedSentence(
                    element_id=element_id,
                    proposition_id=proposition_id,
                    sentence_index=sentence_index,
                    text=text,
                    tokens=tuple(tokens),
                )
            )
        return tuple(parsed_sentences)


class SignalSyntaxFrameProducer:
    def __init__(
        self,
        *,
        parser: object,
        frame_producer: ParsedSyntaxFrameProducer | None = None,
    ) -> None:
        self.parser = parser
        self.frame_producer = frame_producer or ParsedSyntaxFrameProducer()
        self._sentence_cache: dict[tuple[str, str, str], tuple[ParsedSentence, ...]] = {}

    def produce(self, *, signals: list[object], propositions: list[object]) -> SyntaxFrameExtractionResult:
        signal_by_element_id = {str(getattr(signal, "element_id", "")): signal for signal in signals}
        sentences: list[ParsedSentence] = []
        for proposition in propositions:
            proposition_id = str(getattr(proposition, "proposition_id", ""))
            element_id = str(getattr(proposition, "element_id", ""))
            text = str(getattr(proposition, "text", ""))
            if not proposition_id or not element_id or not text.strip():
                continue
            key = (proposition_id, element_id, text)
            parsed = self._sentence_cache.get(key)
            if parsed is None:
                parsed = tuple(
                    self.parser.parse(
                        element_id=element_id,
                        proposition_id=proposition_id,
                        text=text,
                    )
                )
                self._sentence_cache[key] = parsed
            route_links = _route_links_for_signal(signal_by_element_id.get(element_id))
            if route_links:
                sentences.extend(
                    replace(sentence, route_links=tuple(dict.fromkeys([*sentence.route_links, *route_links])))
                    for sentence in parsed
                )
            else:
                sentences.extend(parsed)
        return self.frame_producer.produce(sentences=sentences)


def _root_token(tokens: tuple[ParsedToken, ...]) -> ParsedToken | None:
    return next((token for token in tokens if token.head is None or token.dep == "root"), None)


def _token_by_index(tokens: tuple[ParsedToken, ...], index: int) -> ParsedToken | None:
    return next((token for token in tokens if token.index == index), None)


def _child_with_dep(tokens: tuple[ParsedToken, ...], head: int, deps: set[str]) -> ParsedToken | None:
    return next((token for token in tokens if token.head == head and token.dep in deps), None)


def _subtree_tokens(tokens: tuple[ParsedToken, ...], root_index: int) -> list[ParsedToken]:
    children_by_head: dict[int, list[ParsedToken]] = {}
    for token in tokens:
        if token.head is None:
            continue
        children_by_head.setdefault(token.head, []).append(token)

    collected: list[ParsedToken] = []

    def collect(index: int) -> None:
        token = _token_by_index(tokens, index)
        if token is None:
            return
        collected.append(token)
        for child in children_by_head.get(index, []):
            collect(child.index)

    collect(root_index)
    return sorted(collected, key=lambda token: token.start)


def _span_from_tokens(sentence: ParsedSentence, tokens: list[ParsedToken]) -> tuple[int, int, str] | None:
    usable = [token for token in tokens if token.text.strip() and token.upos != "PUNCT"]
    if not usable:
        return None
    start = min(token.start for token in usable)
    end = max(token.end for token in usable)
    text = sentence.text[start:end].strip()
    if not normalize_term_text(text):
        return None
    return start, end, text


def _numeric_operator(text: str, number_start: int) -> str:
    before = text[max(0, number_start - 24) : number_start].lower()
    if "at most" in before or "no more than" in before:
        return "<="
    if "at least" in before or "no less than" in before:
        return ">="
    if "less than" in before:
        return "<"
    if "greater than" in before:
        return ">"
    return ""


def _term_candidates_for_frame(frame: FrameCandidate) -> list[TermCandidate]:
    terms = [
        TermCandidate(
            element_id=frame.element_id,
            text=slot.text,
            char_start=slot.char_start,
            char_end=slot.char_end,
            source_signal=f"syntax.{frame.predicate}.{slot.name}",
            head=_term_head(slot.text),
            modifiers=_term_modifiers(slot.text),
        )
        for slot in frame.slots.values()
        if normalize_term_text(slot.text)
    ]
    return terms


def _dedupe_terms(candidates: Iterable[TermCandidate]) -> list[TermCandidate]:
    deduped: dict[tuple[str, str, int, int, str], TermCandidate] = {}
    for candidate in candidates:
        key = (
            candidate.element_id,
            normalize_term_text(candidate.text),
            candidate.char_start,
            candidate.char_end,
            candidate.source_signal,
        )
        deduped.setdefault(key, candidate)
    return list(deduped.values())


def _term_head(text: str) -> str:
    parts = normalize_term_text(text).split()
    return parts[-1] if parts else ""


def _term_modifiers(text: str) -> tuple[str, ...]:
    parts = normalize_term_text(text).split()
    return tuple(parts[:-1])


def _route_links_for_signal(signal: object | None) -> tuple[str, ...]:
    if signal is None:
        return ()
    route_links: list[str] = []
    for heading in getattr(signal, "heading_path", []) or []:
        element_id = str(getattr(heading, "element_id", ""))
        if element_id:
            route_links.append(element_id)
    return tuple(dict.fromkeys(route_links))


def _stanza_word_index(raw_id: object, fallback_index: int) -> int:
    if isinstance(raw_id, (tuple, list)) and raw_id:
        raw_id = raw_id[0]
    try:
        return max(0, int(raw_id) - 1)
    except (TypeError, ValueError):
        return fallback_index


def _stanza_head_index(raw_head: object) -> int | None:
    try:
        head = int(raw_head)
    except (TypeError, ValueError):
        return None
    if head <= 0:
        return None
    return head - 1


def _fallback_word_span(text: str, word: str, cursor: int) -> tuple[int, int]:
    if not word:
        return cursor, cursor
    index = text.find(word, cursor)
    if index < 0:
        index = text.find(word)
    if index < 0:
        return cursor, cursor + len(word)
    return index, index + len(word)
