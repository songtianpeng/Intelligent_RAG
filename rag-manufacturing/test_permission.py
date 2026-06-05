"""
权限隔离对比测试
"""
import os, sys
sys.path.insert(0, "src")

from config import settings
from document_loader import DocumentLoader
from embedding import EmbeddingService
from vector_store import VectorStore
from retrieval.bm25_retriever import BM25Retriever
from retrieval.vector_retriever import VectorRetriever
from retrieval.hybrid_retriever import HybridRetriever
from retrieval.permission import PermissionManager
from generation import AnswerGenerator


def print_hits(results, max_n=5):
    for rank, item in enumerate(results[:max_n]):
        meta = item.get("metadata", {})
        src = meta.get("source", "?")
        factory = meta.get("factory", "N/A")
        line = meta.get("production_line", "N/A")
        heading = meta.get("heading_path", "?")[:50]
        print(f"  #{rank+1} src={src}  factory={factory}  line={line}")
        print(f"      heading: {heading}")


if __name__ == "__main__":
    # ── 1. 加载文档 ──
    print("【1】加载文档...")
    loader = DocumentLoader(data_dir=os.path.join(os.path.dirname(__file__), "data"))
    chunks = loader.load_all()

    emb_svc = EmbeddingService(api_key=settings.DASHSCOPE_API_KEY)

    # ── 2. 重建库（带权限字段注入） ──
    print("【2】重建 ChromaDB（带权限字段）...")
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "chroma_data"))

    texts = [c.page_content for c in chunks]
    vectors = emb_svc.embed_documents(texts)
    ids = [str(i) for i in range(len(chunks))]
    metadatas = [
        {"source": c.metadata.get("source", ""),
         "page": c.metadata.get("page", 1),
         "heading_path": c.metadata.get("heading_path", ""),
         "chunk_type": c.metadata.get("chunk_type", "text")}
        for c in chunks
    ]

    # ★ 注入权限字段
    perm_mgr = PermissionManager()
    metadatas = perm_mgr.enrich_metadatas(metadatas)

    store = VectorStore(db_path=db_path)
    store.build(chunks, emb_svc)

    # ── 3. 初始化检索器 ──
    chunk_dicts = [{"text": c.page_content, "metadata": m}
                   for c, m in zip(chunks, metadatas)]
    bm25 = BM25Retriever()
    bm25.build_index(chunk_dicts)
    vec_r = VectorRetriever(store)
    vec_r.chunks = chunk_dicts
    hybrid = HybridRetriever(bm25, vec_r)

    gen = AnswerGenerator(api_key=settings.DASHSCOPE_API_KEY)

    # ── 4. 对比测试 ──
    queries = ["注塑机开机前需要检查什么", "E03报警怎么办"]

    for role_name, factory, line in [
        ("一厂注塑车间操作员", "一厂", "注塑产线"),
        ("无身份（管理员）", None, None),
    ]:
        where = perm_mgr.build_filter(factory=factory, production_line=line)
        print(f"\n{'=' * 60}")
        print(f"用户: {role_name}")
        print(f"过滤条件: {where}")
        print(f"{'=' * 60}")

        for q in queries:
            q_vec = emb_svc.embed_query(q)
            results = hybrid.search(q, q_vec, top_k=5, where_filter=where)

            # 统计
            factories = set()
            for r in results:
                factories.add(r["metadata"].get("factory", "N/A"))
            result_count = len(results)

            print(f"\n  问题: {q}")
            print(f"  召回: {result_count} 条, 涉及工厂: {factories}")
            print_hits(results)
