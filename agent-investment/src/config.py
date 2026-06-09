"""
配置管理模块 — 项目二：智能投研协同分析平台
"""
import os
from dotenv import load_dotenv # 从 python-dotenv 库中导入 load_dotenv 函数

load_dotenv() # Python 项目中加载环境变量的标准写法，通常配合 .env 文件使用


class Settings:
    """全局配置单例"""

    # ===== DashScope =====
    DASHSCOPE_API_KEY: str = os.getenv("DASHSCOPE_API_KEY", "")

    # ===== MySQL =====
    MYSQL_HOST: str = os.getenv("MYSQL_HOST", "127.0.0.1")
    MYSQL_PORT: int = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER: str = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD: str = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DATABASE: str = os.getenv("MYSQL_DATABASE", "agent_investment")

    # ===== Redis =====
    REDIS_HOST: str = os.getenv("REDIS_HOST", "127.0.0.1")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))

    # ===== RocketMQ =====
    ROCKETMQ_NAMESRV: str = os.getenv("ROCKETMQ_NAMESRV", "127.0.0.1:9876")
    ROCKETMQ_TASK_TOPIC: str = os.getenv("ROCKETMQ_TASK_TOPIC", "invest_task_exec")
    ROCKETMQ_LOG_TOPIC: str = os.getenv("ROCKETMQ_LOG_TOPIC", "invest_audit_log")
    ROCKETMQ_CHAT_TOPIC: str = os.getenv("ROCKETMQ_CHAT_TOPIC", "invest_chat_persist")

    # ===== Java 服务 =====
    JAVA_SERVICE_URL: str = os.getenv("JAVA_SERVICE_URL", "http://127.0.0.1:8080")

    # ===== ChromaDB (政策文档RAG) =====
    CHROMA_DB_PATH: str = os.getenv("CHROMA_DB_PATH", "./chroma_policies")

    # ===== 模型配置 =====
    PLANNER_MODEL: str = "qwen-turbo"       # Planner用轻量模型，快
    AGENT_MODEL: str = "qwen-plus"          # 审批Agent用推理模型，准

    # ===== 服务 =====
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))

    # ===== 数据库连接URL =====
    @property
    def mysql_url(self) -> str:
        return (f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
                f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
                f"?charset=utf8mb4")

    @property
    def redis_url(self) -> str:
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


settings = Settings()

# ── 测试 ──
if __name__ == "__main__":
    print("=" * 50)
    print("配置检查")
    print("=" * 50)
    print(f"DashScope Key:   {settings.DASHSCOPE_API_KEY[:10]}...")
    print(f"MySQL:           {settings.MYSQL_HOST}:{settings.MYSQL_PORT}/{settings.MYSQL_DATABASE}")
    print(f"Redis:           {settings.REDIS_HOST}:{settings.REDIS_PORT}")
    print(f"RocketMQ NS:     {settings.ROCKETMQ_NAMESRV}")
    print(f"Java Service:    {settings.JAVA_SERVICE_URL}")
    print(f"Planner Model:   {settings.PLANNER_MODEL}")
    print(f"Agent Model:     {settings.AGENT_MODEL}")
    print(f"MySQL URL:       {settings.mysql_url}")
    print(f"Redis URL:       {settings.redis_url}")
    print("\n[OK] 配置加载成功")
