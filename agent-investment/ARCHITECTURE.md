# 项目二：智能投研协同分析平台 — 完整架构与功能设计 V2

> 综合简历 v2 + 流程图(iodraw) + 实现思路与构想，逐项对齐

---

## 1. 技术栈与兼容版本

| 组件 | 包名 | 版本 | 用途 |
|------|------|------|------|
| LangChain | `langchain` | 1.3.4 | Agent/Tool/ChatModel 统一框架 |
| LangGraph | `langgraph` | 1.2.4 | 有状态多Agent工作流编排 |
| Agent工厂 | `langchain.agents` | 内置 | `create_agent` 统一Agent工厂 |
| Checkpoint | `langgraph-checkpoint` | 4.1.1 | SqliteSaver/PostgresSaver |
| Pydantic | `pydantic` | 2.13.4 | Schema校验 |
| FastAPI | `fastapi` | 0.136.3 | Python侧REST API |
| LLM | `langchain_community.chat_models.ChatTongyi` | — | 通义千问(LangChain封装) |
| ChromaDB | `chromadb` | 1.5.9 | 政策文档向量库 |
| Java | Spring Boot 3.x + MyBatis 3.x | — | 流程模板/报告管理 |
| MySQL | `pymysql` | — | 业务数据主存储 |
| Redis | `redis-py` | — | 缓存/工具回调/状态 |
| RocketMQ | `rocketmq-client-python` | — | 审计日志+聊天记录异步落库 |

**版本兼容性**：全部为最新稳定版，`pip install` 无冲突。

---

## 2. 系统全景架构图

```
┌────────────────────────────────────────────────────────────────┐
│                        前端 (Chat UI)                           │
│                                                                 │
│  ┌──────────┐  ┌───────────────────────────────────────────┐   │
│  │ 左侧边栏  │  │  右侧对话区                                 │   │
│  │          │  │                                           │   │
│  │ +新对话  │  │  ┌─────────────────────────────────────┐  │   │
│  │          │  │  │ 用户消息 / Agent回复 / 审批卡片       │  │   │
│  │ 项目列表  │  │  └─────────────────────────────────────┘  │   │
│  │ ├ 项目A  │  │                                           │   │
│  │ │ ├会话1 │  │  ┌──────────────────────────────────┐     │   │
│  │ │ └会话2 │  │  │ [流程模板] 按钮 → 弹窗选模板       │     │   │
│  │ └ 项目B  │  │  │ 或直接输入框自由输入               │     │   │
│  │          │  │  └──────────────────────────────────┘     │   │
│  │ 流程管理  │  │                                           │   │
│  │ ├状态列表│  │                                           │   │
│  │ │ 待审批 │  │                                           │   │
│  │ │  [处理]│  │                                           │   │
│  │ └ 历史   │  │                                           │   │
│  └──────────┘  └───────────────────────────────────────────┘   │
└──────────────────────┬─────────────────────────────────────────┘
                       │ HTTP / SSE
                       ▼
┌────────────────────────────────────────────────────────────────┐
│                    FastAPI (Python)                              │
│                                                                 │
│  POST /chat                   统一问答入口                       │
│  POST /template/list          获取用户可用模板(权限过滤)         │
│  POST /workflow/start         发起审批流程                       │
│  GET  /workflow/{id}/status   查询流程状态                       │
│  POST /workflow/{id}/approve  人工审批(通过/驳回)                │
│  GET  /workflow/{id}/report   获取最终报告                       │
│  POST /project/create         创建项目                          │
└──────────┬────────────────────────────┬─────────────────────────┘
           │                            │ HTTP
           ▼                            ▼
┌──────────────────────────┐  ┌──────────────────────────────────┐
│  Agent 推理层 (Python)    │  │   业务管理层 (Java)               │
│                          │  │   Spring Boot + MyBatis           │
│                          │  │                                  │
│  ┌────────────────────┐  │  │  /api/templates   模板CRUD       │
│  │   Planner Agent    │  │  │  /api/workflows   实例管理       │
│  │   (系统级路由)      │  │  │  /api/reports     报告查询       │
│  │                    │  │  │  /api/projects    项目管理        │
│  │ 识别三类意图：      │  │  │  /api/users       用户权限        │
│  │ 闲聊│工具│流程     │  │  │                                  │
│  └────────┬───────────┘  │  │  → 共享 MySQL 数据库             │
│           │              │  │  → Python调Java: httpx            │
│     ┌─────┼─────┐        │  │  → Java调Python: 不调用           │
│     ▼     ▼     ▼        │  │    (Java只做CRUD,不调Agent)       │
│  闲聊   工具   流程       │  └──────────────────────────────────┘
│   │     │      │         │
│   ▼     ▼      ▼         │
│  结束  调用   创建异步    │
│       公共   任务+MQ      │
│       工具   ┌─────┐     │
│        │    │主线程│     │
│        ▼    │→结束│     │
│       结束  └──┬──┘     │
│               │异步线程  │
│               ▼         │
│  ┌────────────────────┐  │
│  │ Workflow Router    │  │
│  │ (权限二次校验+分发)  │  │
│  └────────┬───────────┘  │
│           │              │
│     ┌─────┼─────┐        │
│     ▼     ▼     ▼        │
│   主体   债券   授信      │  ← 业务 Subgraph
│   评级   评级   审批      │    每个含2-3个ReAct Agent
│     │     │     │        │
│     └─────┼─────┘        │
│           ▼              │
│  ┌────────────────────┐  │
│  │   Aggregator       │  │
│  │   (结论聚合)        │  │
│  └────────┬───────────┘  │
│           ▼              │
│  ┌────────────────────┐  │
│  │  Human Approval    │  │  ← LangGraph interrupt/resume
│  │  (等待人工审批)     │  │
│  └────────┬───────────┘  │
│           ▼              │
│  ┌────────────────────┐  │
│  │  Report Writer     │  │
│  └────────────────────┘  │
│           │              │
│           ▼              │
│         END              │
└──────────────────────────┘

共享存储层:
┌──────────┐  ┌──────────┐  ┌──────────┐
│  MySQL   │  │  Redis   │  │ RocketMQ │
│  8张表   │  │  5类Key  │  │  3个Topic│
└──────────┘  └──────────┘  └──────────┘
```

