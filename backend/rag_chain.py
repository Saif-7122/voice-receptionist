"""
rag_chain.py — LangChain RAG pipeline.

Pipeline:
    RecursiveCharacterTextSplitter
    → HuggingFaceEmbeddings (BAAI/bge-small-en-v1.5, dim=384)
    → SupabaseVectorStore  (pgvector, table=knowledge_chunks)
    → RetrievalQA chain    (ChatGroq, llama-3.3-70b-versatile)

Public API:
    ingest(docs, business_id)          — chunk + embed + store FAQs
    get_chain(business_id)             — returns a ready RetrievalQA chain
    query(question, business_id, ...)  — run the chain, return answer + sources
"""

from __future__ import annotations

from langchain.chains import RetrievalQA
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import SupabaseVectorStore
from langchain_groq import ChatGroq
from langchain_huggingface import HuggingFaceEmbeddings
from langchain.schema import Document
from supabase import create_client, Client

from config import settings
from langfuse_setup import get_langfuse_handler

# ── Shared singletons (loaded once at import time) ─────────────────────────

_supabase_client: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)

# HuggingFace BGE-small — 384-dim embeddings, runs locally (no API key)
_embeddings = HuggingFaceEmbeddings(
    model_name="BAAI/bge-small-en-v1.5",
    model_kwargs={"device": "cpu"},
    encode_kwargs={"normalize_embeddings": True},  # cosine similarity
)

_text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=50,
    separators=["\n\n", "\n", ". ", " ", ""],
)

# ── Ingestion ──────────────────────────────────────────────────────────────


def ingest(docs: list[Document], business_id: str) -> int:
    """
    Chunk, embed, and store documents for a business.

    Args:
        docs:        list of LangChain Documents (page_content + metadata)
        business_id: UUID of the business — stored in each chunk's metadata
                     so the retriever can filter by business at query time.

    Returns:
        Number of chunks stored.
    """
    # Tag every document with business_id before splitting so the metadata
    # is inherited by every child chunk.
    for doc in docs:
        doc.metadata.setdefault("business_id", business_id)

    chunks = _text_splitter.split_documents(docs)

    SupabaseVectorStore.from_documents(
        documents=chunks,
        embedding=_embeddings,
        client=_supabase_client,
        table_name="knowledge_chunks",
        query_name="match_documents",  # Postgres function required by LangChain
    )

    return len(chunks)


# ── Retriever + Chain ──────────────────────────────────────────────────────


def _get_vector_store(business_id: str) -> SupabaseVectorStore:
    """
    Returns a SupabaseVectorStore scoped to a single business.
    Filtering is done via metadata_filter so each business only
    retrieves its own knowledge chunks.
    """
    return SupabaseVectorStore(
        client=_supabase_client,
        embedding=_embeddings,
        table_name="knowledge_chunks",
        query_name="match_documents",
    )


def get_chain(business_id: str) -> RetrievalQA:
    """
    Build and return a RetrievalQA chain for the given business.
    The chain is NOT cached — create a new one per request so that
    Langfuse callbacks are correctly scoped to individual calls.
    """
    llm = ChatGroq(
        api_key=settings.GROQ_API_KEY,
        model_name=settings.GROQ_MODEL,
        temperature=0.2,        # low temp for factual receptionist answers
        max_tokens=512,
    )

    vector_store = _get_vector_store(business_id)
    retriever = vector_store.as_retriever(
        search_kwargs={
            "k": 4,
            "filter": {"business_id": business_id},
        }
    )

    chain = RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=retriever,
        return_source_documents=True,
        input_key="query",
        output_key="result",
    )

    return chain


def query(
    question: str,
    business_id: str,
    call_id: str | None = None,
) -> dict[str, str | list[str]]:
    """
    Run a RAG query for a business.

    Args:
        question:    The patient/customer's question.
        business_id: Used to scope the vector retrieval.
        call_id:     Vapi call ID — used as Langfuse session_id for tracing.

    Returns:
        { "answer": str, "sources": list[str] }
    """
    chain = get_chain(business_id)
    handler = get_langfuse_handler(
        session_id=call_id,
        user_id=business_id,
    )

    result = chain.invoke(
        {"query": question},
        config={"callbacks": [handler]},
    )

    sources = [
        doc.metadata.get("source", doc.page_content[:80])
        for doc in result.get("source_documents", [])
    ]

    return {
        "answer": result.get("result", "I'm sorry, I don't have that information."),
        "sources": sources,
    }
