"""
Integration test for the full RAG pipeline.

Issue #38: Verifies that retrieval → generation → parsing work together
end-to-end using MockEmbeddingProvider and a mocked LLM response.
No Docker, no real API calls required.
"""

import json
import uuid
from unittest.mock import MagicMock, patch

import chromadb
import pytest

from ingestion.embeddings.provider import MockEmbeddingProvider
from rag.generator.output_parser import FeedbackSection, parse_review_output
from rag.generator.review_generator import ReviewConfig, ReviewGenerator
from rag.retriever.hybrid import HybridRetriever
from rag.retriever.keyword_search import KeywordSearcher
from rag.retriever.vector_store import VectorStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_CHUNKS = [
    {
        "id": "chunk-001",
        "text": "Built REST APIs using Python and FastAPI. Deployed on AWS Lambda.",
        "metadata": {"source_id": "resume-001", "chunk_index": 0, "section": "experience"},
    },
    {
        "id": "chunk-002",
        "text": "React weather application with TypeScript and Tailwind CSS.",
        "metadata": {"source_id": "readme-001", "chunk_index": 0, "section": "projects"},
    },
    {
        "id": "chunk-003",
        "text": "PostgreSQL database design and query optimisation using SQLAlchemy.",
        "metadata": {"source_id": "resume-001", "chunk_index": 1, "section": "skills"},
    },
]

SAMPLE_PROFILE = {
    "github_username": "janedoe",
    "projects": ["weather-app", "api-service"],
}

# generate_full_review calls the LLM once per section (5 calls).
# Each call returns this mock response; parse_review_output extracts one
# FeedbackSection per call, so _consolidate_feedback deduplicates by
# section_name and we end up with 1 unique section in the output.
# We assert >= 1 rather than == 5 because consolidation is intentional
# behaviour of the production code, not a bug in the test.
MOCK_LLM_JSON = json.dumps({
    "skills_feedback": {
        "content": "Strong Python and FastAPI skills demonstrated.",
        "suggestions": ["Add more backend projects"],
    }
})


def _make_mock_llm_response(content: str) -> MagicMock:
    """Build a mock that looks like an openai ChatCompletion response."""
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def embedding_provider():
    return MockEmbeddingProvider()


@pytest.fixture()
def in_memory_vector_store():
    """VectorStore backed by an ephemeral (in-memory) ChromaDB client."""
    client = chromadb.EphemeralClient()
    store = VectorStore.__new__(VectorStore)
    store.client = client
    return store


@pytest.fixture()
def seeded_collection(in_memory_vector_store, embedding_provider):
    """Vector store with SAMPLE_CHUNKS already ingested."""
    collection_name = f"profile_test_{uuid.uuid4().hex[:8]}"

    collection = in_memory_vector_store.client.create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    texts = [c["text"] for c in SAMPLE_CHUNKS]
    embeddings = embedding_provider.embed(texts)

    collection.upsert(
        ids=[c["id"] for c in SAMPLE_CHUNKS],
        embeddings=embeddings,
        documents=texts,
        metadatas=[c["metadata"] for c in SAMPLE_CHUNKS],
    )

    return in_memory_vector_store, collection_name


@pytest.fixture()
def hybrid_retriever(seeded_collection, embedding_provider):
    """HybridRetriever wired to the seeded in-memory store."""
    vector_store, collection_name = seeded_collection

    keyword_searcher = KeywordSearcher()
    keyword_searcher.index(SAMPLE_CHUNKS)

    retriever = HybridRetriever(
        vector_store=vector_store,
        keyword_searcher=keyword_searcher,
    )
    return retriever, collection_name, embedding_provider


@pytest.fixture()
def review_generator():
    """ReviewGenerator with a dummy config (LLM will be mocked per-test)."""
    config = ReviewConfig(
        api_key="test-key",
        base_url="https://mock.example.com/v1",
        model="mock-model",
    )
    with patch("rag.generator.review_generator.openai.OpenAI"):
        generator = ReviewGenerator(config=config)
    return generator


