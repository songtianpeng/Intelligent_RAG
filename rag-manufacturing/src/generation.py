"""
LLM 答案生成 — RAG 的最后一环
"""
from typing import List, Dict
from dashscope import Generation


class AnswerGenerator:
    """
    RAG 生成器

    【原理】
    1. 把检索到的 chunk 内容拼成"参考资料"
    2. 构造 Prompt：系统提示 + 参考资料 + 用户问题
    3. 调用 LLM 生成答案
    4. 从 chunk 的 metadata 中提取来源，附在答案末尾

    【Prompt 设计要点】
    - System Prompt 限定角色和行为（"你是注塑机运维专家"）
    - 明确指令："参考资料中没有的信息请明确说不知道"
    - 要求引用来源：防止 LLM 凭空编造（幻觉）
    """

    SYSTEM_PROMPT = """你是一个专业的注塑机设备运维专家，同时具备严谨的信息筛选和答案生成能力。
    ## 你的任务
    根据提供的参考资料回答用户问题。参考资料可能有多段，但并非全部相关。

    ## 信息筛选规则（重要）
    1. **优先使用直接回答问题的资料**：包含用户提到的故障码、参数名称、操作步骤的资料优先级最高
    2. **区分"直接相关"和"同类但不同"**：
       - 用户问"E03报警"→ 含"E03 电机过载"的资料是直接相关
       - 用户问"E03报警"→ 含"E08 编码器信号丢失"的只是同类故障或者是其它故障码，不能当正确答案
    3. **忽略以下资料**：
       - 仅含文档标题或目录、无实质内容的（如仅"注塑机操作手册"几字）
       - 与问题完全不相关的内容
    4. **如果没有任何资料能回答问题或者你也没有把握的**，明确说"参考资料中未找到相关信息"，不要编造内容

    ## 回答格式
    - 步骤类问题用编号列表
    - 智能识别有的参考资料是不是表格，如果是表格，返回表格的形式
    - 故障处理类先说明原因再给解决方案
    - 引用具体参数值或参考资料时注明出处（如"根据操作手册，额定值为..."）"""

    def __init__(self, api_key: str, model: str = "qwen-plus"):
        self.api_key = api_key
        self.model = model

    def generate(self, question: str, chunks: List[Dict]) -> Dict:
        """
        根据检索结果生成答案

        Args:
            question: 用户问题
            chunks: 检索到的 chunk 列表，每个 {"text": ..., "metadata": {...}}

        Returns:
            {"answer": "回答内容", "sources": ["来源1", "来源2"]}
        """
        # 1. 拼参考资料（每个 chunk 编号）
        context_parts = []
        for i, chunk in enumerate(chunks):
            context_parts.append(f"[参考资料{i+1}]\n{chunk['text']}")
        context = "\n\n".join(context_parts)

        # 2. 构造完整 messages
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": f"参考资料：\n\n{context}\n\n用户问题：{question}"},
        ]

        # 3. 调用 LLM
        resp = Generation.call(
            model=self.model,
            messages=messages,
            api_key=self.api_key,
            result_format="message",
        )

        if resp.status_code != 200:
            return {"answer": f"生成失败：{resp.message}", "sources": []}

        answer = resp.output.choices[0].message.content

        # 4. 提取来源（去重，只保留实际用到的 chunk）
        sources = []
        seen = set()
        for chunk in chunks:
            src = chunk["metadata"].get("source", "未知")
            page = chunk["metadata"].get("page", "?")
            heading = chunk["metadata"].get("heading_path", "")
            key = f"{src}#{page}章节{heading}"
            if key not in seen:
                seen.add(key)
                if heading:
                    sources.append(f"{src} 第{page}页（{heading}）")
                else:
                    sources.append(f"{src} 第{page}页")

        return {"answer": answer, "sources": sources}


if __name__ == "__main__":
    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from config import settings
    from document_loader import DocumentLoader
    from embedding import EmbeddingService
    from vector_store import VectorStore

    # —— 建库（跟之前一样） ——
    print("加载文档 + 建库...")
    # loader = DocumentLoader(data_dir="data")
    # chunks = loader.load_all()
    emb_svc = EmbeddingService(api_key=settings.DASHSCOPE_API_KEY)
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "chroma_data"))
    store = VectorStore(db_path=db_path)
    # store.build(chunks, emb_svc)

    # —— 问答 ——
    gen = AnswerGenerator(api_key=settings.DASHSCOPE_API_KEY,model="qwen-plus")
    questions = [
        "E03报警怎么办？",
        "注塑机开机前需要检查什么？",
    ]
    for q in questions:
        print(f"\n{'='*50}")
        print(f"问题：{q}")
        q_vec = emb_svc.embed_query(q)
        retrieved = store.search(q_vec, top_k=3)
        result = gen.generate(q, retrieved)
        print(f"\n回答：\n{result['answer']}")
        print(f"\n来源：")
        for s in result["sources"]:
            print(f"  📎 {s}")
