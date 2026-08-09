## Week 7 — Issue selection

**Issue link:** https://github.com/ascherj/pathreview/issues/38

**Issue title:** Add an integration test that runs the full RAG pipeline against a mock LLM

**Tier:** [ ] Tier 1  [x] Tier 2  [ ] Tier 3

**Problem summary:**
The pathreview codebase has unit tests for individual RAG components but no integration test that exercises the full pipeline end-to-end. This means a bug that only surfaces when retrieval, reranking, generation, and parsing are chained together would not be caught by the existing test suite. The fix is to add a single integration test in tests/integration/test_rag_pipeline.py that runs a complete query through all four stages using the existing mock LLM provider, so the pipeline can be validated without making real API calls.

**Branch name:** test/38-rag-pipeline-integration-test

**Setup confirmation:** [ ] App runs locally at localhost:5173

**Cohort ledger:** [x] Issue added to cohort ledger

**Is this right for me? — checklist reasoning:**
This is a Tier 2 issue requiring cross-module understanding of the RAG pipeline. The scope is well-defined — one new test file, no changes to production code — which makes it more approachable than a Tier 2 feature addition. The mock LLM provider already exists, so I do not need to write mocking infrastructure from scratch. The estimated effort of 4-6 hours is realistic across the remaining weeks.

## Week 8 — Reproduction & solution planning

**Reproduction commit link:** https://github.com/1WillShine/pathreview/commit/e9eb5fb

**Reproduction summary:**
Confirmed that `tests/integration/` contains only `__init__.py` — `test_rag_pipeline.py` does not exist. The gap is real: all five RAG components (`HybridRetriever`, `VectorStore`, `KeywordSearcher`, `ReviewGenerator`, `parse_review_output`) have unit tests but no test wires them together end-to-end. A bug at any composition boundary (e.g. score format mismatch between retriever output and generator's context formatter) would go undetected.

**PLAN.md link:** https://github.com/1WillShine/pathreview/blob/test/38-rag-pipeline-integration-test/PLAN.md

**Walkthrough video (recommended):** N/A

**Blockers or open questions:**
- Need to confirm whether `chromadb.EphemeralClient()` is available in the pinned version (>=0.29.0) or whether to use `chromadb.Client(Settings(is_persistent=False))` instead.
- Need to verify the correct `unittest.mock.patch` path for `openai.OpenAI` as used inside `rag/generator/review_generator.py`.
- Need to confirm `rank_bm25` is installed in the test environment without Docker running.

## Week 9 — Solution building & PR submission

### Check-in 1 (mid-week)

**Current progress:**
Implemented all five sub-tasks from PLAN.md. The integration test file is complete with 13 passing tests covering: hybrid retrieval (5 tests), review generation with mocked LLM (3 tests), output parser (4 tests), and a full end-to-end pipeline test (1 test). Used ChromaDB EphemeralClient for in-memory vector store (no Docker needed), MockEmbeddingProvider for deterministic embeddings, and unittest.mock to patch the OpenAI client.

**Next steps:**
Commit, push, and open PR against upstream ascherj/pathreview.

**Blockers:**
None — all 13 tests pass locally.

---

### Check-in 2 (end of week)

**PR link:** YOUR_PR_URL_HERE

**Branch:** test/38-rag-pipeline-integration-test

**What you built:**
Added tests/integration/test_rag_pipeline.py with 13 integration tests that wire MockEmbeddingProvider, ChromaDB EphemeralClient, KeywordSearcher (BM25), HybridRetriever, ReviewGenerator (mocked LLM), and parse_review_output together end-to-end. No Docker and no real API calls required — the full pipeline runs in 2.78 seconds.

**Tests added or updated:**
Created tests/integration/test_rag_pipeline.py — 13 tests across TestHybridRetrieval, TestReviewGeneration, TestOutputParser, and TestFullPipeline.

**Self-review confirmation:** [x] make check passes  [x] make test-unit passes

**Draft PR feedback received from:** none

## Week 10 — Iteration & reflection

### Reviewer feedback

**Feedback received:** [ ] No — still awaiting review

**Summary of feedback:**
No reviewer feedback came in during the Summer 2026 cohort. Per the course note, reviewer feedback is not a feature in Summer 2026.

**How you responded:**
N/A — no feedback received.

---

### Reflection

**What was harder than you expected?**
The hardest part was understanding how the five RAG components actually connected to each other before writing a single line of test code. Reading `review_generator.py` in isolation tells you it calls an LLM — but it took reading `hybrid.py`, `vector_store.py`, `keyword_search.py`, and `output_parser.py` together to understand what data format each component expected to receive and what it returned. The score threshold in `HybridRetriever.retrieve()` defaulting to `0.3` was a concrete example: with only 3 seeded test chunks and mock embeddings, blended scores fell below the threshold and the retriever silently returned an empty list. That would have been an invisible failure in the test if I hadn't read the source carefully first.

**What did you learn about working in a large codebase?**
The biggest difference from building your own project is that you cannot change the contracts between components just because they're inconvenient for testing. In my own projects I would have refactored `ReviewGenerator.__init__` to accept an injectable LLM client. Here I had to work with the existing design — patching `rag.generator.review_generator.openai.OpenAI` at the right import path rather than the module I intuitively wanted to patch. That discipline of fitting your contribution to the existing architecture rather than reshaping the architecture around your contribution is the core skill that large-codebase work teaches.

**How did AI tools help — and where did they fall short?**
AI was most useful for two things: quickly summarizing what each service file was responsible for before I read it in detail, and catching the mock patch path issue before I ran into it. Where it fell short was in predicting exactly how `_consolidate_feedback` in `review_generator.py` would behave when every LLM call returned the same JSON key — the AI said the test should assert `len(sections) == 5` but the actual behavior was deduplication to 1. No AI explanation substitutes for running the code and reading the failure message. The read-the-error-and-fix loop is still entirely human work.

**What would you do differently if you started over?**
I would have installed the project dependencies (`chromadb`, `rank-bm25`, `structlog`) in a proper virtual environment from the start instead of the system Python. Working without Docker meant the test environment diverged slightly from what the project expected, which added friction. I also would have written a single passing test first to confirm the mock infrastructure worked before building out all 13 tests — the consolidation bug would have surfaced at test 1 rather than after the full suite was written.

**What are you most proud of from this module?**
The test suite runs in under 3 seconds with no Docker and no real API calls, which means any future contributor can run it instantly on a fresh clone. That was a deliberate design decision — using `chromadb.EphemeralClient()` instead of a persistent client, and patching the LLM at the right import path — and getting those two technical choices right without a reference example to follow is what I'm most proud of.
