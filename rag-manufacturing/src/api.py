"""
FastAPI 接口层
"""
import os, time, uuid, asyncio
from typing import Optional

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
import json as json_module

from config import settings
from document_loader import DocumentLoader
from embedding import EmbeddingService
from vector_store import VectorStore
from retrieval.bm25_retriever import BM25Retriever
from retrieval.vector_retriever import VectorRetriever
from retrieval.hybrid_retriever import HybridRetriever
from retrieval.permission import PermissionManager
from generation import AnswerGenerator
from memory_manager import MemoryManager
from cache import QACache
from mq import producer, consumer


# ── 请求/响应模型 ──
class ChatRequest(BaseModel):
    question: str
    session_id: Optional[str] = None
    factory: Optional[str] = None
    production_line: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    sources: list
    from_cache: bool = False
    session_id: str


# ── 全局服务容器（启动时初始化） ──
services = {}


def init_services():
    """启动时初始化所有服务"""
    print("=" * 50)
    print("[API] 初始化服务...")

    emb_svc = EmbeddingService(api_key=settings.DASHSCOPE_API_KEY)
    cache = QACache()
    gen = AnswerGenerator(api_key=settings.DASHSCOPE_API_KEY, cache=cache)

    # 加载文档 & 建库
    loader = DocumentLoader(data_dir="data")
    chunks = loader.load_all()
    texts = [c.page_content for c in chunks]
    vectors = emb_svc.embed_documents(texts)

    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "chroma_data"))
    store = VectorStore(db_path=db_path)

    # 构建 metadata（含权限字段）
    metadatas = [
        {"source": c.metadata.get("source", ""),
         "page": c.metadata.get("page", 1),
         "heading_path": c.metadata.get("heading_path", ""),
         "chunk_type": c.metadata.get("chunk_type", "text")}
        for c in chunks
    ]
    perm_mgr = PermissionManager()
    metadatas = perm_mgr.enrich_metadatas(metadatas)

    # 用已向量化的数据直接写 ChromaDB
    from chromadb import PersistentClient
    client = PersistentClient(path=db_path)
    try:
        client.delete_collection(store.COLLECTION_NAME)
    except Exception:
        pass
    collection = client.create_collection(
        name=store.COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    ids = [str(i) for i in range(len(chunks))]
    collection.add(ids=ids, documents=texts, embeddings=vectors, metadatas=metadatas)

    # 初始化检索器
    chunk_dicts = [{"text": c.page_content, "metadata": m}
                   for c, m in zip(chunks, metadatas)]
    bm25 = BM25Retriever()
    bm25.build_index(chunk_dicts)
    vr = VectorRetriever(store)
    vr.chunks = chunk_dicts
    hybrid = HybridRetriever(bm25, vr)

    # 多轮记忆（session -> MemoryManager 映射）
    sessions = {}

    services["emb_svc"] = emb_svc
    services["gen"] = gen
    services["cache"] = cache
    services["store"] = store
    services["hybrid"] = hybrid
    services["perm_mgr"] = perm_mgr
    services["sessions"] = sessions
    services["chunk_dicts"] = chunk_dicts
    print(f"[API] 初始化完成: {len(chunks)} chunks 已入库")
    print("=" * 50)


# ── 创建 FastAPI 应用 ──
app = FastAPI(
    title="智能制造设备运维 RAG 系统",
    description="基于 RAG 的注塑机故障排查专家系统",
    version="1.0.0",
)


# ── 前端页面 ──
@app.get("/", response_class=HTMLResponse)
async def index():
    return """
<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>注塑机智能运维助手</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, sans-serif; background: #f0f2f5; display: flex; justify-content: center; min-height: 100vh; }
.container { width: 100%; max-width: 800px; padding: 20px; display: flex; flex-direction: column; height: 100vh; }
.header { text-align: center; padding: 16px; background: #1a73e8; color: white; border-radius: 10px 10px 0 0; }
.header h1 { font-size: 20px; }
.header p { font-size: 12px; opacity: 0.85; }
.chat-box { flex: 1; overflow-y: auto; background: white; padding: 16px; border: 1px solid #e0e0e0; }
.message { margin-bottom: 14px; animation: fadeIn 0.3s; }
.message.user { text-align: right; }
.message.user .bubble { background: #1a73e8; color: white; display: inline-block; padding: 10px 16px; border-radius: 16px 16px 4px 16px; max-width: 85%; text-align: left; }
.message.assistant .bubble { background: #f1f3f4; display: inline-block; padding: 10px 16px; border-radius: 16px 16px 16px 4px; max-width: 85%; white-space: pre-wrap; }
.message .meta { font-size: 11px; color: #999; margin-top: 4px; }
.message.assistant .meta { margin-left: 4px; }
.sources { font-size: 11px; color: #888; margin-top: 6px; padding: 8px; background: #fafafa; border-radius: 6px; border-left: 3px solid #1a73e8; }
.sources span { color: #1a73e8; }
.input-area { display: flex; gap: 8px; padding: 12px; background: white; border: 1px solid #e0e0e0; border-top: none; border-radius: 0 0 10px 10px; }
.input-area input { flex: 1; padding: 10px 14px; border: 1px solid #ddd; border-radius: 20px; font-size: 14px; outline: none; }
.input-area input:focus { border-color: #1a73e8; }
.input-area button { padding: 10px 24px; background: #1a73e8; color: white; border: none; border-radius: 20px; cursor: pointer; font-size: 14px; }
.input-area button:hover { background: #1557b0; }
.input-area button:disabled { background: #ccc; }
.loading { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #1a73e8; animation: bounce 1.4s infinite; margin-left: 8px; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>注塑机智能运维助手</h1>
    <p>基于 RAG 的 HTF1200 故障排查专家系统</p>
  </div>
  <div class="chat-box" id="chat"></div>
  <div class="input-area">
    <input type="text" id="question" placeholder="输入故障现象或问题，如 E03报警怎么办 ..." onkeypress="if(event.key==='Enter') send()">
    <button onclick="send()" id="sendBtn">发送</button>
  </div>
</div>
<script>
const SESSION_ID = 'sess_' + Date.now();

async function send() {
  const q = document.getElementById('question').value.trim();
  if (!q) return;
  addMsg('user', q);
  document.getElementById('question').value = '';
  const btn = document.getElementById('sendBtn');
  btn.disabled = true;
  const bubble = addMsg('assistant', '', true);
  const chat = document.getElementById('chat');

  try {
    const resp = await fetch('/chat/stream', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({question: q, session_id: SESSION_ID})
    });
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let fullText = '';
    let buf = '';

    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      buf += decoder.decode(value, {stream: true});
      const lines = buf.split('\\n');
      buf = lines.pop();

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const data = JSON.parse(line.slice(6));
        if (data.token) {
          fullText += data.token;
          bubble.innerHTML = fullText.replace(/\\n/g, '<br>');
        }
        if (data.done) {
          let html = fullText.replace(/\\n/g, '<br>');
          if (data.sources && data.sources.length) {
            html += '<div class="sources">' + data.sources.map(s => '📎 ' + s).join('<br>') + '</div>';
          }
          bubble.innerHTML = html;
          bubble.insertAdjacentHTML('afterend', '<div class="meta">' + new Date().toLocaleTimeString() + '</div>');
        }
        chat.scrollTop = chat.scrollHeight;
      }
    }
  } catch(e) {
    bubble.innerHTML = '出错了: ' + e.message;
  } finally {
    btn.disabled = false;
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


@app.on_event("startup")
async def startup():
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "chroma_data"))
    # 如果 ChromaDB 已有数据，跳过重建（热加载用）
    from chromadb import PersistentClient
    client = PersistentClient(path=db_path)
    try:
        col = client.get_collection("manufacturing_knowledge")
        if col.count() > 0:
            print(f"[API] ChromaDB 已有 {col.count()} 条，跳过重建")
            # 仍需初始化检索器（轻量操作）
            _init_retrievers_only(db_path)
            return
    except Exception:
        pass
    # 首次启动：完整初始化
    init_services()
    asyncio.create_task(consumer.run())


def _init_retrievers_only(db_path: str):
    """仅初始化检索器（不重做向量化），热加载用"""
    emb_svc = EmbeddingService(api_key=settings.DASHSCOPE_API_KEY)
    cache = QACache()
    gen = AnswerGenerator(api_key=settings.DASHSCOPE_API_KEY, cache=cache)

    store = VectorStore(db_path=db_path)
    store.collection = store.client.get_collection("manufacturing_knowledge")

    # 从 ChromaDB 读取已有数据重建 chunk_dicts
    all_data = store.collection.get(include=["documents", "metadatas"])
    chunk_dicts = [
        {"text": doc, "metadata": meta}
        for doc, meta in zip(all_data["documents"], all_data["metadatas"])
    ]

    bm25 = BM25Retriever()
    bm25.build_index(chunk_dicts)
    vr = VectorRetriever(store)
    vr.chunks = chunk_dicts
    hybrid = HybridRetriever(bm25, vr)
    perm_mgr = PermissionManager()
    sessions = {}

    services["emb_svc"] = emb_svc
    services["gen"] = gen
    services["cache"] = cache
    services["store"] = store
    services["hybrid"] = hybrid
    services["perm_mgr"] = perm_mgr
    services["sessions"] = sessions
    services["chunk_dicts"] = chunk_dicts
    print(f"[API] 检索器就绪: {len(chunk_dicts)} chunks")


# ── 问答接口 ──
@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """智能问答（支持多轮对话）"""
    t0 = time.perf_counter()
    session_id = req.session_id or uuid.uuid4().hex[:12]

    # 1. 获取或创建 session 的 Memory
    sessions = services["sessions"]
    if session_id not in sessions:
        sessions[session_id] = MemoryManager(
            api_key=settings.DASHSCOPE_API_KEY,
        )
    memory = sessions[session_id]

    # 2. 权限过滤
    perm_mgr = services["perm_mgr"]
    where_filter = perm_mgr.build_filter(
        factory=req.factory,
        production_line=req.production_line,
    )

    # 3. 混合检索
    emb_svc = services["emb_svc"]
    hybrid = services["hybrid"]
    q_vec = emb_svc.embed_query(req.question)
    retrieved = hybrid.search(req.question, q_vec, top_k=5, where_filter=where_filter)

    # 4. LLM 生成（含缓存）
    gen = services["gen"]
    memory_ctx = memory.get_context()
    # 把历史上下文拼到问题里
    if memory_ctx:
        augmented_question = f"{memory_ctx}\n\n当前问题：{req.question}"
    else:
        augmented_question = req.question

    result = gen.generate(augmented_question, retrieved)

    # 5. 更新记忆
    memory.add_turn(req.question, result["answer"])

    # 6. MQ 异步：日志 + 聊天记录持久化
    latency = (time.perf_counter() - t0) * 1000
    producer.send(
        req.question, result["answer"],
        cache_hit=result.get("from_cache", False),
        latency_ms=latency,
    )
    producer.send_chat_history(session_id, "user", req.question)
    producer.send_chat_history(session_id, "assistant", result["answer"])

    return ChatResponse(
        answer=result["answer"],
        sources=result.get("sources", []),
        from_cache=result.get("from_cache", False),
        session_id=session_id,
    )


# ── 流式问答 ──
@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """流式问答（SSE）"""
    t0 = time.perf_counter()
    session_id = req.session_id or uuid.uuid4().hex[:12]

    sessions = services["sessions"]
    if session_id not in sessions:
        sessions[session_id] = MemoryManager(api_key=settings.DASHSCOPE_API_KEY)
    memory = sessions[session_id]

    perm_mgr = services["perm_mgr"]
    where_filter = perm_mgr.build_filter(factory=req.factory, production_line=req.production_line)

    emb_svc = services["emb_svc"]
    hybrid = services["hybrid"]
    q_vec = emb_svc.embed_query(req.question)
    retrieved = hybrid.search(req.question, q_vec, top_k=5, where_filter=where_filter)

    memory_ctx = memory.get_context()
    augmented_question = f"{memory_ctx}\n\n当前问题：{req.question}" if memory_ctx else req.question

    gen = services["gen"]

    async def event_stream():
        full_answer = ""
        sources = []
        for event in gen.generate_stream(augmented_question, retrieved):
            if event["done"]:
                full_answer = event["answer"]
                sources = event["sources"]
                yield f"data: {json_module.dumps({'done': True, 'sources': sources}, ensure_ascii=False)}\n\n"
            else:
                yield f"data: {json_module.dumps({'token': event['token']}, ensure_ascii=False)}\n\n"

        # 更新记忆 + MQ
        memory.add_turn(req.question, full_answer)
        latency = (time.perf_counter() - t0) * 1000
        producer.send(req.question, full_answer, cache_hit=False, latency_ms=latency)
        producer.send_chat_history(session_id, "user", req.question)
        producer.send_chat_history(session_id, "assistant", full_answer)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── 文档上传 ──
@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    """上传工业文档入库"""
    # 保存到临时路径
    upload_dir = os.path.join(os.path.dirname(__file__), "..", "data", "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, file.filename)
    with open(file_path, "wb") as f:
        f.write(await file.read())

    # 加载 & 向量化 & 入库
    loader = DocumentLoader(data_dir=upload_dir)
    chunks = loader.load_all()
    emb_svc = services["emb_svc"]
    vectors = emb_svc.embed_documents([c.page_content for c in chunks])

    store = services["store"]
    # 追加到已有 collection
    existing_count = len(store.collection.get()["ids"])
    new_ids = [str(existing_count + i) for i in range(len(chunks))]
    new_metadatas = [
        {"source": c.metadata.get("source", ""),
         "page": c.metadata.get("page", 1),
         "heading_path": c.metadata.get("heading_path", ""),
         "chunk_type": c.metadata.get("chunk_type", "text")}
        for c in chunks
    ]
    store.collection.add(
        ids=new_ids,
        documents=[c.page_content for c in chunks],
        embeddings=vectors,
        metadatas=new_metadatas,
    )

    # 重建 BM25 索引
    new_chunk_dicts = [{"text": c.page_content, "metadata": m}
                       for c, m in zip(chunks, new_metadatas)]
    services["chunk_dicts"].extend(new_chunk_dicts)
    bm25 = BM25Retriever()
    bm25.build_index(services["chunk_dicts"])
    vr = VectorRetriever(store)
    vr.chunks = services["chunk_dicts"]
    services["hybrid"] = HybridRetriever(bm25, vr)

    return {"status": "ok", "added": len(chunks), "filename": file.filename}


# ── 健康检查 ──
@app.get("/health")
async def health():
    store = services.get("store")
    cache = services.get("cache")
    return {
        "status": "healthy",
        "chroma_chunks": len(store.collection.get()["ids"]) if store else 0,
        "cache": cache.stats() if cache else {},
    }