---

## 3. 前端 UI 设计

### 3.1 布局结构

```
┌──────────────┬─────────────────────────────────────────┐
│   左侧 280px │  右侧对话区 (flex:1)                      │
│              │                                         │
│ [+ 新对话]   │  ┌────────────────────────────────────┐ │
│              │  │  对话消息1 (user)                    │ │
│ 📁 项目列表  │  │  对话消息2 (assistant)               │ │
│  ├ 项目A    │  │  审批卡片 (状态:待审批 [通过][驳回])  │ │
│  │ ├ 会话1  │  │  对话消息3 ...                       │ │
│  │ └ 会话2  │  └────────────────────────────────────┘ │
│  └ 项目B    │                                         │
│              │  ┌────────────────────────────────┐     │
│ 📋 流程管理  │  │ [流程模板] 按钮                   │     │
│  ├ 待审批   │  │  点击 → 弹窗选择模板 → 填必填字段  │     │
│  │ └ [处理] │  │  或直接在输入框自由输入              │     │
│  └ 已审批   │  │  [输入框________________] [发送]    │     │
└──────────────┴─────────────────────────────────────────┘
```

### 3.2 流程模板弹窗

```
┌─────────────────────────────────────┐
│  选择流程模板                   [X]  │
├─────────────────────────────────────┤
│                                     │
│  ┌─────────────────────────────┐   │
│  │ 📝 股票投资审批              │   │
│  │    需要审批: 风控+合规        │   │
│  │    必填: 标的、金额           │   │
│  │                        [选择]│   │
│  └─────────────────────────────┘   │
│                                     │
│  ┌─────────────────────────────┐   │
│  │ 📝 债券评级流程              │   │
│  │    需要审批: 规则审查+评级    │   │
│  │    必填: 标的、发行方         │   │
│  │                        [选择]│   │
│  └─────────────────────────────┘   │
│                                     │
│  (该列表根据用户权限动态过滤)        │
└─────────────────────────────────────┘

选择后 ↓

┌─────────────────────────────────────┐
│  股票投资审批 - 填写信息        [X]  │
├─────────────────────────────────────┤
│  标的名称: [贵州茅台____________]   │
│  标的代码: [600519______________]   │
│  投资金额: [5000000_____________]   │
│  风控偏好: [保守/平衡/进取  ▼]     │
│                                     │
│              [取消]    [确认发起]    │
└─────────────────────────────────────┘
```

### 3.3 流程管理面板

```
┌─────────────────────────────────────┐
│  流程管理                            │
├──────┬────────┬────────┬────────────┤
│ 状态  │ 类型    │ 标的    │ 操作       │
├──────┼────────┼────────┼────────────┤
│ 待审批│股票审批 │贵州茅台 │ [通过][驳回]│
│ 待审批│债券评级 │XX债券   │ [通过][驳回]│
│ 审批中│授信审批 │XX集团   │ 等待中...  │
│ 已通过│股票审批 │腾讯控股 │ [查看报告] │
│ 已驳回│债券评级 │YY债券   │ [重新发起] │
└──────┴────────┴────────┴────────────┘
```

---

## 4. 意图识别设计（Planner Agent）

### 4.1 三级路由体系

```
用户输入 ──→ Planner Agent
                  │
                  ├── 闲聊 ("你好"、"今天天气") → chitchat_node → END
                  │
                  ├── 工具调用 ("查茅台财务数据"、"茅台舆情") → tool_agent → END
                  │    (非流程类查询，调一次工具就返回)
                  │
                  └── 流程发起 ("审批茅台500万投资"、"发起债券评级")
                       │
                       ├── 低置信度(intent模糊) → human_confirm → 用户确认
                       │
                       └── 高置信度 → 创建异步任务 → 主线程立即返回
                                        │             "任务已创建，正在执行中..."
                                        └── 异步线程 → Workflow Router
```

### 4.2 Planner Prompt 工程设计

