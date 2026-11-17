# Evaluation

A small labelled dataset and a runner that measures the workflow with a real model.

## Dataset

Twenty synthetic applications in `dataset/`, built by `build_dataset.py` from `cases.py`. Each folder holds the submitted files and an `expected.json` with, for every requirement:

- `expected`: the status the workflow should give before any human decision
- `accepted`: the statuses counted as correct
- `decision`: the decision a reviewer would take when the finding is doubtful

and the verdict expected after those decisions. The reference date for time based requirements is 2026-11-17.

| Group | Cases | What is tested |
|---|---|---|
| complete | 3 | Separate files, one combined file, misleading file names |
| missing | 3 | One mandatory document absent, several absent, no file |
| optional | 2 | Optional document absent, mandatory absent with optional present |
| false_present | 3 | Document only mentioned, announced as not included, irrelevant quote |
| doubtful | 3 | Partial document, ambiguous type, period mismatch |
| unreadable | 2 | Corrupted PDF, scanned PDF without text |
| truncation | 2 | Evidence after the character budget, long text without the document |
| adversarial | 2 | Instructions inside a file, contradictory files |

## Measures

- False present: the document is absent or not provable and the workflow said present. This is the error that matters most.
- Missed mandatory missing: a mandatory document is absent and the workflow said present.
- Status within the accepted statuses: per requirement.
- Verdict before any human decision, with doubtful counted as not present.
- Verdict after the reference decisions.
- Applications paused for human review.
- Model answers downgraded because the quoted evidence was not found in the file.
- Technical errors, duration, tokens.

The verdict after the reference decisions mixes model quality and reviewer input. Read it together with the measures before any decision.

## Run

```bash
uv run python -m evaluation.build_dataset   # only after changing cases.py
uv run python -m evaluation.run             # needs the model configured in .env
uv run python -m evaluation.run --only prompt_injection corrupted_pdf
```

Results are written to `results/<date>-<model>.md` and `.json`. The dataset is small: read the raw numbers and the listed failures, not percentages.

## Known limits

- The documents are synthetic and in English. Real applications are longer, scanned, and in the buyer's language.
- The evidence check proves that a quote comes from a file, not that it establishes the requirement. The false_present group measures the second point on a few cases only.
- A few cases should be kept aside for a final check after any prompt change, so that the prompt is not tuned on the whole set.
