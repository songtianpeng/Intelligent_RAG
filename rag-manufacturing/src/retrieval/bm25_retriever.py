"""
BM25 关键词检索器

【原理】
BM25 是一种基于词频的检索算法，核心思想：
- 一个词在本文档中出现越多次，这篇文档越相关（TF）
- 一个词在所有文档中都出现，说明它不重要（IDF）
- 文档越短，每个词的价值越大（长度归一化）

为什么 RAG 需要 BM25？
向量检索擅长语义："电机过载" ←→ "电流过大"
向量检索不擅长精确匹配："E03" vs "E08" → 向量分不清
BM25 擅长精确匹配："E03" → 只召回含"E03"的文档
两者互补。
"""
import jieba  # 中文分词，将查询和文档切分为词语列表
import numpy as np  # 用于BM25分数、向量分数的归一化及加权融合计算
from rank_bm25 import BM25Okapi  # BM25关键词检索模型，根据关键词匹配度计算相关性得分
from typing import List, Dict, Tuple  # 类型注解：文档列表、元数据字典、(文档,分数)结果等


class BM25Retriever:
    """BM25 关键词检索器"""
    def __init__(self):
        self.chunks = []          # 原始 chunk 列表
        self.tokenized = []       # 分词后的文档
        self.bm25 = None          # BM25 索引

    def build_index(self, chunks: List[Dict]):
        """
        构建 BM25 索引
        【原理】
        1. jieba 分词：把中文文本切成词列表
           "E03电机过载" → ["E03", "电机", "过载"]
        2. BM25Okapi：对所有分词结果建倒排索引
           倒排索引 = {词 → [文档ID列表]}
           搜"E03"时直接定位到含"E03"的文档，不需要遍历全部
        Args:
            chunks: [{"text": "...", "metadata": {...}}, ...]
        """
        self.chunks = chunks
        self.tokenized = [list(jieba.cut(chunk["text"])) for chunk in chunks]
        self.bm25 = BM25Okapi(self.tokenized) # 创建索引
        print(f"[BM25] 索引构建完成：{len(chunks)} 篇文档")

    def search(self, query: str, top_k: int = 10) -> List[Tuple[int, float]]:
        """
        BM25 检索
        Args:
            query: 用户问题（原始中文）
            top_k: 返回数量
        Returns:
            [(chunk_index, score), ...]  按分数降序
        """
        tokens = list(jieba.cut(query))
        scores = self.bm25.get_scores(tokens) # 对应分数和对应chunk的索引
        # 取 top_k
        top_indices = np.argsort(scores)[::-1][:top_k]  # 按分数顺序排序，然后再倒序，然后取前 top_k 个 chunk 的索引
        return [(int(i), float(scores[i])) for i in top_indices if scores[i] > 0] # 返回 chunk_index 和分数，按分数倒序