```python
PLANNER_SYSTEM_PROMPT = """你是一个金融投研平台的智能路由助手。

## 职责
分析用户输入，判断意图类型并提取关键信息。

## 意图分类规则

### 1. chitchat（闲聊）
用户打招呼、问候、或与投研业务无关的对话
示例: "你好"、"谢谢"、"今天忙不忙"

### 2. tool_call（工具调用，非流程）
用户要求查询数据、分析标的、查看舆情，但不涉及审批流程
示例: "帮我查茅台的财务数据"、"茅台最近舆情怎么样"、"帮我分析腾讯估值"
这类请求只调用一次工具，结果直接返回给用户。

### 3. workflow（流程发起）
用户明确要求发起审批、评估、评级等业务流程
示例: "帮我审批茅台500万投资"、"发起债券A的主体评级"、"对XX集团做授信审批"
这类请求需要走完整的多Agent审批链路。

## 槽位提取
对 tool_call 和 workflow 意图，提取关键槽位:
- 标的: 股票/债券/基金名称或代码
- 金额: 投资金额（数字+单位）
- 发行方: 债券发行人（仅债券类需要）
- 其他: 用户提到的其他约束条件

## 输出格式（严格JSON）
{
  "intent": "chitchat|tool_call|workflow",
  "confidence": 0.0-1.0,
  "slots": {"标的": "贵州茅台", "金额": "5000000"},
  "tool_name": "search_rag|query_financial_db|sentiment_analysis|null",
  "tool_args": {},
  "workflow_type": "stock_approval|bond_rating|credit_approval|null",
  "reasoning": "一句话说明判断依据"
}

## 关键规则
1. 置信度 < 0.7 时标记 need_human_confirm=true
2. 无法区分 tool_call 和 workflow 时，默认走 tool_call（不影响审批流程）
3. 不要编造槽位，用户没提到的填 null
"""
```

### 4.3 条件路由代码

```python
def route_after_planner(state: InvestmentState) -> str:
    intent = state.get("intent", "chitchat")
    confidence = state.get("confidence", 0.0)

    if intent == "chitchat":
        return "chitchat_node"

    if intent == "tool_call":
        return "tool_agent"

    if intent == "workflow":
        if confidence < 0.7:
            return "human_confirm"  # 低置信度先问用户
        return "create_async_task"  # 创建异步任务

    return END
```

---

## 5. 异步任务流程设计

### 5.1 为什么异步？

流程图明确区分了**主线程**和**异步线程**：

```
用户发起流程
    │
    ▼
创建异步任务(写入MySQL + 发MQ)
    │
    ├──→ 主线程: 立即返回 "流程已创建,任务ID:xxx,正在异步执行"
    │        用户不用卡在聊天界面等10秒
    │
    └──→ 异步线程: MQ消费 → Workflow Router → Subgraph → Aggregator → Human → END
             执行完通知用户
```

### 5.2 创建异步任务

```python
def create_async_task(state: InvestmentState) -> dict:
    """
    1. 生成 task_id
    2. 同步写 MySQL workflow_instance (status=RUNNING)
    3. 发 MQ 消息给 Worker
    4. 立即返回
    """
    import uuid, json
    task_id = uuid.uuid4().hex[:16]

    # 同步落库（这条不能丢）
    insert_workflow_instance(
        task_id=task_id,
        user_id=state["user_id"],
        workflow_type=state["workflow_type"],
        slots=json.dumps(state["slots"]),
        status="RUNNING",
    )

    # MQ 异步触发
    producer.send_task({
        "type": "execute_workflow",
        "task_id": task_id,
        "workflow_type": state["workflow_type"],
        "slots": state["slots"],
        "user_id": state["user_id"],
    })

    return {
        "task_id": task_id,
        "messages": [{
            "role": "system",
            "content": f"✅ 流程已创建（任务ID: {task_id}），"
                       f"类型: {state['workflow_type']}，正在异步执行中..."
                       f"可通过 /workflow/{task_id}/status 查询进度。"
        }]
    }
```

### 5.3 后台 Worker 执行

```python
async def workflow_worker(checkpointer):
    """消费 MQ，执行 LangGraph 审批流程"""
    while True:
        msg = await mq_queue.get()

        if msg["type"] != "execute_workflow":
            continue

        task_id = msg["task_id"]

        # 从 MySQL 恢复初始状态
        initial_state = load_initial_state(task_id)

        # 编译审批子图（跳过 Planner，从 Workflow Router 开始）
        approval_graph = build_approval_subgraph().compile(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": task_id}}

        try:
            async for event in approval_graph.astream(initial_state, config):
                node_name = list(event.keys())[0]

                # 遇到 Human Approval → interrupt 暂停，通知用户
                if node_name == "__interrupt__":
                    update_workflow_status(task_id, "PENDING_APPROVAL")
                    notify_user(msg["user_id"], task_id)
                    break  # 等用户审批后通过 resume 继续

                # 记录 Trace
                save_node_trace(task_id, node_name, event[node_name])

                # 更新状态
                update_workflow_status(task_id, "RUNNING", node_name)

        except Exception as e:
            update_workflow_status(task_id, "ERROR", str(e))

        # 最终状态
        if approval_graph.get_state(config).next == ():
            update_workflow_status(task_id, "APPROVED")
```

### 5.4 Human Approval (interrupt/resume)

```python
# 在 Aggregator 之后
def human_approval_node(state: InvestmentState) -> dict:
    """人工终审节点 — LangGraph interrupt"""
    # interrupt() 暂停执行，等待外部输入
    # 用户通过 POST /workflow/{id}/approve 传入 decision
    return {"human_approved": None}  # None = 等待中

# 用户审批后 resume
@app.post("/workflow/{task_id}/approve")
async def approve(task_id: str, decision: str, reason: str = ""):
    config = {"configurable": {"thread_id": task_id}}
    graph = get_approval_graph()

    # 恢复执行，传入审批结果
    await graph.aupdate_state(
        config,
        {"human_approved": decision == "approved",
         "human_feedback": reason}
    )

    # 继续执行后续节点
    async for event in graph.astream(None, config):
        ...
```

