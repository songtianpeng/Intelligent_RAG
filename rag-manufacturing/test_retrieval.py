"""
检索链路对比测试：向量 / BM25 / RRF融合 / RRF+MMR
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
from generation import AnswerGenerator


def print_result(label, results, show_content=True):
    """打印检索结果"""
    print(f"\n{'─' * 40}")
    print(f"  [{label}]")
    for rank, item in enumerate(results):
        meta = item.get("metadata", item.get("entity", {}))
        text = item.get("text", item.get("page_content", ""))
        score = item.get("score", item.get("distance", 0))
        print(f"  #{rank+1} score={score:.4f}  src={meta.get('source','?')}")
        print(f"      heading: {meta.get('heading_path','?')[:60]}")
        if show_content:
            print(f"      text: {text[:100]}...")


if __name__ == "__main__":
    # ── 1. 加载 + 建库 ──
    print("【1】加载文档 & 建库...")
    loader = DocumentLoader(data_dir=os.path.join(os.path.dirname(__file__), "data"))
    chunks = loader.load_all()

    emb_svc = EmbeddingService(api_key=settings.DASHSCOPE_API_KEY)
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "chroma_data"))
    store = VectorStore(db_path=db_path)
    # store.build(chunks, emb_svc)   # 向量重新存储

    # chunk 转成 Dict 列表（BM25 和 Hybrid 用）
    chunk_dicts = [
        {"text": c.page_content, "metadata": c.metadata}
        for c in chunks
    ]

    # ── 2. 初始化检索器 ──
    bm25 = BM25Retriever()
    bm25.build_index(chunk_dicts)
    vec_retriever = VectorRetriever(store)
    vec_retriever.chunks = chunk_dicts
    hybrid = HybridRetriever(bm25, vec_retriever)

    # ── 3. 测试 ──
    queries = [
        # "E03报警怎么办",
        # "注塑机开机前需要检查哪些项目",
        # "液压油温过高怎么处理",
        "屏蔽安全门开关会发生什么"
    ]

    for q in queries:
        print(f"\n{'=' * 60}")
        print(f"问题：{q}")
        q_vec = emb_svc.embed_query(q)

        # 纯 BM25
        bm25_hits = bm25.search(q, top_k=5)
        bm25_output = []
        for idx, score in bm25_hits:
            bm25_output.append({**chunk_dicts[idx], "score": score})

        # 纯向量
        vec_hits = vec_retriever.search(q_vec, top_k=5)
        vec_output = []
        for idx, sim in vec_hits:
            vec_output.append({**chunk_dicts[idx], "score": sim})

        # 混合（RRF only，跳过 MMR）
        mixed_rrf = hybrid._rrf_fusion(bm25.search(q, top_k=10),
                                        vec_retriever.search(q_vec, top_k=10))
        rrf_output = []
        for idx, score in mixed_rrf[:5]:
            rrf_output.append({**chunk_dicts[idx], "score": score})

        # 混合（RRF + MMR）
        hybrid_output = hybrid.search(q, q_vec, top_k=5)

        print_result("纯 BM25", bm25_output)
        print_result("纯向量", vec_output)
        print_result("RRF融合", rrf_output)
        print_result("RRF + MMR", hybrid_output)

        # ── 4. 使用大模型生成答案 ──
        gen = AnswerGenerator(api_key=settings.DASHSCOPE_API_KEY)
        response = gen.generate(q, hybrid_output)
        print("------------------大模型生成答案-------------------")
        print(f"\n答案：\n{response['answer']}\n参考资料：{response['sources']}")
