"""
三级混合记忆管理 — 5轮周期压缩
从项目一复用，适配项目二 State 结构

【面试话术】
多轮投研对话中，用户可能说"改成1000万"——这句话离开了上下文无法理解。
三级记忆保证 Agent 知道"之前的标的是茅台、现在金额是1000万"。
"""
import json
from typing import List, Dict

from langchain_community.chat_models import ChatTongyi
from langchain_core.messages import HumanMessage


COMPRESS_PROMPT = """你是一个投研对话信息压缩助手。

根据旧摘要、旧槽位和近5轮对话，完成两项任务：
1. 合并生成不超过200字的新摘要（只保留事实性排查信息）
2. 更新关键槽位（标的、金额、发行方、风控偏好等）

旧摘要：{old_summary}
旧槽位：{old_slots}
近5轮对话：
{recent_dialog}

严格按JSON格式输出：
{{"summary": "合并后的摘要", "slots": {{"标的": "贵州茅台", "金额": "5000000"}}}}"""


class MemoryManager:
    """投研对话记忆管理（5轮压缩周期）"""

    def __init__(self, api_key: str, max_recent: int = 5):
        self.max_recent = max_recent
        self.recent_messages: List[str] = []
        self.summary: str = ""
        self.slots: Dict[str, str] = {}

        self.llm = ChatTongyi(
            model="qwen-turbo",
            dashscope_api_key=api_key,
            temperature=0.1,
        )

    def add_turn(self, question: str, answer: str):
        """添加一轮问答，满5轮自动触发压缩"""
        self.recent_messages.append(f"用户：{question}")
        self.recent_messages.append(f"助手：{answer}")

        if len(self.recent_messages) >= self.max_recent * 2:
            self._compress()

    def get_context(self) -> str:
        """构建给 LLM 的上下文"""
        parts = []
        if self.summary:
            parts.append(f"[历史摘要] {self.summary}")
        if self.slots:
            parts.append(f"[关键信息] {json.dumps(self.slots, ensure_ascii=False)}")
        if self.recent_messages:
            parts.append("[近期对话]\n" + "\n".join(self.recent_messages[-10:]))
        return "\n\n".join(parts)

    def augment_question(self, question: str) -> str:
        """把记忆上下文拼到用户问题里（检索增强用）"""
        ctx = self.get_context()
        return f"{ctx}\n\n当前问题：{question}" if ctx else question

    def reset(self):
        self.recent_messages = []
        self.summary = ""
        self.slots = {}

    def _compress(self):
        """一次 ChatTongyi 调用完成压缩+槽位更新"""
        recent_dialog = "\n".join(self.recent_messages)
        old_summary = self.summary or "（无）"
        old_slots = json.dumps(self.slots, ensure_ascii=False) if self.slots else "（无）"

        prompt = COMPRESS_PROMPT.format(
            old_summary=old_summary,
            old_slots=old_slots,
            recent_dialog=recent_dialog,
        )

        try:
            resp = self.llm.invoke([HumanMessage(content=prompt)])
            result = json.loads(resp.content)
            self.summary = result.get("summary", "")
            self.slots = result.get("slots", {})
        except Exception as e:
            print(f"[Memory] 压缩失败: {e}")
            self.summary = recent_dialog[-300:]

        self.recent_messages = []
        print(f"[Memory] 压缩完成: 摘要{len(self.summary)}字, 槽位{len(self.slots)}个")


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from config import settings

    mem = MemoryManager(api_key=settings.DASHSCOPE_API_KEY)

    # ── 正确流程：提交前累积槽位，提交后冻结 ──
    rounds = [
        # 阶段1: 用户描述需求 → 系统提取槽位，不提交
        ("帮我审批茅台500万投资",
         "已理解: 标的=贵州茅台, 金额=500万。请确认是否发起审批？"),
        # 阶段2: 用户修改槽位 → 系统更新，仍不提交
        ("改成1000万",
         "已更新: 金额从500万改为1000万。还需要修改什么吗？"),
        # 阶段3: 用户补充信息 → 系统追加槽位
        ("风控偏好改成保守型",
         "已补充: 风控偏好=保守型。当前信息: 标的=贵州茅台, 金额=1000万, 偏好=保守。确认发起？"),
        # 阶段4: 用户确认 → 系统此时才调用 Router 分发流程
        ("确认发起",
         "流程已提交。任务ID: abc123, 类型: 股票审批。风控和合规Agent正在并行评估，请稍候。"),
        # 阶段5: 流程已运行中，用户再改 → 系统提示不可修改
        ("等等，金额改成2000万",
         "流程 abc123 已在审批中，无法直接修改。请先撤回/驳回后重新发起，或发起一个新流程。"),
    ]

    for q, a in rounds:
        mem.add_turn(q, a)

    output_path = os.path.join(os.path.dirname(__file__), "..", "memory_test.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"摘要: {mem.summary}\n\n")
        f.write(f"槽位: {json.dumps(mem.slots, ensure_ascii=False, indent=2)}\n\n")
        f.write(f"上下文:\n{mem.get_context()}")
    print(f"结果已写入: {output_path}")
