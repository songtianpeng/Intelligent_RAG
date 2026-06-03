"""
配置管理模块
单一配置源：所有环境变量从这里读取，其他模块从这里导入
"""
import os
from dotenv import load_dotenv

# 加载 .env 文件到环境变量
load_dotenv()


class Settings:
    """全局配置单例"""

    # ===== DashScope =====
    DASHSCOPE_API_KEY: str = os.getenv("DASHSCOPE_API_KEY", "")

    # ===== MySQL =====
    MYSQL_HOST: str = os.getenv("MYSQL_HOST", "127.0.0.1")
    MYSQL_PORT: int = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER: str = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD: str = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DATABASE: str = os.getenv("MYSQL_DATABASE", "rag_manufacturing")

    # ===== Redis =====
    REDIS_HOST: str = os.getenv("REDIS_HOST", "127.0.0.1")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))

    # ===== RocketMQ =====
    ROCKETMQ_NAMESRV: str = os.getenv("ROCKETMQ_NAMESRV", "127.0.0.1:9876")
    ROCKETMQ_TOPIC: str = os.getenv("ROCKETMQ_TOPIC", "rag_qa_logs")
    ROCKETMQ_GROUP: str = os.getenv("ROCKETMQ_GROUP", "rag_consumer_group")

    # ===== Milvus =====
    MILVUS_DB_PATH: str = os.getenv("MILVUS_DB_PATH", "./milvus_data/milvus.db")

    # ===== 服务 =====
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))

    # ===== 数据库连接URL（SQLAlchemy用）=====
    @property
    def mysql_url(self) -> str:
        return (
            f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
            f"?charset=utf8mb4"
        )

    # ===== Redis连接URL =====
    @property
    def redis_url(self) -> str:
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


# 全局单例，其他模块直接 from config import settings 使用
settings = Settings()
