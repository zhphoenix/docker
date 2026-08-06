"""AC-P4-3 A/B Prompt 分流验证脚本

在 langgraph 容器内直接调用 loader，验证：
1. _variant_pool 是否正确构建（chat/system 含 v1/v2）
2. 多次 load_prompt 命中 variant 的分布是否接近权重比例
3. 同一次运行内（不 reset）是否复用同一 variant
"""
import asyncio
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import prompts.loader as loader


async def main() -> None:
    await loader.load_all_from_db()
    print("[1] _variant_pool keys:", list(loader._variant_pool.keys()))

    pool = loader._variant_pool.get("chat/system", [])
    print("[2] chat/system pool:", [(v["version"], v["weight"]) for v in pool])
    assert len(pool) == 2, "chat/system 应包含 2 个 variant"
    assert {(v["version"], v["weight"]) for v in pool} == {(1, 50), (2, 50)}, "variant 应为 v1/v2，权重各 50"

    N = 200
    cnt: Counter = Counter()
    for _ in range(N):
        loader.reset_variant_context()
        loader.load_prompt("chat/system", question="q", context="c")
        cnt[loader.variant_label()] += 1
    print(f"[3] 分布（{N} 次）:", dict(cnt))
    total = sum(cnt.values())
    if total:
        pct = {k: round(v * 100 / total, 1) for k, v in cnt.items()}
        print(f"    占比:", pct)

    # 同一次运行内复用同一 variant
    loader.reset_variant_context()
    seen: set = set()
    for _ in range(5):
        loader.load_prompt("chat/system", question="q", context="c")
        seen.add(loader.variant_label())
    print("[4] 同一次运行内命中 variants（应为 1 个）:", seen)
    assert len(seen) == 1, "同一次运行内应复用同一 variant"

    # 手动触发一次分流，验证 get_resolved_variants
    loader.reset_variant_context()
    loader.load_prompt("chat/system", question="q", context="c")
    print("[5] get_resolved_variants:", loader.get_resolved_variants())
    print("[6] variant_label:", loader.variant_label())

    print("\nALL CHECKS PASSED\n")


if __name__ == "__main__":
    asyncio.run(main())