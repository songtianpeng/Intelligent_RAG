"""测试：文档加载 → 向量化 → Milvus入库 → 检索"""
import os, sys
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, 'src')

from config import settings
from document_loader import DocumentLoader
from embedding import EmbeddingService
from vector_store import VectorStore


print("CWD:", os.getcwd())

print("\n【Step 1】加载文档...")
loader = DocumentLoader(data_dir="data")
chunks = loader.load_all()

if len(chunks) == 0:
    print("ERROR: 0 chunks loaded!")
    sys.exit(1)

print(f"\n【Step 2】向量化 + 写入Milvus ({len(chunks)} chunks)...")
emb_svc = EmbeddingService(api_key=settings.DASHSCOPE_API_KEY)
db_path = os.path.join(os.getcwd(), "milvus_data", "milvus.db")
os.makedirs(os.path.dirname(db_path), exist_ok=True)

store = VectorStore(db_path=db_path)
store.build(chunks, emb_svc)

print("\n【Step 3】检索测试: 'E03报警怎么办'")
q_vec = emb_svc.embed_query("E03报警怎么办")
results = store.search(q_vec, top_k=3)
for i, doc in enumerate(results):
    print(f"\n  Top-{i+1}:")
    print(f"    source: {doc.metadata.get('source', '?')}")
    print(f"    heading: {doc.metadata.get('heading_path', '?')[:80]}")
    print(f"    content: {doc.page_content[:120]}")
