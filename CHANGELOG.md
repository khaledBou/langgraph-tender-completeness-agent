# Changelog

All notable changes to this project are listed here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- LangGraph workflow that checks a tender application against a checklist: parallel file extraction and requirement checks, evidence validated against the source text, human review on doubtful findings, resume after a service restart through PostgreSQL checkpoints.
- Django REST API to create a review with files, follow its status, send reviewer decisions.
- Angular interface with the reviews list, the review form and the review detail.
- Docker Compose stack with PostgreSQL, the API and the interface, configurable through a single `.env` file.
- Command line runner and a deterministic model double for tests and CI.
- Specifications: expression of need, functional and technical specifications, Figma mockups.
- Evaluation set of twenty labelled applications with a runner, auditable results and the first run with Claude.
- Deployment guide for Scaleway.
- LangGraph Studio support through `langgraph.json` and the `make studio` target.
- Recovery command for reviews interrupted by a restart of the service.
- Evaluation results record whether the working tree was clean and a fingerprint of the code executed.

### Fixed

- Scaleway guide: the Compose override now removes the dependency on the local database with `!reset`; a plain empty list kept it and made the project invalid.
