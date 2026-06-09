"""
FastAPI 接口层 — 项目二：智能投研协同分析平台
"""
import os, sys, time, uuid, asyncio, json
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from config import settings
from state import InvestmentState
from agents.planner import PlannerNode
from agents.chitchat_node import ChitchatNode
from agents.tool_agent import ToolAgentNode
from agents.workflow_router import WorkflowRouterNode
from agents.risk_agent import RiskAgentNode
from agents.compliance_agent import ComplianceAgentNode
from agents.aggregator import AggregatorNode
from workflow import build_graph
from memory import MemoryManager
from mq import producer, consumer
from langgraph.checkpoint.memory import MemorySaver


# ── 请求/响应模型 ──
class ChatRequest(BaseModel):
    question: str
    session_id: Optional[str] = None
    user_id: int = 1001


class ChatResponse(BaseModel):
    answer: str
    intent: str
    session_id: str


# ── 全局服务容器 ──
services = {}


def init_services():
    """启动时一次性初始化所有节点"""
    print("=" * 50)
    print("[API] 初始化服务...")

    api_key = settings.DASHSCOPE_API_KEY

    services["planner"] = PlannerNode(api_key=api_key)
    services["chitchat"] = ChitchatNode(api_key=api_key)
    services["tool_agent"] = ToolAgentNode(api_key=api_key)
    services["router"] = WorkflowRouterNode()
    services["risk"] = RiskAgentNode(api_key=api_key)
    services["compliance"] = ComplianceAgentNode(api_key=api_key)
    services["aggregator"] = AggregatorNode(api_key=api_key)
    services["sessions"] = {}  # session_id -> MemoryManager

    # 编译 LangGraph
    graph_builder = build_graph(
        services["planner"], services["chitchat"],
        services["tool_agent"], services["router"],
        services["risk"], services["compliance"],
        services["aggregator"],
    )
    checkpointer = MemorySaver()
    services["graph"] = graph_builder.compile(checkpointer=checkpointer)  # 保持 context manager 存活

    print(f"[API] 初始化完成")
    print("=" * 50)


# ── FastAPI 应用 ──
app = FastAPI(
    title="智能投研协同分析平台",
    description="基于 Multi-Agent Workflow 的投研审批系统",
    version="1.0.0",
)


@app.on_event("startup")
async def startup():
    init_services()
    asyncio.create_task(consumer.run())


# ── 前端页面 ──
@app.get("/", response_class=HTMLResponse)
async def index():
    return """
<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>智能投研协同分析平台</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, sans-serif; background: #1a1a2e; color: #eee; display: flex; justify-content: center; min-height: 100vh; }
.container { width: 100%; max-width: 800px; padding: 20px; display: flex; flex-direction: column; height: 100vh; }
.header { text-align: center; padding: 16px; background: linear-gradient(135deg, #16213e, #0f3460); border-radius: 10px 10px 0 0; }
.header h1 { font-size: 20px; color: #e94560; }
.header p { font-size: 12px; opacity: 0.7; }
.chat-box { flex: 1; overflow-y: auto; padding: 16px; background: #16213e; }
.message { margin-bottom: 14px; }
.message.user { text-align: right; }
.message.user .bubble { background: #e94560; color: white; display: inline-block; padding: 10px 16px; border-radius: 16px 16px 4px 16px; max-width: 85%; text-align: left; }
.message.assistant .bubble { background: #0f3460; display: inline-block; padding: 10px 16px; border-radius: 16px 16px 16px 4px; max-width: 85%; white-space: pre-wrap; }
.message .meta { font-size: 11px; color: #666; margin-top: 4px; }
.sources { font-size: 11px; color: #888; margin-top: 6px; padding: 8px; background: #1a1a2e; border-radius: 6px; border-left: 3px solid #e94560; }
.input-area { display: flex; gap: 8px; padding: 12px; background: #16213e; border: 1px solid #0f3460; border-top: none; border-radius: 0 0 10px 10px; }
.input-area input { flex: 1; padding: 10px 14px; border: 1px solid #0f3460; border-radius: 20px; font-size: 14px; outline: none; background: #1a1a2e; color: #eee; }
.input-area input:focus { border-color: #e94560; }
.input-area button { padding: 10px 24px; background: #e94560; color: white; border: none; border-radius: 20px; cursor: pointer; font-size: 14px; }
.input-area button:hover { background: #c73e54; }
.input-area button:disabled { background: #555; }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>智能投研协同分析平台</h1>
    <p>Multi-Agent Workflow | Planner + Router + Risk + Compliance</p>
  </div>
  <div class="chat-box" id="chat"></div>
  <div class="input-area">
    <input type="text" id="question" placeholder="如：帮我审批茅台500万投资 / 查茅台财务数据 / 你好" onkeypress="if(event.key==='Enter')send()">
    <button onclick="send()" id="sendBtn">发送</button>
  </div>
</div>
<script>
const SID = 'sess_' + Date.now();
async function send() {
  const q = document.getElementById('question').value.trim();
  if (!q) return;
  addMsg('user', q);
  document.getElementById('question').value = '';
  const btn = document.getElementById('sendBtn');
  btn.disabled = true;
  const bubble = addMsg('assistant', '思考中...', true);
  try {
    const resp = await fetch('/chat', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q,session_id:SID,user_id:1001})});
    const data = await resp.json();
    let html = data.answer.replace(/\\n/g,'<br>');
    if (data.intent) html += '<div class="meta">意图: ' + data.intent + '</div>';
    bubble.innerHTML = html;
  } catch(e) {
    bubble.innerHTML = '出错了: ' + e.message;
  } finally {
    btn.disabled = false;
    document.getElementById('chat').scrollTop = document.getElementById('chat').scrollHeight;
  }
}
function addMsg(role, content, isTemp) {
  const div = document.createElement('div');
  div.className = 'message ' + role;
  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.innerHTML = content;
  div.appendChild(bubble);
  document.getElementById('chat').appendChild(div);
  document.getElementById('chat').scrollTop = document.getElementById('chat').scrollHeight;
  return bubble;
}
</script>
</body>
</html>"""


