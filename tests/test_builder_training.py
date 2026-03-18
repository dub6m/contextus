from pathlib import Path

from contextus.builder.training import AttachmentDirectionResolver, ChunkActionDataset, ChunkActionModel


def make_row(action: str, confidence: float = 0.9, needs_review: bool = False, **kwargs):
    row = {
        "weak_action": action,
        "weak_confidence": confidence,
        "weak_needs_review": needs_review,
        "type_histogram": {"text": 1},
        "contains_title": False,
        "contains_non_text": False,
        "singleton_chunk": True,
        "chunk_size": 1,
        "token_count": 10,
        "content_token_count": 8,
        "sentence_count": 1,
        "left_similarity": 0.0,
        "right_similarity": 0.0,
        "left_context_similarity": 0.0,
        "right_context_similarity": 0.0,
        "previous_substantive_distance": 1,
        "next_substantive_distance": 1,
        "previous_substantive_similarity": 0.0,
        "next_substantive_similarity": 0.0,
        "max_previous_similarity": 0.0,
        "token_substance": 0.6,
        "lexical_density": 0.7,
        "type_richness": 0.3,
        "left_independence": 1.0,
        "right_independence": 1.0,
        "novelty": 1.0,
        "rhetorical_penalty": 0.0,
        "duplicate_penalty": 0.0,
        "heading_score": 0.1,
        "proposition_score": 0.7,
        "admin_score": 0.0,
        "toc_score": 0.0,
        "artifact_score": 0.0,
        "list_item_score": 0.0,
        "heuristic_viability": 0.7,
        "chunk_text": "Chunk text",
        "left_chunk_text": "",
        "right_chunk_text": "",
        "left_context_text": "",
        "right_context_text": "",
        "previous_substantive_text": "",
        "next_substantive_text": "",
    }
    row.update(kwargs)
    return row


def make_training_rows() -> list[dict]:
    rows = []
    for index in range(12):
        rows.append(
            make_row(
                "standalone",
                chunk_text=f"Concept {index} is defined by a self-contained statement with enough detail.",
                token_count=18 + index,
                content_token_count=12 + index,
                sentence_count=2,
                proposition_score=0.92,
                heuristic_viability=0.84,
                previous_substantive_similarity=0.15,
                next_substantive_similarity=0.12,
            )
        )
        rows.append(
            make_row(
                "duplicate_drop",
                chunk_text=f"Repeated heading {index}",
                duplicate_penalty=0.96,
                heading_score=0.72,
                proposition_score=0.14,
                heuristic_viability=0.22,
                token_count=3,
                content_token_count=2,
                max_previous_similarity=0.94,
            )
        )
        rows.append(
            make_row(
                "support_only",
                contains_title=True,
                type_histogram={"title": 1},
                chunk_text=f"{index + 1}.1 Section heading",
                heading_score=0.94,
                proposition_score=0.18,
                heuristic_viability=0.34,
                token_count=4,
                content_token_count=2,
                left_chunk_text="Previous section summary",
                right_chunk_text="Detailed explanation of the section topic.",
                next_substantive_text="Detailed explanation of the section topic.",
                left_similarity=0.08,
                right_similarity=0.42,
                left_context_similarity=0.06,
                right_context_similarity=0.35,
                previous_substantive_similarity=0.10,
                next_substantive_similarity=0.48,
                previous_substantive_distance=2,
                next_substantive_distance=1,
            )
        )
        rows.append(
            make_row(
                "attach_right",
                contains_title=True,
                type_histogram={"title": 1},
                chunk_text=f"{index + 1}.1 Section content anchor",
                heading_score=0.76,
                proposition_score=0.28,
                heuristic_viability=0.34,
                token_count=5,
                content_token_count=3,
                left_chunk_text="Previous section summary",
                right_chunk_text="Detailed explanation of the section topic.",
                next_substantive_text="Detailed explanation of the section topic.",
                left_similarity=0.08,
                right_similarity=0.42,
                left_context_similarity=0.06,
                right_context_similarity=0.35,
                previous_substantive_similarity=0.10,
                next_substantive_similarity=0.48,
                previous_substantive_distance=2,
                next_substantive_distance=1,
            )
        )
        rows.append(
            make_row(
                "attach_left",
                chunk_text=f"1. Supporting point about the prior measure {index}.",
                list_item_score=0.86,
                proposition_score=0.24,
                heuristic_viability=0.38,
                token_count=8,
                content_token_count=5,
                left_chunk_text="Parent section discussion",
                right_chunk_text="Next heading",
                previous_substantive_text="Parent section discussion",
                next_substantive_text="Next section summary",
                left_similarity=0.34,
                right_similarity=0.06,
                left_context_similarity=0.30,
                right_context_similarity=0.04,
                previous_substantive_similarity=0.40,
                next_substantive_similarity=0.08,
                previous_substantive_distance=1,
                next_substantive_distance=2,
            )
        )
    return rows


