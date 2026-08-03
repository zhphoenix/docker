"""DocumentState 定义 - 文档处理流程（Document Graph）的数据载体

注意：不含 messages 字段（非对话型流程，是处理流水线）。
实际处理逻辑委托 pipelines/document_pipeline.py 执行，
本 State 仅承载编排所需的输入与阶段标记。
"""

from typing import TypedDict, Any


class DocumentState(TypedDict, total=False):
    """文档处理流水线状态"""

    # 输入：来自 PostgreSQL documents 表的单条文档记录
    document: dict
    # 关联的 task_queue 任务 ID（可选）
    task_id: str
    # 在批次中的序号（用于日志）
    index: int

    # 处理阶段标记: pending → parsing → chunking → embedding → done / failed
    stage: str
    # 处理结果（doc_pipeline 返回的状态字符串）
    result: Any
    # 失败原因
    error: str

    # 运行元信息
    metadata: dict
