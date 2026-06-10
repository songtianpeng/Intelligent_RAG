"""
FastAPI 接口层 — 项目二：智能投研协同分析平台
"""
import os, sys, time, uuid, asyncio, json
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
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
from auth import login as auth_login, get_session, set_session, get_user_by_id
from langgraph.checkpoint.memory import MemorySaver


# ── 模型 ──
class LoginRequest(BaseModel):
    username: str
    password: str


class ChatRequest(BaseModel):
    question: str
    session_id: Optional[str] = None
    token: str = ""


class ChatResponse(BaseModel):
    answer: str
    intent: str
    session_id: str
    task_id: Optional[str] = None


class ApproveRequest(BaseModel):
    token: str
    approved: bool
    feedback: str = ""


# ── 服务 ──
services: dict = {}
_workflow_store: dict = {}


def get_or_create_graph(auto_approve: bool):
    key = f"graph_{auto_approve}"
    if key not in services:
        graph_builder = build_graph(
            services["planner"], services["chitchat"],
            services["tool_agent"], services["router"],
            services["risk"], services["compliance"],
            services["aggregator"], auto_approve=auto_approve,
        )
        services[key] = graph_builder.compile(checkpointer=MemorySaver())
    return services[key]


def init_services():
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
    services["sessions"] = {}
    graph_builder = build_graph(
        services["planner"], services["chitchat"],
        services["tool_agent"], services["router"],
        services["risk"], services["compliance"],
        services["aggregator"], auto_approve=True,
    )
    services["graph"] = graph_builder.compile(checkpointer=MemorySaver())
    print(f"[API] 初始化完成")
    print("=" * 50)


async def _execute_workflow_async(task_id: str, initial_state: dict):
    print(f"[Worker] 开始异步执行: {task_id}")
    try:
        graph = get_or_create_graph(auto_approve=False)
        config = {"configurable": {"thread_id": task_id}}
        result = graph.invoke(initial_state, config)
        final_answer = result.get("final_report") or result.get("aggregated_result") or "处理完成"
        _workflow_store[task_id].update({
            "status": "APPROVED" if result.get("human_approved") else "PENDING_APPROVAL",
            "result": final_answer,
        })
        print(f"[Worker] 执行完成: {task_id}")
    except Exception as e:
        err_msg = str(e)
        if "GraphInterrupt" in type(e).__name__ or "interrupt" in err_msg.lower():
            graph = get_or_create_graph(auto_approve=False)
            config = {"configurable": {"thread_id": task_id}}
            state = graph.get_state(config)
            agg = state.values.get("aggregated_result", "") if state.values else ""
            _workflow_store[task_id].update({
                "status": "PENDING_APPROVAL",
                "result": agg,
                "risk_decision": state.values.get("risk_decision", "") if state.values else "",
                "compliance_decision": state.values.get("compliance_decision", "") if state.values else "",
            })
            print(f"[Worker] 已暂停(PENDING_APPROVAL): {task_id}")
        else:
            _workflow_store[task_id].update({"status": "ERROR", "result": err_msg[:500]})
            print(f"[Worker] 失败: {task_id}")


# ── FastAPI ──
app = FastAPI(title="智能投研协同分析平台", version="1.0.0")


@app.on_event("startup")
async def startup():
    print("[Server] 正在初始化 Planner + Risk + Compliance Agent...")
    print("[Server] 首次启动约 1-2 分钟，请等待 '初始化完成' 提示")
    print("[Server] 等待期间访问页面会显示 503 Service Unavailable，这是正常的")
    init_services()
    print("[Server] 服务就绪！访问 http://localhost:8000")
    asyncio.create_task(consumer.run())


