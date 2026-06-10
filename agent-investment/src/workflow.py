"""
LangGraph 工作流编排 — 核心

流程:
  User → Planner → [chitchat|tool_agent|workflow]
                           │            │           │
                           ▼            ▼           ▼
                          END          END    Workflow Router
                                                │
                                     ┌──────────┼──────────┐
                                     ▼          ▼          ▼
                                  stock_     bond_     credit_
                                  approval   rating    approval
                                     │          │          │
                                     └──────────┼──────────┘
                                                ▼
                                          Aggregator
                                                │
                                     ┌──────────┴──────────┐
                                     │  Human Approval     │ ← interrupt()
                                     │  (等待审批/自动通过) │
                                     └──────────┬──────────┘
                                                ▼
                                               END
"""
from langgraph.graph import StateGraph, END
from langgraph.types import interrupt
from state import InvestmentState


def build_graph(
    planner,
    chitchat_node,
    tool_agent,
    workflow_router,
    risk_agent,
    compliance_agent,
    aggregator,
    auto_approve: bool = True,
) -> StateGraph:
    """
    构建完整投研工作流图

    Args:
        auto_approve: True=自动通过(测试用), False=需要人工审批
    """

    # ── 路由函数 ──
    def route_after_planner(state: InvestmentState) -> str:
        intent = state.get("intent", "chitchat")
        if intent == "chitchat":
            return "chitchat_node"
        if intent == "tool_call":
            return "tool_agent"
        if intent == "workflow":
            if state.get("need_human_confirm"):
                return "chitchat_node"
            return "workflow_router"
        return END

    def route_after_router(state: InvestmentState) -> str:
        if not state.get("permission_checked"):
            return END
        wf_type = state.get("workflow_type", "")
        if wf_type == "stock_approval":
            return "risk_agent"
        if wf_type == "bond_rating":
            return "compliance_agent"
        if wf_type == "credit_approval":
            return "compliance_agent"
        return END

    # ── Human Approval 节点 ──
    def human_approval_node(state: InvestmentState) -> dict:
        """
        人工终审节点 — LangGraph interrupt

        auto_approve=True:  跳过人工，自动通过
        auto_approve=False: 调用 interrupt() 暂停，等待外部 API 审批
        """
        if auto_approve:
            return {
                "human_approved": True,
                "human_feedback": "（自动通过）",
                "final_report": (state.get("aggregated_result", "")
                                 + "\n\n[审批结果]: 自动通过"),
                "messages": [{"role": "human_approval",
                              "content": "自动通过"}],
            }

        # ★ 生产模式: interrupt 暂停 → 状态保存到 PostgresSaver
        #    审核员通过 POST /workflow/{task_id}/approve 恢复执行
        aggregated = state.get("aggregated_result", "暂无聚合结论")
        decision = interrupt({
            "message": "请审核以下投研审批结论",
            "aggregated_result": aggregated[:500],
            "risk_decision": state.get("risk_decision", ""),
            "compliance_decision": state.get("compliance_decision", ""),
        })
        # 外部 API 调用 graph.update_state() 传入 decision 后，从这里继续
        return {
            "human_approved": decision.get("approved", False),
            "human_feedback": decision.get("feedback", ""),
            "final_report": (aggregated + "\n\n"
                             f"[审批结果]: {'通过' if decision.get('approved') else '驳回'}"
                             f"\n[审批意见]: {decision.get('feedback', '')}"),
            "messages": [{"role": "human_approval",
                          "content": f"人工审批: {decision}"}],
        }

    # ── 构建 Graph ──
    workflow = StateGraph(InvestmentState)

    workflow.add_node("planner", planner)
    workflow.add_node("chitchat_node", chitchat_node)
    workflow.add_node("tool_agent", tool_agent)
    workflow.add_node("workflow_router", workflow_router)
    workflow.add_node("risk_agent", risk_agent)
    workflow.add_node("compliance_agent", compliance_agent)
    workflow.add_node("aggregator", aggregator)
    workflow.add_node("human_approval", human_approval_node)

    workflow.set_entry_point("planner")

    workflow.add_conditional_edges("planner", route_after_planner, {
        "chitchat_node": "chitchat_node",
        "tool_agent": "tool_agent",
        "workflow_router": "workflow_router",
    })

    workflow.add_edge("chitchat_node", END)
    workflow.add_edge("tool_agent", END)

    workflow.add_conditional_edges("workflow_router", route_after_router, {
        "risk_agent": "risk_agent",
        "compliance_agent": "compliance_agent",
    })

    workflow.add_edge("risk_agent", "compliance_agent")
    workflow.add_edge("compliance_agent", "aggregator")
    # ★ Aggregator → Human Approval → END
    workflow.add_edge("aggregator", "human_approval")
    workflow.add_edge("human_approval", END)

    return workflow
