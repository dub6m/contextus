from __future__ import annotations

from pathlib import Path
import argparse
import json

from contextus.builder.training import ChunkActionDataset, ChunkActionModel


def main() -> None:
    """Train the clean-split two-stage baseline for chunk actions."""
    parser = argparse.ArgumentParser(description="Train a two-stage chunk-action model from labeled audit rows.")
    parser.add_argument("--input", "-i", required=True, help="Input labeled chunk-audit JSONL path")
    parser.add_argument("--model-out", default="models/chunk-action-logreg.pkl", help="Output path for the trained model artifact")
    parser.add_argument("--metrics-out", default="models/chunk-action-logreg.metrics.json", help="Output path for the training metrics JSON")
    parser.add_argument("--min-confidence", type=float, default=0.78, help="Minimum weak-label confidence to keep for training")
    parser.add_argument("--holdout", type=float, default=0.2, help="Fraction of clean rows reserved for held-out evaluation")
    args = parser.parse_args()

    dataset = ChunkActionDataset()
    rows = dataset.load_rows(Path(args.input))
    model = ChunkActionModel()
    result = model.train(rows, min_confidence=args.min_confidence, holdout_fraction=args.holdout)

    model_path = model.save(Path(args.model_out))
    metrics_path = Path(args.metrics_out)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")

    print(f"Saved model to: {model_path}")
    print(f"Saved metrics to: {metrics_path}")
    print(f"Clean rows: {result.total_clean_rows}")
    print(f"Stage 2 training rows: {result.stage2_training_rows}")
    print(f"Stage 2 promoted review rows: {result.stage2_promoted_review_rows}")
    print("Stage 1: coarse action")
    print(f"  Train rows: {result.stage1.train_rows}")
    print(f"  Test rows: {result.stage1.test_rows}")
    print(f"  Accuracy: {result.stage1.accuracy:.3f}")
    print(f"  Macro F1: {result.stage1.macro_f1:.3f}")
    print(f"  Weighted F1: {result.stage1.weighted_f1:.3f}")
    if result.stage2 is None:
        print("Stage 2: not trained")
    else:
        print("Stage 2: attachment direction")
        print(f"  Train rows: {result.stage2.train_rows}")
        print(f"  Test rows: {result.stage2.test_rows}")
        print(f"  Accuracy: {result.stage2.accuracy:.3f}")
        print(f"  Macro F1: {result.stage2.macro_f1:.3f}")
        print(f"  Weighted F1: {result.stage2.weighted_f1:.3f}")


if __name__ == "__main__":
    main()