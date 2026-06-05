"""
三级混合记忆管理 — 5轮周期压缩
"""
import json
from typing import List, Dict, Optional

from langchain_community.chat_models import ChatTongyi
from langchain_core.messages import HumanMessage,AIMessage,SystemMessage


COMPRESS_PROMPT = """你是一个工业设备运维对话的信息压缩助手。

请根据以下内容完成两项任务：
1. 将对话压缩为不超过200字的摘要，只保留事实性的排查信息
2. 提取关键槽位（如果有的话）

旧摘要：{old_summary}
旧槽位：{old_slots}
近5轮对话：
{recent_dialog}

严格按JSON格式输出，不要加任何前缀解释或其他格式：
{{"summary": "新的合并摘要", "slots": {{"fault_code": "E03", "device_model": "HTF1200"}}}}"""

class MemoryManager:
    def __init__(self, api_key: str, max_recent: int = 5):
        self.max_recent = max_recent
        self.recent_messages: List[str] = []  # 累积近5轮原文
        self.summary: str = ""
        self.slots: Dict[str, str] = {}

        # ChatTongyi: LangChain 封装，跟 embedding.py 的 DashScopeEmbeddings 一个风格
        self.llm = ChatTongyi(
            model="qwen-turbo",
            dashscope_api_key=api_key,
            temperature=0.1,  # 低温度 → 输出稳定，JSON不乱
        )

    def add_turn(self, question: str, answer: str):
        """添加一轮问答，满5轮自动压缩"""
        self.recent_messages.append(f"用户：{question}")
        self.recent_messages.append(f"专家：{answer}")

        if len(self.recent_messages) >= self.max_recent * 2:
            self._compress()

    def get_context(self) -> str:
        """构建给 LLM 的上下文（检索增强后的 Prompt 里用）"""
        parts = []
        if self.summary:
            parts.append(f"[历史摘要] {self.summary}")
        if self.slots:
            parts.append(f"[关键信息] {json.dumps(self.slots, ensure_ascii=False)}")
        if self.recent_messages:
            parts.append("[近期对话]\n" + "\n".join(self.recent_messages[-10:]))
        return "\n\n".join(parts)

    def reset(self):
        self.recent_messages = []
        self.summary = ""
        self.slots = {}

    def _compress(self):
        """核心：一次调用完成压缩+槽位提取"""
        # 1. 准备数据
        recent_dialog = "\n".join(self.recent_messages)
        old_summary = self.summary or "（无历史摘要）"
        old_slots = json.dumps(self.slots, ensure_ascii=False) if self.slots else "（无历史槽位）"

        # 2. 构造 Prompt
        prompt = COMPRESS_PROMPT.format(
            old_summary=old_summary,
            old_slots=old_slots,
            recent_dialog=recent_dialog,
        )

        # 3. 调 ChatTongyi
        try:
            resp = self.llm.invoke([HumanMessage(content=prompt)])
            result = json.loads(resp.content)  # 解析 JSON
            self.summary = result.get("summary", "")
            self.slots = result.get("slots", {})
        except (json.JSONDecodeError, Exception) as e:
            print(f"[Memory] 压缩失败: {e}，使用截断降级")
            self.summary = recent_dialog[-300:]
            self.slots = {}

        # 4. 清空累积（开始下一个5轮周期）
        self.recent_messages = []
        print(f"[Memory] 压缩完成: 摘要{len(self.summary)}字, 槽位{len(self.slots)}个")


if __name__ == "__main__":
    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from config import settings

    mem = MemoryManager(api_key=settings.DASHSCOPE_API_KEY)

    # 模拟8轮
    rounds = [
        ("HTF1200注塑机E03报警怎么办", "E03是电机过载，检查机械传动、测量三相电压、降低负载"),
        ("传动没有卡滞", "那测量三相电压，看偏差是否超过5%"),
        ("电压也正常", "可能是负载过大，检查是否超过最大注射量"),
        ("还有其他原因吗", "检查变频器电流限幅值是否设置正确"),
        ("变频器正常", "检查电机轴承磨损和绝缘电阻"),
        # 第5轮结束 → 触发压缩
        ("电机轴承有异响", "轴承磨损会导致电流增大触发E03，建议更换轴承"),
        ("换完轴承了", "更换后确认电流是否恢复正常，E03应该不会再出现"),
        ("故障排除了", "很好，建议每季度检查轴承润滑，预防类似故障"),
    ]

    for q, a in rounds:
        mem.add_turn(q, a)

    print("\n===== 最终状态 =====")
    print(f"摘要: {mem.summary}")
    print(f"槽位: {mem.slots}")
    print(f"近轮累积: {len(mem.recent_messages)} 条")
    print(f"\n===== 给LLM的上下文 =====")
    print(mem.get_context())

