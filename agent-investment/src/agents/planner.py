"""
Planner Agent — 系统级路由中枢

职责: 接收用户输入 → 意图识别 → 槽位提取 → 路由决策
不处理具体业务，只做分类和分发。

【LangGraph 节点接口】
__call__(state) -> dict  返回部分 State 更新
"""
import json, re
from dashscope import Generation
from langchain_community.chat_models import ChatTongyi
from langchain_core.messages import HumanMessage, SystemMessage


PLANNER_SYSTEM_PROMPT = """你是一个金融投研平台的智能路由助手。

## 职责
分析用户输入，判断意图类型并提取关键信息。只输出JSON，不要加任何解释。

## 意图分类

### 1. chitchat（闲聊）
问候、感谢、或与投研业务无关的对话。
示例: "你好"、"谢谢"

### 2. tool_call（工具调用）
用户要求查询数据、分析标的、查看舆情，但不涉及审批流程。
示例: "帮我查茅台的财务数据"、"茅台最近舆情怎么样"

### 3. workflow（流程发起）
用户明确要求发起审批、评估、评级等业务流程。
示例: "帮我审批茅台500万投资"、"发起债券A的主体评级"

## 槽位提取
提取以下信息（没有就填null）:
- 标的: 股票/债券/基金名称或代码
- 金额: 数字+单位
- 发行方: 债券发行人(仅债券)

## 置信度低于0.7需要人工确认

## 输出格式（严格JSON，不要加markdown代码块）
{"intent": "chitchat|tool_call|workflow", "confidence": 0.0-1.0, "slots": {"标的": "贵州茅台", "金额": "5000000"}, "tool_name": "search_rag|query_financial_db|sentiment_analysis|null", "workflow_type": "stock_approval|bond_rating|credit_approval|null", "reasoning": "判断依据"}"""


class PlannerNode:
    """Planner Agent — LangGraph 节点"""

    def __init__(self, api_key: str, model: str = "qwen-turbo"):
        self.api_key = api_key
        self.model = model
        self.llm = ChatTongyi(
            model=model,
            dashscope_api_key=api_key,
            temperature=0.1,  # 低温度 → 路由决策稳定
        )

    def __call__(self, state: dict) -> dict:
        """
        LangGraph 节点入口
        输入: InvestmentState
        输出: 更新的字段 (intent, confidence, slots, ...)
        """
        question = state["messages"][-1]["content"]

        # ── 调用 LLM ──
        raw = self._call_llm(question)
        print(f"[Planner] 原始输出: {raw[:150]}...")

        # ── 解析 + 兜底 ──
        parsed = self._parse(raw, question)

        return {
            "intent": parsed["intent"],
            "confidence": parsed["confidence"],
            "slots": parsed["slots"],
            "tool_name": parsed.get("tool_name", ""),
            "workflow_type": parsed.get("workflow_type", ""),
            "need_human_confirm": parsed["confidence"] < 0.7,
            "messages": [
                {"role": "planner",
                 "content": f"意图={parsed['intent']}, "
                            f"置信度={parsed['confidence']}, "
                            f"槽位={parsed['slots']}"}
            ],
        }

    def _call_llm(self, question: str) -> str:
        """调 ChatTongyi"""
        resp = self.llm.invoke([
            SystemMessage(content=PLANNER_SYSTEM_PROMPT),
            HumanMessage(content=question),
        ])
        return resp.content

    def _parse(self, raw: str, question: str) -> dict:
        """解析LLM输出 + Schema兜底"""
        # 提取JSON（LLM可能在JSON外加说明）
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        json_str = match.group(0) if match else raw

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            print(f"[Planner] JSON解析失败，使用兜底")
            return self._fallback(question)

        # 校验必需字段
        if "intent" not in data or data["intent"] not in ("chitchat", "tool_call", "workflow"):
            print(f"[Planner] intent字段无效: {data.get('intent')}")
            return self._fallback(question)

        data.setdefault("confidence", 0.5)
        data.setdefault("slots", {})
        data.setdefault("tool_name", "")
        data.setdefault("workflow_type", "")
        return data

    def _fallback(self, question: str) -> dict:
        """兜底：无法解析时默认走 chitchat"""
        return {
            "intent": "chitchat",
            "confidence": 0.3,
            "slots": {},
            "tool_name": "",
            "workflow_type": "",
        }


# ── 测试 ──
if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from config import settings

    planner = PlannerNode(api_key=settings.DASHSCOPE_API_KEY)

    tests = [
        {"messages": [{"role": "user", "content": "帮我查一下茅台的财务数据"}]},
        {"messages": [{"role": "user", "content": "你好"}]},
        {"messages": [{"role": "user", "content": "帮我审批茅台500万投资"}]},
    ]

    for i, state in enumerate(tests):
        print(f"\n{'=' * 50}")
        print(f"测试 {i+1}: {state['messages'][-1]['content']}")
        result = planner(state)
        print(f"  意图: {result['intent']}")
        print(f"  置信度: {result['confidence']}")
        print(f"  槽位: {result['slots']}")
        print(f"  工具: {result['tool_name']}")
        print(f"  流程类型: {result['workflow_type']}")
        print(f"  需人工确认: {result['need_human_confirm']}")
