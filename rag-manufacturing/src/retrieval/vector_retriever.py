"""
向量语义检索器
对 VectorStore.search() 做轻量封装，统一输出格式
"""
from typing import List, Tuple


class VectorRetriever:
    """向量语义检索器"""
    def __init__(self, vector_store):
        """
        Args:
            vector_store: VectorStore 实例
        """
        self.store = vector_store
        self.chunks = []  # build_index 时填充

    def build_index(self, chunks):
        """保存 chunk 列表引用（向量库已经建好了，这里只存映射）"""
        self.chunks = chunks

    def search(self, query_vector: List[float], top_k: int = 10,where_filter=None) -> List[Tuple[int, float]]:
        """
        向量检索

        Args:
            query_vector: embedding_service.embed_query() 的结果
            top_k: 返回数量

        Returns:
            [(chunk_index, distance), ...]
            注意：ChromaDB 的 COSINE distance = 1 - cos(θ)
            值越小越相似（0 = 完全相同，1 = 完全无关）
            所以返回时用 (index, 1 - distance) 转成"相似度分数"
            这样跟 BM25 的分数方向一致——都是越大越好
        """
        results = self.store.search(query_vector, top_k=top_k, where_filter=where_filter)

        output = []
        for hit in results:
            chunk_id = int(hit["id"])
            # distance 越小越相似 → 转成相似度分数（越大越好）
            similarity = 1.0 - hit["distance"]
            output.append((chunk_id, similarity))
        return output
