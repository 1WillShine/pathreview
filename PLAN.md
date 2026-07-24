## Solution Plan

**Issue:** [Add an integration test that runs the full RAG pipeline against a mock LLM](https://github.com/ascherj/pathreview/issues/38)

### Understand

**Expected behavior:** A test in `tests/integration/test_rag_pipeline.py` that wires retrieval → reranking → generation → parsing together and asserts the full pipeline produces valid structured output without making real API or database calls.

**Actual behavior:** `tests/integration/test_rag_pipeline.py` does not exist. `tests/integration/` contains only `__init__.py`. Unit tests cover each component in isolation but no test exercises the full chain together, meaning bugs that only appear when components are composed (e.g. a retriever returns unexpected score format that breaks the generator's context formatter) would go undetected.

**Root cause of the gap:** The integration test file was planned (referenced in the issue) but never implemented. The mock infrastructure already exists — `MockEmbeddingProvider` in `ingestion/embeddings/provider.py` provides deterministic 1536-dim embeddings with no API key required. A mock LLM response needs to be added to avoid calling OpenRouter/OpenAI.

### Map

Files I will read but not modify:
- `ingestion/embeddings/provider.py` — `MockEmbeddingProvider.embed()` is the mock embedding source
- `rag/retriever/vector_store.py` — `VectorStore` wraps ChromaDB; needs an in-memory client for testing
- `rag/retriever/keyword_search.py` — `KeywordSearcher.index()` and `.search()` use BM25
- `rag/retriever/hybrid.py` — `HybridRetriever.retrieve()` blends vector + keyword results
- `rag/generator/review_generator.py` — `ReviewGenerator.generate_full_review()` calls OpenAI client
- `rag/generator/output_parser.py` — `parse_review_output()` parses LLM response string
- `rag/generator/prompt_templates.py` — `get_template()` provides prompt strings
- `tests/unit/test_llm_provider_contract.py` — fixture pattern to follow
- `tests/conftest.py` — shared fixtures for sample resume and readme text

File I will create:
- `tests/integration/test_rag_pipeline.py` — the integration test

### Plan

1. **Set up in-memory ChromaDB and seed test chunks.** Use `chromadb.EphemeralClient()` (no disk persistence, no Docker needed) to create a test collection. Seed it with 2-3 sample text chunks embedded via `MockEmbeddingProvider` so the vector store has data to retrieve.

2. **Build and exercise `HybridRetriever`.** Instantiate `VectorStore` with the ephemeral client, instantiate `KeywordSearcher` and call `.index()` on the same chunks, then instantiate `HybridRetriever`. Call `.retrieve()` with a sample query and a mock query embedding from `MockEmbeddingProvider`. Assert the result is a non-empty list of dicts with `id`, `text`, `metadata`, and `score` keys.

3. **Mock the LLM call and run `ReviewGenerator`.** Patch `openai.OpenAI` using `unittest.mock.patch` so no real API call is made. Configure the mock to return a realistic JSON string matching the prompt template's expected output format. Instantiate `ReviewGenerator` with a dummy `ReviewConfig` and call `generate_full_review()` with sample profile data and the retrieved chunks.

4. **Assert parsed output structure.** Call `parse_review_output()` on the mocked response and assert it returns a list of `FeedbackSection` objects with non-empty `section_name`, `content`, and `confidence` fields. This validates the full retrieval → generation → parsing chain end-to-end.

5. **Add a negative-path test.** Test that the pipeline handles an empty retrieval result gracefully — `HybridRetriever.retrieve()` with no indexed chunks should return an empty list, and `generate_full_review()` called with empty chunks should still return a list of `FeedbackSection` objects (using the error fallback in `review_generator.py`).

### Inputs & Outputs

**Input:** A sample query string (e.g. `"Python FastAPI REST API"`), sample profile data dict with `github_username` and `projects` fields, and 2-3 sample text chunks seeded into the in-memory vector store.

**Output:** A list of `FeedbackSection` objects — one per section name in `["skills_feedback", "projects_feedback", "presentation_feedback", "gaps_feedback", "first_impression"]` — each with non-empty `section_name` and `content` fields and a `confidence` value between 0 and 1.

**What changes:** Only `tests/integration/test_rag_pipeline.py` is created. No production code is modified.

### Risks & Unknowns

- **ChromaDB ephemeral client availability:** `chromadb.EphemeralClient()` was introduced in ChromaDB 0.4+. The repo pins `chromadb>=0.29.0` (visible in the `=0.29.0` file in the repo root). Need to verify the installed version supports `EphemeralClient` — if not, fall back to `chromadb.Client()` with `Settings(is_persistent=False)`.

- **OpenAI mock patching path:** `review_generator.py` instantiates `openai.OpenAI` inside `__init__`. The mock patch path must be `rag.generator.review_generator.openai.OpenAI`, not `openai.OpenAI`, or the patch won't intercept the call. This needs to be verified when writing the test.

- **BM25 dependency:** `keyword_search.py` imports `rank_bm25`. Need to confirm it is in `pyproject.toml` and installed in the test environment without Docker.

- **Score threshold in HybridRetriever:** `retrieve()` filters results with `min_score=0.3` by default. With only 2-3 seeded chunks and mock embeddings, blended scores may fall below this threshold and return an empty list. May need to pass `min_score=0.0` in the test or seed more chunks.

### Edge Cases

- Empty retrieval result (no chunks above `min_score`) — pipeline should not crash; generator should use empty context and still return sections via error fallback.
- Single chunk in vector store — BM25 with one document returns score 0.0 for all queries; `keyword_scores_max` will be 0, causing division by zero in `hybrid.py` unless guarded. This is a real edge case to test and potentially fix.
- Malformed mock LLM response — if the mock returns non-JSON text, `parse_review_output()` should fall through to `_parse_plaintext_output()` and return a single `general_feedback` section. Test this path too.
- `generate_full_review()` with an unrecognized section name in `get_template()` raises `ValueError` — the generator's try/except catches this and appends an error section. Verify this behavior is preserved.
