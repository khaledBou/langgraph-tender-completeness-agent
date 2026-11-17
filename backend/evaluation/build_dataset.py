"""Write the evaluation cases to evaluation/dataset/<case>/ so they can be read and reviewed.

uv run python -m evaluation.build_dataset
"""

import json
import shutil
from dataclasses import asdict
from pathlib import Path

from evaluation.cases import REFERENCE_DATE, build_cases

DATASET_DIR = Path(__file__).parent / "dataset"


def main() -> None:
    if DATASET_DIR.exists():
        shutil.rmtree(DATASET_DIR)
    for case in build_cases():
        folder = DATASET_DIR / case.name
        (folder / "files").mkdir(parents=True)
        for name, content in case.files.items():
            (folder / "files" / name).write_bytes(content)
        expected = {
            "group": case.group,
            "description": case.description,
            "reference_date": REFERENCE_DATE,
            "expectations": {code: asdict(e) for code, e in case.expectations.items()},
            "final_verdict": case.final_verdict,
        }
        (folder / "expected.json").write_text(json.dumps(expected, indent=2) + "\n")
    print(f"{len(list(DATASET_DIR.iterdir()))} cases written to {DATASET_DIR}")


if __name__ == "__main__":
    main()
