import asyncio
import traceback
import re

from tools.minio import minio_tool
from tools.qdrant import qdrant_tool

_ANNUAL_REPORT_RE = re.compile(
    r"^(?P<market>[^/]+)/(?P<symbol>[^/]+)/annual_report/(?P<year>\d{4})/report\.(pdf|md)$"
)

async def main():
    # 1) 统计 MinIO 各 market 的 report 对象
    print("== MinIO report objects summary ==", flush=True)
    try:
        all_keys = await minio_tool.list_objects("documents", "")
        print(f"total objects under documents: {len(all_keys)}", flush=True)
        by_market = {"cn": 0, "hk": 0, "us": 0, "other": 0}
        matched = {"cn": [], "hk": [], "us": []}
        unmatched = 0
        for k in all_keys:
            m = _ANNUAL_REPORT_RE.match(k)
            if m:
                mk = m.group("market")
                by_market[mk] = by_market.get(mk, 0) + 1
                if mk in matched:
                    matched[mk].append(k)
            else:
                unmatched += 1
        print("by_market(map annual report objects):", by_market, flush=True)
        print("unmatched objects:", unmatched, flush=True)
        for mk, keys in matched.items():
            years = sorted({k.split('/annual_report/')[1].split('/')[0] for k in keys})
            print(f"  {mk}: {len(keys)} annual reports | years={years[:20]}", flush=True)
    except Exception:
        print("MINIO LIST FAIL", flush=True)
        traceback.print_exc()

    # 2) 确认 Qdrant collection 当前 state
    print("\n== Qdrant collections state ==", flush=True)
    try:
        cols = await asyncio.to_thread(qdrant_tool.client.get_collections)
        for c in cols.collections:
            info = await asyncio.to_thread(qdrant_tool.client.get_collection, c.name)
            print(
                f"  {c.name}: points={info.points_count} "
                f"vector_size={info.config.params.vectors.size} "
                f"distance={info.config.params.vectors.distance}",
                flush=True,
            )
    except Exception:
        print("QDRANT STATE FAIL", flush=True)
        traceback.print_exc()

asyncio.run(main())