"""文章摘要生成器

调用 LLM（OpenAI Compatible API）为单篇文章生成结构化摘要。
支持两种调用方式：
1. 独立使用（通过 httpx 直接调用 LLM API）
2. 在 LangGraph Agent 内使用（复用 tools.llm.llm_tool 单例）

用法:
    summarizer = ArticleSummarizer(llm_url="http://localhost:8080/v1/chat/completions")
    summary = await summarizer.summarize(title="...", markdown="...")
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# 摘要生成 Prompt
SUMMARY_SYSTEM_PROMPT = "你是一位专业的政策研究分析师，擅长提炼文章核心观点并生成结构化摘要。"

SUMMARY_USER_PROMPT = """请为以下文章生成结构化摘要。

要求：
1. 用中文输出
2. 格式：
   - **核心观点**：1-2 句话概括文章主旨
   - **主要论述**：3-5 个要点（用编号列表）
   - **政策信号**：如有明确政策导向或信号，简要指出（如无则省略此项）
3. 总长度不超过 {max_chars} 字
4. 客观准确，不添加原文没有的信息
5. 不要输出标题行，直接输出摘要内容

文章标题：{title}

文章正文：
{content}
"""


class ArticleSummarizer:
    """文章摘要生成器

    Args:
        llm_url: LLM API 地址（OpenAI Compatible /v1/chat/completions）
        model: 模型名称
        max_input_chars: 输入正文截断长度
        max_summary_chars: 摘要最大长度
        timeout: LLM 请求超时（秒）
    """

    def __init__(
        self,
        llm_url: str | None = None,
        model: str = "qwen3",
        max_input_chars: int = 6000,
        max_summary_chars: int = 500,
        timeout: float = 120.0,
    ):
        self.llm_url = llm_url or os.getenv(
            "LLM_BASE_URL", "http://localhost:8080/v1/chat/completions"
        )
        self.model = model
        self.max_input_chars = max_input_chars
        self.max_summary_chars = max_summary_chars
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """获取复用的 httpx 客户端"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                limits=httpx.Limits(max_connections=5, max_keepalive_connections=2),
            )
        return self._client

    async def summarize(self, title: str, markdown: str) -> str | None:
        """生成文章摘要

        Args:
            title: 文章标题
            markdown: 清洗后的 Markdown 正文

        Returns:
            摘要文本，失败返回 None
        """
        if not markdown or not markdown.strip():
            return None

        content = markdown[:self.max_input_chars]

        user_prompt = SUMMARY_USER_PROMPT.format(
            title=title or "未知标题",
            content=content,
            max_chars=self.max_summary_chars,
        )

        try:
            client = self._get_client()
            resp = await client.post(
                self.llm_url,
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 1024,
                    "stream": False,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            summary = data["choices"][0]["message"]["content"]
            logger.info(f"摘要生成成功: {title[:30]}... ({len(summary)} 字)")
            return summary

        except httpx.ConnectError:
            logger.error(f"LLM 服务不可达: {self.llm_url}")
            return None
        except Exception as e:
            logger.error(f"摘要生成失败: {title[:30]} -> {e}")
            return None

    async def summarize_with_llm_tool(self, title: str, markdown: str) -> str | None:
        """使用 LangGraph Agent 内的 llm_tool 单例生成摘要

        适用于在 Agent Skill 内部调用，复用已有连接池。

        Args:
            title: 文章标题
            markdown: 清洗后的 Markdown 正文

        Returns:
            摘要文本，失败返回 None
        """
        if not markdown or not markdown.strip():
            return None

        from tools.llm import llm_tool

        content = markdown[:self.max_input_chars]

        user_prompt = SUMMARY_USER_PROMPT.format(
            title=title or "未知标题",
            content=content,
            max_chars=self.max_summary_chars,
        )

        try:
            messages = [
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]
            result = await llm_tool.chat(messages, temperature=0.3, max_tokens=1024)
            summary = result["choices"][0]["message"]["content"]
            logger.info(f"摘要生成成功(llm_tool): {title[:30]}... ({len(summary)} 字)")
            return summary

        except Exception as e:
            logger.error(f"摘要生成失败(llm_tool): {title[:30]} -> {e}")
            return None

    async def close(self):
        """关闭 HTTP 客户端"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "ArticleSummarizer":
        """从 crawl4ai.yaml 的 summary 配置构建"""
        summary_cfg = config.get("summary", {})
        return cls(
            model=summary_cfg.get("model", "qwen3"),
            max_input_chars=summary_cfg.get("max_input_chars", 6000),
            max_summary_chars=summary_cfg.get("max_summary_chars", 500),
        )
