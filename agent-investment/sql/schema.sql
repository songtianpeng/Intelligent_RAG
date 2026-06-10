-- ============================================================
--  项目二：智能投研协同分析平台 — PostgreSQL 完整建表
--  执行: psql -U postgres -d postgres -f schema.sql
-- ============================================================

-- 1. 用户表
CREATE TABLE IF NOT EXISTS sys_user (
    id SERIAL PRIMARY KEY,
    username VARCHAR(64) NOT NULL UNIQUE,
    password_hash VARCHAR(256) NOT NULL,
    display_name VARCHAR(64),
    role VARCHAR(32) NOT NULL DEFAULT 'analyst',
    department VARCHAR(64),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 密码: 123456 → SHA256
-- 开发阶段直接用明文哈希，生产用 bcrypt
INSERT INTO sys_user (id, username, password_hash, display_name, role) VALUES
(1001, 'zhang', '8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92', '张分析师', 'analyst'),
(1002, 'li',    '8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92', '李审核员', 'reviewer'),
(1003, 'wang',  '8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92', '王管理员', 'admin')
ON CONFLICT (id) DO NOTHING;

-- 2. 流程实例表
CREATE TABLE IF NOT EXISTS workflow_instance (
    task_id VARCHAR(32) PRIMARY KEY,
    user_id INT NOT NULL,
    workflow_type VARCHAR(64),
    slots JSONB DEFAULT '{}',
    status VARCHAR(32) DEFAULT 'RUNNING',
    result TEXT,
    risk_decision VARCHAR(16),
    compliance_decision VARCHAR(16),
    feedback TEXT,
    approver VARCHAR(64),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 3. 聊天消息表
CREATE TABLE IF NOT EXISTS chat_message (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(32) NOT NULL,
    role VARCHAR(16) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_chat_session ON chat_message(session_id, created_at);
