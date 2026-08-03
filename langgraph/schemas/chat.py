"""OpenAI Compatible API 请求/响应模型"""

from typing import Optional
from pydantic import BaseModel


# ===== Chat Message =====

class ChatMessage(BaseModel):
    role: str  # system / user / assistant
    content: str


# ===== Chat Request =====

class ChatRequest(BaseModel):
    model: str = "qwen3"
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float = 0.7
    max_tokens: int = 4096
    stop: Optional[list[str]] = None


# ===== Chat Response (non-streaming) =====

class UsageInfo(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"


class ChatResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatChoice]
    usage: UsageInfo


# ===== Stream Response =====

class StreamDelta(BaseModel):
    role: Optional[str] = None
    content: Optional[str] = None


class StreamChoice(BaseModel):
    index: int = 0
    delta: StreamDelta
    finish_reason: Optional[str] = None


class StreamChunk(BaseModel):
    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: list[StreamChoice]


# ===== Error Response =====

class ErrorDetail(BaseModel):
    message: str
    type: str
    param: Optional[str] = None
    code: Optional[str] = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


# ===== Models Response =====

class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int = 0
    owned_by: str = "local"


class ModelsResponse(BaseModel):
    object: str = "list"
    data: list[ModelInfo]
