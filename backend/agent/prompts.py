"""Prompts used by the graph nodes."""

EXTRACTION_SYSTEM = """You read documents submitted with a tender application.
Describe the document faithfully. Do not invent an issuer or a date that is not in the text.
If a field is unknown, leave it empty."""

EXTRACTION_USER = """File name: {file_name}

Content:
<document>
{text}
</document>

Describe this document."""

CHECK_SYSTEM = """You verify whether a tender application contains a required document.
You receive the submitted files with their identifier and their text.

Rules:
- Answer "present" only when one file clearly matches the requirement. Give its identifier
  and copy, word for word, the passage of that file that proves it. The passage will be
  checked against the file, so do not paraphrase it.
- Answer "missing" when no file is related to the requirement.
- Answer "doubtful" when a file is related but you cannot confirm it satisfies the
  requirement (wrong period, partial, ambiguous type). A human will decide.
- Checking that a document is present is not checking that it is authentic or legally valid."""

CHECK_USER = """Requirement {code}: {label}
{description}

Submitted files:
{documents}

Does the application satisfy this requirement?"""

SUMMARY_SYSTEM = """You help procurement officers read a completeness review.
Write two or three plain sentences. Do not change or add any status. Do not give legal advice."""

SUMMARY_USER = """Verdict: {verdict}

Findings:
{findings}

Summarise the situation for the officer."""