def test_select_clean_rows_filters_low_confidence_and_review_rows():
    dataset = ChunkActionDataset()
    rows = [
        make_row("standalone", confidence=0.9, needs_review=False),
        make_row("attach_right", confidence=0.6, needs_review=False),
        make_row("attach_left", confidence=0.9, needs_review=True),
    ]

    clean_rows = dataset.select_clean_rows(rows, min_confidence=0.78)

    assert len(clean_rows) == 1
    assert clean_rows[0]["weak_action"] == "standalone"


def test_stage_matrices_split_actions_correctly():
    dataset = ChunkActionDataset()
    rows = make_training_rows()[:5]

    stage1_matrix, stage1_labels, stage1_features = dataset.build_stage1_matrix(rows)
    stage2_rows, promoted_count = dataset.select_stage2_rows(rows, min_confidence=0.78)
    stage2_matrix, stage2_labels, stage2_features = dataset.build_stage2_matrix(stage2_rows)

    assert stage1_matrix.shape == (5, len(stage1_features))
    assert stage1_labels.tolist() == ["standalone", "duplicate_drop", "attach", "attach", "attach"]
    assert promoted_count == 0
    assert stage2_matrix.shape == (2, len(stage2_features))
    assert stage2_labels.tolist() == ["attach_right", "attach_left"]
    assert "fit_delta" in stage2_features
    assert "type_count__text" in stage1_features


def test_stage2_row_selection_promotes_high_confidence_review_rows():
    dataset = ChunkActionDataset()
    resolver = AttachmentDirectionResolver(dataset)
    rows = [
        make_row(
            "attach_left",
            confidence=0.64,
            needs_review=True,
            chunk_text="Supporting list item for prior section.",
            list_item_score=0.82,
            proposition_score=0.18,
            left_chunk_text="Parent section discussion",
            right_chunk_text="Next heading",
            previous_substantive_text="Parent section discussion",
            next_substantive_text="Next section summary",
            left_similarity=0.28,
            right_similarity=0.02,
            left_context_similarity=0.24,
            right_context_similarity=0.01,
            previous_substantive_similarity=0.32,
            next_substantive_similarity=0.05,
            previous_substantive_distance=1,
            next_substantive_distance=2,
        )
    ]

    stage2_rows, promoted_count = dataset.select_stage2_rows(rows, min_confidence=0.78, resolver=resolver)

    assert promoted_count == 1
    assert len(stage2_rows) == 1
    assert stage2_rows[0]["weak_action"] == "attach_left"
    assert stage2_rows[0]["weak_needs_review"] is False
    assert stage2_rows[0]["direction_training_source"] == "promoted_review"


