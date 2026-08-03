"""Document Graph - 文档处理流程（LangGraph 编排层）

流程: process → END

说明:
  实际的文档处理逻辑（MinIO PDF → Docling 解析 → Chunk → Embedding → Qdrant → PostgreSQL）
  已在 pipelines/document_pipeline.py 的 doc_pipeline 中成熟实现。
  本 Graph 不重复造轮子，仅作为统一的 LangGraph 编排入口，
  将单个文档的处理委托给 doc_pipeline，使文档处理与其他工作流
  保持一致的 Graph 调用方式，便于未来扩展多节点编排（如并行、重试）。
"""

import logging

from langgraph.graph import StateGraph, START, END

from state.document_state import DocumentState

logger = logging.getLogger(__name__)


async def process(state: DocumentState) -> dict:
    """处理单个文档（委托 doc_pipeline）"""
    from pipelines.document_pipeline import doc_pipeline

    document = state.get("document") or {}
    task_id = state.get("task_id")
    index = state.get("index", 0)

    doc_id = document.get("id", "?")
    logger.info("DocumentGraph: processing doc=%s task=%s index=%d", doc_id, task_id, index)

    try:
        result = await doc_pipeline._process_single_document(document, task_id=task_id, index=index)
        return {"stage": "done", "result": result}
    except Exception as e:
        logger.error("DocumentGraph: doc=%s failed: %s", doc_id, e, exc_info=True)
        return {"stage": "failed", "error": str(e)}


def build_document_graph():
    """构建 Document Graph

    START → process → END
    """
    graph = StateGraph(DocumentState)
    graph.add_node("process", process)
    graph.add_edge(START, "process")
    graph.add_edge("process", END)
    return graph.compile()
