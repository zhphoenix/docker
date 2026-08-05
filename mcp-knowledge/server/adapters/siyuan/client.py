"""SiYuan HTTP API 客户端

封装 SiYuan 文档/笔记本 CRUD，内置：
  - 限流：asyncio.Semaphore 控制并发 + 队列背压
  - 幂等：upsert（按路径存在则更新，否则创建）
  - 重试：指数退避 + 抖动（429 / 5xx / 网络错误）

参考 SiYuan HTTP API（b3log/siyuan -> /api/...）：
  - /api/filetree/createDocWithMd
  - /api/filetree/getIDsByHPath（按 HPath 查询文档 id，幂等判断）
  - /api/filetree/removeDocByID
  - /api/notebook/lsNotebooks / createNotebook

注意：本 SiYuan 版本已移除 getDocByPath / updateDoc 可用 API（getDocByPath 未注册、
updateDoc 返回空且不生效），且 createDocWithMd 不幂等（同路径重复创建）。
因此：按路径查询用 getIDsByHPath；更新采用 removeDocByID + createDocWithMd 重建，
保证幂等且不产生重复。文档 id 随重建变化，但 SiYuan 块引用 [[标题]] 按标题解析，
关系图不受影响。
"""

import asyncio
import hashlib
import logging
import random
import time
from typing import Any

import httpx

from server.adapters.siyuan.config import get_siyuan_config

logger = logging.getLogger(__name__)

# 需要重试的错误码：限流 / 服务端瞬时错误
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class SiYuanError(Exception):
    """SiYuan API 调用错误"""

    def __init__(
        self,
        message: str,
        code: int | None = None,
        payload: Any = None,
        retryable: bool = False,
    ):
        super().__init__(message)
        self.code = code
        self.payload = payload
        # 仅瞬时错误（429/5xx）可重试；业务错误 / 4xx 不可重试
        self.retryable = retryable