# ═══════════════════════════════════
#  / → 登录页
# ═══════════════════════════════════
@app.get("/", response_class=HTMLResponse)
async def login_page():
    return """<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><title>登录 - 投研平台</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,sans-serif;background:#1a1a2e;display:flex;justify-content:center;align-items:center;min-height:100vh}
.card{background:#16213e;padding:40px 32px;border-radius:12px;width:360px;text-align:center;border:1px solid #0f3460}
.card h2{color:#e94560;margin-bottom:8px;font-size:22px}
.card p{color:#888;font-size:13px;margin-bottom:24px}
.card input{width:100%;padding:10px 14px;margin:8px 0;border:1px solid #0f3460;border-radius:8px;font-size:14px;outline:none;background:#1a1a2e;color:#eee}
.card input:focus{border-color:#e94560}
.card button{width:100%;padding:10px;margin-top:12px;background:#e94560;color:#fff;border:none;border-radius:8px;cursor:pointer;font-size:15px;font-weight:bold}
.card button:hover{background:#c73e54}
.card .hint{color:#666;font-size:11px;margin-top:16px;text-align:left}
.card .error{color:#e74c3c;font-size:12px;margin-top:8px;display:none}
</style></head><body>
<div class="card">
<h2>投研审批平台</h2>
<p>Multi-Agent Workflow System</p>
<input type="text" id="u" placeholder="用户名" value="zhang">
<input type="password" id="p" placeholder="密码" value="123456">
<button onclick="doLogin()">登 录</button>
<div class="error" id="err">登录失败，请检查用户名密码</div>
<div class="hint">
测试账号:<br>
分析师: zhang / 123456<br>
审核员: li / 123456
</div>
</div>
<script>
function doLogin(){
var u=document.getElementById('u').value.trim();
var p=document.getElementById('p').value;
if(!u||!p)return;
fetch('/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u,password:p})})
.then(function(r){return r.json()}).then(function(d){
if(d.token){localStorage.setItem('token',d.token);localStorage.setItem('user',JSON.stringify(d));window.location.href='/chat'}
else{document.getElementById('err').style.display='block'}
}).catch(function(){document.getElementById('err').style.display='block'})
}
</script></body></html>"""


