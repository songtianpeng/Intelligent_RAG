"""
工具调用 Agent — 非流程类请求

Planner 识别到 tool_call 意图后路由到这个节点。
用 create_agent 绑定工具，Agent 自主决定调哪个工具、传什么参数、
拿到结果后如何总结。

【与 workflow 类请求的区别】
- tool_call: 调一次工具，结果直接返回给用户（结束）
- workflow: 走完整的多 Agent 审批链路（Router → Subgraph → Aggregator → Human）
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from langchain.agents import create_agent
from langchain_community.chat_models import ChatTongyi
from langchain_core.messages import AIMessage
from tools import ALL_TOOLS


SYSTEM_PROMPT = """你是一个金融投研数据查询助手。

## 可用工具
- search_rag(query): 检索金融政策法规和合规标准
- query_financial_db(query_type, symbol, amount): 查询标的财务数据。
  query_type 可选: "基本面" / "估值" / "舆情" / "历史波动"
- sentiment_analysis(topic, days): 舆情情感分析

## 工作规则
1. 先分析用户问题，确定需要调用哪个工具
2. 调用工具获取数据
3. 用简洁的语言总结数据，给出分析结论
4. 如果用户问题需要多个工具，可以依次调用"""


class ToolAgentNode:
    """
    公共工具 Agent — LangGraph 节点

    create_agent 会自动生成 ReAct 循环:
    Thought → Action(调工具) → Observation(工具返回) → 重复 → Final Answer
    """

    def __init__(self, api_key: str, model: str = "qwen-plus"):
        self.llm = ChatTongyi(
            model=model,
            dashscope_api_key=api_key,
            temperature=0.1,
        )
        # ★ create_agent: LangChain 1.x 统一 Agent 工厂
        # 自动处理 tool calling 循环，不需要手动写 ReAct 逻辑
        self.agent = create_agent(
            model=self.llm,
            tools=ALL_TOOLS,
            system_prompt=SYSTEM_PROMPT,
        )

    def __call__(self, state: dict) -> dict:
        question = state["messages"][-1]["content"]

        # invoke agent — 它会自动调工具、拿到结果、生成回复
        result = self.agent.invoke({
            "messages": [{"role": "user", "content": question}],
        })

        # 提取最后一条 AI 消息作为回复
        final_msg = ""
        for m in reversed(result["messages"]):
            if isinstance(m, AIMessage):
                final_msg = m.content
                break

        return {
            "final_report": final_msg,
            "messages": [{"role": "assistant", "content": final_msg}],
        }


# ── 测试 ──
if __name__ == "__main__":

    from config import settings

    node = ToolAgentNode(api_key=settings.DASHSCOPE_API_KEY)

    tests = [
        "帮我查一下茅台的财务数据",
        "茅台最近舆情怎么样",
        "股票投资有什么风控要求",
    ]

    # 写文件避免GBK报错
    output_path = os.path.join(os.path.dirname(__file__), "..", "..", "tool_agent_test.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        for q in tests:
            f.write(f"\n{'=' * 50}\n")
            f.write(f"用户: {q}\n\n")
            state = {"messages": [{"role": "user", "content": q}]}
            result = node(state)
            f.write(f"Agent: {result['final_report']}\n")
            f.write(f"消息数: {len(result['messages'])}\n")

    print(f"测试结果已写入: {output_path}")