def test_two_stage_model_trains_and_predicts(tmp_path):
    rows = make_training_rows()
    model = ChunkActionModel()

    result = model.train(rows, min_confidence=0.78, holdout_fraction=0.25, random_state=7)

    assert result.total_clean_rows == len(rows)
    assert result.stage2_training_rows == 24
    assert result.stage2_promoted_review_rows == 0
    assert result.stage1.train_rows > result.stage1.test_rows > 0
    assert result.stage1.accuracy >= 0.8
    assert result.stage2 is not None
    assert result.stage2.accuracy >= 0.8
    assert result.stage2.labels == ["attach_left", "attach_right"]

    standalone_prediction = model.predict_row(
        make_row(
            "standalone",
            chunk_text="Independent concept with enough explanatory detail to remain a node.",
            proposition_score=0.94,
            heuristic_viability=0.88,
            token_count=20,
            content_token_count=14,
            sentence_count=2,
        )
    )
    assert standalone_prediction["action"] == "standalone"
    assert standalone_prediction["stage1_action"] == "standalone"
    assert standalone_prediction["needs_review"] is False

    heading_prediction = model.predict_row(
        make_row(
            "support_only",
            contains_title=True,
            type_histogram={"title": 1},
            chunk_text="REQUIREMENTS FOR",
            heading_score=0.96,
            proposition_score=0.1,
            heuristic_viability=0.28,
            token_count=2,
            content_token_count=1,
            right_chunk_text="Detailed requirements explanation.",
            next_substantive_text="Detailed requirements explanation.",
            left_chunk_text="Prior section",
            left_similarity=0.05,
            right_similarity=0.48,
            next_substantive_similarity=0.52,
            previous_substantive_similarity=0.08,
            previous_substantive_distance=2,
            next_substantive_distance=1,
        )
    )
    assert heading_prediction["action"] == "support_only"
    assert heading_prediction["used_rule"] == "support_only_role_gate"
    assert heading_prediction["needs_review"] is False

    right_prediction = model.predict_row(
        make_row(
            "attach_right",
            contains_title=True,
            type_histogram={"title": 1},
            chunk_text="Section content anchor",
            heading_score=0.76,
            proposition_score=0.28,
            heuristic_viability=0.34,
            token_count=5,
            content_token_count=3,
            left_chunk_text="Previous section summary",
            right_chunk_text="Detailed explanation of the section topic.",
            next_substantive_text="Detailed explanation of the section topic.",
            left_similarity=0.08,
            right_similarity=0.42,
            left_context_similarity=0.06,
            right_context_similarity=0.35,
            previous_substantive_similarity=0.10,
            next_substantive_similarity=0.48,
            previous_substantive_distance=2,
            next_substantive_distance=1,
        )
    )
    assert right_prediction["action"] == "attach_right"
    assert right_prediction["needs_review"] is False

    support_prediction = model.predict_row(
        make_row(
            "support_only",
            contains_title=True,
            type_histogram={"title": 1},
            chunk_text="Acknowledgments",
            heading_score=0.92,
            proposition_score=0.12,
            heuristic_viability=0.22,
            token_count=1,
            content_token_count=1,
            right_chunk_text="Funding information.",
            next_substantive_text="Funding information.",
            previous_substantive_distance=2,
            next_substantive_distance=1,
        )
    )
    assert support_prediction["action"] == "support_only"
    assert support_prediction["used_rule"] == "support_only_role_gate"
    assert support_prediction["needs_review"] is False

    left_prediction = model.predict_row(
        make_row(
            "attach_left",
            chunk_text="1. Supporting point about the prior measure.",
            list_item_score=0.88,
            proposition_score=0.2,
            heuristic_viability=0.36,
            token_count=8,
            content_token_count=5,
            left_chunk_text="Parent section discussion",
            right_chunk_text="Next section heading",
            previous_substantive_text="Parent section discussion",
            next_substantive_text="Next section summary",
            left_similarity=0.36,
            right_similarity=0.05,
            previous_substantive_similarity=0.42,
            next_substantive_similarity=0.09,
            previous_substantive_distance=1,
            next_substantive_distance=2,
        )
    )
    assert left_prediction["action"] == "attach_left"
    assert left_prediction["used_rule"] == "list_item_parent"
    assert left_prediction["needs_review"] is False

    model_path = model.save(tmp_path / "chunk-model.pkl")
    loaded = ChunkActionModel.load(model_path)
    loaded_prediction = loaded.predict_row(
        make_row(
            "attach_left",
            chunk_text="Respectfully submitted,",
            admin_score=0.9,
            proposition_score=0.0,
            heuristic_viability=0.18,
            token_count=2,
            content_token_count=2,
            left_chunk_text="Letter body",
            right_chunk_text="Original Signed By",
            previous_substantive_text="Letter body",
            left_similarity=0.30,
            previous_substantive_similarity=0.35,
            previous_substantive_distance=1,
            next_substantive_distance=3,
        )
    )
    assert loaded_prediction["action"] == "support_only"
    assert loaded_prediction["used_rule"] == "support_only_role_gate"