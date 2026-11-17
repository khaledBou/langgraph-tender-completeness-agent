# Functional specification

## Objects

Checklist: an ordered list of requirements. Each requirement has a code, a label, a description, and a mandatory flag.

Application: the set of files submitted by one candidate. Supported formats: PDF, TXT, MD, CSV.

Review: one run of the check on one application. A review has a status, a list of findings, the decisions of the reviewer, a verdict, and a report.

## Statuses

Review status:

| Status | Meaning |
|---|---|
| pending | Created, not started |
| running | The workflow is executing |
| waiting_for_human | Paused on doubtful findings |
| completed | Report available |
| failed | Technical error, see message |

Finding status:

| Status | Meaning |
|---|---|
| present | A file covers the requirement, with validated evidence |
| missing | No file relates to the requirement |
| doubtful | A file may relate to the requirement but the model cannot confirm it, or the evidence could not be validated, or a file could not be read |

Document status:

| Status | Meaning |
|---|---|
| ok | Text extracted and described |
| unreadable | The file could not be read or described |

## Rules

1. A requirement is present only if the model points to one submitted file and quotes a passage that exists in that file. If the quote is not found in the file, the finding becomes doubtful.
2. If no file was submitted, every requirement is missing without calling the model.
3. If a file is unreadable, no requirement can be missing: each requirement not found elsewhere becomes doubtful, because the unreadable file may contain it.
4. The review pauses when at least one finding is doubtful. The reviewer must decide present or missing for every doubtful finding. Partial or unknown answers are rejected and the review stays paused.
5. The verdict is complete when every mandatory requirement is present after the reviewer decisions. Otherwise it is incomplete. The verdict is computed by code, not by the model.
6. Original findings are kept for audit. The resolved findings are the authoritative result.
7. A review can be resumed after a restart of the service, with the same review identifier.

## Screens

1. Reviews list: identifier, candidate name, status, verdict, date. Button to create a review.
2. New review: choose a checklist, name the candidate, upload the files, start.
3. Review detail: progress while running, table of findings with evidence and source file, decision form when paused, verdict and report when completed, error message when failed.

## Acceptance tests

| Id | Scenario | Expected |
|---|---|---|
| A1 | Complete application, all documents clear | All findings present, verdict complete, no pause |
| A2 | No file submitted | All findings missing, no model call, verdict incomplete |
| A3 | Insurance certificate for a past year | Finding doubtful, review pauses, reviewer answers missing, verdict incomplete |
| A4 | Reviewer answers only some doubtful findings | Answer rejected, review still paused |
| A5 | Reviewer answers with an unknown requirement code | Answer rejected, review still paused |
| A6 | Model quotes a passage that is not in the file | Finding doubtful, not present |
| A7 | One file is corrupted | Document unreadable, requirements not found elsewhere are doubtful, never missing |
| A8 | Service restarted while paused | Review resumes from the pause with the same identifier |
| A9 | Optional requirement missing | Verdict still complete if all mandatory requirements are present |
