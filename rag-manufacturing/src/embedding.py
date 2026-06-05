"""
文本向量化服务 — 基于 LangChain DashScopeEmbeddings 封装
"""
from typing import List

from langchain_community.embeddings import DashScopeEmbeddings
from langchain_core.embeddings import Embeddings


class EmbeddingService(Embeddings):
    """
    向量化服务

    【原理】
    文本 → Embedding模型 → 固定长度的浮点数向量

    比如 "E03电机过载" → [0.023, -0.451, 0.789, ..., 0.312]  (通常是1024或1536维)

    关键特性：语义相近的文本，向量在空间中距离也近。
    "E03电机过载" 和 "电机电流过大报警" 的向量夹角很小
    "E03电机过载" 和 "今天天气不错" 的向量夹角很大

    这就是 RAG 能做语义检索的数学基础——不是关键词匹配，是向量距离。

    【DashScope text-embedding-v3 参数说明】
    - text_type: "query" 表示查询文本，"document" 表示文档文本
      模型对查询和文档会做不同的编码优化（非对称 embedding）
      传 "document" 时模型的注意力机制会偏向保留细节
      传 "query" 时会偏向提取意图和关键语义
    """

    def __init__(self, api_key: str, model: str = "text-embedding-v3"):
        """
        DashScopeEmbeddings 是 LangChain 对阿里云 DashScope API 的封装
        底层调用 dashscope.TextEmbedding.call()
        LangChain 帮我们处理了重试、批量切分、结果排序这些脏活
        """
        self.model = model
        self.embeddings = DashScopeEmbeddings(
            model=model,
            dashscope_api_key=api_key,
        )

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        文档转向量（离线建库时用）

        【原理】
        对每个chunk的page_content调用embedding API
        LangChain内部会自动：
        1. 按batch_size分批（默认25条一批）
        2. 调用 DashScope API
        3. 按 text_index 排序确保输出顺序 = 输入顺序
        4. 失败自动重试

        调用示例：
          chunks = document_loader.load_all()
          texts = [c.page_content for c in chunks]
          vectors = svc.embed_documents(texts)
          # → [[0.023, -0.451, ...], [0.019, -0.447, ...], ...]
          # vectors[0] 就是 chunks[0] 的向量，一一对应
        """
        return self.embeddings.embed_documents(texts)

    def embed_query(self, text: str) -> List[float]:
        """
        用户问题转向量（在线检索时用）

        【原理】
        传 text_type="query" 给模型，模型会对短文本做不同的编码策略
        虽然维度一样，但 query embedding 和 document embedding 在
        向量空间里的分布略有不同——这是非对称embedding的优化点
        """
        return self.embeddings.embed_query(text)


if __name__ == "__main__":
    import sys;

    sys.path.insert(0, '.')
    from config import settings

    svc = EmbeddingService(api_key=settings.DASHSCOPE_API_KEY)

    # 测试：文档向量化
    docs = [
        "[第一章 电气系统故障 > E03 电机过载]\n电机电流超过额定值120%持续3秒...",
        "[第三章 参数设置 > 3.1 温度参数]\n第一段（料斗侧）180-200度...",
    ]
    doc_vectors = svc.embed_documents(docs)
    print(f"文档向量: {len(doc_vectors)} 条, 维度: {len(doc_vectors[0])}")

    # 测试：查询向量化
    q_vec = svc.embed_query("E03报警怎么办")
    print(f"查询向量维度: {len(q_vec)}")

    # 【面试考点】embed_documents vs embed_query 的区别
    print("\n[原理] embed_documents(text_type='document') 和 embed_query(text_type='query')")
    print("对同一句话生成的向量是不同的，因为模型的注意力偏向不同：")
    print("  document: 保留更多细节信息（长文本、名词实体）")
    print("  query:    提取意图和关键语义（短文本、问句结构）")
