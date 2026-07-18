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
