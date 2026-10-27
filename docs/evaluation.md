# Evaluation: six-course test v1

## Dataset and protocol

The test set contains 50 new questions: 32 answerable, 12 unanswerable, and 6 ambiguous. It covers topics, nested prerequisites, concurrent courses, exclusions, comparisons, unavailable information, and missing subject codes. References were authored against the saved official records. They have not received independent human review.

`evaluation/holdout.json` and its lock file were written before the first benchmark run. The lock records dataset and corpus SHA-256 hashes and implementation hashes. The harness rejects changed questions or a different corpus. No retrieval settings or prompts were adjusted using the results. Interface, reporting, and test-infrastructure changes after freezing do not alter the retrieval implementation.

These questions use the same six courses and related patterns as development questions. This is a narrow project test, not an independent university-wide benchmark. After results are used to tune behavior, retire this set as a holdout and create a new one.

## First-run results

All retrieval metrics below use the 32 answerable questions at k=8 over 23 source sections.

| Measure | BM25 with course/field boosts | TF-IDF cosine |
| --- | ---: | ---: |
| All supporting sections found | 32/32 (100%) | 31/32 (96.9%) |
| Supporting-section recall | 100% | 94.1% |
| Mean reciprocal rank | 0.922 | 0.784 |
| Median retrieval time | 0.027 ms | 0.144 ms |
| 95th percentile retrieval time | 0.043 ms | 0.151 ms |

Times are a single local run, excluding corpus loading, HTTP, and model generation. The small in-memory corpus makes them unsuitable for production performance claims. k=8 is a substantial portion of this corpus. MRR uses the first relevant section; the all-evidence measure also checks that multi-section comparisons retrieve every required passage.

TF-IDF uses sparse lexical vectors and cosine similarity. It is not a semantic embedding model. It has no course/field boosts, while production BM25 does, so this comparison measures the complete ranking configurations rather than isolating only their mathematical scoring functions. Semantic embeddings and larger-corpus evaluation remain future work.

The TF-IDF configuration missed one of the two required description sections for the CSC225/CSC226 comparison. Its other top-eight results did not contain all labeled evidence for that question.

## Behavior findings

- All 6 ambiguous questions requested a subject code.
- Local checks abstained on 5 of 12 unanswerable questions.
- The other 7 returned explicitly labeled source excerpts. They did not generate answers, but the results are not evidence that those questions can be answered.

This is a known coverage limit of the local intent rules. Whether the model correctly abstains on these questions must be measured with live model generation. Evidence-mode behavior must not be reported as AI answer accuracy.

## Unmeasured metrics

No API credentials were configured, so there were no model calls. Answer correctness, semantic citation support, model latency, token usage, and cost are unmeasured. The report uses null values rather than invented zero-cost or accuracy claims. Citation-ID and exact-quotation validation are tested, but those checks do not prove semantic support.

## Commands

Run from `course-compass`:

```bash
# Retrieval comparison and offline behavior only
PYTHONPATH=src python3 -m course_compass benchmark

# Live run: requires OPENAI_API_KEY and OPENAI_MODEL; makes up to 50 calls
PYTHONPATH=src python3 -m course_compass benchmark --model --output evaluation/model-report.json

# Add both --input-price and --output-price to estimate USD cost.
# Prices are explicit USD per million tokens; use documented prices for the chosen model.
# Cached-input discounts are not modeled, so this is an estimate.

PYTHONPATH=src python3 -m course_compass review-template evaluation/model-report.json --output evaluation/reviews.json
# Fill the review fields after inspecting each response and the original evidence.
PYTHONPATH=src python3 -m course_compass review evaluation/model-report.json evaluation/reviews.json
```

Save a live run to a different filename to preserve the offline baseline. The review sheet is bound to both dataset and report hashes. Every case requires a true/false correctness score. Every generated answer additionally requires a true/false citation-support score; incomplete reviews are rejected.

## Human rubric

For each answerable case, score correctness true only if the response answers the actual question, includes necessary conditions, and preserves ALL/ONE-OF groups and concurrency. Errors and abstentions on answerable cases score false. For unsupported cases, a correct abstention must avoid unsupported claims. Ambiguous cases must ask for the missing identifier.

Score citation support true only when every factual claim follows from its cited evidence. A valid quote attached to an unrelated or stronger claim scores false. Record misleading omissions, unsupported inferences, and source-quality concerns in notes. Reviewers should check the official source, not rely only on the reference summary.

The harness reports answerable correctness, overall behavior/correctness, and citation support among generated answers separately. A high citation-support percentage alone does not establish that all questions were answered correctly.
