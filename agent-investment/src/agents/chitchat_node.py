"""
闲聊节点 — 简单 LLM 回复，不调用工具，不走流程
"""
from langchain_community.chat_models import ChatTongyi
from langchain_core.messages import HumanMessage


CHITCHAT_PROMPT = """你是一个金融投研平台的友好助手。
用简洁亲切的语气回复用户的问候或闲聊。
如果用户问你能做什么，告诉对方你可以:
- 查询投资标的数据（基本面、估值、舆情）
- 检索金融政策法规
- 发起投研审批流程（股票/债券/授信）"""


class ChitchatNode:
    """闲聊回复节点"""

    def __init__(self, api_key: str, model: str = "qwen-turbo"):
        self.llm = ChatTongyi(
            model=model,
            dashscope_api_key=api_key,
            temperature=0.7,  # 闲聊可以高一点，有变化
        )

    def __call__(self, state: dict) -> dict:
        question = state["messages"][-1]["content"]

        resp = self.llm.invoke([
            HumanMessage(content=f"{CHITCHAT_PROMPT}\n\n用户消息: {question}"),
        ])

        return {
            "final_report": resp.content,
            "messages": [{"role": "assistant", "content": resp.content}],
        }


# ── 测试 ──
if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from config import settings

    node = ChitchatNode(api_key=settings.DASHSCOPE_API_KEY)

    for q in ["你好", "你能做什么"]:
        state = {"messages": [{"role": "user", "content": q}]}
        result = node(state)
        print(f"\n用户: {q}")
        # 去除emoji避免GBK报错
        import re
        clean = re.sub(r'[^一-鿿　-〿＀-￯a-zA-Z0-9\s,.!?;:()（）""''、。，！？；：（）《》【】…—\-\+]', '', result['final_report'])
        print(f"回复: {clean[:200]}")