---

## 6. 权限隔离设计

### 6.1 三层权限

| 层级 | 位置 | 内容 |
|------|------|------|
| **UI层** | 前端模板弹窗 | 只展示当前用户可发起的模板（调 `/template/list?user_id=xxx`） |
| **API层** | FastAPI middleware | JWT 解析 user_id → 注入 Request Context |
| **Agent层** | Workflow Router | 二次权限校验，拦截绕过UI的直接API调用 |

### 6.2 模板权限矩阵

```sql
-- workflow_template_permission 表
-- 优先级: user_id > role > department，NULL=全部

-- 示例数据
INSERT INTO workflow_template_permission (template_id, user_id, role, department, can_initiate) VALUES
(1, NULL, 'analyst', NULL, 1),       -- 股票审批: 所有分析师可发起
(1, NULL, 'intern', NULL, 0),        --            实习生不能发起
(2, NULL, NULL, '固收部', 1),        -- 债券评级: 固收部全员可发起
(2, NULL, NULL, '权益部', 0),        --           权益部不能发起
(3, 1001, NULL, NULL, 1);            -- 授信审批: 仅用户1001可发起
```

### 6.3 Workflow Router 权限校验

```python
def workflow_router(state: InvestmentState) -> dict:
    user_id = state["user_id"]
    workflow_type = state["workflow_type"]

    # 调 Java 服务查询权限
    resp = httpx.get(
        f"{JAVA_SERVICE}/api/permissions/check",
        params={"user_id": user_id, "workflow_type": workflow_type}
    )
    has_permission = resp.json()["can_initiate"]

    if not has_permission:
        return {
            "final_report": f"权限不足: 您没有发起「{workflow_type}」流程的权限",
            "messages": [{"role": "system",
                          "content": f"您的角色无权发起此流程。请联系管理员。"}]
        }
        # → END (graph直接结束)

    # 有权限 → 分发到对应 Subgraph
    return {"permission_checked": True}
```

---

## 7. 业务 Subgraph 设计

### 7.1 三个业务流程

```
┌─────────────────────────────────────────────────────────┐
│               Workflow Router (条件边判断)               │
└──────┬──────────────────┬──────────────────┬───────────┘
       ▼                  ▼                  ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ 主体评级流程  │  │ 债券评级流程  │  │ 授信审批流程  │
│              │  │              │  │              │
│ 主体规则审查  │  │ 债券规则审查  │  │  合规审查Agent│
│   Agent      │  │   Agent      │  │              │
│    ↓         │  │    ↓         │  │    ↓         │
│ 主体评级人员  │  │ 债券评级人员  │  │  风控审批Agent│
│   Agent      │  │   Agent      │  │              │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                 │
       └─────────────────┼─────────────────┘
                         ▼
                ┌────────────────┐
                │   Aggregator   │
                └────────────────┘
```

### 7.2 ReAct Agent 内部设计（以风控审批为例）

```python
RISK_AGENT_PROMPT = """你是一个专业的金融风控审批专家。

## 身份
投研平台风控审批Agent，负责对投资标的进行风险评估。

## 审批规则
1. 单一标的集中度 ≤ 10%
2. VaR(95%) ≤ 2%
3. 杠杆率 ≤ 140%
4. 流动性覆盖率 ≥ 100%
5. 投资金额 > 500万需额外投委会审批

## 可调用工具
- query_financial_db: 查询标的财务数据(基本面/估值/历史波动)
- sentiment_analysis: 查询市场舆情

## 工作流程
1. Thought: 分析需要什么数据
2. Action: 调用工具获取数据
3. Observation: 工具返回结果
4. 重复 1-3 直到信息充分
5. 输出审批结论: APPROVED / REJECTED / NEED_MORE_INFO

## 输出格式
{
  "decision": "APPROVED|REJECTED|NEED_MORE_INFO",
  "reason": "审批理由，引用具体数据",
  "risk_score": 0-100,
  "concerns": ["关注点1", "关注点2"]
}
"""

# 使用 create_agent 工厂方法
from langchain.agents import create_agent

risk_agent = create_agent(
    model=ChatTongyi(model="qwen-plus", api_key=...),
    tools=[query_financial_db, sentiment_analysis],
    prompt=RISK_AGENT_PROMPT,
)
```

### 7.3 自动驳回机制

```python
def auto_reject_check(agent_output: dict) -> bool:
    """
    自动驳回条件:
    1. 数据库中查不到该标的数据 → 数据问题，自动驳回
    2. 风控红线被触发(集中度>10% 或 VaR>2%) → 规则问题，自动驳回
    3. 工具调用全部失败 → 无法评估，需要人工介入
    """
    if agent_output.get("data_not_found"):
        return True  # 数据缺失，自动驳回

    if agent_output.get("risk_score", 0) > 90:
        return True  # 高风险，自动驳回

    if agent_output.get("all_tools_failed"):
        return True  # 无法评估

    return False
```

---

## 8. 数据库表结构设计

### 8.1 ER 图

