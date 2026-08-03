import asyncio
import sys
import traceback

async def main():
    print("== code load check ==", flush=True)
    try:
        from pipelines.document_pipeline import doc_pipeline  # noqa
        print("import doc_pipeline: OK", flush=True)
    except Exception:
        print("IMPORT FAIL", flush=True)
        traceback.print_exc()
        return

    try:
        from api.knowledge import MinioIngestRequest, router  # noqa
        print("import api.knowledge: OK", flush=True)
    except Exception:
        print("API IMPORT FAIL", flush=True)
        traceback.print_exc()
        return

    # 正则匹配测试
    tests = [
        "cn/000002/annual_report/2024/report.pdf",
        "hk/00005/annual_report/2023/report.pdf",
        "us/AAPL/annual_report/2024/report.md",
        "cn/000002/quarterly_report/2024q1/report.pdf",
        "website/foo/annual_report/2024/report.pdf",
    ]
    print("\n== regex tests ==", flush=True)
    re_obj = doc_pipeline._ANNUAL_REPORT_RE
    for t in tests:
        m = re_obj.match(t)
        if m:
            print(f"MATCH   {t} -> {m.group('market')}/{m.group('symbol')}/year={m.group('year')}", flush=True)
        else:
            print(f"NO-MATCH {t}", flush=True)

asyncio.run(main())