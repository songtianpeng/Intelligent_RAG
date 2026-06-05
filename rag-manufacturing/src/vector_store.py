"""
向量库管理 — 基于 ChromaDB
pip install chromadb 一行，API 稳定 3 年无 breaking change
"""
from typing import List, Dict, Optional

import chromadb


class VectorStore:
    """
    ChromaDB 嵌入式向量库

    【原理】
    - PersistentClient: 数据存在本地文件，进程内运行
    - Collection: 类似 MySQL 的表，存 documents + embeddings + metadatas
    - HNSW 索引: 自动创建，COSINE 度量
    - 标量过滤: where 子句，跟 Milvus 的 filter_expr 对等

    【生产切换】
    开发用 ChromaDB（嵌入式），生产可切 Milvus 集群或 ChromaDB 服务端。
    两者的向量检索、标量过滤、Collection 管理概念完全一致。
    """

    COLLECTION_NAME = "manufacturing_knowledge"

    def __init__(self, db_path: str = "./chroma_data"):
        # PersistentClient: 数据持久化到磁盘
        self.client = chromadb.PersistentClient(path=db_path)
        self.collection = self.client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    # ── 建库 ──
    def build(self, documents, embedding_service):
        """
        建库三步走：
        1. 删旧建新（开发模式）
        2. 向量化所有 chunk
        3. 批量写入 Collection
        """
        # 1. 开发阶段：每次重建，数据干净
        try:
            self.client.delete_collection(self.COLLECTION_NAME)
        except Exception:
            pass

        # 2. 创建 Collection，指定 COSINE 度量
        #    ChromaDB 默认用 L2 距离，改成 cosine 更适合语义检索
        self.collection = self.client.create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

        # 3. 向量化
        texts = [doc.page_content for doc in documents]
        vectors = embedding_service.embed_documents(texts)

        # 4. 准备数据
        ids = [str(i) for i in range(len(documents))]
        metadatas = [
            {
                "source": doc.metadata.get("source", ""),
                "page": doc.metadata.get("page", 1),
                "heading_path": doc.metadata.get("heading_path", ""),
                "chunk_type": doc.metadata.get("chunk_type", "text"),
            }
            for doc in documents
        ]

        # 5. 批量写入（ChromaDB 自动分批 + 建索引）
        self.collection.add(
            ids=ids,
            documents=texts,
            embeddings=vectors,
            metadatas=metadatas,
        )
        print(f"[VectorStore] 建库完成: {len(documents)} 条已写入 '{self.COLLECTION_NAME}'")

    # ── 检索 ──
    def search(
        self,
        query_vector: List[float],
        top_k: int = 5,
        where_filter: Optional[Dict] = None,
    ) -> List[Dict]:
        """
        向量检索 + 可选标量过滤

        Args:
            query_vector: 用户问题的向量
            top_k: 返回条数
            where_filter: 标量过滤，ChromaDB 格式
                {"source": "02_故障码手册.docx"}
                {"chunk_type": "table"}
                {"$and": [{"source": "xxx"}, {"chunk_type": "table"}]}

        Returns:
            [{...}, ...]
        """
        results = self.collection.query(
            query_embeddings=[query_vector],
            n_results=top_k,
            where=where_filter,
            include=["documents", "metadatas", "distances"],
        )

        # 转成调用方友好的格式
        output = []
        ids_list = results["ids"][0]
        docs_list = results["documents"][0]
        metas_list = results["metadatas"][0]
        dists_list = results["distances"][0]

        for i in range(len(ids_list)):
            output.append({
                "id": ids_list[i],
                "text": docs_list[i],
                "metadata": metas_list[i],
                "distance": dists_list[i],
            })
        return output


if __name__ == "__main__":
    import os, sys

    # 确保从项目根目录运行
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..")) # 把当前文件的上一级目录加入 Python 模块搜索路径（sys.path）中。
    from config import settings
    from document_loader import DocumentLoader
    from embedding import EmbeddingService

    print("=" * 50)
    print("【Step 1】加载文档...")
    loader = DocumentLoader(data_dir="../data")
    chunks = loader.load_all()

    print(f"\n【Step 2】向量化 + 写入 ChromaDB ({len(chunks)} chunks)...")
    emb_svc = EmbeddingService(api_key=settings.DASHSCOPE_API_KEY)

    db_path = os.path.join(os.path.dirname(__file__), "..", "chroma_data")
    db_path = os.path.abspath(db_path)

    store = VectorStore(db_path=db_path)
    store.build(chunks, emb_svc)

    print(f"\n【Step 3】检索测试: 'E03报警怎么办'")
    q_vec = emb_svc.embed_query("E03报警怎么办")
    results = store.search(q_vec, top_k=3)

    for i, hit in enumerate(results):
        print(f"\n  Top-{i+1}: distance={hit['distance']:.4f}") # distance 越小越相似
        print(f"    source: {hit['metadata'].get('source', '?')}")
        print(f"    heading: {hit['metadata'].get('heading_path', '?')[:80]}")
        print(f"    page: {hit['metadata'].get('page', 1)}")
        print(f"    chunk_type: {hit['metadata'].get('chunk_type', '?')}")
        print(f"    text: {hit['text'][:120]}...")
