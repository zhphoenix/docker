"""分 bucket 批量删除 MinIO 所有对象（流式分批，避免内存溢出）"""
import sys; sys.path.insert(0, '/app')
from tools.minio import minio_tool
from minio.deleteobjects import DeleteObject
from itertools import islice
import time

client = minio_tool.client
BATCH = 500  # 每批删除 500 个对象

buckets = client.list_buckets()
print(f"Found {len(buckets)} buckets\n")

total_deleted = 0
total_start = time.time()

for b in buckets:
    bucket_start = time.time()
    count = 0

    while True:
        # list_objects 返回 generator，用 islice 取一批
        batch = list(islice(client.list_objects(b.name, recursive=True), BATCH))
        if not batch:
            break

        delete_list = [DeleteObject(obj.object_name) for obj in batch]
        errors = list(client.remove_objects(b.name, delete_list))

        batch_count = len(batch) - len(errors)
        count += batch_count

        if count % 2000 < BATCH:
            print(f"    {b.name}: {count:,} deleted so far...")

        if errors:
            for e in errors[:2]:
                print(f"    ERR: {e.object_name[:50]} -> {e.message[:40]}")

    elapsed = time.time() - bucket_start
    total_deleted += count
    print(f"  {b.name:15s}: deleted {count:>6,} objects ({elapsed:.1f}s)")

total_elapsed = time.time() - total_start
print(f"\nTotal deleted: {total_deleted:,} objects in {total_elapsed:.1f}s")