# ═══════════════════════════════════
#  /chat → 聊天页（需登录）
# ═══════════════════════════════════
@app.get("/chat", response_class=HTMLResponse)
async def chat_page():
    return """<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><title>智能投研平台</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,sans-serif;background:#1a1a2e;color:#eee;display:flex;min-height:100vh}
.sidebar{width:230px;background:#16213e;padding:14px;border-right:1px solid #0f3460}
.sidebar h3{color:#e94560;margin:0 0 10px 0;font-size:15px}
.sidebar .info{font-size:12px;color:#888;margin:6px 0;padding:6px;background:#1a1a2e;border-radius:4px}
.sidebar .sec{margin:10px 0}
.sidebar .sec-title{font-size:11px;color:#888;margin:4px 0}
.sidebar button{width:100%;padding:7px;margin:2px 0;background:#0f3460;color:#eee;border:none;border-radius:5px;cursor:pointer;font-size:12px;text-align:left}
.sidebar button:hover{background:#1a4a80}
.main{flex:1;display:flex;flex-direction:column;max-width:740px;padding:14px}
.header{text-align:center;padding:10px;background:linear-gradient(135deg,#16213e,#0f3460);border-radius:10px 10px 0 0}
.header h1{font-size:17px;color:#e94560}
.chat-box{flex:1;overflow-y:auto;padding:10px;background:#16213e}
.msg{margin-bottom:10px}.msg.user{text-align:right}
.msg.user .b{background:#e94560;color:#fff;display:inline-block;padding:8px 12px;border-radius:14px 14px 4px 14px;max-width:80%;text-align:left;font-size:13px}
.msg.asst .b{background:#0f3460;display:inline-block;padding:8px 12px;border-radius:14px 14px 14px 4px;max-width:90%;white-space:pre-wrap;font-size:13px}
.msg .meta{font-size:10px;color:#888;margin-top:2px}
.card{background:#1a1a2e;padding:8px;margin:4px 0;border-radius:6px;font-size:12px}
.card .tag{float:right;padding:1px 6px;border-radius:3px;font-size:10px}
.tag-pending{background:#f39c12;color:#111}.tag-approved{background:#27ae60;color:#fff}.tag-rejected{background:#e74c3c;color:#fff}
.card button{font-size:10px;padding:2px 8px;margin:2px}
.input-area{display:flex;gap:6px;padding:10px;background:#16213e;border:1px solid #0f3460;border-top:none;border-radius:0 0 10px 10px}
.input-area input{flex:1;padding:8px 12px;border:1px solid #0f3460;border-radius:20px;font-size:14px;outline:none;background:#1a1a2e;color:#eee}
.input-area input:focus{border-color:#e94560}
.input-area button{padding:8px 16px;background:#e94560;color:#fff;border:none;border-radius:20px;cursor:pointer;font-size:13px}
</style></head><body>
<div class="sidebar">
<h3>投研审批平台</h3>
<div class="info" id="info"></div>
<div class="sec"><div class="sec-title">流程操作</div>
<button onclick="pendingList()" id="btnPending" style="display:none">待审批流程</button>
<button onclick="myWorkflows()">我已发起的流程</button>
<button onclick="window.location.href='/'">退出登录</button>
</div>
</div>
<div class="main">
<div class="header"><h1>智能投研协同分析</h1></div>
<div class="chat-box" id="chat"></div>
<div class="input-area">
<input type="text" id="q" placeholder="输入需求..." onkeydown="if(event.key==='Enter')send()">
<button onclick="send()">发送</button>
</div></div>
<script>
var TOKEN=localStorage.getItem('token')||'',USER=JSON.parse(localStorage.getItem('user')||'{}'),SID='sess_'+Date.now();
if(!TOKEN){window.location.href='/'}
document.getElementById('info').innerHTML='已登录: '+USER.name+'<br>角色: '+USER.role;
if(USER.role==='reviewer'||USER.role==='admin'){document.getElementById('btnPending').style.display='block'}
function pendingList(){
fetch('/workflow/pending?token='+TOKEN).then(function(r){return r.json()}).then(function(tasks){
var h='';if(tasks.length===0){h='暂无待审批流程'}
tasks.forEach(function(t){
h+='<div class=card>'+t.workflow_type+' | '+JSON.stringify(t.slots)+'<span class=tag tag-pending>待审批</span><br>';
h+='<button data-tid='+t.task_id+' data-ok=1 class=btn-approve>通过</button> ';
h+='<button data-tid='+t.task_id+' data-ok=0 class=btn-approve>驳回</button></div>';
});
addMsg('asst',h);
document.querySelectorAll('.btn-approve').forEach(function(b){b.onclick=function(){approve(this.dataset.tid,this.dataset.ok==='1')}})
})}
function myWorkflows(){
fetch('/workflow/my?token='+TOKEN).then(function(r){return r.json()}).then(function(tasks){
var h='';if(tasks.length===0){h='暂无已发起流程'}
tasks.forEach(function(t){h+='<div class=card>'+t.workflow_type+' | '+JSON.stringify(t.slots)+'<span class=tag tag-'+t.status.toLowerCase()+'">'+t.status+'</span></div>'});
addMsg('asst',h)
})}
function approve(tid,ok){
fetch('/workflow/'+tid+'/approve',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:TOKEN,approved:ok,feedback:ok?'同意':'驳回'})})
.then(function(r){return r.json()}).then(function(d){addMsg('asst','审批完成: '+JSON.stringify(d));pendingList()})}
function send(){
var q=document.getElementById('q').value.trim();if(!q)return;
addMsg('user',q);document.getElementById('q').value='';
var b=addMsg('asst','处理中...');
fetch('/chat/api',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q,session_id:SID,token:TOKEN})})
.then(function(r){return r.json()}).then(function(d){
var t=d.answer;if(d.task_id)t+='<br><span class=meta>任务ID: '+d.task_id+'</span>';
if(d.intent)t+='<br><span class=meta>意图: '+d.intent+'</span>';b.innerHTML=t
}).catch(function(e){b.innerHTML='出错: '+e.message})}
function addMsg(role,content){
var d=document.createElement('div');d.className='msg '+role;
var bb=document.createElement('div');bb.className='b';bb.innerHTML=content;
d.appendChild(bb);document.getElementById('chat').appendChild(d);
document.getElementById('chat').scrollTop=document.getElementById('chat').scrollHeight;return bb}
</script></body></html>"""


# ═══════════════════════════════════
#  API
# ═══════════════════════════════════
@app.post("/login")
async def login(req: LoginRequest):
    user = auth_login(req.username, req.password)
    if not user:
        raise HTTPException(401, "用户名或密码错误")
    set_session(user["token"], user)
    return user


