"""
消息队列 — 异步日志采集 + 聊天记录持久化

【面试话术】
日志写入和聊天记录持久化是IO操作，同步写阻塞主流程。
MQ异步解耦后主流程只发一条消息（<1ms），消费者后台慢慢写MySQL。

【部署切换】
开发(Win): 模拟层 = asyncio.Queue  |  逻辑与 RocketMQ 完全等价
生产(Linux): 注释掉模拟层 _put()，启用 _put_rocketmq()

三个 Topic:
  invest_task_exec     → 流程任务异步执行
  invest_audit_log     → Agent节点执行记录 (workflow_trace表)
  invest_chat_persist  → 聊天记录持久化 (chat_message表)
"""
import json
import asyncio
from datetime import datetime
from typing import Optional

from config import settings

# ═══════════════════════════════════════════════════
#  RocketMQ 生产层（部署 Linux 时启用）
#
#  依赖安装:
#    pip install rocketmq-client-python==2.0.0
#
#  导入:
#    from rocketmq.client import Producer, PushConsumer, Message as RmqMessage
#
#  启动前确认:
#    1. Linux 服务器能 ping 通 RocketMQ NameServer (192.168.88.130:9876)
#    2. RocketMQ Console 里预先创建好三个 Topic
#    3. Producer/Consumer Group 名不要跟其他服务冲突
#
#  取消下面整段注释即可切换到真实 RocketMQ：
# ═══════════════════════════════════════════════════
# from rocketmq.client import Producer, PushConsumer, Message as RmqMessage
#
# # --- Producer ---
# _rmq_producer = Producer("invest_producer_group")
# _rmq_producer.set_namesrv_addr(settings.ROCKETMQ_NAMESRV)
# _rmq_producer.start()
#
#
# def _put_rocketmq(topic: str, body: str):
#     """RocketMQ 真实发送 — 替代 _put_simulated()"""
#     msg = RmqMessage(topic)
#     msg.set_body(body)
#     _rmq_producer.send_sync(msg)      # 同步发送，保证投递不丢
#
#
# # --- Consumer (Push模式，Broker推消息过来) ---
# _rmq_consumer = PushConsumer("invest_consumer_group")
# _rmq_consumer.set_namesrv_addr(settings.ROCKETMQ_NAMESRV)
#
# def _on_task_received(msg):
#     """invest_task_exec 回调 → 启动 LangGraph 异步执行"""
#     data = json.loads(msg.body)
#     # await execute_workflow_async(data["task_id"], data["workflow_type"], data["slots"])
#
# def _on_audit_log_received(msg):
#     """invest_audit_log 回调 → 批量 INSERT workflow_trace"""
#     data = json.loads(msg.body)
#     # INSERT INTO workflow_trace (trace_id, node_name, latency_ms, token_used)
#
# def _on_chat_history_received(msg):
#     """invest_chat_persist 回调 → 批量 INSERT chat_message"""
#     data = json.loads(msg.body)
#     # INSERT INTO chat_message (session_id, role, content, created_at)
#
# _rmq_consumer.subscribe(settings.ROCKETMQ_TASK_TOPIC, _on_task_received)
# _rmq_consumer.subscribe(settings.ROCKETMQ_LOG_TOPIC, _on_audit_log_received)
# _rmq_consumer.subscribe(settings.ROCKETMQ_CHAT_TOPIC, _on_chat_history_received)
# _rmq_consumer.start()
# ═══════════════════════════════════════════════════


# ═══════════════════════════════════════════
#  模拟层 — 开发用 asyncio.Queue
#  接口与 RocketMQ 完全一致：Topic + JSON Body
# ═══════════════════════════════════════════
_queue: Optional[asyncio.Queue] = None

def _get_queue() -> asyncio.Queue:
    global _queue
    if _queue is None:
        _queue = asyncio.Queue(maxsize=1000)
    return _queue

def _put_simulated(topic: str, body: str):
    """asyncio.Queue 模拟 — 替代 _put_rocketmq()"""
    try:
        _get_queue().put_nowait(body)
    except asyncio.QueueFull:
        pass


