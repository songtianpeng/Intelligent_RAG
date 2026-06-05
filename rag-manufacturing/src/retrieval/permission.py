"""
权限隔离 — ChromaDB where 标量过滤

【原理】
每个文档在入库时打上 factory 和 production_line 标签。
检索时根据用户身份构建 where 过滤条件，在向量检索前缩小范围。

两个效果：
1. 杜绝信息泄露：一厂操作员看不到二厂的维保文档
2. 提升检索精度：无关文档不进候选池，RRF 排序更准
"""
from typing import Dict, Optional


class PermissionManager:
    """
    权限隔离管理器
    【面试话术】
    工业场景下不同产线的维修手册互不可见——一厂的操作员不应该搜到二厂注塑机的故障码。
    实现上用 ChromaDB 的 where 子句做检索前置过滤：
    不是搜完全库再做权限判断（费时），而是在向量检索开始前就用标量索引缩小范围。
    """
    # 文档 → 权限映射（生产环境从数据库读，这里硬编码）
    DOC_PERMISSIONS = {
        "01_注塑机操作手册.docx": {"factory": "一厂", "production_line": "注塑产线"},
        "01_注塑机操作手册.pdf":  {"factory": "一厂", "production_line": "注塑产线"},
        "02_故障码手册.docx":     {"factory": "*", "production_line": "*"},  # 公共
        "02_故障码手册.pdf":      {"factory": "*", "production_line": "*"},
        "03_维保操作规范.docx":   {"factory": "*", "production_line": "*"},
        "03_维保操作规范.pdf":    {"factory": "*", "production_line": "*"},
    }

    def enrich_metadatas(self, metadatas: list) -> list:
        """
        入库前给每条的 metadata 注入权限字段
        在 vector_store.build() 里调用
        """
        for meta in metadatas:
            source = meta.get("source", "")
            perm = self.DOC_PERMISSIONS.get(source, {})
            meta["factory"] = perm.get("factory", "*")
            meta["production_line"] = perm.get("production_line", "*")
        return metadatas

    def build_filter(
        self, factory: Optional[str] = None, production_line: Optional[str] = None
    ) -> Optional[Dict]:
        """
        构建 ChromaDB where 过滤条件

        【过滤逻辑】
        用户可访问 = (自己的工厂) OR (公共文档)
        公共文档用 "*" 标记，不做过滤

        示例：
          用户来自 "一厂/注塑产线"
          → 能看到 factory IN ("一厂", "*") AND production_line IN ("注塑产线", "*")

        返回 None 表示不过滤（管理员或未指定身份时）
        """
        if not factory and not production_line:
            return None  # 无身份 → 不过滤

        conditions = []

        if factory:
            # 自己的工厂 或 公共文档
            conditions.append({"$or": [
                {"factory": factory},
                {"factory": "*"},
            ]})

        if production_line:
            conditions.append({"$or": [
                {"production_line": production_line},
                {"production_line": "*"},
            ]})

        if len(conditions) == 1:
            return conditions[0]
        return {"$and": conditions}