# ---------------------------------------------------------------------------
# Tests — retrieval stage
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestHybridRetrieval:
    """Integration tests for the hybrid retrieval stage."""

    def test_retrieve_returns_results_for_known_query(self, hybrid_retriever):
        retriever, collection_name, provider = hybrid_retriever
        query = "Python FastAPI REST API"
        query_embedding = provider.embed([query])[0]

        results = retriever.retrieve(
            query=query,
            profile_id=collection_name.replace("profile_", ""),
            query_embedding=query_embedding,
            min_score=0.0,
        )

        assert isinstance(results, list)
        assert len(results) > 0

    def test_retrieve_result_shape(self, hybrid_retriever):
        retriever, collection_name, provider = hybrid_retriever
        query_embedding = provider.embed(["React TypeScript frontend"])[0]

        results = retriever.retrieve(
            query="React TypeScript frontend",
            profile_id=collection_name.replace("profile_", ""),
            query_embedding=query_embedding,
            min_score=0.0,
        )

        for result in results:
            assert "id" in result
            assert "text" in result
            assert "metadata" in result
            assert "score" in result
            assert isinstance(result["score"], float)

    def test_retrieve_respects_max_chunks(self, hybrid_retriever):
        retriever, collection_name, provider = hybrid_retriever
        query_embedding = provider.embed(["Python"])[0]

        results = retriever.retrieve(
            query="Python",
            profile_id=collection_name.replace("profile_", ""),
            query_embedding=query_embedding,
            max_chunks=2,
            min_score=0.0,
        )

        assert len(results) <= 2

    def test_retrieve_empty_when_min_score_too_high(self, hybrid_retriever):
        retriever, collection_name, provider = hybrid_retriever
        query_embedding = provider.embed(["Python"])[0]

        results = retriever.retrieve(
            query="Python",
            profile_id=collection_name.replace("profile_", ""),
            query_embedding=query_embedding,
            min_score=1.1,
        )

        assert results == []

    def test_retrieve_scores_sorted_descending(self, hybrid_retriever):
        retriever, collection_name, provider = hybrid_retriever
        query_embedding = provider.embed(["Python FastAPI"])[0]

        results = retriever.retrieve(
            query="Python FastAPI",
            profile_id=collection_name.replace("profile_", ""),
            query_embedding=query_embedding,
            min_score=0.0,
        )

        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# Tests — generation + parsing stage
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestReviewGeneration:
    """Integration tests for the generation and parsing stage."""

    def test_generate_full_review_returns_feedback_sections(self, review_generator, hybrid_retriever):
        retriever, collection_name, provider = hybrid_retriever
        query_embedding = provider.embed(["Python FastAPI"])[0]
        chunks = retriever.retrieve(
            query="Python FastAPI",
            profile_id=collection_name.replace("profile_", ""),
            query_embedding=query_embedding,
            min_score=0.0,
        )

        mock_response = _make_mock_llm_response(MOCK_LLM_JSON)
        review_generator.client.chat.completions.create.return_value = mock_response

        sections = review_generator.generate_full_review(
            profile_data=SAMPLE_PROFILE,
            retrieved_chunks=chunks,
        )

        assert isinstance(sections, list)
        # generate_full_review calls LLM once per section name (5 calls).
        # _consolidate_feedback deduplicates by section_name, so when every
        # call returns the same mock JSON key the list is collapsed to 1.
        # We assert >= 1: the pipeline ran and produced structured output.
        assert len(sections) >= 1

    def test_each_section_has_required_fields(self, review_generator, hybrid_retriever):
        retriever, collection_name, provider = hybrid_retriever
        query_embedding = provider.embed(["Python"])[0]
        chunks = retriever.retrieve(
            query="Python",
            profile_id=collection_name.replace("profile_", ""),
            query_embedding=query_embedding,
            min_score=0.0,
        )

        mock_response = _make_mock_llm_response(MOCK_LLM_JSON)
        review_generator.client.chat.completions.create.return_value = mock_response

        sections = review_generator.generate_full_review(
            profile_data=SAMPLE_PROFILE,
            retrieved_chunks=chunks,
        )

        for section in sections:
            assert isinstance(section, FeedbackSection)
            assert section.section_name
            assert isinstance(section.content, str)
            assert isinstance(section.confidence, float)
            assert isinstance(section.suggestions, list)

    def test_generate_full_review_with_empty_chunks(self, review_generator):
        """Pipeline should not crash when retrieval returns nothing."""
        mock_response = _make_mock_llm_response(MOCK_LLM_JSON)
        review_generator.client.chat.completions.create.return_value = mock_response

        sections = review_generator.generate_full_review(
            profile_data=SAMPLE_PROFILE,
            retrieved_chunks=[],
        )

        assert isinstance(sections, list)
        assert len(sections) >= 1


# ---------------------------------------------------------------------------
# Tests — output parser stage
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestOutputParser:
    """Integration tests for parse_review_output covering all three paths."""

    def test_parse_valid_json_response(self):
        raw = json.dumps({"skills_feedback": "Strong Python skills."})
        sections = parse_review_output(raw)
        assert len(sections) == 1
        assert sections[0].section_name == "skills_feedback"
        assert sections[0].content == "Strong Python skills."

    def test_parse_json_in_code_fence(self):
        raw = '```json\n{"projects_feedback": "Good project variety."}\n```'
        sections = parse_review_output(raw)
        assert len(sections) == 1
        assert sections[0].section_name == "projects_feedback"

    def test_parse_plaintext_fallback(self):
        """Non-JSON LLM output falls back to a single general_feedback section."""
        raw = "This is plain text feedback with no JSON structure."
        sections = parse_review_output(raw)
        assert len(sections) == 1
        assert sections[0].section_name == "general_feedback"
        assert sections[0].confidence == 0.7
        assert raw in sections[0].content

    def test_parse_nested_json_with_suggestions(self):
        raw = json.dumps({
            "gaps_feedback": {
                "content": "Missing cloud experience.",
                "suggestions": ["Add AWS project", "Learn Kubernetes"],
            }
        })
        sections = parse_review_output(raw)
        assert len(sections) == 1
        assert sections[0].suggestions == ["Add AWS project", "Learn Kubernetes"]


# ---------------------------------------------------------------------------
# Tests — full end-to-end pipeline
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestFullPipeline:
    """End-to-end integration: retrieval → generation → parsing in one flow."""

    def test_full_pipeline_produces_valid_output(self, hybrid_retriever, review_generator):
        retriever, collection_name, provider = hybrid_retriever
        query = "Python FastAPI PostgreSQL REST API"
        query_embedding = provider.embed([query])[0]

        # Stage 1: retrieve
        chunks = retriever.retrieve(
            query=query,
            profile_id=collection_name.replace("profile_", ""),
            query_embedding=query_embedding,
            min_score=0.0,
        )
        assert isinstance(chunks, list)

        # Stage 2: generate (mocked LLM)
        mock_response = _make_mock_llm_response(MOCK_LLM_JSON)
        review_generator.client.chat.completions.create.return_value = mock_response

        sections = review_generator.generate_full_review(
            profile_data=SAMPLE_PROFILE,
            retrieved_chunks=chunks,
        )

        # Stage 3: assert parsed output
        assert len(sections) >= 1
        for section in sections:
            assert section.section_name
            assert isinstance(section.content, str)
            assert 0.0 <= section.confidence <= 1.0
