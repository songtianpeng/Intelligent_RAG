"""
问答缓存 — 开发用本地字典，生产切 Redis
"""
import hashlib


class QACache:
    """
    问答缓存
    【面试话术】
    产线上同一个故障码（如E03报警）每天可能被几十个操作员搜索，
    缓存命中后直接返回，不需要再走检索+LLM生成，延迟从2秒降到50ms以内。

    开发阶段用 Python dict 替代 Redis（接口一致），
    部署到 Linux 服务器时切 Redis——改一行就行。
    """

    def __init__(self, redis_client=None):
        """
        Args:
            redis_client: redis.Redis 实例。传 None 则用本地字典
        """
        self.redis = redis_client
        self._local_cache = {}  # 开发用

    def _make_key(self, question: str) -> str:
        """MD5(问题文本) → 缓存键"""
        return "rag:cache:" + hashlib.md5(question.encode("utf-8")).hexdigest()

    def get(self, question: str):
        """查缓存，命中返回 dict，未命中返回 None"""
        key = self._make_key(question)
        if self.redis:
            val = self.redis.get(key)
            if val:
                import json
                return json.loads(val) # 反序列化
        else:
            return self._local_cache.get(key)
        return None

    def set(self, question: str, answer_data: dict, ttl: int = 86400):
        """
        写缓存
        ttl: 过期秒数，默认 86400 = 24小时
        """
        key = self._make_key(question)
        if self.redis:
            import json
            self.redis.setex(key, ttl, json.dumps(answer_data, ensure_ascii=False))
        else:
            self._local_cache[key] = answer_data

    def stats(self) -> dict:
        """缓存统计"""
        if self.redis:
            # Redis: 用 DBSIZE 近似
            return {"backend": "redis", "size": self.redis.dbsize()}
        return {"backend": "dict", "size": len(self._local_cache)}
