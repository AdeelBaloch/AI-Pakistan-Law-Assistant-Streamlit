import math


def dot_product(vector_a, vector_b):
    return sum(a * b for a, b in zip(vector_a, vector_b))


def magnitude(vector):
    return math.sqrt(sum(value * value for value in vector))


def cosine_similarity(vector_a, vector_b):
    if len(vector_a) != len(vector_b):
        raise ValueError(
            "Vectors must have the same length "
            f"({len(vector_a)} vs {len(vector_b)})"
        )

    denom = magnitude(vector_a) * magnitude(vector_b)
    if denom == 0:
        return 0.0

    return dot_product(vector_a, vector_b) / denom


def rank_by_similarity(query_vector, embeddings):
    ranked = []

    for chunk_id, item in embeddings.items():
        ranked.append({
            "chunk_id": item.get("chunk_id", chunk_id),
            "page": item.get("page"),
            "score": cosine_similarity(query_vector, item["embedding"]),
        })

    ranked.sort(key=lambda row: row["score"], reverse=True)
    return ranked