class MessageProducer:
    """
    消息生产者

    【RocketMQ 等价关系】
    Topic  → RocketMQ Topic (在 Console 里预先创建)
    Body   → 消息体 (JSON)
    _put() → Producer.send_sync() (同步发送，保证投递)
    """

    def send_task(self, task_id: str, workflow_type: str,
                  slots: dict, user_id: int):
        """Topic=invest_task_exec | Worker消费→启动LangGraph异步执行"""
        body = json.dumps({
            "type": "execute_workflow",
            "task_id": task_id,
            "workflow_type": workflow_type,
            "slots": slots,
            "user_id": user_id,
            "timestamp": datetime.now().isoformat(),
        }, ensure_ascii=False)
        self._send(settings.ROCKETMQ_TASK_TOPIC, body)

    def send_audit_log(self, trace_id: str, node_name: str,
                       latency_ms: float, token_used: int = 0):
        """Topic=invest_audit_log | Consumer批量INSERT→workflow_trace"""
        body = json.dumps({
            "type": "node_trace",
            "trace_id": trace_id,
            "node_name": node_name,
            "latency_ms": round(latency_ms, 2),
            "token_used": token_used,
            "timestamp": datetime.now().isoformat(),
        }, ensure_ascii=False)
        self._send(settings.ROCKETMQ_LOG_TOPIC, body)

    def send_chat_history(self, session_id: str, role: str, content: str):
        """Topic=invest_chat_persist | Consumer批量INSERT→chat_message"""
        body = json.dumps({
            "type": "chat_message",
            "session_id": session_id,
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        }, ensure_ascii=False)
        self._send(settings.ROCKETMQ_CHAT_TOPIC, body)

    def _send(self, topic: str, body: str):
        """
        发送入口 — 开发/生产自动切换

        开发: _put_simulated() → asyncio.Queue
        生产: _put_rocketmq()  → RocketMQ Broker → Consumer → MySQL
        """
        _put_simulated(topic, body)
        # ★ 部署 Linux 后改: _put_rocketmq(topic, body)


# ═══════════════════════════════════════════
#  Consumer
# ═══════════════════════════════════════════
class MessageConsumer:
    """
    消息消费者

    【RocketMQ 等价关系】
    开发: asyncio.Queue.get() 循环消费
    生产: PushConsumer.subscribe(topic, callback)

    部署 Linux 后改为:
      consumer = PushConsumer("invest_consumer_group")
      consumer.set_namesrv_addr(settings.ROCKETMQ_NAMESRV)
      consumer.subscribe("invest_task_exec", handle_workflow_task)
      consumer.subscribe("invest_audit_log", handle_audit_log)
      consumer.subscribe("invest_chat_persist", handle_chat_persist)
      consumer.start()
    """

    async def run(self):
        """消费循环 — asyncio.Queue 模拟"""
        print("[MQ] Consumer 已启动 (asyncio.Queue 模拟 RocketMQ)")
        q = _get_queue()
        while True:
            try:
                msg_str = await asyncio.wait_for(q.get(), timeout=1.0)
                data = json.loads(msg_str)
                await self._handle(data)
            except asyncio.TimeoutError:
                continue

    async def _handle(self, data: dict):
        """
        消息处理 — 模拟 MySQL 写入

        ★ 生产环境: 根据 type 分发到不同 Consumer 回调
        - chat_message  → INSERT INTO chat_message (session_id, role, content, created_at)
        - node_trace    → INSERT INTO workflow_trace (trace_id, node_name, latency_ms, token_used)
        - execute_workflow → 后台 Worker 启动 LangGraph 异步执行审批
        """
        msg_type = data.get("type", "")
        if msg_type == "chat_message":
            print(f"[MQ→MySQL] chat_message: [{data['role']}] "
                  f"{data['content'][:50]}...")
        elif msg_type == "node_trace":
            print(f"[MQ→MySQL] trace: [{data['node_name']}] "
                  f"{data['latency_ms']}ms | tokens={data.get('token_used', 0)}")
        elif msg_type == "execute_workflow":
            print(f"[MQ→Worker] 异步任务: {data['task_id']} | "
                  f"type={data['workflow_type']} | user={data['user_id']}")
            # ★ 生产: 这里启动 LangGraph 审批子图
            # await execute_workflow_async(
            #     task_id=data["task_id"],
            #     workflow_type=data["workflow_type"],
            #     slots=data["slots"],
            # )
        else:
            print(f"[MQ] 未知类型: {msg_type}")


producer = MessageProducer()
consumer = MessageConsumer()
