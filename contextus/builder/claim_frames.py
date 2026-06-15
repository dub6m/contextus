from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Iterable, Mapping

from .dependency_resolver import SourceRef, normalize_term_text
from .syntax_frames import ParsedSentence, ParsedToken


SUPPORT_ELEMENT_TYPES = frozenset({"figure", "image", "chart", "diagram", "flowchart", "table", "formula"})
HEADING_ELEMENT_TYPES = frozenset({"title", "heading", "section_header"})


@dataclass(frozen=True)
class ClaimSpan:
    text: str
    normalized: str
    char_start: int
    char_end: int
    dep: str = ""
    head: str = ""
    token_indexes: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "token_indexes", tuple(self.token_indexes))


@dataclass(frozen=True)
class ClaimRelation:
    text: str
    normalized: str
    lemma: str
    role: str
    char_start: int
    char_end: int
    dep: str = ""
    head: str = ""
    token_indexes: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "token_indexes", tuple(self.token_indexes))


@dataclass(frozen=True)
class ClaimModifier:
    text: str
    normalized: str
    char_start: int
    char_end: int
    target: str
    dep: str = ""
    has_own_predicate: bool = False
    token_indexes: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "token_indexes", tuple(self.token_indexes))


@dataclass(frozen=True)
class ClaimFrame:
    frame_id: str
    proposition_id: str
    element_id: str
    sentence_index: int
    text: str
    subject: ClaimSpan | None = None
    relation: ClaimRelation | None = None
    object: ClaimSpan | None = None
    qualifiers: tuple[ClaimModifier, ...] = ()
    conditions: tuple[ClaimModifier, ...] = ()
    evidence_source: SourceRef | None = None
    polarity: str | None = None
    modality: str | None = None
    frame_kind: str = "proof"

    def __post_init__(self) -> None:
        object.__setattr__(self, "qualifiers", tuple(self.qualifiers))
        object.__setattr__(self, "conditions", tuple(self.conditions))


class ParsedClaimFrameBuilder:
    def build(
        self,
        *,
        sentences: Iterable[ParsedSentence],
        frame_kind_by_element_id: Mapping[str, str] | None = None,
    ) -> list[ClaimFrame]:
        frame_kinds = MappingProxyType(dict(frame_kind_by_element_id or {}))
        frames: list[ClaimFrame] = []
        for sentence in sentences:
            frame_kind = frame_kinds.get(sentence.element_id, "proof")
            frames.append(self._build_sentence_frame(sentence, frame_kind=frame_kind))
        return frames

    def _build_sentence_frame(self, sentence: ParsedSentence, *, frame_kind: str) -> ClaimFrame:
        root = _root_token(sentence.tokens)
        subject_token = _subject_token(sentence.tokens, root)
        object_token = _object_token(sentence.tokens, root)
        copula_token = _child_with_dep(sentence.tokens, root.index, {"cop"}) if root is not None else None
        relation_token = copula_token if copula_token is not None and root is not None and root.upos not in {"VERB", "AUX"} else root

        subject = _claim_span(sentence, _subtree_tokens(sentence.tokens, subject_token.index), include_determiners=False) if subject_token else None
        relation = _relation_span(relation_token)
        obj = (
            _claim_span(sentence, _copular_object_tokens(sentence.tokens, root, subject_token, copula_token), include_determiners=True)
            if relation_token is copula_token
            else _claim_span(sentence, _object_tokens(sentence.tokens, object_token), include_determiners=True)
        )
        qualifiers = tuple(_qualifiers(sentence, subject_token=subject_token, object_token=object_token, relation_token=root))
        conditions = tuple(_conditions(sentence, root))

        return ClaimFrame(
            frame_id=f"claim:{sentence.proposition_id}:{sentence.sentence_index:02d}",
            proposition_id=sentence.proposition_id,
            element_id=sentence.element_id,
            sentence_index=sentence.sentence_index,
            text=sentence.text,
            subject=subject,
            relation=relation,
            object=obj,
            qualifiers=qualifiers,
            conditions=conditions,
            evidence_source=SourceRef(
                element_id=sentence.element_id,
                proposition_id=sentence.proposition_id,
                sentence_index=sentence.sentence_index,
                char_start=0,
                char_end=len(sentence.text),
                text=sentence.text,
            ),
            polarity=_polarity(sentence.tokens, root),
            modality=_modality(sentence.tokens, root),
            frame_kind=frame_kind,
        )


