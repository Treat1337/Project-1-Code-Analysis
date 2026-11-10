import json
import re
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class KnowledgeBase:
    def __init__(self, documents: list[dict[str, str]]) -> None:
        self.documents = documents
        self.vectorizer = TfidfVectorizer(
            lowercase=True,
            strip_accents="unicode",
            token_pattern=r"(?u)\b\w+\b",
            ngram_range=(1, 2),
        )
        if documents:
            self.matrix = self.vectorizer.fit_transform(
                [f"{doc['title']} {doc['content']}" for doc in documents]
            )
        else:
            self.matrix = None

    @classmethod
    def from_json(cls, path: Path) -> "KnowledgeBase":
        try:
            documents = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Could not load knowledge base at {path}: {exc}") from exc
        if not isinstance(documents, list) or any(
            not isinstance(doc, dict)
            or not isinstance(doc.get("title"), str)
            or not isinstance(doc.get("content"), str)
            for doc in documents
        ):
            raise RuntimeError("Knowledge base must be a JSON list of title/content documents")
        return cls(documents)

    def search(self, query: str, limit: int = 3) -> list[dict[str, str]]:
        if not self.documents or self.matrix is None or not query.strip():
            return []
        query_vector = self.vectorizer.transform([query])
        scores = cosine_similarity(query_vector, self.matrix).ravel()
        ranked = scores.argsort()[::-1][:limit]
        return [
            {**self.documents[index], "score": f"{scores[index]:.4f}"}
            for index in ranked
            if scores[index] > 0
        ]


_WORD_PATTERN = re.compile(r"\w+", flags=re.UNICODE)


def tokenize(source: str) -> list[str]:
    return _WORD_PATTERN.findall(source.lower())