```
sys_user ──< chat_session ──< chat_message
    │
    ├──< workflow_instance ──< workflow_approval
    │         │
    │         └──< tool_call_log
    │         └──< workflow_trace
    │
    └──< workflow_template ──< workflow_template_permission
```

### 8.2 完整建表 SQL

```sql
-- 1. 用户表
CREATE TABLE sys_user (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(64) NOT NULL UNIQUE,
    password_hash VARCHAR(256) NOT NULL,
    display_name VARCHAR(64),
    role VARCHAR(32) NOT NULL COMMENT 'analyst/reviewer/admin/intern',
    department VARCHAR(64) COMMENT '固收部/权益部/风控部',
    is_active TINYINT DEFAULT 1,
    created_at DATETIME DEFAULT NOW()
) COMMENT '用户表';

-- 2. 流程模板表（Java服务管理）
CREATE TABLE workflow_template (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(128) NOT NULL COMMENT '股票投资审批/债券评级流程',
    workflow_type VARCHAR(64) NOT NULL UNIQUE COMMENT 'stock_approval/bond_rating/credit_approval',
    category VARCHAR(32) NOT NULL COMMENT '审批/评级/尽调',
    description TEXT,
    required_slots JSON COMMENT '["标的","金额"]',
    agent_chain JSON COMMENT '["risk_agent","compliance_agent"]',
    is_active TINYINT DEFAULT 1,
    created_at DATETIME DEFAULT NOW()
) COMMENT '流程模板表';

-- 3. 模板权限表
CREATE TABLE workflow_template_permission (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    template_id BIGINT NOT NULL,
    user_id BIGINT COMMENT 'NULL=不限定用户',
    role VARCHAR(32) COMMENT 'NULL=不限定角色',
    department VARCHAR(64) COMMENT 'NULL=不限定部门',
    can_initiate TINYINT DEFAULT 1,
    FOREIGN KEY (template_id) REFERENCES workflow_template(id),
    INDEX idx_perm (template_id, user_id, role, department)
) COMMENT '模板权限';

-- 4. 流程实例表（运行时核心表）
CREATE TABLE workflow_instance (
    id VARCHAR(32) PRIMARY KEY COMMENT 'task_id',
    template_id BIGINT,
    user_id BIGINT NOT NULL,
    workflow_type VARCHAR(64) NOT NULL,
    session_id VARCHAR(32) COMMENT '关联的聊天会话',
    slots JSON COMMENT '{"标的":"贵州茅台","金额":5000000}',
    status VARCHAR(32) DEFAULT 'RUNNING'
        COMMENT 'RUNNING/PENDING_APPROVAL/APPROVED/REJECTED/ERROR/CANCELLED',
    current_node VARCHAR(64) COMMENT '当前执行节点',
    checkpoint_data LONGBLOB COMMENT 'LangGraph checkpoint 序列化',
    final_report TEXT COMMENT '最终报告',
    created_at DATETIME DEFAULT NOW(),
    updated_at DATETIME DEFAULT NOW(),
    FOREIGN KEY (user_id) REFERENCES sys_user(id),
    FOREIGN KEY (template_id) REFERENCES workflow_template(id),
    INDEX idx_user_status (user_id, status),
    INDEX idx_status (status),
    INDEX idx_session (session_id)
) COMMENT '流程实例表';

-- 5. 审批记录表
CREATE TABLE workflow_approval (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    instance_id VARCHAR(32) NOT NULL,
    node_name VARCHAR(64) NOT NULL COMMENT 'risk_agent/compliance_agent/human_approval',
    approver_id BIGINT COMMENT '系统自动审批为NULL',
    decision VARCHAR(16) NOT NULL COMMENT 'APPROVED/REJECTED',
    reason TEXT,
    risk_score INT COMMENT '风控评分0-100',
    created_at DATETIME DEFAULT NOW(),
    FOREIGN KEY (instance_id) REFERENCES workflow_instance(id),
    FOREIGN KEY (approver_id) REFERENCES sys_user(id)
) COMMENT '审批记录表';

-- 6. 工具调用日志表
CREATE TABLE tool_call_log (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    instance_id VARCHAR(32) NOT NULL,
    node_name VARCHAR(64),
    tool_name VARCHAR(64),
    tool_input JSON,
    tool_output TEXT,
    latency_ms INT,
    status VARCHAR(16) DEFAULT 'SUCCESS' COMMENT 'SUCCESS/FAILED',
    error_msg TEXT,
    created_at DATETIME DEFAULT NOW(),
    FOREIGN KEY (instance_id) REFERENCES workflow_instance(id),
    INDEX idx_instance (instance_id)
) COMMENT '工具调用日志';

-- 7. 聊天会话表
CREATE TABLE chat_session (
    session_id VARCHAR(32) PRIMARY KEY,
    user_id BIGINT NOT NULL,
    project_id BIGINT COMMENT '所属项目(NULL=未分类)',
    title VARCHAR(256) DEFAULT '新对话',
    workflow_instance_id VARCHAR(32) COMMENT '关联的流程实例',
    is_active TINYINT DEFAULT 1,
    created_at DATETIME DEFAULT NOW(),
    FOREIGN KEY (user_id) REFERENCES sys_user(id)
) COMMENT '聊天会话表';

-- 8. 聊天消息表
CREATE TABLE chat_message (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    session_id VARCHAR(32) NOT NULL,
    role VARCHAR(32) NOT NULL COMMENT 'user/assistant/planner/router/risk_agent/...',
    content TEXT NOT NULL,
    metadata JSON COMMENT '{"intent":"workflow","task_id":"xxx","confidence":0.92}',
    created_at DATETIME DEFAULT NOW(),
    FOREIGN KEY (session_id) REFERENCES chat_session(session_id),
    INDEX idx_session_time (session_id, created_at)
) COMMENT '聊天消息表';

-- 9. 项目表
CREATE TABLE chat_project (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    name VARCHAR(256) NOT NULL,
    parent_id BIGINT COMMENT '支持嵌套(N级项目树)',
    created_at DATETIME DEFAULT NOW(),
    FOREIGN KEY (user_id) REFERENCES sys_user(id),
    FOREIGN KEY (parent_id) REFERENCES chat_project(id)
) COMMENT '项目表';

-- 10. Trace 追踪表
CREATE TABLE workflow_trace (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    trace_id VARCHAR(32) NOT NULL COMMENT '= instance_id',
    node_name VARCHAR(64),
    node_input TEXT,
    node_output TEXT,
    tool_calls JSON,
    latency_ms INT,
    token_used INT,
    created_at DATETIME DEFAULT NOW(),
    INDEX idx_trace (trace_id, created_at)
) COMMENT '全链路Trace表';
```

