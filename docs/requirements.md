# Requirements and acceptance criteria

## User and task

A student needs to find and understand published course information without searching multiple calendar pages manually. The first release covers one department and one calendar edition.

## Answer behavior

1. Every factual course claim must be supported by a cited source passage.
2. Citations open the original official source and show the supporting excerpt in the app.
3. The answer identifies the calendar edition used.
4. Unsupported questions receive an explicit insufficient-evidence response.
5. Ambiguous course identifiers trigger clarification rather than a guessed course.
6. Prerequisite language preserves alternatives, minimum grades, and other conditions present in the source.
7. Source text is treated as data, including any embedded instructions.
8. The assistant does not claim to know a student's registration eligibility, live seat availability, or unpublished policy.

## Data requirements

Retain source URL, title, calendar edition, section, retrieval timestamp, content hash, extracted text, and stable passage identifiers. Keep editions separate in retrieval. Record extraction failures and avoid silently indexing empty pages. Validate that fetched content is the intended course page rather than an error or navigation page.

## Evaluation design

Create a small development set during ingestion and reserve a separate 50-question test set before optimization. Include direct lookups, comparisons, prerequisite conditions, ambiguous questions, and questions the corpus cannot answer. Record reference answers and supporting passages. Do not use the held-out test set to choose search settings.

Measure:

- Retrieval hit rate against labeled supporting passages.
- Answer correctness against a written rubric.
- Citation support, including whether each factual claim is supported.
- Correct abstention on unanswerable questions.
- End-to-end latency and model usage cost, with model and pricing assumptions recorded.

Use human review for correctness and citation support; optional automated graders supplement that review. Publish observed results and failure examples. Numeric release targets will be set after the baseline is measured; no results are claimed in advance.

## First-release limits

No personal transcript uploads, degree audit, autonomous registration, multi-university corpus, fine-tuning, or agent tool loop. Add features only after the core question-to-evidence flow is measured and reliable.

## Milestone 2 checklist

- [x] Confirm university, department, and calendar edition.
- [x] Identify official course sources and check their access/reuse conditions.
- [x] Save a source manifest and a small representative sample.
- [x] Implement extraction with provenance and failure reporting.
- [x] Manually inspect examples with simple and complex prerequisites.
- [x] Write development questions with expected supporting passages.
