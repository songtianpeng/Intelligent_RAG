"""
RocketMQ HTTP 桥接 — 部署在 Linux 上
启动: pip install fastapi uvicorn rocketmq-client-python
      python mq_bridge.py
Windows 通过 HTTP 请求这个桥，间接调 RocketMQ
"""
from fastapi import FastAPI
from pydantic import BaseModel
try:
    from rocketmq.client import Producer, Message as RmqMsg
    p = Producer("bridge_group")
    p.set_namesrv_addr("192.168.88.130:9876")
    p.start()
    print("[Bridge] RocketMQ Producer 就绪")
except Exception as e:
    print(f"[Bridge] RocketMQ 不可用: {e}")
    p = None

app = FastAPI()

class MqMessage(BaseModel):
    topic: str
    body: str

@app.post("/mq/send")
def send(msg: MqMessage):
    if p:
        m = RmqMsg(msg.topic)
        m.set_body(msg.body)
        p.send_sync(m)
        return {"ok": True, "backend": "rocketmq"}
    return {"ok": False, "backend": "disabled", "body_preview": msg.body[:100]}

@app.get("/health")
def health():
    return {"rocketmq": p is not None}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