---

## 9. Redis 设计

### 9.1 Key 规划

| Key Pattern | 类型 | 内容 | TTL |
|------|------|------|------|
| `workflow_status:{task_id}` | String | RUNNING/PENDING_APPROVAL/APPROVED/REJECTED | 7天 |
| `tool_result:{task_id}:{tool_name}` | String(JSON) | 异步工具回调结果 | 300s |
| `session:{session_id}` | Hash | `{memory_summary, memory_slots, user_id}` | 无过期 |
| `template_list:{user_id}` | String(JSON) | 该用户可发起的模板列表(缓存) | 600s |
| `rag:cache:{md5}` | String(JSON) | 政策问答缓存(复用项目一) | 86400s |

### 9.2 工具回调流程（Redis Pub/Sub）

```
Agent发出工具调用
    │
    ├──→ MQ异步发送 tool_exec 消息
    │
    ├──→ Agent不阻塞，继续处理其他工具
    │
    └──→ Worker消费，执行查询，结果写入
         Redis: SET tool_result:{task_id}:{tool_name} = JSON
         然后 PUBLISH tool_done:{task_id} "tool_name"
              │
              ▼
         Agent收到Pub/Sub通知 → 读取Redis结果 → 继续推理
```

---

## 10. RocketMQ 设计

### 10.1 Topic 规划

| Topic | 生产者 | 消费者 | 消息内容 |
|------|------|------|------|
| `invest_task_exec` | FastAPI(创建流程时) | Workflow Worker | `{type, task_id, workflow_type, slots, user_id}` |
| `invest_audit_log` | 每个LangGraph节点 | 审计日志Consumer | `{type, trace_id, node_name, input_preview, output_preview, latency_ms, token_used}` |
| `invest_chat_persist` | FastAPI(问答后) | 持久化Consumer | `{type, session_id, user_id, role, content, metadata}` |

### 10.2 为什么日志走MQ而不是同步写MySQL

```
同步写:  节点执行 → INSERT INTO workflow_trace (10ms) → 继续下一个节点
MQ异步:  节点执行 → 发MQ消息 (<1ms) → 继续下一个节点
                          └→ Consumer批量INSERT (不影响主流程)

一个流程有10个节点，同步方案多等100ms，MQ方案几乎不增加延迟。
```

### 10.3 聊天记录持久化策略

```python
# 策略选择（自动判断）
def persist_chat_message(msg: dict):
    """
    低流量: 直接同步写MySQL  (适合开发环境/用户量小)
    高流量: Redis LIST + MQ异步批量落库 (生产环境)
    """
    if is_low_traffic():
        # 同步写
        mysql.execute("INSERT INTO chat_message (...) VALUES (...)", msg)
    else:
        # 异步: 先写Redis缓冲
        redis.lpush(f"chat_buffer:{msg['session_id']}", json.dumps(msg))
        # 每100条或每5秒批量flush到MySQL (由定时任务处理)
```

---

## 11. Memory 管理设计

### 11.1 三级混合记忆

```
┌─────────────────────────────────────────────────────────┐
│  第1-5轮 (近轮原文)                                      │
│  完整保留 → 注入 LangGraph State.messages                 │
├─────────────────────────────────────────────────────────┤
│  第6轮+ (远轮摘要)                                       │
│  LLM 压缩 → 存入 Redis session:{id}.memory_summary       │
│  内容: "此前讨论了贵州茅台(E03)投资审批,风控评分85分..."  │
├─────────────────────────────────────────────────────────┤
│  关键槽位 (持久化)                                       │
│  结构化存储 → Redis session:{id}.memory_slots            │
│  {"标的": "贵州茅台", "标的代码": "600519", "金额": 500万,│
│   "风控偏好": "进取", "工作流类型": "stock_approval"}     │
└─────────────────────────────────────────────────────────┘
```

### 11.2 跨轮上下文传递