class SignalClaimFrameProducer:
    def __init__(self, *, parser: object, frame_builder: ParsedClaimFrameBuilder | None = None) -> None:
        self.parser = parser
        self.frame_builder = frame_builder or ParsedClaimFrameBuilder()
        self._sentence_cache: dict[tuple[str, str, str], tuple[ParsedSentence, ...]] = {}

    def produce(self, *, signals: list[object], propositions: list[object]) -> list[ClaimFrame]:
        kind_by_element_id = {
            str(getattr(signal, "element_id", "")): _frame_kind_for_signal(signal)
            for signal in signals
            if str(getattr(signal, "element_id", ""))
        }
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
                parsed = tuple(self.parser.parse(element_id=element_id, proposition_id=proposition_id, text=text))
                self._sentence_cache[key] = parsed
            sentences.extend(parsed)
        return self.frame_builder.build(sentences=sentences, frame_kind_by_element_id=kind_by_element_id)


def _root_token(tokens: tuple[ParsedToken, ...]) -> ParsedToken | None:
    return next((token for token in tokens if token.head is None or token.dep == "root"), None)


def _token_by_index(tokens: tuple[ParsedToken, ...], index: int) -> ParsedToken | None:
    return next((token for token in tokens if token.index == index), None)


def _child_with_dep(tokens: tuple[ParsedToken, ...], head: int, deps: set[str]) -> ParsedToken | None:
    return next((token for token in tokens if token.head == head and token.dep in deps), None)


def _children_with_dep(tokens: tuple[ParsedToken, ...], head: int, deps: set[str]) -> list[ParsedToken]:
    return [token for token in tokens if token.head == head and token.dep in deps]


def _subject_token(tokens: tuple[ParsedToken, ...], root: ParsedToken | None) -> ParsedToken | None:
    if root is None:
        return None
    return next((token for token in tokens if token.head == root.index and (token.dep.startswith("nsubj") or token.dep.startswith("csubj"))), None)


def _object_token(tokens: tuple[ParsedToken, ...], root: ParsedToken | None) -> ParsedToken | None:
    if root is None:
        return None
    return _child_with_dep(tokens, root.index, {"obj", "iobj", "obl", "xcomp", "ccomp", "attr"})


def _subtree_tokens(tokens: tuple[ParsedToken, ...], root_index: int, *, excluded_roots: set[int] | None = None) -> list[ParsedToken]:
    excluded = excluded_roots or set()
    if root_index in excluded:
        return []
    children_by_head: dict[int, list[ParsedToken]] = {}
    for token in tokens:
        if token.head is None:
            continue
        children_by_head.setdefault(token.head, []).append(token)

    collected: list[ParsedToken] = []

    def collect(index: int) -> None:
        if index in excluded:
            return
        token = _token_by_index(tokens, index)
        if token is None:
            return
        collected.append(token)
        for child in children_by_head.get(index, []):
            collect(child.index)

    collect(root_index)
    return sorted(collected, key=lambda token: token.start)


def _object_tokens(tokens: tuple[ParsedToken, ...], object_token: ParsedToken | None) -> list[ParsedToken]:
    if object_token is None:
        return []
    excluded = {
        token.index
        for token in _children_with_dep(tokens, object_token.index, {"nummod"})
    }
    return _subtree_tokens(tokens, object_token.index, excluded_roots=excluded)


def _copular_object_tokens(
    tokens: tuple[ParsedToken, ...],
    root: ParsedToken | None,
    subject_token: ParsedToken | None,
    copula_token: ParsedToken | None,
) -> list[ParsedToken]:
    if root is None:
        return []
    excluded = {token.index for token in (subject_token, copula_token) if token is not None}
    excluded.update(token.index for token in _children_with_dep(tokens, root.index, {"obl", "advmod"}))
    if subject_token is not None:
        excluded.update(token.index for token in _subtree_tokens(tokens, subject_token.index))
    return _subtree_tokens(tokens, root.index, excluded_roots=excluded)


def _claim_span(sentence: ParsedSentence, tokens: list[ParsedToken], *, include_determiners: bool) -> ClaimSpan | None:
    usable = [
        token
        for token in tokens
        if token.text.strip()
        and token.upos != "PUNCT"
        and (include_determiners or token.dep != "det")
    ]
    if not usable:
        return None
    start = min(token.start for token in usable)
    end = max(token.end for token in usable)
    text = sentence.text[start:end].strip()
    normalized = normalize_term_text(text)
    if not normalized:
        return None
    head = next((token for token in usable if token.head not in {item.index for item in usable}), usable[-1])
    return ClaimSpan(
        text=text,
        normalized=normalized,
        char_start=start,
        char_end=end,
        dep=head.dep,
        head=head.lemma or head.text,
        token_indexes=tuple(token.index for token in usable),
    )


