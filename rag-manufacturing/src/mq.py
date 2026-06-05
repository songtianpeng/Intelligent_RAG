"""
消息队列 — 异步日志采集
Windows 开发用 asyncio.Queue 模拟 RocketMQ，代码结构一致
部署 Linux 时改 3 行切换到真实 RocketMQ
"""
import json
import asyncio
from datetime import datetime
from typing import Optional


# ── 模拟层：开发用 asyncio.Queue ──
_queue: Optional[asyncio.Queue] = None

def _get_queue() -> asyncio.Queue:
    """
    获取全局异步队列实例。
    采用懒加载（Lazy Initialization）方式：
    - 首次调用时创建 asyncio.Queue 实例；
    - 后续调用直接返回已创建的队列对象；
    - 确保整个应用共享同一个队列实例。
    Returns:
        asyncio.Queue: 全局异步队列对象，最大容量为1000。
    """
    global _queue
    if _queue is None:
        _queue = asyncio.Queue(maxsize=1000)
    return _queue


class QALogProducer:
    """
    问答日志生产者

    【面试话术——为什么用MQ解耦】
    日志写入 MySQL 是 IO 操作，同步写大概 10-50ms。
    每个问答都等日志写完再返回，用户多等 50ms 没有意义。
    MQ 异步解耦后，主流程只负责发一条消息（<1ms），
    日志消费者后台慢慢写 MySQL，不影响用户响应时间。

    【RocketMQ 对应关系】
    开发模拟            生产 RocketMQ
    ─────────          ──────────────
    asyncio.Queue       RocketMQ Topic: rag_qa_logs
    put_nowait()        Producer.send_sync()
    get()               Consumer.pull()
    """

    def send(self, question: str, answer: str, cache_hit: bool,
             latency_ms: float, token_count: int = 0):
        """发送日志消息（非阻塞）"""
        msg = json.dumps({
            "type": "qa_log",
            "question": question,
            "answer_preview": answer[:200],
            "cache_hit": cache_hit,
            "latency_ms": round(latency_ms, 2),
            "token_count": token_count,
            "timestamp": datetime.now().isoformat(),
        }, ensure_ascii=False)
        self._put(msg)

    def send_chat_history(self, session_id: str, role: str, content: str):
        """发送聊天记录持久化消息"""
        msg = json.dumps({
            "type": "chat_history",
            "session_id": session_id,
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        }, ensure_ascii=False)
        self._put(msg)

    def _put(self, msg: str):
        try:
            _get_queue().put_nowait(msg)
            # ★ 生产环境: RocketMQ Producer.send_sync()
        except asyncio.QueueFull:
            print("[MQ] 队列满，消息丢弃（不影响主流程）")


class QALogConsumer:
    """
    问答日志消费者
    后台协程运行，消费消息 → 写入 MySQL
    """
    def __init__(self, mysql_engine=None):
        """
        Args:
            mysql_engine: SQLAlchemy engine。传 None 则只打印
        """
        self.engine = mysql_engine

    async def run(self):
        """后台消费循环"""
        print("[MQ] 消费者启动...")
        # ★ 生产环境:
        # consumer = PushConsumer("qa_log_consumer")
        # consumer.set_namesrv_addr(settings.ROCKETMQ_NAMESRV)
        # consumer.subscribe(settings.ROCKETMQ_TOPIC, self._handle)
        # consumer.start()

        q = _get_queue()
        while True:
            try:
                msg = await asyncio.wait_for(q.get(), timeout=1.0) # 阻塞等待消息，1秒超时，循环检查
                await self._handle(msg) # 处理消息
            except asyncio.TimeoutError:
                continue

    async def _handle(self, msg_str: str):
        """处理一条消息（日志 或 聊天记录持久化）"""
        msg = json.loads(msg_str)
        msg_type = msg.get("type", "qa_log")

        if self.engine:
            # ★ 生产环境:
            # if msg_type == "chat_history":
            #     INSERT INTO chat_history (session_id, role, content, created_at)
            # elif msg_type == "qa_log":
            #     INSERT INTO qa_logs (...)
            pass
        else:
            # 开发环境: 只打印
            if msg_type == "chat_history":
                print(f"[MQ] 对话记忆已写入: session={msg['session_id'][:8]} "
                      f"role={msg['role']} content={msg['content'][:40]}...")
            else:
                print(f"[MQ] 日志写入: {msg['question'][:30]}... "
                      f"cache={msg['cache_hit']} latency={msg['latency_ms']}ms")


# ── 全局单例 ──
producer = QALogProducer()
consumer = QALogConsumer()