```
用户第1轮: "帮我审批茅台500万投资"  → slots = {标的:茅台, 金额:500万}
用户第2轮: "改成1000万"              → memory继承slots, 更新金额=1000万
用户第3轮: "风控偏好改成保守"         → memory继承slots, 更新偏好=保守
用户第4轮: "确认发起"                → 用完整的slots创建流程
```

---

## 12. 全链路 Trace 设计

### 12.1 Trace 数据模型

```python
class TraceEvent:
    trace_id: str          # = instance_id, 贯穿所有节点
    node_name: str         # planner/risk_agent/compliance_agent/aggregator/human
    node_input: str        # 节点输入的State快照(前200字)
    node_output: str       # 节点输出的State快照(前200字)
    tool_calls: list       # [{tool_name, latency_ms, status}]
    latency_ms: int        # 本节点耗时
    token_used: int        # LLM token消耗
    timestamp: datetime    # 记录时间
```

### 12.2 在每个节点中的集成

```python
# LangGraph 节点装饰器
def with_trace(node_func):
    """为节点添加Trace记录"""
    async def wrapper(state, config):
        trace_id = config["configurable"]["thread_id"]
        t0 = time.perf_counter()

        result = await node_func(state, config)

        # MQ 异步发Trace
        producer.send_audit_log({
            "trace_id": trace_id,
            "node_name": node_func.__name__,
            "node_input": str(state)[:200],
            "node_output": str(result)[:200],
            "latency_ms": (time.perf_counter() - t0) * 1000,
        })
        return result
    return wrapper
```

---

## 13. 与 Java 服务的协作

### 13.1 职责划分

| Python (Agent推理层) | Java (业务管理层) |
|------|------|
| Planner Agent 意图识别 | 流程模板 CRUD |
| Workflow Router 分发 | 流程实例状态查询 |
| ReAct Agent 审批推理 | 报告管理(CRUD) |
| Tool Calling | 用户管理 |
| Aggregator 聚合 | 权限查询 |
| Memory 管理 | 项目结构管理 |
| LangGraph 编排 | — |

### 13.2 通信方式

```
Python → Java:  HTTP/JSON (httpx)
  - 查权限: GET /api/permissions/check?user_id=xxx&workflow_type=xxx
  - 查模板: GET /api/templates?user_id=xxx
  - 保存报告: POST /api/reports

Java → MySQL: JDBC/MyBatis
Python → MySQL: SQLAlchemy/pymysql (直接读写 chat_*, workflow_instance 表)
```

**为什么不互通**：Python和Java各有一套数据库访问层，通过共享MySQL实现数据互通。Python写 `workflow_instance`，Java读 `workflow_instance`，没有循环依赖。

---

## 14. 并发与部署架构

### 14.1 为什么不用微服务框架

本系统的并发特征与传统 Web 高并发不同：

```
传统Web: 1000请求/s, 每个<50ms, CPU密集型
本系统:  100请求/s,  每个5-7s(LLM IO等待), IO密集型
```

瓶颈不在服务处理能力，在 DashScope API 的并发限制和 LLM 推理等待时间。两个服务不需要 Nacos/Eureka 注册发现，不需要 Feign 远程调用，不需要 Sentinel 熔断降级。轻量部署即可满足百级并发。

### 14.2 部署架构图

```
                        互联网
                          │
                          ▼
              ┌──────────────────────┐
              │       Nginx          │
              │  - 反向代理           │
              │  - 静态资源           │
              │  - limit_req 限流     │
              │    (100r/s + burst)  │
              │  - 负载均衡           │
              └──────┬───────────────┘
                     │
          ┌──────────┴──────────┐
          ▼                     ▼
┌──────────────────┐  ┌──────────────────┐
│  FastAPI × 4     │  │  Spring Boot × 2 │
│  (Uvicorn workers)│  │  (Tomcat 200线程) │
│                  │  │                  │
│  Agent推理        │  │  CRUD业务         │
│  Tool Calling    │  │  权限查询         │
│  流式SSE         │  │  报告管理         │
│                  │  │  项目管理         │
│  IO密集          │  │  CPU密集          │
└──────┬───────────┘  └──────┬───────────┘
       │                     │
       └──────────┬──────────┘
                  │
     ┌────────────┼────────────┐
     ▼            ▼            ▼
┌─────────┐ ┌─────────┐ ┌──────────┐
│  Redis  │ │ RocketMQ│ │  MySQL   │
│ 缓存/状态│ │ 削峰/日志│ │  持久化   │
└─────────┘ └─────────┘ └──────────┘
```

### 14.3 各层并发能力

| 层 | 组件 | 并发模型 | 处理能力 |
|------|------|------|------|
| 入口 | Nginx | `worker_processes auto` + `limit_req rate=100r/s burst=50` | 100+ QPS正常，超限排队 |
| Python | Uvicorn `--workers 4` | asyncio事件循环 × 4进程 | 同时处理40-80个LLM等待请求 |
| Java | Spring Boot | Tomcat默认 `max-threads=200` | CRUD毫秒级，单机数千QPS |
| 削峰 | RocketMQ | 异步消费 | 流程任务走MQ，Worker按自身节奏消费 |
| 缓存 | Redis | 单线程事件驱动 | 10万+ QPS，缓存命中不到1ms |

### 14.4 并发场景推演

**场景1: 100个分析师同时查询标的**

```
100个请求 → Nginx(通过) → FastAPI async(40-80个并发等待LLM)
→ 其余排队 → 等LLM返回 → 用户收到流式输出

最大等待: DashScope API并发限制(默认100 QPS)
用户体感: 首Token 1.5s, 完整体验 5-7s
```