@app.post("/chat/api", response_model=ChatResponse)
async def chat_api(req: ChatRequest):
    user = get_session(req.token)
    if not user:
        user = {"user_id": 1001, "name": "访客", "role": "analyst"}
    user_id = user["user_id"]

    t0 = time.perf_counter()
    session_id = req.session_id or uuid.uuid4().hex[:12]
    sessions = services["sessions"]
    if session_id not in sessions:
        sessions[session_id] = MemoryManager(api_key=settings.DASHSCOPE_API_KEY)
    memory = sessions[session_id]

    augmented_q = memory.augment_question(req.question)
    task_id = str(uuid.uuid4().hex[:16])

    initial_state: InvestmentState = {
        "messages": [{"role": "user", "content": augmented_q}],
        "user_id": user_id,
        "intent": "", "confidence": 0.0, "slots": {},
        "need_human_confirm": False,
        "tool_name": "", "tool_args": {}, "workflow_type": "",
        "task_id": task_id, "permission_checked": False,
        "risk_decision": "", "risk_reason": "",
        "compliance_decision": "", "compliance_reason": "",
        "aggregated_result": "", "human_approved": None,
        "human_feedback": "", "final_report": "", "trace_id": task_id,
    }

    config = {"configurable": {"thread_id": task_id}}
    graph = services["graph"]

    try:
        partial = graph.invoke(initial_state, config)
    except Exception as e:
        return ChatResponse(answer=f"服务不可用。（{str(e)[:80]}）",
                            intent="error", session_id=session_id, task_id=None)

    intent = partial.get("intent", "chitchat")

    if intent in ("chitchat", "tool_call"):
        final_answer = partial.get("final_report") or "处理完成。"
        memory.add_turn(req.question, final_answer)
        producer.send_chat_history(session_id, "user", req.question)
        producer.send_chat_history(session_id, "assistant", final_answer)
        return ChatResponse(answer=final_answer, intent=intent,
                            session_id=session_id, task_id=None)

    # workflow → 异步
    wf_type = partial.get("workflow_type", "stock_approval")
    slots = partial.get("slots", {})
    _workflow_store[task_id] = {
        "status": "PENDING_APPROVAL", "workflow_type": wf_type,
        "slots": slots, "user_id": user_id, "initiator": user["name"],
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    asyncio.create_task(_execute_workflow_async(task_id, initial_state))
    answer = (f"任务已创建\n\n流程类型: {wf_type}\n"
              f"标的/金额: {json.dumps(slots, ensure_ascii=False)}\n"
              f"任务ID: {task_id}\n状态: 审批中")
    memory.add_turn(req.question, answer)
    producer.send_chat_history(session_id, "user", req.question)
    producer.send_chat_history(session_id, "assistant", answer)
    return ChatResponse(answer=answer, intent=intent,
                        session_id=session_id, task_id=task_id)


@app.get("/workflow/my")
async def my_workflows(token: str = Query("")):
    user = get_session(token)
    if not user:
        raise HTTPException(401, "请先登录")
    result = []
    for tid, wf in _workflow_store.items():
        if wf.get("user_id") == user["user_id"]:
            result.append({"task_id": tid, "workflow_type": wf["workflow_type"],
                           "slots": wf.get("slots", {}), "status": wf["status"],
                           "result": wf.get("result", "")[:200],
                           "created_at": wf.get("created_at", "")})
    return sorted(result, key=lambda x: x["created_at"], reverse=True)


@app.get("/workflow/pending")
async def pending_workflows(token: str = Query("")):
    user = get_session(token)
    if not user:
        raise HTTPException(401, "请先登录")
    result = []
    for tid, wf in _workflow_store.items():
        if wf["status"] in ("PENDING_APPROVAL",):
            result.append({"task_id": tid, "workflow_type": wf["workflow_type"],
                           "slots": wf.get("slots", {}), "status": wf["status"],
                           "initiator": wf.get("initiator", ""),
                           "created_at": wf.get("created_at", "")})
    return sorted(result, key=lambda x: x["created_at"], reverse=True)


@app.post("/workflow/{task_id}/approve")
async def approve(task_id: str, req: ApproveRequest):
    user = get_session(req.token)
    if not user:
        raise HTTPException(401, "请先登录")
    wf = _workflow_store.get(task_id)
    if not wf:
        raise HTTPException(404, "任务不存在")
    wf["status"] = "APPROVED" if req.approved else "REJECTED"
    wf["approver"] = user["name"]
    wf["feedback"] = req.feedback
    return {"task_id": task_id, "status": wf["status"],
            "approver": user["name"], "message": "审批完成"}


@app.get("/health")
async def health():
    return {"status": "healthy", "workflows": len(_workflow_store)}
