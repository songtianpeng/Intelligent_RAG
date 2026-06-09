"""
合规审查 Agent — ReAct 模式

跟风控Agent结构一样，但角色不同：调用 search_rag 查政策，调用 query_financial_db 查基本信息
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from langchain.agents import create_agent
from langchain_community.chat_models import ChatTongyi
from langchain_core.messages import AIMessage
from tools import search_rag, query_financial_db

COMPLIANCE_TOOLS = [search_rag, query_financial_db]

COMPLIANCE_AGENT_PROMPT = """你是一个专业的金融合规审查Agent。

## 你的身份
投研平台合规审查节点，负责核查投资标的的合规性并给出审批结论。

## 审查规则
1. 内幕信息核查: 标的是否涉及未公开重大信息
2. 关联交易申报: 投资方与标的是否存在关联关系需申报
3. 反洗钱审查: 资金来源是否合规
4. 信息披露义务: 是否触发强制信息披露义务
5. 适当性匹配: 产品风险等级与投资者风险承受能力是否匹配
6. 创业板/ST等特殊板块需额外合规审查

## 可用工具
- search_rag(query): 检索金融政策法规和合规标准
- query_financial_db(query_type, symbol): 查询标的基本信息
  query_type: "基本面"可获取评级、行业分类等

## 工作流程
1. 从 State 获取 slots（标的、金额等）
2. 调用 search_rag 查询相关政策法规
3. 调用 query_financial_db 获取标的基本面信息（评级、行业）
4. 逐条对照审查规则判断
5. 输出最终审批结论

## 输出格式
{
  "decision": "APPROVED|REJECTED",
  "reason": "审批理由",
  "compliance_score": 0-100,
  "issues": ["合规问题"]
}"""


class ComplianceAgentNode:
    """合规审查 Agent — LangGraph 节点"""

    def __init__(self, api_key: str, model: str = "qwen-plus"):
        self.llm = ChatTongyi(
            model=model,
            dashscope_api_key=api_key,
            temperature=0.1,
        )
        self.agent = create_agent(
            model=self.llm,
            tools=COMPLIANCE_TOOLS,
            system_prompt=COMPLIANCE_AGENT_PROMPT,
        )

    def __call__(self, state: dict) -> dict:
        slots = state.get("slots", {})
        symbol = slots.get("标的", "未知")
        amount = slots.get("金额", "0")

        user_msg = f"""请对以下投资进行合规审查：
标的: {symbol}
金额: {amount}
请调用工具获取政策法规和标的基本信息，逐条对照审查规则给出结论。"""

        result = self.agent.invoke({
            "messages": [{"role": "user", "content": user_msg}],
        })

        final_msg = ""
        for m in reversed(result["messages"]):
            if isinstance(m, AIMessage):
                final_msg = m.content
                break

        return {
            "compliance_decision": "APPROVED" if "APPROVED" in final_msg.upper() else "PENDING",
            "compliance_reason": final_msg,
            "messages": [{"role": "compliance_agent", "content": final_msg}],
        }


# ── 测试 ──
if __name__ == "__main__":

    from config import settings

    agent = ComplianceAgentNode(api_key=settings.DASHSCOPE_API_KEY)

    state = {
        "slots": {"标的": "贵州茅台", "金额": "5000000"},
        "messages": [],
    }

    print("合规Agent执行中...")
    result = agent(state)

    output_path = os.path.join(os.path.dirname(__file__), "..", "..", "compliance_agent_test.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"Decision: {result['compliance_decision']}\n\n")
        f.write(f"Reason:\n{result['compliance_reason']}")
    print(f"结果已写入: {output_path}")
