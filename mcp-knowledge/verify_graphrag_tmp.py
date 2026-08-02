import asyncio, json
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def run(s, name, args):
    try:
        res = await s.call_tool(name, args)
        print(f"=== {name}({json.dumps(args, ensure_ascii=False)}) ===")
        for c in res.content:
            t = getattr(c, "text", None)
            if t is not None:
                try:
                    print(json.dumps(json.loads(t), ensure_ascii=False, indent=2)[:4000])
                except Exception:
                    print(t[:4000])
    except Exception as e:
        print(f"=== {name} FAILED: {e} ===")


async def main():
    async with streamable_http_client("http://localhost:8200/mcp") as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            # 1. 带锚定实体（有丰富图关系）
            await run(s, "graphrag_search", {"query": "Donald Trump 与哪些实体有关联，主要关系是什么？", "entity_name": "Donald Trump", "limit": 8})
            # 2. 无锚定实体（仅向量检索 → 应降级）
            await run(s, "graphrag_search", {"query": "Waymo 与 Uber 是什么关系？", "limit": 6})


asyncio.run(main())