def _relation_span(token: ParsedToken | None) -> ClaimRelation | None:
    if token is None or not normalize_term_text(token.text):
        return None
    role = "copula" if token.dep == "cop" else "verb" if token.upos in {"VERB", "AUX"} else "predicate_head"
    return ClaimRelation(
        text=token.text,
        normalized=normalize_term_text(token.text),
        lemma=token.lemma or normalize_term_text(token.text),
        role=role,
        char_start=token.start,
        char_end=token.end,
        dep=token.dep,
        head=token.lemma or token.text,
        token_indexes=(token.index,),
    )


def _qualifiers(
    sentence: ParsedSentence,
    *,
    subject_token: ParsedToken | None,
    object_token: ParsedToken | None,
    relation_token: ParsedToken | None,
) -> list[ClaimModifier]:
    qualifiers: list[ClaimModifier] = []
    if object_token is not None:
        qualifiers.extend(
            _modifier_for_token(sentence, token, target="object")
            for token in _children_with_dep(sentence.tokens, object_token.index, {"nummod", "amod", "advmod"})
        )
    if subject_token is not None:
        qualifiers.extend(
            _modifier_for_token(sentence, token, target="subject")
            for token in _children_with_dep(sentence.tokens, subject_token.index, {"amod", "nummod", "advmod"})
        )
    if relation_token is not None:
        qualifiers.extend(
            _modifier_for_token(sentence, token, target="relation")
            for token in _children_with_dep(sentence.tokens, relation_token.index, {"advmod", "obl"})
            if token.dep != "neg"
        )
    return [qualifier for qualifier in qualifiers if qualifier is not None]


def _modifier_for_token(sentence: ParsedSentence, token: ParsedToken, *, target: str) -> ClaimModifier | None:
    span = _modifier_span(sentence, token)
    if span is None:
        return None
    start, end, text, token_indexes = span
    return ClaimModifier(
        text=text,
        normalized=normalize_term_text(text),
        char_start=start,
        char_end=end,
        target=target,
        dep=token.dep,
        has_own_predicate=_has_predicate([_token_by_index(sentence.tokens, index) for index in token_indexes]),
        token_indexes=tuple(token_indexes),
    )


def _modifier_span(sentence: ParsedSentence, token: ParsedToken) -> tuple[int, int, str, tuple[int, ...]] | None:
    tokens = _subtree_tokens(sentence.tokens, token.index)
    usable = [item for item in tokens if item.text.strip() and item.upos != "PUNCT"]
    if not usable:
        return None
    start = min(item.start for item in usable)
    end = max(item.end for item in usable)
    text = sentence.text[start:end].strip()
    if not normalize_term_text(text):
        return None
    return start, end, text, tuple(item.index for item in usable)


def _conditions(sentence: ParsedSentence, root: ParsedToken | None) -> list[ClaimModifier]:
    if root is None:
        return []
    conditions: list[ClaimModifier] = []
    for token in _children_with_dep(sentence.tokens, root.index, {"advcl"}):
        span = _modifier_span(sentence, token)
        if span is None:
            continue
        start, end, text, token_indexes = span
        conditions.append(
            ClaimModifier(
                text=text,
                normalized=normalize_term_text(text),
                char_start=start,
                char_end=end,
                target="claim",
                dep=token.dep,
                has_own_predicate=True,
                token_indexes=tuple(token_indexes),
            )
        )
    return conditions


def _has_predicate(tokens: Iterable[ParsedToken | None]) -> bool:
    return any(token is not None and token.upos in {"VERB", "AUX"} for token in tokens)


def _polarity(tokens: tuple[ParsedToken, ...], root: ParsedToken | None) -> str:
    if root is not None and any(token.head == root.index and token.dep == "neg" for token in tokens):
        return "negative"
    if any(token.dep == "neg" for token in tokens):
        return "negative"
    return "positive"


def _modality(tokens: tuple[ParsedToken, ...], root: ParsedToken | None) -> str:
    if root is None:
        return "asserted"
    aux_lemmas = {
        normalize_term_text(token.lemma or token.text)
        for token in tokens
        if token.head == root.index and token.dep.startswith("aux")
    }
    if aux_lemmas & {"may", "might", "can", "could"}:
        return "possible"
    if aux_lemmas & {"must", "should", "shall", "need"}:
        return "required"
    return "asserted"


def _frame_kind_for_signal(signal: object) -> str:
    element_type = str(getattr(signal, "element_type", "")).lower()
    if element_type in SUPPORT_ELEMENT_TYPES:
        return "artifact"
    if bool(getattr(signal, "is_heading", False)) or element_type in HEADING_ELEMENT_TYPES:
        return "route"
    return "proof"
