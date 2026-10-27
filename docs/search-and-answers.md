# Search and cited answers

## Part 3: retrieval

Search uses a dependency-free BM25 implementation over the imported sections. Course codes are normalized so `CSC225`, `CSC 225`, and `CSC-225` match. Ranking adds explicit boosts for course identity and question-relevant fields, such as prerequisites versus descriptions. It does not use embeddings yet.

Each section is one passage. Prerequisite trees are kept whole because splitting inside an ALL/ONE-OF group could change the apparent requirement. Original HTML stays in the source corpus; search exposes the normalized text, section ID, URL, edition, and source-quality flags. The sample is small enough to build the in-memory index directly from verified JSON. SQLite persistence is deferred until corpus size or API usage justifies it.

`SearchIndex.load` rejects a failed import, manifest/corpus mismatch, duplicate section IDs, and the wrong calendar edition.

## Part 4: answers

The CLI defaults to **evidence mode**: it shows ranked excerpts and links without claiming to have answered the question. **Model mode** calls the OpenAI Responses API using a strict JSON schema. The model receives the question, edition, and retrieved excerpts as data. Instructions require supported claims, exact source quotations, preservation of prerequisite groups, and abstention when evidence is insufficient.

The application validates every claim's citation IDs and checks that quoted text literally occurs in a retrieved section. Citation URLs come from the corpus, never from the model. Unknown IDs, inaccurate quotations, missing citations, model refusals, incomplete responses, invalid JSON, and service errors produce an error rather than a displayed answer. Every response includes its edition, mode, elapsed time, and any returned model token usage. Cost is not computed without recorded model-specific prices.

**This validates citation existence and quotation accuracy, not whether the quoted passage logically supports the claim.** A model could still make an unsupported inference while citing real text. Human-reviewed answer evaluation and adversarial questions remain necessary in part 6. Keyword retrieval also cannot establish sufficiency on its own.

Before model invocation, local checks ask for clarification on bare course numbers and abstain on recognized requests for live seats, scheduling, or registration data absent from this corpus. These are conservative rules, not a comprehensive intent classifier. Current code normalization covers the subject prefixes present in the sample and its references.

## Run

From the project directory:

```bash
PYTHONPATH=src python3 -m course_compass search "What are the prerequisites for CSC 360?"
PYTHONPATH=src python3 -m course_compass ask "What must I complete before CSC 226?"
PYTHONPATH=src python3 -m course_compass ask "What are the prerequisites for 225?"
PYTHONPATH=src python3 -m course_compass evaluate --output evaluation/retrieval-baseline.json
```

To use model mode, set `OPENAI_API_KEY` and `OPENAI_MODEL` in the process environment, then run:

```bash
PYTHONPATH=src python3 -m course_compass ask "What must I complete before CSC 226?" --mode model
```

Do not put a key in the repository or a command you intend to share. `.env.example` lists the variable names; `.env` files are ignored, and automatic `.env` loading is not implemented. Model calls send the question and retrieved public excerpts to OpenAI and use `store: false`. The integration follows [Structured Outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs).

Add `--json` to `ask` for machine-readable output. `search` always returns JSON. `ask` exits nonzero on model or validation errors. There is no silent switch from a model failure to an apparently generated answer.

## Verification and measured limits

- 15 automated tests cover extraction, course-code matching, prerequisite ranking, bad imports, ambiguity, insufficient evidence, citation validation, missing credentials, request structure, refusals, incomplete responses, and service failures.
- `evaluation/retrieval-baseline.json` records full supporting-section recall for 8/8 answerable development questions at k=8, across a corpus of 23 sections. The other two questions exercise abstention and clarification.
- This small, visible development set is not held out, and k=8 retrieves a substantial portion of the sample. The result is a smoke check, not a generalization or answer-accuracy claim.
- Live model generation has not been tested because no API key is configured. Request serialization and response handling are tested with mocked HTTP responses. Credentials and a structured-output-capable model must be configured before that end-to-end check.
