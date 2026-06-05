"""
启动入口
python app.py → http://localhost:8000/docs
"""
import sys, os
# 确保 src/ 在 Python 路径中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import asyncio
import uvicorn
from config import settings

if __name__ == "__main__":
    uvicorn.run(
        "api:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=True,           # 代码改动自动重启
        reload_dirs=["src"],   # 只监控 src 目录
    )
