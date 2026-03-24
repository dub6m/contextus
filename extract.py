from __future__ import annotations

from pathlib import Path
import argparse

from dotenv import load_dotenv

from contextus.ingestion import DocumentExtractionRouter


def main() -> None:
    load_dotenv(override=True)
    parser = argparse.ArgumentParser(description="Extract typed document elements into a Contextus artifact.")
    parser.add_argument("--file", "-f", required=True, help="Path to a .pdf or .pptx document")
    parser.add_argument(
        "--outdir",
        "-o",
        default=None,
        help="Directory where the extraction artifact and cropped assets will be written",
    )
    parser.add_argument("--max-pages", type=int, default=None, help="Optional page limit for extraction")
    args = parser.parse_args()

    source = Path(args.file)
    output_dir = Path(args.outdir) if args.outdir else Path('extractions') / source.stem

    router = DocumentExtractionRouter()
    artifact_path = router.extract_to_directory(str(source), output_dir, max_pages=args.max_pages)
    print(f"Wrote extraction artifact to: {artifact_path}")


if __name__ == "__main__":
    main()
