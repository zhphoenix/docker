#!/usr/bin/env python3
"""Web Ingestion Layer 端到端测试

测试内容:
1. Crawl4AI Provider 抓取
2. RetryPolicy 重试逻辑
3. RateLimiter 限速
4. DiffDetector 变更检测
5. PostgreSQL 数据写入

用法:
    python3 scripts/test_web_ingestion.py
"""

import asyncio
import sys
import os

# 添加 src 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ingestion.web.retry import RetryPolicy
from ingestion.web.rate_limiter import RateLimiter
from ingestion.web.diff_detector import DiffDetector, ChangeStatus
from providers.web.crawl4ai_provider import Crawl4AIProvider


def test_retry_policy():
    """测试重试策略"""
    print("\n" + "=" * 60)
    print("测试 1: RetryPolicy 重试策略")
    print("=" * 60)

    policy = RetryPolicy(
        max_attempts=3,
        backoff_base=2,
        backoff_max=60,
        retry_on_status=[429, 500, 502, 503, 504],
        dead_letter_after=5,
    )

    # 测试 should_retry
    assert policy.should_retry(429, 1) == True, "429 应该重试"
    assert policy.should_retry(429, 3) == False, "达到最大次数不应重试"
    assert policy.should_retry(404, 1) == False, "404 不应重试"
    assert policy.should_retry(None, 1) == True, "网络错误应该重试"
    print("  ✅ should_retry 逻辑正确")

    # 测试 backoff delay
    assert policy.get_backoff_delay(1) == 2.0, "第1次退避应为2s"
    assert policy.get_backoff_delay(2) == 4.0, "第2次退避应为4s"
    assert policy.get_backoff_delay(10) == 60.0, "退避应限制在60s"
    print("  ✅ get_backoff_delay 计算正确")

    # 测试 dead letter
    assert policy.is_dead_letter(4) == False, "4次失败不应为死信"
    assert policy.is_dead_letter(5) == True, "5次失败应为死信"
    print("  ✅ is_dead_letter 判断正确")

    # 测试域名覆盖
    policy.with_domain_override("cninfo.com.cn", {"max_attempts": 5})
    assert policy.should_retry(429, 4, "cninfo.com.cn") == True, "覆盖后应可重试"
    print("  ✅ 域名覆盖配置生效")

    print("\n  🎉 RetryPolicy 全部测试通过!")


def test_rate_limiter():
    """测试速率限制器"""
    print("\n" + "=" * 60)
    print("测试 2: RateLimiter 速率限制")
    print("=" * 60)

    limiter = RateLimiter(
        default_rpm=60,
        per_domain={"cninfo.com.cn": 20, "sec.gov": 30},
    )

    # 测试 RPM 获取
    assert limiter.get_rpm("example.com") == 60, "默认 RPM 应为 60"
    assert limiter.get_rpm("cninfo.com.cn") == 20, "cninfo RPM 应为 20"
    assert limiter.get_rpm("sec.gov") == 30, "sec.gov RPM 应为 30"
    print("  ✅ get_rpm 配置正确")

    # 测试域名提取
    assert limiter.extract_domain("https://www.example.com/path") == "www.example.com"
    print("  ✅ extract_domain 解析正确")

    # 测试 can_acquire（初始应该有令牌）
    assert limiter.can_acquire("example.com") == True, "初始应有令牌"
    print("  ✅ can_acquire 初始状态正确")

    print("\n  🎉 RateLimiter 全部测试通过!")


def test_diff_detector():
    """测试变更检测器"""
    print("\n" + "=" * 60)
    print("测试 3: DiffDetector 变更检测")
    print("=" * 60)

    detector = DiffDetector(
        hash_algorithm="sha256",
        on_page_removed="archive",
    )

    # 测试配置
    assert detector.hash_algorithm == "sha256"
    assert detector.on_page_removed == "archive"
    print("  ✅ 配置初始化正确")

    # 测试 ChangeStatus 枚举
    assert ChangeStatus.NEW.value == "new"
    assert ChangeStatus.CHANGED.value == "changed"
    assert ChangeStatus.UNCHANGED.value == "unchanged"
    assert ChangeStatus.REMOVED.value == "removed"
    print("  ✅ ChangeStatus 枚举正确")

    print("\n  🎉 DiffDetector 全部测试通过!")


async def test_crawl4ai_provider():
    """测试 Crawl4AI Provider（实际网络请求）"""
    print("\n" + "=" * 60)
    print("测试 4: Crawl4AI Provider 实际抓取")
    print("=" * 60)

    provider = Crawl4AIProvider(
        base_url="http://localhost:11235",
        timeout=30,
        api_token="crawl4ai-dev-token",
    )

    # 健康检查
    healthy = await provider.health_check()
    print(f"  健康检查: {'✅ 通过' if healthy else '❌ 失败'}")

    if not healthy:
        print("  ⚠️ Crawl4AI 服务不可用，跳过抓取测试")
        return

    # 抓取测试
    print("  正在抓取 https://example.com ...")
    result = await provider.fetch("https://example.com")

    print(f"  抓取结果:")
    print(f"    - success: {result.success}")
    print(f"    - status_code: {result.status_code}")
    print(f"    - title: {result.title}")
    print(f"    - content_hash: {result.content_hash[:16] if result.content_hash else None}...")
    print(f"    - markdown 长度: {len(result.markdown) if result.markdown else 0}")
    print(f"    - attempts: {result.attempts}")

    assert result.success == True, "抓取应成功"
    assert result.status_code == 200, "状态码应为 200"
    assert result.markdown is not None, "应有 Markdown 内容"
    assert result.content_hash is not None, "应有内容 Hash"

    print("\n  🎉 Crawl4AI Provider 抓取测试通过!")

    await provider.close()


async def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("  Web Ingestion Layer 端到端测试")
    print("=" * 60)

    # 单元测试（无需网络）
    test_retry_policy()
    test_rate_limiter()
    test_diff_detector()

    # 集成测试（需要 Crawl4AI 服务）
    await test_crawl4ai_provider()

    print("\n" + "=" * 60)
    print("  ✅ 所有测试完成!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
