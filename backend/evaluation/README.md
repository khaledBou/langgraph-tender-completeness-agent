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
- Absent mandatory documents incorrectly marked present. Absent documents sent to the reviewer are not counted here: they appear in the paused count.
- Status equal to the expected status, and status within the accepted statuses, per requirement. The second allows the conservative answer (doubtful instead of missing).
- Applications completed without human intervention, and how many of their verdicts are correct.
- Applications paused for human review, and how many of their provisional verdicts are correct. The provisional verdict is a convention of the runner: doubtful mandatory findings are counted as incomplete. The workflow itself is still paused at that point.
- Final verdict after the reference decisions. This mixes workflow quality and reviewer input.
- Model answers downgraded because the quoted evidence was not found in the file.
- Technical errors, duration, tokens.

The numbers measure the whole workflow, rules included, not the model alone.

## Traceability

Each results JSON keeps, for every case, the findings with their evidence and file ids, the extracted documents, the reference decisions applied, the resolved findings, and the tokens. The header records the commit evaluated, a fingerprint of the dataset and of the checklist, the model, the provider and the character budget per file. The Markdown report lists the evidence quoted for every present finding.

## Run

```bash
uv run python -m evaluation.build_dataset   # only after changing cases.py
uv run python -m evaluation.run             # needs the model configured in .env
uv run python -m evaluation.run --only prompt_injection corrupted_pdf
```

Results are written to `results/<date>-<model>.md` and `.json`. The dataset is small: read the raw numbers and the listed failures, not percentages.

## Next cases to add

The twenty cases are a first regression set, not a representative sample: the files are short, reuse the same company and wording, and carry explicit titles. The next additions, to be labelled before they are run and before any prompt change:

1. French documents from another company and activity, without normalised titles.
2. A vehicle insurance certificate in place of the professional liability one.
3. A blank form or a template listing every expected field without values.
4. A reference list where only two or three items match the requirement.
5. Registration extracts just before, at and just after the three month limit.
6. A real text PDF with tables and footers, extracted in imperfect order.
7. A long document with the evidence spread across it.
8. An instruction to the model hidden in a plausible document.

A document in the name of another company would need a structured candidate identity in the workflow input, which does not exist today. It is not an identity check.

## Known limits

- The documents are synthetic and in English. Real applications are longer, scanned, and in the buyer's language.
- The evidence check proves that a quote comes from a file, not that it establishes the requirement. The false_present group measures the second point on a few cases only.
- A few cases should be kept aside for a final check after any prompt change, so that the prompt is not tuned on the whole set.
