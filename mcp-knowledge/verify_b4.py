"""通过真实 MCP 协议（Streamable HTTP）验证 B4 新工具实际调用。"""
import asyncio
import json

from mcp import ClientSession, StdioServerParameters
from mcp.client.streamable_http import streamable_http_client


async def main():
    async with streamable_http_client("http://localhost:8200/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 1. 列出工具，确认新工具是否注册
            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            new_tools = ["query_company_relationship", "find_related_companies", "graphrag_search"]
            print("=== TOOLS REGISTERED ===")
            print("graph tools present:", {n: (n in names) for n in new_tools})

            # 2. 找出库中存在的公司，用真实数据调用
            entities = await session.call_tool("search_entity", {"query": "台积电", "limit": 3})
            print("\n=== search_entity(台积电) ===")
            _print(entities)

            # 3. query_company_relationship: 台积电 -> 苹果
            res = await session.call_tool(
                "query_company_relationship", {"source": "台积电", "target": "苹果", "max_depth": 4}
            )
            print("\n=== query_company_relationship(台积电->苹果) ===")
            _print(res)

            # 4. find_related_companies
            res = await session.call_tool(
                "find_related_companies", {"entity": "台积电", "depth": 2, "limit": 20}
            )
            print("\n=== find_related_companies(台积电) ===")
            _print(res)

            # 5. graphrag_search
            res = await session.call_tool(
                "graphrag_search", {"query": "台积电的主要客户有哪些？", "entity_name": "台积电", "limit": 8}
            )
            print("\n=== graphrag_search ===")
            _print(res)


def _print(result):
    for content in result.content:
        txt = getattr(content, "text", None)
        if txt is not None:
            try:
                data = json.loads(txt)
                print(json.dumps(data, ensure_ascii=False, indent=2)[:2500])
            except Exception:
                print(txt[:2500])


if __name__ == "__main__":
    asyncio.run(main())