"""
环境连通性检查脚本
运行方式：python check_env.py
"""
import sys
from pathlib import Path

# sys.path.insert(0, "../src")
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config import settings

import pymysql
import redis
import socket
import dashscope
import os
from pymilvus import MilvusClient


def check_mysql():
    """检查MySQL连接"""
    print("[MySQL] 检查连接...", end=" ")
    try:
        conn = pymysql.connect(
            host=settings.MYSQL_HOST,
            port=settings.MYSQL_PORT,
            user=settings.MYSQL_USER,
            password=settings.MYSQL_PASSWORD,
            database=settings.MYSQL_DATABASE,
            charset="utf8mb4",
        )
        conn.ping()
        conn.close()
        print("[OK] 连接成功")
        return True
    except Exception as e:
        print(f"[FAIL] 失败: {e}")
        return False


def check_redis():
    """检查Redis连接"""
    print("[Redis] 检查连接...", end=" ")
    try:

        r = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD or None,
            db=settings.REDIS_DB,
            socket_connect_timeout=5,
        )
        r.ping()
        r.close()
        print("[OK] 连接成功")
        return True
    except Exception as e:
        print(f"[FAIL] 失败: {e}")
        return False


def check_rocketmq():
    """检查RocketMQ NameServer连通性（TCP端口）"""
    print("[RocketMQ] 检查NameServer...", end=" ")
    try:
        host, port = settings.ROCKETMQ_NAMESRV.rsplit(":", 1)
        port = int(port)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((host, port))
        sock.close()
        if result == 0:
            print(f"[OK] NameServer可达（{host}:{port}）")
            return True
        else:
            print(f"[FAIL] 端口不可达（{host}:{port}，错误码{result}）")
            return False
    except Exception as e:
        print(f"[FAIL] 失败: {e}")
        return False


def check_dashscope():
    """检查DashScope API Key"""
    print("[DashScope] 检查API Key...", end=" ")
    try:
        # 简单验证: 用embedding接口测一下连通性
        resp = dashscope.TextEmbedding.call(
            model="text-embedding-v3",
            input="测试",
            api_key=settings.DASHSCOPE_API_KEY,
        )
        if resp.status_code == 200:
            print("[OK] API Key有效")
            return True
        else:
            print(f"[FAIL] API返回错误: {resp.message}")
            return False
    except Exception as e:
        print(f"[FAIL] 失败: {e}")
        return False


def check_milvus():
    """检查Milvus Lite"""
    print("[Milvus] 检查初始化...", end=" ")
    try:
        dirname = os.path.dirname(settings.MILVUS_DB_PATH)
        os.makedirs(dirname, exist_ok=True)
        client = MilvusClient(settings.MILVUS_DB_PATH)
        # 列出collections验证可用
        collections = client.list_collections()
        print(f"[OK] Milvus就绪（已有{len(collections)}个Collection）")
        client.close()
        return True
    except Exception as e:
        print(f"[FAIL] 失败: {e}")
        return False


if __name__ == "__main__":
    print("=" * 50)
    print("环境连通性检查")
    print("=" * 50)

    results = {
        "MySQL": check_mysql(),
        "Redis": check_redis(),
        "RocketMQ": check_rocketmq(),
        "DashScope": check_dashscope(),
        "Milvus": check_milvus(),
    }

    print("\n" + "=" * 50)
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"结果: {passed}/{total} 项通过")

    for name, ok in results.items():
        print(f"  {'[OK]' if ok else '[FAIL]'} {name}")

    if passed < total:
        print(f"\n[WARN]  {total - passed} 项未通过，请检查对应服务")
        sys.exit(1)
    else:
        print("\n[OK] 所有服务连接正常！")
