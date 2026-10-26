import math
import re
from typing import List, Dict, Any, Tuple, Optional
import numpy as np
from rank_bm25 import BM25Okapi
from pydantic import BaseModel, Field

class RetrievalResult(BaseModel):
    chunk_id: int
    text: str
    score: float
    retrieval_mode: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

def simple_tokenize(text: str) -> List[str]:
    """Tokenize and normalize financial text."""
    clean = re.sub(r"[^\w\s\$\%]", " ", text.lower())
    return [w for w in clean.split() if w]

class InMemDenseEmbedding:
    """
    Lightweight, deterministic character/word n-gram embedding vectorizer.
    Guarantees fast, offline vector similarity without heavy GPU/Torch dependencies.
    """
    def __init__(self, vocab_dim: int = 256):
        self.vocab_dim = vocab_dim

    def encode(self, text: str) -> np.ndarray:
        tokens = simple_tokenize(text)
        vec = np.zeros(self.vocab_dim, dtype=np.float32)
        if not tokens:
            return vec
        for tok in tokens:
            # Deterministic hash projection into embedding dimensions
            h = hash(tok) % self.vocab_dim
            vec[h] += 1.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec

class HybridRetriever:
    """
    Enterprise Hybrid Search Engine featuring:
    1. Sparse keyword search (BM25Okapi)
    2. Dense vector cosine similarity
    3. Weighted Reciprocal Rank Fusion (RRF)
    4. Pre-retrieval Metadata Filtering
    5. Two-Stage Exact Financial Number & Term Reranking
    """
    def __init__(self, documents: List[str], metadata: Optional[List[Dict[str, Any]]] = None):
        self.documents = documents
        self.metadata = metadata or [{} for _ in documents]
        self.tokenized_corpus = [simple_tokenize(doc) for doc in documents]
        
        # Sparse BM25 index
        self.bm25 = BM25Okapi(self.tokenized_corpus) if self.tokenized_corpus else None
        
        # Dense vector index
        self.dense_embedder = InMemDenseEmbedding(vocab_dim=256)
        self.dense_matrix = np.array([self.dense_embedder.encode(doc) for doc in documents]) if documents else np.zeros((0, 256))

    def _matches_filter(self, meta: Dict[str, Any], filter_dict: Optional[Dict[str, Any]]) -> bool:
        """Check if chunk metadata satisfies filter constraints."""
        if not filter_dict:
            return True
        for k, v in filter_dict.items():
            if str(meta.get(k, "")).lower() != str(v).lower():
                return False
        return True

    def search_sparse(
        self,
        query: str,
        top_k: int = 5,
        filter_dict: Optional[Dict[str, Any]] = None
    ) -> List[RetrievalResult]:
        """BM25 keyword search with optional metadata filtering."""
        query_tokens = simple_tokenize(query)
        scores = self.bm25.get_scores(query_tokens) if self.bm25 else np.zeros(len(self.documents))
        
        # Filter indices
        candidate_indices = [
            i for i in range(len(self.documents))
            if self._matches_filter(self.metadata[i], filter_dict)
        ]

        if not candidate_indices:
            return []

        sorted_candidates = sorted(candidate_indices, key=lambda idx: scores[idx], reverse=True)[:top_k]

        results = []
        for idx in sorted_candidates:
            results.append(RetrievalResult(
                chunk_id=int(idx),
                text=self.documents[idx],
                score=float(scores[idx]),
                retrieval_mode="sparse_bm25",
                metadata=self.metadata[idx]
            ))
        return results

    def search_dense(
        self,
        query: str,
        top_k: int = 5,
        filter_dict: Optional[Dict[str, Any]] = None
    ) -> List[RetrievalResult]:
        """Dense vector cosine similarity search with metadata filtering."""
        query_vec = self.dense_embedder.encode(query)
        if np.linalg.norm(query_vec) == 0 or len(self.dense_matrix) == 0:
            scores = np.zeros(len(self.documents))
        else:
            scores = np.dot(self.dense_matrix, query_vec)

        candidate_indices = [
            i for i in range(len(self.documents))
            if self._matches_filter(self.metadata[i], filter_dict)
        ]

        if not candidate_indices:
            return []

        sorted_candidates = sorted(candidate_indices, key=lambda idx: scores[idx], reverse=True)[:top_k]

        results = []
        for idx in sorted_candidates:
            results.append(RetrievalResult(
                chunk_id=int(idx),
                text=self.documents[idx],
                score=float(scores[idx]),
                retrieval_mode="dense_vector",
                metadata=self.metadata[idx]
            ))
        return results

    def search_hybrid_rrf(
        self,
        query: str,
        top_k: int = 5,
        rrf_k: int = 60,
        sparse_weight: float = 0.5,
        dense_weight: float = 0.5,
        filter_dict: Optional[Dict[str, Any]] = None
    ) -> List[RetrievalResult]:
        """
        Weighted Reciprocal Rank Fusion (RRF) with metadata pre-filtering:
        RRF_Score(d) = w_sparse * (1/(k + rank_bm25(d))) + w_dense * (1/(k + rank_dense(d)))
        """
        search_k = min(len(self.documents), max(top_k * 3, 20))

        sparse_results = self.search_sparse(query, top_k=search_k, filter_dict=filter_dict)
        dense_results = self.search_dense(query, top_k=search_k, filter_dict=filter_dict)

        rrf_scores: Dict[int, float] = {}

        # Accumulate sparse ranks
        for rank, res in enumerate(sparse_results, start=1):
            rrf_scores[res.chunk_id] = rrf_scores.get(res.chunk_id, 0.0) + (sparse_weight / (rrf_k + rank))

        # Accumulate dense ranks
        for rank, res in enumerate(dense_results, start=1):
            rrf_scores[res.chunk_id] = rrf_scores.get(res.chunk_id, 0.0) + (dense_weight / (rrf_k + rank))

        sorted_chunks = sorted(rrf_scores.items(), key=lambda item: item[1], reverse=True)[:top_k]

        results = []
        for chunk_id, score in sorted_chunks:
            results.append(RetrievalResult(
                chunk_id=chunk_id,
                text=self.documents[chunk_id],
                score=float(score),
                retrieval_mode="hybrid_rrf",
                metadata=self.metadata[chunk_id]
            ))
        return results

    def rerank_exact_terms(
        self,
        query: str,
        candidates: List[RetrievalResult],
        top_n: int = 3
    ) -> List[RetrievalResult]:
        """
        Second-Stage Exact Financial Terms Reranker:
        Boosts candidates containing exact numeric mentions and key financial tokens.
        """
        query_numbers = re.findall(r"\b\d{4}\b|\b\d+(?:\.\d+)?%?\b", query)
        query_words = set(simple_tokenize(query))

        reranked = []
        for c in candidates:
            chunk_text = c.text.lower()
            bonus = 0.0

            # Exact year or number match bonus (e.g. FY2023, 2024)
            for num in query_numbers:
                if num.lower() in chunk_text:
                    bonus += 0.015

            # Key terms overlap bonus
            chunk_tokens = set(simple_tokenize(chunk_text))
            overlap = len(query_words.intersection(chunk_tokens))
            bonus += overlap * 0.002

            new_score = c.score + bonus
            reranked.append(RetrievalResult(
                chunk_id=c.chunk_id,
                text=c.text,
                score=float(new_score),
                retrieval_mode=f"{c.retrieval_mode}+reranked",
                metadata=c.metadata
            ))

        reranked.sort(key=lambda x: x.score, reverse=True)
        return reranked[:top_n]
