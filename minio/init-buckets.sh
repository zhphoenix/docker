#!/bin/sh
# MinIO Bucket 初始化脚本
# 基于 24_数据底座规范.md 第二章 + DLM（新闻数据生命周期管理）总体原则
# 在 MinIO 服务就绪后运行
#
# Bucket 定位（DLM 数据分层）:
#   documents   - MD 源文件（年报/公告解析后），长期保存
#   knowledge   - 报告文件（Research Agent 输出），永久保存
#   news-raw    - 新闻原始 HTML/JSON，90-180 天自动清理
#   news-images - 新闻图片，90 天
#   artifacts   - Agent 输出（markdown/ppt），长期保存
#   staging     - 临时处理，30 天自动清理
#   datasets    - 结构化数据集（TuShare/AKShare），长期保存

set -e

# 等待 MinIO 健康检查通过
echo "Waiting for MinIO to be ready..."
until curl -sf http://minio:9000/minio/health/live > /dev/null 2>&1; do
  sleep 2
done
echo "MinIO is ready."

# 配置 alias（使用环境变量）
mc alias set local http://minio:9000 "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}"

# ===== 创建 Buckets =====
echo "Creating buckets..."
mc mb local/documents --ignore-existing
mc mb local/knowledge  --ignore-existing
mc mb local/datasets   --ignore-existing
mc mb local/artifacts  --ignore-existing
mc mb local/staging    --ignore-existing
mc mb local/news-raw   --ignore-existing
mc mb local/news-images --ignore-existing

# ===== 版本控制 =====
echo "Enabling versioning..."
mc version enable local/documents
mc version enable local/knowledge
mc version enable local/artifacts

# ===== 生命周期策略 =====
# staging: 临时处理目录，30天自动清理
mc ilm rule add --expire-days 30 local/staging 2>/dev/null || true

# news-raw: 新闻原始文件，90天自动清理（已处理后无需长期保留）
mc ilm rule add --expire-days 90 local/news-raw 2>/dev/null || true

# ===== 创建目录结构 =====
echo "Creating directory structure..."

# documents: {market}/{symbol}/{doc_type}/{year}/
for market in cn hk us; do
  mc cp --recursive /dev/null local/documents/${market}/ 2>/dev/null || true
done
# A股示例目录
mc cp --recursive /dev/null local/documents/cn/600519/annual_report/2025/ 2>/dev/null || true
mc cp --recursive /dev/null local/documents/cn/600519/annual_report/2024/ 2>/dev/null || true
mc cp --recursive /dev/null local/documents/cn/600519/announcement/2025/ 2>/dev/null || true
mc cp --recursive /dev/null local/documents/cn/600519/news/ 2>/dev/null || true
mc cp --recursive /dev/null local/documents/cn/600519/research/ 2>/dev/null || true
mc cp --recursive /dev/null local/documents/cn/600519/prospectus/ 2>/dev/null || true
# 港股示例
mc cp --recursive /dev/null local/documents/hk/00700/annual_report/2025/ 2>/dev/null || true
# 美股示例
mc cp --recursive /dev/null local/documents/us/aapl/annual_report/2025/ 2>/dev/null || true

# knowledge: {market}/{symbol}/{doc_type}/{year}/
for market in cn hk us; do
  mc cp --recursive /dev/null local/knowledge/${market}/ 2>/dev/null || true
done
mc cp --recursive /dev/null local/knowledge/cn/600519/annual_report/2025/ 2>/dev/null || true
mc cp --recursive /dev/null local/knowledge/hk/00700/annual_report/2025/ 2>/dev/null || true
mc cp --recursive /dev/null local/knowledge/us/aapl/annual_report/2025/ 2>/dev/null || true

# datasets: {source}/
for source in tushare akshare wind macro industry; do
  mc cp --recursive /dev/null local/datasets/${source}/ 2>/dev/null || true
done

# artifacts: {type}/
for type in research markdown pdf ppt; do
  mc cp --recursive /dev/null local/artifacts/${type}/ 2>/dev/null || true
done

# staging: {status}/
for status in download ocr chunk tmp retry; do
  mc cp --recursive /dev/null local/staging/${status}/ 2>/dev/null || true
done

# news-raw: {year}/{month}/{day}/
mc cp --recursive /dev/null local/news-raw/2026/08/ 2>/dev/null || true

# news-images: {year}/{month}/
mc cp --recursive /dev/null local/news-images/2026/08/ 2>/dev/null || true

echo "Bucket initialization complete."
echo ""
echo "  documents   - MD源文件（年报/公告解析后），长期保存（版本控制已启用）"
echo "  knowledge   - 报告文件（Research Agent输出），永久保存（版本控制已启用）"
echo "  datasets    - 结构化数据集（TuShare/AKShare），长期保存"
echo "  artifacts   - Agent输出（markdown/ppt），长期保存（版本控制已启用）"
echo "  staging     - 临时处理（30天自动清理）"
echo "  news-raw    - 新闻原始HTML/JSON（90天自动清理，DLM Raw News Layer）"
echo "  news-images - 新闻图片（90天）"
echo ""
echo "目录规范:"
echo "  documents/{market}/{symbol}/{doc_type}/{year}/"
echo "  knowledge/{market}/{symbol}/{doc_type}/{year}/"
echo "  datasets/{source}/"
echo "  artifacts/{type}/"
echo "  staging/{status}/"
