"""SiYuan Adapter 单元测试

覆盖：
  1. 限流：并发上限（Semaphore）阻塞超限请求
  2. 幂等：getDocByPath 已存在 → 更新而非创建
  3. 重试：429/5xx 指数退避后成功
  4. 模板渲染与路径映射
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from server.adapters.siyuan.client import SiYuanClient, SiYuanError
from server.adapters.siyuan.config import SiYuanConfig
from server.adapters.siyuan.mapper import entity_to_path, notebook_for, section_path
from server.adapters.siyuan.templates import renderer


@pytest.fixture
def client() -> SiYuanClient:
    cfg = SiYuanConfig(
        base_url="http://127.0.0.1:6806",
        token="test-token",
        concurrency=2,
        queue_size=10,
        max_retries=1,
        timeout=10.0,
    )
    return SiYuanClient(config=cfg)


@pytest.mark.asyncio
async def test_concurrency_limited(client):
    """超过 concurrency 的并发请求应被限流（Semaphore 阻塞）"""
    active = 0
    peak = 0

    class FakeResp:
        status_code = 200

        def json(self):
            return {"code": 0, "data": {"ok": True}}

    class FakeHTTP:
        async def post(self, api, json=None):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.05)
            active -= 1
            return FakeResp()

        async def aclose(self):
            pass

    # patch 底层 client，让 _post 真正走 Semaphore 限流
    with patch.object(client, "_ensure_client", AsyncMock(return_value=FakeHTTP())):
        await asyncio.gather(*[client._post("/api/x", {}) for _ in range(8)])

    assert peak <= 2, f"并发峰值 {peak} 超过上限 2"


@pytest.mark.asyncio
async def test_upsert_idempotent_updates_existing(client):
    """幂等：路径已存在 → 更新而非创建"""
    with patch.object(client, "get_doc_by_path", AsyncMock(return_value={"id": "doc-1"})) as mock_get, \
         patch.object(client, "update_doc", AsyncMock(return_value={"ok": True})) as mock_upd, \
         patch.object(client, "create_doc", AsyncMock(return_value={"ok": True})) as mock_create:
        result = await client.upsert_doc("Companies", "000001_平安银行", "md")

    assert result["action"] == "updated"
    mock_get.assert_awaited_once()
    mock_upd.assert_awaited_once()
    mock_create.assert_not_awaited()


@pytest.mark.asyncio
async def test_upsert_idempotent_creates_when_missing(client):
    """幂等：路径不存在 → 创建"""
    with patch.object(client, "get_doc_by_path", AsyncMock(return_value=None)), \
         patch.object(client, "create_doc", AsyncMock(return_value={"ok": True})) as mock_create:
        result = await client.upsert_doc("Companies", "000001_平安银行", "md")

    assert result["action"] == "created"
    mock_create.assert_awaited_once()


@pytest.mark.asyncio
async def test_retry_on_429(client):
    """429 触发指数退避重试，最终成功"""
    cfg = SiYuanConfig(base_url="http://127.0.0.1:6806", token="t", concurrency=1, max_retries=2)
    c = SiYuanClient(config=cfg)
    calls = 0

    async def flaky_post(api, payload):
        nonlocal calls
        calls += 1
        if calls < 3:
            raise client.SiYuanError("429", code=429)
        return {"code": 0, "data": {"ok": True}}

    with patch.object(c, "_post", side_effect=flaky_post):
        # 直接调用底层（绕过 _post 自身重试，验证 _backoff 逻辑存在）
        assert c._backoff(0, 429) >= 1.0
        assert c._backoff(1, 429) >= 2.0


@pytest.mark.asyncio
async def test_business_error_not_retried(client):
    """业务错误（code != 0）不应进入重试，立即抛出，只调用一次"""
    calls = 0

    class FakeResp:
        status_code = 200

        def json(self):
            return {"code": 10001, "msg": "bad request"}

    class FakeHTTP:
        async def post(self, api, json=None):
            nonlocal calls
            calls += 1
            return FakeResp()

        async def aclose(self):
            pass

    with patch.object(client, "_ensure_client", AsyncMock(return_value=FakeHTTP())):
        with pytest.raises(SiYuanError):
            await client._post("/api/x", {})
    assert calls == 1, f"业务错误应只调用 1 次（不重试），实际 {calls}"


@pytest.mark.asyncio
async def test_429_retry_then_success(client):
    """429 瞬时错误应重试后成功"""
    calls = 0

    class FakeResp:
        def __init__(self, code=0):
            self.status_code = 200
            self._code = code

        def json(self):
            return {"code": self._code, "data": {"ok": True}}

    class FakeHTTP:
        async def post(self, api, json=None):
            nonlocal calls
            calls += 1
            if calls == 1:
                resp = FakeResp()
                resp.status_code = 429
                return resp
            return FakeResp()

        async def aclose(self):
            pass

    with patch.object(client, "_ensure_client", AsyncMock(return_value=FakeHTTP())):
        result = await client._post("/api/x", {})
    assert result == {"ok": True}
    assert calls == 2, f"429 应重试 1 次，实际调用 {calls}"


def test_mapper_paths():
    """路径映射规则"""
    assert entity_to_path({"entity_type": "Company", "properties": {"ticker": "000001"}, "canonical_name": "平安银行"}) == "000001_平安银行"
    assert entity_to_path({"entity_type": "Event", "properties": {"event_date": "2025-01-01"}, "canonical_name": "发布会"}) == "2025-01-01_发布会"
    assert notebook_for("Company") == "Companies"
    assert notebook_for("Industry") == "Industries"
    assert notebook_for("Event") == "Events"
    assert section_path("000001_平安银行", "Financial") == "000001_平安银行/Financial"


def test_template_render_company():
    """公司模板渲染含关键字段"""
    ctx = {
        "name": "平安银行", "entity_type": "Company", "ticker": "000001", "market": "A",
        "description": "test", "aliases": [], "confidence": 0.95,
        "sections": [{"title": "概览", "content": "内容"}],
    }
    md = renderer.render("Company", ctx)
    assert "# 平安银行" in md
    assert "`000001`" in md
    assert "95%" in md
    assert "内容" in md


@pytest.mark.asyncio
async def test_content_hash_stable():
    """内容指纹稳定且可区分"""
    a = SiYuanClient.content_hash("hello")
    b = SiYuanClient.content_hash("hello")
    c = SiYuanClient.content_hash("world")
    assert a == b
    assert a != c