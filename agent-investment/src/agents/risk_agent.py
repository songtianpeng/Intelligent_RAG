"""
风控审批 Agent — ReAct 模式

create_agent 自动生成 Thought → Action → Observation 循环：
- Thought: Agent 分析当前信息，决定下一步
- Action: 调用工具(query_financial_db, sentiment_analysis)
- Observation: 收到工具返回
- 重复直到输出最终审批结论(APPROVED/REJECTED)
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from langchain.agents import create_agent
from langchain_community.chat_models import ChatTongyi
from langchain_core.messages import AIMessage
from tools import query_financial_db, sentiment_analysis

RISK_TOOLS = [query_financial_db, sentiment_analysis]

RISK_AGENT_PROMPT = """你是一个专业的金融风控审批Agent。

## 你的身份
投研平台风控审批节点，负责对投资标的进行风险评估并给出审批结论。

## 审批规则（红线）
1. 单一标的集中度 <= 10%
2. VaR(95%) <= 2%
3. 杠杆率 <= 140%
4. 流动性覆盖率 >= 100%
5. 单笔投资金额 > 500万需额外投委会审批

## 可用工具
- query_financial_db(query_type, symbol, amount): 查询标的财务数据
  query_type可选: "基本面" / "估值" / "历史波动"
- sentiment_analysis(topic, days): 查询市场舆情

## 工作流程
1. 先从 State 中获取 slots（标的、金额等）
2. 调用 query_financial_db 查询基本面和历史波动数据
3. 根据需要调用 sentiment_analysis 查看舆情
4. 对照审批红线逐条判断
5. 输出最终审批结论

## 输出格式
{
  "decision": "APPROVED|REJECTED",
  "reason": "审批理由，逐条对照红线说明",
  "risk_score": 0-100,
  "concerns": ["关注点"]
}"""


class RiskAgentNode:
    """
    风控审批 Agent — LangGraph 节点

    ReAct 循环由 create_agent 自动处理：
    1. Agent 读入 State（含 slots）
    2. 自主决定调用哪些工具
    3. 拿到数据后对照片审批红线给出结论
    4. 返回审批结果
    """

    def __init__(self, api_key: str, model: str = "qwen-plus"):
        self.llm = ChatTongyi(
            model=model,
            dashscope_api_key=api_key,
            temperature=0.1,
        )
        self.agent = create_agent(
            model=self.llm,
            tools=RISK_TOOLS,
            system_prompt=RISK_AGENT_PROMPT,
        )

    def __call__(self, state: dict) -> dict:
        slots = state.get("slots", {})
        symbol = slots.get("标的", "未知")
        amount = slots.get("金额", "0")

        # 构造清晰的输入
        user_msg = f"""请对以下投资进行风控评估：
标的: {symbol}
金额: {amount}
请调用工具获取相关数据，然后逐条对照审批红线给出结论。"""

        result = self.agent.invoke({
            "messages": [{"role": "user", "content": user_msg}],
        })

        # 提取最后一条 AI 消息
        final_msg = ""
        for m in reversed(result["messages"]):
            if isinstance(m, AIMessage):
                final_msg = m.content
                break

        return {
            "risk_decision": "APPROVED" if "APPROVED" in final_msg.upper() else "PENDING",
            "risk_reason": final_msg,
            "messages": [{"role": "risk_agent", "content": final_msg}],
        }


# ── 测试 ──
if __name__ == "__main__":

    from config import settings

    agent = RiskAgentNode(api_key=settings.DASHSCOPE_API_KEY)

    state = {
        "slots": {"标的": "贵州茅台", "金额": "5000000"},
        "messages": [],
    }

    print("风控Agent执行中...")
    result = agent(state)

    output_path = os.path.join(os.path.dirname(__file__), "..", "..", "risk_agent_test.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"Decision: {result['risk_decision']}\n\n")
        f.write(f"Reason:\n{result['risk_reason']}")
    print(f"结果已写入: {output_path}")