# ── 问答接口 ──
@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    t0 = time.perf_counter()
    session_id = req.session_id or uuid.uuid4().hex[:12]

    # 1. 获取或创建 session 的 Memory
    sessions = services["sessions"]
    if session_id not in sessions:
        sessions[session_id] = MemoryManager(api_key=settings.DASHSCOPE_API_KEY)
    memory = sessions[session_id]

    # 2. 用记忆增强问题
    augmented_q = memory.augment_question(req.question)

    # 3. 构建初始 State（Planner 会填充 intent/slots 等字段）
    initial_state: InvestmentState = {
        "messages": [{"role": "user", "content": augmented_q}],
        "user_id": req.user_id,
        "intent": "", "confidence": 0.0, "slots": {},
        "need_human_confirm": False,
        "tool_name": "", "tool_args": {}, "workflow_type": "",
        "task_id": str(uuid.uuid4().hex[:16]),
        "permission_checked": False,
        "risk_decision": "", "risk_reason": "",
        "compliance_decision": "", "compliance_reason": "",
        "aggregated_result": "", "human_approved": None,
        "human_feedback": "", "final_report": "",
        "trace_id": session_id,
    }

    # 4. 执行 LangGraph 工作流
    config = {"configurable": {"thread_id": session_id}}
    graph = services["graph"]
    try:
        result = graph.invoke(initial_state, config)
    except Exception as e:
        return ChatResponse(
            answer=f"服务暂时不可用，请稍后重试。（{str(e)[:100]}）",
            intent="error",
            session_id=session_id,
        )

    # 5. 提取最终回答
    final_answer = (
        result.get("final_report") or
        result.get("aggregated_result") or
        "处理完成，请查看结果。"
    )

    # 6. 更新记忆
    memory.add_turn(req.question, final_answer)

    # 7. MQ: 聊天记录异步持久化
    producer.send_chat_history(session_id, "user", req.question)
    producer.send_chat_history(session_id, "assistant", final_answer)

    # 8. MQ: 审计日志
    latency = (time.perf_counter() - t0) * 1000
    producer.send_audit_log(session_id, "chat_endpoint", latency)

    return ChatResponse(
        answer=final_answer,
        intent=result.get("intent", "unknown"),
        session_id=session_id,
    )


# ── 健康检查 ──
@app.get("/health")
async def health():
    return {"status": "healthy", "sessions": len(services["sessions"])}