class SiYuanClient:
    """SiYuan HTTP 客户端（限流 + 幂等 + 重试）"""

    def __init__(self, config=None, concurrency: int | None = None):
        cfg = config or get_siyuan_config()
        self._cfg = cfg
        self._base_url = cfg.base_url
        self._sem = asyncio.Semaphore(concurrency or cfg.concurrency)
        self._client: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()

    # ──────────────────────────────
    # 生命周期
    # ──────────────────────────────
    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            async with self._lock:
                if self._client is None:
                    self._client = httpx.AsyncClient(
                        base_url=self._base_url,
                        headers=self._cfg.headers,
                        timeout=self._cfg.timeout,
                    )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # ──────────────────────────────
    # 底层请求（限流 + 重试）
    # ──────────────────────────────
    async def _post(self, api: str, payload: dict, retries: int | None = None) -> dict:
        """POST /api/...，带限流与指数退避重试"""
        client = await self._ensure_client()
        max_retries = retries or self._cfg.max_retries
        async with self._sem:  # 限流：并发上限
            attempt = 0
            while True:
                try:
                    resp = await client.post(api, json=payload)
                    if resp.status_code in _RETRYABLE_STATUS:
                        raise SiYuanError(
                            f"SiYuan {api} transient HTTP {resp.status_code}",
                            code=resp.status_code,
                            retryable=True,
                        )
                    if resp.status_code >= 400:
                        raise SiYuanError(
                            f"SiYuan {api} failed HTTP {resp.status_code}: {resp.text[:300]}",
                            code=resp.status_code,
                        )
                    data = resp.json()
                    if data.get("code") not in (0, None):
                        raise SiYuanError(
                            f"SiYuan {api} business error: {data.get('msg', data)}",
                            code=data.get("code"),
                            payload=data,
                        )
                    return data.get("data") or {}
                except (httpx.HTTPError, SiYuanError) as e:
                    # 业务错误 / 4xx 不可重试，直接抛出
                    if isinstance(e, SiYuanError) and not e.retryable:
                        raise
                    if attempt >= max_retries:
                        raise SiYuanError(f"SiYuan {api} failed after retries: {e}") from e
                    delay = self._backoff(attempt, status_code=getattr(e, "code", None))
                    logger.warning(
                        "SiYuan %s retry %d/%d in %.2fs: %s",
                        api, attempt + 1, max_retries, delay, e,
                    )
                    attempt += 1
                    await asyncio.sleep(delay)

    @staticmethod
    def _backoff(attempt: int, status_code: int | None = None) -> float:
        """指数退避 + 抖动：1, 2, 4, 8...；429 额外加长"""
        base = 2 ** attempt
        if status_code == 429:
            base *= 2
        return base + random.uniform(0, 0.5)

    # ──────────────────────────────
    # 笔记本（Notebook）
    # ──────────────────────────────
    async def list_notebooks(self) -> list[dict]:
        """列出全部笔记本 [{id, name}]"""
        data = await self._post("/api/notebook/lsNotebooks", {})
        return data.get("notebooks", []) or []

    async def get_notebook_id(self, name: str) -> str | None:
        """按名称查找笔记本 id（幂等）"""
        for nb in await self.list_notebooks():
            if nb.get("name") == name:
                return nb.get("id")
        return None

    async def ensure_notebook(self, name: str) -> str:
        """确保笔记本存在，不存在则创建，返回（惰性）id"""
        existing = await self.get_notebook_id(name)
        if existing:
            return existing
        data = await self._post("/api/notebook/createNotebook", {"name": name})
        return data.get("id") or data.get("box") or ""

    # ──────────────────────────────
    # 文档（Doc）— 幂等 upsert
    # ──────────────────────────────
    async def get_doc_ids_by_hpath(self, notebook: str, path: str) -> list[str]:
        """按人类可读路径（HPath）查询文档 id 列表。

        返回可能包含历史重复文档（此前 createDocWithMd 重复创建所致），
        upsert 时会一并清理并重建。

        注意：getIDsByHPath 要求 HPath 带前导斜杠（如 /Indian_government），
        而 entity_to_path 返回无斜杠路径（如 Indian_government），此处归一化。
        """
        hpath = path if path.startswith("/") else "/" + path
        data = await self._post("/api/filetree/getIDsByHPath", {"notebook": notebook, "path": hpath})
        return data or []

    async def create_doc(self, notebook: str, path: str, markdown: str) -> dict:
        """创建文档（createDocWithMd）"""
        return await self._post(
            "/api/filetree/createDocWithMd",
            {"notebook": notebook, "path": path, "markdown": markdown},
        )

    async def remove_doc_by_id(self, doc_id: str) -> dict:
        """按 id 删除文档（removeDocByID）"""
        return await self._post("/api/filetree/removeDocByID", {"id": doc_id})

    async def upsert_doc(self, notebook: str, path: str, markdown: str) -> dict:
        """幂等写入文档：路径已存在则重建，否则创建。

        说明：该 SiYuan 版本无 updateDoc 可用 API（updateDoc 返回空且不生效），
        且 createDocWithMd 不幂等（同路径重复创建）。因此采用 getIDsByHPath 查出
        已存在文档（含历史重复）→ removeDocByID 清理 → createDocWithMd 重建，
        保证"路径存在则更新、不存在则创建"且不产生重复。文档 id 随重建变化，
        但 SiYuan 块引用 [[标题]] 按标题解析，关系图不受影响。

        notebook 参数为笔记本名称（如 "Companies"），内部先解析为笔记本 id。

        返回 {action: 'created'|'updated', id, path}
        """
        box_id = await self.ensure_notebook(notebook)
        existing_ids = await self.get_doc_ids_by_hpath(box_id, path)
        for doc_id in existing_ids:
            await self.remove_doc_by_id(doc_id)
        await self.create_doc(box_id, path, markdown)
        return {"action": "updated" if existing_ids else "created", "id": "", "path": path}

    # ──────────────────────────────
    # 工具
    # ──────────────────────────────
    @staticmethod
    def content_hash(markdown: str) -> str:
        """内容指纹（用于幂等去重判断）"""
        return hashlib.sha256(markdown.encode("utf-8")).hexdigest()

    @staticmethod
    def is_available_url(url: str) -> bool:
        """判断是否已配置可用的 SiYuan 服务地址（非空即视为已接入）"""
        return bool(url and url.strip())


# 模块级单例
siyuan_client = SiYuanClient()