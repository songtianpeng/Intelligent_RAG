"""
Aggregator — 结论聚合节点

职责: 收集并行/串行审批 Agent 的结果 → LLM 汇总 → 生成统一结论
输入给下一步 Human Approval 做最终裁决
"""
from langchain_community.chat_models import ChatTongyi
from langchain_core.messages import HumanMessage


AGGREGATOR_PROMPT = """你是一个投研审批结论汇总专家。

请根据以下审批 Agent 的输出，生成一份结构化的审批汇总报告。

## 输出格式
1. **审批概要**: 一句话总结
2. **风控评估**: 风控Agent的结论和关键风险点
3. **合规评估**: 合规Agent的结论和合规要点
4. **综合建议**: APPROVED / REJECTED / NEED_DISCUSSION
5. **风险提示**: 需要投委会或人工关注的要点

## 各 Agent 输出"""


class AggregatorNode:
    """结论聚合节点"""

    def __init__(self, api_key: str, model: str = "qwen-turbo"):
        self.llm = ChatTongyi(
            model=model,
            dashscope_api_key=api_key,
            temperature=0.1,
        )

    def __call__(self, state: dict) -> dict:
        # 从 messages 中提取各 Agent 的回复
        agent_outputs = []
        for msg in state.get("messages", []):
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role in ("risk_agent", "compliance_agent", "ai"):
                agent_outputs.append(f"[{role}]: {content}")
            elif hasattr(msg, "name") and hasattr(msg, "content"):
                if getattr(msg, "name", "") in ("risk_agent", "compliance_agent"):
                    agent_outputs.append(f"[{msg.name}]: {msg.content}")

        outputs_text = "\n\n".join(agent_outputs) if agent_outputs else "暂无审批Agent输出"

        resp = self.llm.invoke([
            HumanMessage(content=f"{AGGREGATOR_PROMPT}\n\n{outputs_text}"),
        ])

        return {
            "aggregated_result": resp.content,
            "messages": [{"role": "aggregator", "content": resp.content}],
        }


# ── 测试 ──
if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from config import settings

    agg = AggregatorNode(api_key=settings.DASHSCOPE_API_KEY)

    # 模拟审批后的 State
    state = {
        "messages": [
            {"role": "risk_agent", "content": "风控评估: APPROVED。集中度8.5%<10%, VaR=1.8%<2%, "
             "杠杆率125%<140%。风险评分: 15/100。关注点: 消费行业下行风险。"},
            {"role": "compliance_agent", "content": "合规审查: APPROVED。标的600519无内幕信息风险, "
             "关联交易已申报, 反洗钱审查通过。需注意: 投资金额超500万需投委会备案。"},
        ]
    }

    result = agg(state)
    output_path = os.path.join(os.path.dirname(__file__), "..", "..", "aggregator_test.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(result["aggregated_result"])
    print(f"聚合结果已写入: {output_path}")
