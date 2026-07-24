"""
Integration test for the full RAG pipeline.

Issue #38: There are unit tests for individual RAG components but no
integration test that runs a full query through:
  retrieval -> reranking -> generation -> parsing

This file is the reproduction commit showing the gap exists.
The full implementation will follow in Week 9.

Relevant components identified:
- ingestion/embeddings/provider.py: MockEmbeddingProvider (deterministic, no API key needed)
- rag/retriever/vector_store.py: VectorStore (ChromaDB-backed)
- rag/retriever/keyword_search.py: KeywordSearcher (BM25)
- rag/retriever/hybrid.py: HybridRetriever (combines vector + keyword)
- rag/generator/review_generator.py: ReviewGenerator (calls LLM)
- rag/generator/output_parser.py: parse_review_output (parses LLM response)
- rag/generator/prompt_templates.py: get_template (prompt construction)

Current state: tests/integration/ contains only __init__.py — no pipeline test exists.
Expected state: A test that wires all components together using MockEmbeddingProvider
                and a mock LLM response to validate the full query flow without
                making real API calls.
"""

# Placeholder — full implementation in Week 9
# This file documents that tests/integration/test_rag_pipeline.py does not exist yet,
# confirming the gap described in issue #38.