**场景2: 50个审批流程同时发起**

```
50个请求 → FastAPI → 创建异步任务(50ms) → 立即返回"已创建"
→ RocketMQ Topic → Worker逐个消费 → 后台执行LangGraph
→ Human Approval节点暂停 → 通知用户审批

用户体感: <1s返回任务ID, 异步执行不受前端影响
```

**场景3: 普通CRUD (查报告/查状态)**

```
N个请求 → Nginx → Java Tomcat(200线程)
→ MyBatis查询MySQL(索引优化, <10ms) → 返回JSON

单机瓶颈: ~3000 QPS (远大于实际需求)
```

### 14.5 Nginx 核心配置

```nginx
upstream python_api {
    server 127.0.0.1:8000;
}

upstream java_api {
    server 127.0.0.1:8080;
}

limit_req_zone $binary_remote_addr zone=api_limit:10m rate=100r/s;

server {
    listen 80;

    location / {
        root /var/www/invest-frontend;
        try_files $uri /index.html;
    }

    location /api/chat {
        limit_req zone=api_limit burst=50 nodelay;
        proxy_pass http://python_api;
        proxy_read_timeout 60s;
        proxy_buffering off;     # SSE流式需关闭缓冲
    }

    location /api/workflow {
        proxy_pass http://python_api;
    }

    location /api/templates {
        proxy_pass http://java_api;
    }

    location /api/reports {
        proxy_pass http://java_api;
    }
}
```

### 14.6 启动命令

```bash
# Python Agent推理服务
uvicorn src.api:app --host 127.0.0.1 --port 8000 --workers 4

# Java 业务服务
mvn spring-boot:run -Dserver.port=8080

# Nginx
nginx -c /etc/nginx/nginx.conf
```

### 14.7 简历话术

> 系统采用 Nginx + 多 Worker 进程的轻量部署架构。Python侧 FastAPI 基于 asyncio 异步模型处理 IO 密集的 Agent 推理请求，通过 4 进程 Uvicorn 实现并发；Java侧 Spring Boot 处理 CRUD 类业务请求；RocketMQ 负责流程任务削峰和日志异步落库；Nginx 做反向代理、静态资源托管和请求限流。整体部署仅需 3 个进程，满足百级并发用户的日常使用。

---

## 15. 项目文件结构

```
agent-investment/
├── requirements.txt
├── .env
├── ARCHITECTURE.md
├── app.py
│
├── src/
│   ├── config.py
│   ├── state.py                     # InvestmentState TypedDict
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── planner.py               # Planner (系统路由+意图识别)
│   │   ├── workflow_router.py       # Workflow Router (分发+权限)
│   │   ├── risk_agent.py            # 风控审批 (ReAct)
│   │   ├── compliance_agent.py      # 合规审查 (ReAct)
│   │   ├── aggregator.py            # 结论聚合
│   │   ├── chitchat_node.py         # 闲聊回复
│   │   └── tool_agent.py            # 公共工具Agent
│   ├── tools/
│   │   ├── __init__.py              # ALL_TOOLS 注册表
│   │   ├── search_rag.py            # RAG政策检索(复用项目一)
│   │   ├── query_financial_db.py    # 财务数据库查询
│   │   └── sentiment_analysis.py    # 舆情分析
│   ├── workflow.py                  # LangGraph编排(核心)
│   ├── memory.py                    # 三级混合记忆(复用项目一)
│   ├── mq.py                        # MQ抽象层
│   ├── trace.py                     # 全链路追踪
│   ├── cache.py                     # Redis缓存(复用项目一)
│   └── api.py                       # FastAPI接口
│
├── java-service/
│   ├── pom.xml
│   └── src/main/java/com/invest/
│       ├── Application.java
│       ├── controller/
│       │   ├── TemplateController.java
│       │   ├── WorkflowController.java
│       │   ├── ReportController.java
│       │   └── PermissionController.java
│       ├── service/
│       ├── mapper/
│       └── entity/
│
├── data/policies/                   # 政策文档(RAG源)
├── sql/schema.sql                   # 建表语句
└── tests/
```

---

## 16. 面试核心话术

**问: 为什么用异步任务而不是同步等待审批结果？**

> 投研审批流程涉及多次LLM推理和工具调用，端到端耗时可能10-20秒。同步等待会让用户盯着空白页面。我们在Planner识别到流程意图后，立即创建异步任务、MQ触发后台执行，主线程在50ms内返回"任务已创建"。用户随时通过流程管理面板查看进度，到人工审批节点时系统会主动通知。

**问: 权限隔离怎么做的？**

> 三层。UI层通过模板弹窗展示用户可发起的流程，Agent层的Workflow Router做二次校验防止绕过UI。权限数据存在MySQL，支持按用户、角色、部门三个维度配置，符合企业内部审批的实际需求。

**问: 为什么Python和Java混用？**

> AI推理链路（LangChain/LangGraph/Tool Calling）的最佳实践是Python生态，而传统业务流程管理（模板CRUD、权限管理、报告查询）是Java/SpringBoot的强项。两者通过MySQL共享数据、HTTP通信，各取所长。我们也在Java侧封装了对Python Agent服务的调用，形成完整的技术栈闭环。
