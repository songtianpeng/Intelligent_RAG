"""
LangGraph 工作流编排 — 核心

把所有节点（Planner/Router/Agent/Aggregator/Human）组装成一个有状态图。

流程:
  User → Planner → [chitchat|tool_agent|create_async_task]
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
                                          Human Approval
                                                │
                                               END
"""
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from state import InvestmentState


def build_graph(
    planner,
    chitchat_node,
    tool_agent,
    workflow_router,
    risk_agent,
    compliance_agent,
    aggregator,
) -> StateGraph:
    """
    构建完整投研工作流图

    返回: CompiledStateGraph
    """

    # ── 条件路由函数 ──
    def route_after_planner(state: InvestmentState) -> str:
        intent = state.get("intent", "chitchat")
        if intent == "chitchat":
            return "chitchat_node"
        if intent == "tool_call":
            return "tool_agent"
        if intent == "workflow":
            if state.get("need_human_confirm"):
                return "chitchat_node"  # 低置信度走闲聊确认
            return "workflow_router"
        return END

    def route_after_router(state: InvestmentState) -> str:
        """Router 后判断：权限通过 → 分发到第一个审批Agent"""
        if not state.get("permission_checked"):
            return END  # 权限不通过，直接结束
        wf_type = state.get("workflow_type", "")
        if wf_type == "stock_approval":
            return "risk_agent"
        if wf_type == "bond_rating":
            return "compliance_agent"  # 债券: 先合规(规则审查)
        if wf_type == "credit_approval":
            return "compliance_agent"  # 授信: 先合规
        return END

    # ── 构建 Graph ──
    workflow = StateGraph(InvestmentState)

    # 注册所有节点
    workflow.add_node("planner", planner)
    workflow.add_node("chitchat_node", chitchat_node)
    workflow.add_node("tool_agent", tool_agent)
    workflow.add_node("workflow_router", workflow_router)
    workflow.add_node("risk_agent", risk_agent)
    workflow.add_node("compliance_agent", compliance_agent)
    workflow.add_node("aggregator", aggregator)

    # 设置入口
    workflow.set_entry_point("planner")

    # Planner → 条件路由
    workflow.add_conditional_edges("planner", route_after_planner, {
        "chitchat_node": "chitchat_node",
        "tool_agent": "tool_agent",
        "workflow_router": "workflow_router",
    })

    # 闲聊/工具 → 结束
    workflow.add_edge("chitchat_node", END)
    workflow.add_edge("tool_agent", END)

    # Workflow Router → 条件分发到第一个审批Agent
    workflow.add_conditional_edges("workflow_router", route_after_router, {
        "risk_agent": "risk_agent",
        "compliance_agent": "compliance_agent",
    })

    # 审批链路(简化: 风险→合规→汇总, 串行演示)
    # 股票审批: risk → compliance → aggregator
    workflow.add_edge("risk_agent", "compliance_agent")
    workflow.add_edge("compliance_agent", "aggregator")

    # 聚合 → 结束
    workflow.add_edge("aggregator", END)

    return workflow


# ── 测试 ──
if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
    from config import settings
    from agents.planner import PlannerNode
    from agents.chitchat_node import ChitchatNode
    from agents.tool_agent import ToolAgentNode
    from agents.workflow_router import WorkflowRouterNode
    from agents.risk_agent import RiskAgentNode
    from agents.compliance_agent import ComplianceAgentNode
    from agents.aggregator import AggregatorNode

    # 初始化所有节点
    planner = PlannerNode(api_key=settings.DASHSCOPE_API_KEY)
    chitchat = ChitchatNode(api_key=settings.DASHSCOPE_API_KEY)
    tool = ToolAgentNode(api_key=settings.DASHSCOPE_API_KEY)
    router = WorkflowRouterNode()
    risk = RiskAgentNode(api_key=settings.DASHSCOPE_API_KEY)
    compliance = ComplianceAgentNode(api_key=settings.DASHSCOPE_API_KEY)
    agg = AggregatorNode(api_key=settings.DASHSCOPE_API_KEY)

    # 构建图
    graph_builder = build_graph(planner, chitchat, tool, router, risk, compliance, agg)

    print("=" * 50)
    print("LangGraph 工作流测试")
    print("=" * 50)

    tests = [
        {
            "messages": [{"role": "user", "content": "你好"}],
            "user_id": 1001,
            "intent": "", "confidence": 0, "slots": {},
            "need_human_confirm": False,
            "tool_name": "", "tool_args": {}, "workflow_type": "",
            "task_id": "", "permission_checked": False,
            "risk_decision": "", "risk_reason": "",
            "compliance_decision": "", "compliance_reason": "",
            "aggregated_result": "", "human_approved": None,
            "human_feedback": "", "final_report": "", "trace_id": "test-1",
        },
        {
            "messages": [{"role": "user", "content": "帮我审批茅台500万投资"}],
            "user_id": 1001,
            "intent": "", "confidence": 0, "slots": {},
            "need_human_confirm": False,
            "tool_name": "", "tool_args": {}, "workflow_type": "",
            "task_id": "", "permission_checked": False,
            "risk_decision": "", "risk_reason": "",
            "compliance_decision": "", "compliance_reason": "",
            "aggregated_result": "", "human_approved": None,
            "human_feedback": "", "final_report": "", "trace_id": "test-2",
        },
    ]

    output_path = os.path.join(os.path.dirname(__file__), "..", "workflow_test.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        # 编译（带 checkpoint 持久化）
        with SqliteSaver.from_conn_string(":memory:") as checkpointer:
            app = graph_builder.compile(checkpointer=checkpointer)

            for i, state in enumerate(tests):
                f.write(f"\n{'=' * 50}\n")
                f.write(f"测试 {i+1}: {state['messages'][-1]['content']}\n")
                f.write(f"{'=' * 50}\n\n")

                config = {"configurable": {"thread_id": state["trace_id"]}}
                result = app.invoke(state, config)

                f.write(f"意图: {result.get('intent', '?')}\n")
                f.write(f"置信度: {result.get('confidence', '?')}\n")
                f.write(f"最终输出: {result.get('final_report', '?')[:300]}\n")
                f.write(f"聚合结果: {result.get('aggregated_result', '?')[:300]}\n")
                f.write(f"消息数: {len(result.get('messages', []))}\n")

                for msg in result.get("messages", []):
                    role = msg.get("role", "?")
                    preview = msg.get("content", "")[:100]
                    f.write(f"  [{role}] {preview}...\n")

    print(f"测试结果已写入: {output_path}")
