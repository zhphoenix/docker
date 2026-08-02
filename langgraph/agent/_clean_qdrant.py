import asyncio

from tools.qdrant import qdrant_tool
from qdrant_client.models import Filter, FieldCondition, MatchValue

async def main():
    # 用户已授权：删除 Qdrant documents_cn / documents_hk 中孤立向量（保留 collection 配置）
    for col, market in [("documents_cn", "cn"), ("documents_hk", "hk")]:
        before = (await asyncio.to_thread(
            qdrant_tool.client.get_collection, col)).points_count
        print(f"[{col}] before points={before}", flush=True)
        # 用 filter 删除该 collection 全部点
        await asyncio.to_thread(
            qdrant_tool.client.delete_points,
            collection_name=col,
            points_selector=Filter(
                must=[FieldCondition(key="market", match=MatchValue(value=market))]
            ),
        )
        # 部分 payload 可能没有 market 字段，补充删除：用 scroll-only 全删兜底
        # 这里用 delete_collection+重建 410 分析：为保证 collection 配置(2560/Cosine)不变，
        # 直接重建会丢失配置，故用 scroll 删除所有点
        from qdrant_client.models import PointIdsList
        # 逐批 scroll 删除
        next_offset = None
        deleted = 0
        while True:
            rows, next_offset = await asyncio.to_thread(
                qdrant_tool.client.scroll,
                collection_name=col,
                limit=2000,
                offset=next_offset,
                with_payload=False,
                with_vectors=False,
            )
            if not rows:
                break
            ids = [p.id for p in rows]
            await asyncio.to_thread(
                qdrant_tool.client.delete_points,
                collection_name=col,
                points_selector=PointIdsList(points=ids),
            )
            deleted += len(ids)
            if next_offset is None:
                break
        after = (await asyncio.to_thread(
            qdrant_tool.client.get_collection, col)).points_count
        print(f"[{col}] scroll-deleted={deleted} | after points={after}", flush=True)

asyncio.run(main())