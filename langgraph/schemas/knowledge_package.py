"""Knowledge Package 契约模型 - 文档知识抽取的交换格式

DP-A1 定义 Package JSON Schema，包含：
  Package Metadata / Source Metadata / Entities / Relations / Facts / Events /
  Embeddings(引用) / Evidence / Confidence / Processing Metadata / Version(含 history)。

采用 pydantic v2 模型，与
  AI-Platform-System-Design/schemas/ai_platform/knowledge_package.schema.json
字段一一对应（JSON Schema 为手工维护的 draft-07 静态文件）。

该模型是 Document Pipeline 产出的统一交换格式：
  - 上层（生产侧）构造 KnowledgePackage 实例
  - payload 以 JSONB 存入 knowledge_packages 表
  - 消费侧（KOC Inbox）按 status=draft/published 轮询消费
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PackageStatus(str, Enum):
    """Package 生命周期状态（与 knowledge_packages.status 枚举一致）"""

    DRAFT = "draft"
    PUBLISHED = "published"
    CONSUMED = "consumed"
    FAILED = "failed"


class SourceType(str, Enum):
    """源文档类型"""

    ANNUAL_REPORT = "annual_report"
    NEWS = "news"
    WEB = "web"
    GENERAL = "general"


class Confidence(BaseModel):
    """置信度：得分 + 支撑证据数量 + 产出模型"""

    score: float = Field(description="置信度得分 0-1")
    evidence_count: int = Field(default=0, description="支撑证据数量")
    model: str | None = Field(default=None, description="产出该置信度的模型")


class SourceMetadata(BaseModel):
    """源文档元信息"""

    source_type: SourceType = Field(description="源类型")
    source_id: str = Field(description="数据源标识（如 providers.yaml 的 id）")
    document_id: str | None = Field(default=None, description="document.documents.id")
    title: str | None = Field(default=None, description="文档标题")
    url: str | None = Field(default=None, description="来源 URL")
    file_path: str | None = Field(default=None, description="本地文件路径")
    hash: str | None = Field(default=None, description="文件 SHA256 哈希")
    publish_time: datetime | None = Field(default=None, description="原文发布时间")


class Entity(BaseModel):
    """实体（对应 core.entities）"""

    id: str = Field(description="实体 UUID")
    name: str = Field(description="实体名称")
    entity_type: str = Field(description="实体类型（company/person/org/...）")
    aliases: list[str] = Field(default_factory=list, description="别名")
    properties: dict[str, Any] = Field(default_factory=dict, description="扩展属性")
    canonical_name: str | None = Field(default=None, description="规范名")
    confidence: Confidence | float | None = Field(default=None, description="置信度")


class Relation(BaseModel):
    """实体关系（对应 core.relations）"""

    id: str = Field(description="关系 UUID")
    source_entity: str = Field(description="源实体 ID")
    target_entity: str = Field(description="目标实体 ID")
    relation_type: str = Field(description="关系类型")
    properties: dict[str, Any] = Field(default_factory=dict, description="扩展属性")
    confidence: Confidence | float | None = Field(default=None, description="置信度")


class Fact(BaseModel):
    """事实（对应 core.facts）"""

    id: str = Field(description="事实 UUID")
    subject_entity: str = Field(description="主体实体 ID")
    predicate: str = Field(description="谓词")
    object_value: Any = Field(description="宾语值（标量或 JSON）")
    unit: str | None = Field(default=None, description="数值单位")
    time_start: datetime | None = Field(default=None, description="有效起始时间")
    time_end: datetime | None = Field(default=None, description="有效结束时间")
    source_document: str | None = Field(default=None, description="来源文档 ID")
    confidence: Confidence | float | None = Field(default=None, description="置信度")


class Event(BaseModel):
    """事件（对应 core.events）"""

    id: str = Field(description="事件 UUID")
    name: str = Field(description="事件名称")
    event_type: str | None = Field(default=None, description="事件类型")
    start_time: datetime | None = Field(default=None, description="开始时间")
    end_time: datetime | None = Field(default=None, description="结束时间")
    entities: list[str] = Field(default_factory=list, description="关联实体 ID 列表")
    properties: dict[str, Any] = Field(default_factory=dict, description="扩展属性")
    confidence: Confidence | float | None = Field(default=None, description="置信度")


class Evidence(BaseModel):
    """证据（对应 core.evidence）"""

    id: str = Field(description="证据 UUID")
    fact_id: str | None = Field(default=None, description="关联事实 ID")
    document_id: str | None = Field(default=None, description="来源文档 ID")
    location: str | None = Field(default=None, description="证据位置（页码/段落）")
    quote: str | None = Field(default=None, description="原文引用")
    confidence: float | None = Field(default=None, description="证据置信度")


class EmbeddingRef(BaseModel):
    """Embedding 引用（不内嵌向量，仅引用向量存储中的 ID）"""

    entity_id: str | None = Field(default=None, description="实体 ID")
    chunk_id: str | None = Field(default=None, description="分片 ID")
    vector_id: str | None = Field(default=None, description="向量存储中的 ID")
    model: str | None = Field(default=None, description="Embedding 模型")
    dimension: int | None = Field(default=None, description="向量维度")


class ProcessingStage(BaseModel):
    """处理阶段记录"""

    stage: str = Field(description="阶段名（Acquire/Parse/Chunk/Extraction/...）")
    status: str = Field(description="阶段状态（pending/running/success/failed）")
    started_at: datetime | None = Field(default=None, description="开始时间")
    finished_at: datetime | None = Field(default=None, description="结束时间")
    duration_ms: int | None = Field(default=None, description="耗时（毫秒）")


class ProcessingMetadata(BaseModel):
    """处理元信息（DP-B4：parser/ocr/embedding/llm/routing/processing_time 全部落库）"""

    parser: str | None = Field(default=None, description="解析器名（如 docling）")
    parser_version: str | None = Field(default=None, description="解析器版本")
    chunk_strategy: str | None = Field(default=None, description="切块策略")
    embedding_model: str | None = Field(default=None, description="Embedding 模型")
    embedding_version: str | None = Field(default=None, description="Embedding 版本")
    routing_strategy: str | None = Field(default=None, description="路由策略（annual_report/general）")
    llm_model: str | None = Field(default=None, description="LLM 模型")
    ocr_engine: str | None = Field(default=None, description="OCR 引擎（如 paddleocr）")
    processing_time: float | None = Field(default=None, description="处理耗时（秒）")
    stages: list[ProcessingStage] = Field(default_factory=list, description="阶段记录")


class PackageVersion(BaseModel):
    """版本记录（支持 Rollback/Diff）"""

    version: int = Field(description="版本号（从 1 递增）")
    status: PackageStatus = Field(description="该版本状态")
    created_at: datetime = Field(default_factory=_utcnow, description="版本创建时间")
    change_note: str | None = Field(default=None, description="变更说明")


class KnowledgePackage(BaseModel):
    """Document Pipeline 产出的知识包（顶层契约）

    与 knowledge_packages 表 payload JSONB 对应。
    payload 存 KnowledgePackage 的完整序列化结果；
    processing_metadata 另列冗余存储以支持按处理信息索引。
    """

    id: str = Field(description="Package 全局唯一 ID")
    package_version: int = Field(default=1, description="Package 版本号（从 1 递增）")
    schema_version: str = Field(default="1.0", description="契约 schema 版本（预留演进）")
    source_type: SourceType = Field(description="源文档类型")
    document_id: str | None = Field(default=None, description="关联文档 ID")
    status: PackageStatus = Field(default=PackageStatus.DRAFT, description="Package 状态")
    source: SourceMetadata = Field(description="源元信息")
    entities: list[Entity] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    embeddings: list[EmbeddingRef] = Field(default_factory=list)
    processing_metadata: ProcessingMetadata = Field(default_factory=ProcessingMetadata)
    history: list[PackageVersion] = Field(default_factory=list, description="版本历史")
    created_at: datetime = Field(default_factory=_utcnow, description="创建时间")
    updated_at: datetime = Field(default_factory=_utcnow, description="更新时间")