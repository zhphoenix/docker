#!/bin/bash
set -e

MODEL_CACHE="/opt/app-root/src/.cache/docling/models"
IMAGE_MODELS="/usr/local/lib/python3.12/dist-packages/rapidocr/models"

# Sync bundled RapidOCR models to cache (in case volume is empty or outdated)
echo "Syncing RapidOCR models..."
mkdir -p "${MODEL_CACHE}/RapidOcr/onnx/PP-OCRv6/det"
mkdir -p "${MODEL_CACHE}/RapidOcr/onnx/PP-OCRv6/rec"
mkdir -p "${MODEL_CACHE}/RapidOcr/onnx/PP-OCRv4/cls"

cp -n "${IMAGE_MODELS}/PP-OCRv6_det_small.onnx" "${MODEL_CACHE}/RapidOcr/onnx/PP-OCRv6/det/" 2>/dev/null || true
cp -n "${IMAGE_MODELS}/PP-OCRv6_rec_small.onnx" "${MODEL_CACHE}/RapidOcr/onnx/PP-OCRv6/rec/" 2>/dev/null || true
cp -n "${IMAGE_MODELS}/ch_ppocr_mobile_v2.0_cls_mobile.onnx" "${MODEL_CACHE}/RapidOcr/onnx/PP-OCRv4/cls/" 2>/dev/null || true

echo "RapidOCR models synced."

# Execute the main command
exec "$@"
