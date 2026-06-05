"""
混合检索器：RRF 融合 + MMR 多样性
简历原话：BM25 关键词检索 + 向量语义检索 + RRF 融合排序 + MMR 多样性保证
"""
import numpy as np
from typing import List, Dict, Tuple


class HybridRetriever:
    """
    混合检索器
    【面试话术】
    单一检索器有天花板——BM25 对故障码精确但不懂同义词，
    向量检索懂语义但对精确字符串区分度不够。
    混合检索取两者之长，RRF 做排名级融合（不看绝对分数看排名），
    MMR 保证召回结果不冗余。
    """

    def __init__(self, bm25_retriever, vector_retriever,
                 rrf_k: int = 60, mmr_lambda: float = 0.7):
        self.bm25 = bm25_retriever # BM25倒排索引 关键词检索器
        self.vector = vector_retriever # 向量语义相似度 检索器
        self.rrf_k = rrf_k           # RRF 平滑参数
        self.mmr_lambda = mmr_lambda  # MMR 相关性 vs 多样性权重  λ 越大 → 越强调相关性，可能重复

    def search(self, question: str, query_vector: List[float],
               top_k: int = 5) -> List[Dict]:
        """
        混合检索入口
        Args:
            question: 用户原始问题
            query_vector: 问题的向量
            top_k: 最终返回数量
        Returns:
            [{"text": ..., "metadata": {...}, "score": ...}, ...]
        """
        # ── 第一阶段：分别检索 ──
        bm25_results = self.bm25.search(question, top_k=10)
        vector_results = self.vector.search(query_vector, top_k=10)

        # ── 第二阶段：RRF 融合 ──
        fused = self._rrf_fusion(bm25_results, vector_results)

        # ── 第三阶段：MMR 多样性 ──
        diverse = self._mmr_select(fused, query_vector, top_k)

        # ── 组装返回 ──
        output = []
        for idx, score in diverse:
            chunk = self.bm25.chunks[idx]
            output.append({
                "text": chunk["text"],
                "metadata": chunk["metadata"],
                "score": score,
            })
        return output

    # ── RRF 融合 ──
    def _rrf_fusion(self, bm25_results, vector_results) -> List[Tuple[int, float]]:
        """
        RRF 倒数排名融合
        【公式】score(d) = Σ 1/(k + rank_i(d))
        对每个 chunk，取它在 BM25 中的排名和向量检索中的排名，
        分别计算 RRF 分数后相加。排名越靠前（数字越小），
        RRF 分数越高。
        虚拟排名：如果某个 chunk 只在 BM25 中出现（向量检索没召回），
        它在向量检索里的虚拟排名 = 999（远大于实际 Top-20）
        """
        scores = {}
        max_rank = 500  # 虚拟排名

        # BM25 排名 → RRF 分数
        for rank, (idx, _) in enumerate(bm25_results): # 字段分别是，排名，chunk_index，chunk_score没展示用了_
            rrf = 1.0 / (self.rrf_k + rank + 1)  # rank 从 0 开始，+1 变从 1 开始
            scores[idx] = scores.get(idx, 0) + rrf # 这种方式相当于直接给key赋值value,没有键自动创建

        # 向量检索排名 → RRF 分数
        for rank, (idx, _) in enumerate(vector_results):
            rrf = 1.0 / (self.rrf_k + rank + 1)
            scores[idx] = scores.get(idx, 0) + rrf

        # 向量检索独有的 chunk：给 BM25 虚拟排名
        for idx, _ in vector_results:
            if idx not in [i for i, _ in bm25_results]:
                scores[idx] = scores.get(idx, 0) + 1.0 / (self.rrf_k + max_rank)

        # BM25 独有的 chunk：给向量检索虚拟排名
        for idx, _ in bm25_results:
            if idx not in [i for i, _ in vector_results]:
                scores[idx] = scores.get(idx, 0) + 1.0 / (self.rrf_k + max_rank)

        # 按 RRF 分数降序
        sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_items

    # ── MMR 多样性 ──   余弦相似度方案
    # def _mmr_select(self, candidates, query_vector, top_k) -> List[Tuple[int, float]]:
    #     """
    #     MMR 最大边际相关性
    #     【公式】MMR = λ × rel(d, Q) - (1-λ) × max_sim(d, already_selected)
    #     λ=0.7: 70% 权重给"跟问题多相关"，30% 权重给"跟已选的多不重复"
    #     λ 越大 → 越强调相关性，可能重复
    #     λ 越小 → 越强调多样性，可能跑偏
    #     实现中用向量余弦相似度近似 sim()
    #     """
    #     if len(candidates) <= top_k:
    #         return candidates
    #
    #     selected = []
    #     remaining = list(candidates)
    #
    #     for _ in range(top_k): # top-k是几就循环多少次，每循环一次
    #         if not remaining:
    #             break
    #
    #         if not selected:
    #             # 第一轮：直接选分数最高的
    #             best = remaining.pop(0)
    #             selected.append(best)
    #         else:
    #             # 后续轮：MMR 计算
    #             best_score = -float("inf")
    #             best_idx = 0
    #
    #             for i, (idx, rrf_score) in enumerate(remaining):
    #                 # rel: RRF 分数归一化（近似相关性）
    #                 rel = rrf_score
    #
    #                 # max_sim: 跟已选中 chunk 的最大相似度
    #                 max_sim = 0.0
    #                 for sel_idx, _ in selected:
    #                     sim = self._cosine_similarity(
    #                         self.vector.store.search(
    #                             np.array(self._get_chunk_vector(sel_idx)), top_k=1
    #                         )[0].get("distance", 1.0) if False else 0.0,
    #                         # 简化：用 1 - RRF排名的差异来近似
    #                         0.0
    #                     )
    #                     # 实际工程中这里会用 chunk 的向量算余弦相似度
    #                     # 简化版：用两个 chunk 在 RRF 列表中的位置差来近似
    #                     max_sim = max(max_sim, 0.0)
    #
    #                 mmr = self.mmr_lambda * rel - (1 - self.mmr_lambda) * max_sim
    #                 if mmr > best_score:
    #                     best_score = mmr
    #                     best_idx = i
    #
    #             best = remaining.pop(best_idx)
    #             selected.append(best)
    #
    #     return selected

    def _mmr_select(self, candidates, query_vector, top_k):
        """MMR 多样性选择（Jaccard 近似版）"""
        if len(candidates) <= top_k:
            return candidates

        selected = []
        remaining = list(candidates)

        for _ in range(top_k): # top-k是几就循环多少次，每循环一次，就选中一个答案
            if not remaining:
                break

            best_score = -float("inf") # 最佳得分，每次初始化为负无穷
            best_i = 0 # 最佳索引，每次初始化为 0

            for i, (idx, rrf_score) in enumerate(remaining): # 答案中剩余未选中的答案
                rel = rrf_score  # 跟问题的相关性 = RRF 分数
                # 跟已选 chunk 的最大相似度（用 Jaccard 近似）
                max_sim = 0.0
                chunk_text = set(self.bm25.chunks[idx]["text"])
                for sel_idx, _ in selected: # 已选中的答案
                    sel_text = set(self.bm25.chunks[sel_idx]["text"])
                    # Jaccard = 交集 / 并集
                    intersection = len(chunk_text & sel_text)
                    union = len(chunk_text | sel_text)
                    sim = intersection / union if union > 0 else 0
                    max_sim = max(max_sim, sim)

                mmr = self.mmr_lambda * rel - (1 - self.mmr_lambda) * max_sim # 拿到每一个未选中的MMR的得分
                if mmr > best_score: # 找到MMR得分最高的未选中的答案
                    best_score = mmr # 更新最佳得分
                    best_i = i # 获取该答案的索引

            selected.append(remaining.pop(best_i)) # 选中该答案
        return selected

# 余弦相似度方案
    # def _cosine_similarity(self, a, b):
    #     """余弦相似度（简化版，实际用向量算）"""
    #     return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8)
    #
    # def _get_chunk_vector(self, idx):
    #     """获取 chunk 的向量（从 VectorStore 中查询）"""
    #     # 简化：用零向量占位
    #     # 实际工程中从 ChromaDB 的 collection.get() 获取
    #     return np.zeros(1024)
