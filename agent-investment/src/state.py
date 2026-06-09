"""
LangGraph State 定义 — 贯穿 Planner → Router → Subgraph → Aggregator → Human
"""
from typing import TypedDict, List, Dict, Annotated, Optional
from operator import add


class InvestmentState(TypedDict):
    """投研工作流 State"""

    # ── 输入层 ──
    messages: Annotated[List[Dict], add]
    # 对话历史，Annotated[..., add] 表示追加而非覆盖
    # 每个节点往里加自己的消息，后续节点能看到完整历史

    user_id: int
    # 当前用户ID，用于权限校验

    # ── Planner 输出 ──
    intent: str
    # chitchat / tool_call / workflow

    confidence: float
    # 意图置信度 0-1

    slots: Dict[str, str]
    # 关键槽位: {"标的": "贵州茅台", "金额": "5000000"}

    need_human_confirm: bool
    # Planner 低置信度时标记为 True

    tool_name: str
    # 工具调用类: search_rag / query_financial_db / sentiment_analysis

    tool_args: Dict
    # 工具参数

    workflow_type: str
    # 流程类型: stock_approval / bond_rating / credit_approval

    task_id: str
    # 异步任务ID

    # ── Workflow Router 输出 ──
    permission_checked: bool
    # 权限校验是否通过

    # ── 审批 Agent 输出 (并行, 存在 messages 里) ──
    risk_decision: str
    # APPROVED / REJECTED

    risk_reason: str

    compliance_decision: str

    compliance_reason: str

    # ── Aggregator 输出 ──
    aggregated_result: str
    # 审批结论聚合文本

    # ── Human Approval ──
    human_approved: Optional[bool]
    # None=等待中, True=通过, False=驳回

    human_feedback: str
    # 人工审批意见

    # ── 输出 ──
    final_report: str

    # ── Trace ──
    trace_id: str
    # = task_id, 全链路追踪ID


if __name__ == "__main__":
    # 测试: 验证 State 结构
    from langgraph.graph import StateGraph

    def test_node(state: InvestmentState) -> dict:
        print(f"  intent={state.get('intent','?')}, slots={state.get('slots',{})}")
        return {"messages": [{"role": "test", "content": "ok"}]}

    graph = StateGraph(InvestmentState)
    graph.add_node("test", test_node)
    graph.set_entry_point("test") # 默认入口点
    graph.set_finish_point("test") # 默认结束点
    app = graph.compile()

    result = app.invoke({
        "messages": [{"role": "user", "content": "帮我审批茅台500万投资"}],
        "user_id": 1001,
        "intent": "workflow",
        "confidence": 0.92,
        "slots": {"标的": "贵州茅台", "金额": "5000000"},
        "need_human_confirm": False,
        "tool_name": "",
        "tool_args": {},
        "workflow_type": "stock_approval",
        "task_id": "",
        "permission_checked": False,
        "risk_decision": "",
        "risk_reason": "",
        "compliance_decision": "",
        "compliance_reason": "",
        "aggregated_result": "",
        "human_approved": None,
        "human_feedback": "",
        "final_report": "",
        "trace_id": "test-001",
    })
    print(f"\n[OK] State 图编译成功")
    print(f"  消息数: {len(result['messages'])}")
