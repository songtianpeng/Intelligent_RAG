"""
启动入口 — python app.py → http://localhost:8000
首次启动需 1-2 分钟初始化 LLM 模型，请耐心等待控制台输出。
"""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import uvicorn
from src.config import settings

print("=" * 50)
print("智能投研协同分析平台 — 启动中...")
print("首次启动需要初始化 Planner/Risk/Compliance LLM Agent，约 1-2 分钟")
print("=" * 50)

if __name__ == "__main__":
    uvicorn.run(
        "src.api:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=False,
    )
