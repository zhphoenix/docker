"""Node 1: Document Parser - 文档解析与分片

输入: raw_text
输出: chunks
"""

import logging

from tools.chunker import chunk_markdown
from config.policy_loader import get_policy

logger = logging.getLogger(__name__)


async def document_parser(state: dict) -> dict:
    """文档解析节点

    将原始文本分片为 chunks，供后续提取节点使用。
    大文档保护：超过 max_chunks_per_document 时截断。
    """
    raw_text = state.get("raw_text", "")
    errors = list(state.get("errors", []))

    if not raw_text or not raw_text.strip():
        errors.append("Parser: raw_text is empty")
        return {"chunks": [], "errors": errors}

    # 分片
    chunks = chunk_markdown(raw_text)

    # 大文档保护
    max_chunks = get_policy("knowledge.extraction.max_chunks_per_document", 200)
    if len(chunks) > max_chunks:
        logger.warning(
            "Document %s has %d chunks, truncating to %d",
            state.get("document_id", "?")[:8], len(chunks), max_chunks,
        )
        chunks = chunks[:max_chunks]
        errors.append(f"Parser: truncated from {len(chunks)} to {max_chunks} chunks")

    logger.info(
        "Parser: %d chars → %d chunks | doc=%s",
        len(raw_text), len(chunks), state.get("document_id", "?")[:8],
    )

    return {"chunks": chunks}
