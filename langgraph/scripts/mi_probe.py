import asyncio, json
from tools.postgres import postgres_tool
from tools.qdrant import qdrant_tool

async def main():
    # 1. collections 表定义
    try:
        cols = await postgres_tool.query(
            "SELECT name, vector_size, distance, domain FROM collections ORDER BY name")
        print("PG collections:", json.dumps(cols, ensure_ascii=False), flush=True)
    except Exception as e:
        print("PG collections ERR", repr(e), flush=True)

    # 2. Qdrant 现有 collection 配置
    try:
        col_list = qdrant_tool.client.get_collections().collections
        for c in col_list:
            info = qdrant_tool.client.get_collection(c.name)
            print("Qdrant collection: name=%s params=%s points=%d" % (
                c.name,
                {"size": info.config.params.vectors.size,
                 "distance": str(info.config.params.vectors.distance),
                 "on_disk": info.config.params.vectors.on_disk},
                info.points_count), flush=True)
    except Exception as e:
        print("Qdrant ERR", repr(e), flush=True)

    # 3. documents 表结构（列）
    try:
        rows = await postgres_tool.query(
            "SELECT column_name, data_type FROM information_schema.columns WHERE table_name='documents' ORDER BY ordinal_position")
        print("documents columns:", json.dumps(rows, ensure_ascii=False), flush=True)
    except Exception as e:
        print("documents columns ERR", repr(e), flush=True)

asyncio.run(main())