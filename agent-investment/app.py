"""
启动入口
python app.py → http://localhost:8000
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import uvicorn
from src.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "src.api:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=True,
    )
