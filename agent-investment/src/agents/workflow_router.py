"""
Workflow Router Agent — 流程分发 + 权限二次校验

职责: 接收 Planner 路由来的 workflow 请求 → 权限校验 → 分发到具体业务 Subgraph
"""
import json


# ── 流程模板配置（开发硬编码，生产从MySQL读） ──
WORKFLOW_REGISTRY = {
    "stock_approval": {
        "name": "股票投资审批",
        "agents": ["risk_agent", "compliance_agent"],
        "parallel": True,   # 风控+合规并行：互不依赖，同时审批
    },
    "bond_rating": {
        "name": "债券评级流程",
        "agents": ["bond_rule_agent", "bond_rating_agent"],
        "parallel": False,  # 串行：规则审查通过 → 才做评级
    },
    "credit_approval": {
        "name": "授信审批流程",
        "agents": ["compliance_agent", "risk_agent"],
        "parallel": False,  # 串行：先合规 → 再风控，合规驳回则跳过风控
    },
}


class WorkflowRouterNode:
    """
    Workflow Router — LangGraph 节点

    职责:
    1. 二次权限校验（防止绕过UI直接调API）
    2. 匹配流程模板
    3. 返回需要执行的 Agent 列表
    """

    def __init__(self, java_service_url: str = ""):
        self.java_url = java_service_url
        # 开发阶段硬编码权限，生产调 Java 服务
        self._dev_permissions = {
            1001: ["stock_approval", "bond_rating", "credit_approval"],
            1002: ["stock_approval"],
            1003: ["bond_rating"],
        }

    def __call__(self, state: dict) -> dict:
        user_id = state.get("user_id", 0)
        workflow_type = state.get("workflow_type", "")
        slots = state.get("slots", {})

        # ── 1. 权限校验 ──
        has_permission = self._check_permission(user_id, workflow_type)
        if not has_permission:
            return {
                "permission_checked": False,
                "final_report": f"权限不足：您没有发起「{workflow_type}」流程的权限",
                "messages": [{"role": "router",
                              "content": f"权限校验失败: user={user_id}, "
                                         f"type={workflow_type}"}],
            }

        # ── 2. 匹配模板 ──
        template = WORKFLOW_REGISTRY.get(workflow_type)
        if not template:
            return {
                "permission_checked": False,
                "final_report": f"未找到流程模板: {workflow_type}",
                "messages": [{"role": "router",
                              "content": f"模板匹配失败: {workflow_type}"}],
            }

        # ── 3. 槽位完整性检查 ──
        missing = self._check_required_slots(slots, workflow_type)
        if missing:
            return {
                "permission_checked": True,
                "need_human_confirm": True,
                "messages": [{"role": "router",
                              "content": f"信息不完整，缺少: {missing}。"
                                         f"已填槽位: {slots}"}],
            }

        return {
            "permission_checked": True,
            "messages": [{"role": "router",
                          "content": f"流程已分发: {template['name']}, "
                                     f"执行Agent: {template['agents']}"}],
        }

    def _check_permission(self, user_id: int, workflow_type: str) -> bool:
        """权限校验（开发用本地字典，生产调Java服务）"""
        # ★ 生产环境: httpx.get(f"{self.java_url}/api/permissions/check?...")
        allowed = self._dev_permissions.get(user_id, [])
        return workflow_type in allowed

    def _check_required_slots(self, slots: dict, workflow_type: str) -> list:
        """检查必填槽位"""
        required_map = {
            "stock_approval": ["标的", "金额"],
            "bond_rating": ["标的", "发行方"],
            "credit_approval": ["标的", "金额"],
        }
        required = required_map.get(workflow_type, [])
        return [k for k in required if not slots.get(k)]


# ── 测试 ──
if __name__ == "__main__":
    router = WorkflowRouterNode()

    tests = [
        # 测试1: 有权限 + 槽位完整
        {"user_id": 1001, "workflow_type": "stock_approval",
         "slots": {"标的": "贵州茅台", "金额": "5000000"}},
        # 测试2: 无权限
        {"user_id": 1002, "workflow_type": "bond_rating",
         "slots": {"标的": "XX债券"}},
        # 测试3: 有权限但槽位不完整
        {"user_id": 1001, "workflow_type": "stock_approval",
         "slots": {"标的": "贵州茅台"}},
    ]

    for i, state in enumerate(tests):
        print(f"\n{'=' * 50}")
        print(f"测试 {i+1}: user={state['user_id']}, "
              f"type={state['workflow_type']}, slots={state['slots']}")
        result = router(state)
        print(f"  权限通过: {result['permission_checked']}")
        if result.get("need_human_confirm"):
            print(f"  需人工确认: True")
        if result.get("final_report"):
            print(f"  终止原因: {result['final_report']}")
        if result.get("messages"):
            print(f"  消息: {result['messages'][-1]['content']}")
