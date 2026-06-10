"""
用户认证 — PostgreSQL 持久化

密码: SHA256 哈希（开发用，生产切 bcrypt）
"""
import hashlib
import uuid
from typing import Optional
import psycopg2
from config import settings


def _hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def _get_conn():
    # 不用 URL（密码含特殊字符），直接用参数
    return psycopg2.connect(
        host=settings.PG_HOST, port=settings.PG_PORT,
        user=settings.PG_USER, password=settings.PG_PASSWORD,
        dbname=settings.PG_DATABASE,
    )


def login(username: str, password: str) -> Optional[dict]:
    """
    用户名密码登录 → 查 PG → 返回用户信息 + token
    """
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, display_name, role FROM sys_user "
            "WHERE username=%s AND password_hash=%s AND is_active=TRUE",
            (username, _hash(password))
        )
        row = cur.fetchone()
        cur.close(); conn.close()

        if row:
            return {
                "user_id": row[0],
                "name": row[1],
                "role": row[2],
                "token": uuid.uuid4().hex[:16],
            }
    except Exception as e:
        print(f"[Auth] PG查询失败: {e}")
    return None


def get_user_by_id(user_id: int) -> Optional[dict]:
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("SELECT id, display_name, role FROM sys_user WHERE id=%s", (user_id,))
        row = cur.fetchone()
        cur.close(); conn.close()
        if row:
            return {"user_id": row[0], "name": row[1], "role": row[2]}
    except Exception as e:
        print(f"[Auth] PG查询失败: {e}")
    return None


# 内存 session 表（token → user_info）
_sessions: dict = {}


def get_session(token: str) -> Optional[dict]:
    return _sessions.get(token)


def set_session(token: str, user: dict):
    _sessions[token] = user
