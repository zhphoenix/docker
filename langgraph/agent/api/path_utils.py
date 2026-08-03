"""路径转换工具 - 处理 Windows / WSL / 容器三种环境的路径差异

路径映射链:
  Windows:  E:\\ai-platform\\data\\stock_a
  WSL:      /mnt/e/ai-platform/data/stock_a
  Container: /data/stock_a

browse-dirs API 返回容器路径，用户通过目录浏览器选择时无需转换。
用户手动输入 Windows 或 WSL 格式路径时，本模块负责统一转换为容器路径。
"""

import re
import logging
from pathlib import PureWindowsPath, PurePosixPath

logger = logging.getLogger(__name__)

# ─── 卷映射表（WSL 宿主机路径 → 容器内路径）───────────────
# 与 compose.yml volumes 保持一致
VOLUME_MOUNTS: list[tuple[str, str]] = [
    ("/mnt/e/ai-platform/data/reports", "/data/analysis_reports"),
    ("/mnt/e/ai-platform/data/stock_a", "/data/stock_a"),
    ("/mnt/e/ai-platform/data/stock_h", "/data/stock_h"),
    ("/mnt/e/ai-platform/data/stock_us", "/data/stock_us"),
    ("/mnt/d/minio/data", "/data/minio"),
    ("/mnt/e/ai-platform/registry", "/registry"),
    ("/mnt/e/ai-platform/langgraph/agent", "/app"),
]

# Windows 盘符 → WSL /mnt 映射（小写盘符）
_DRIVE_LETTERS = set("abcdefghijklmnopqrstuvwxyz")


def _is_windows_path(path: str) -> bool:
    """检测是否为 Windows 格式路径（如 E:\\... 或 E:/...）"""
    if len(path) < 3:
        return False
    return (
        path[0].lower() in _DRIVE_LETTERS
        and path[1] == ":"
        and path[2] in ("\\", "/")
    )


def _windows_to_wsl(path: str) -> str:
    """Windows 路径 → WSL 路径

    E:\\ai-platform\\data\\stock_a → /mnt/e/ai-platform/data/stock_a
    """
    drive = path[0].lower()
    rest = path[2:].replace("\\", "/")
    return f"/mnt/{drive}{rest}"


def _wsl_to_container(path: str) -> str:
    """WSL 路径 → 容器路径（通过卷映射表）

    /mnt/e/ai-platform/data/stock_a/000001_xxx.pdf → /data/stock_a/000001_xxx.pdf
    """
    # 按映射长度降序排列，优先匹配最长前缀（避免 /mnt/e/ai-platform/data 误匹配）
    sorted_mounts = sorted(VOLUME_MOUNTS, key=lambda x: len(x[0]), reverse=True)
    for wsl_prefix, container_prefix in sorted_mounts:
        if path == wsl_prefix:
            return container_prefix
        if path.startswith(wsl_prefix + "/"):
            relative = path[len(wsl_prefix):]
            return container_prefix + relative
    return path  # 无匹配则原样返回


def normalize_path(raw: str) -> str:
    """统一路径格式 → 容器内路径

    处理顺序:
    1. Windows 路径 (E:\\...) → WSL 路径 → 容器路径
    2. WSL 路径 (/mnt/e/...) → 容器路径
    3. 容器路径 (/data/...) → 直接返回

    Args:
        raw: 用户输入的原始路径字符串

    Returns:
        转换后的容器内路径

    Examples:
        >>> normalize_path("E:\\\\ai-platform\\\\data\\\\stock_a")
        '/data/stock_a'
        >>> normalize_path("/mnt/e/ai-platform/data/stock_a")
        '/data/stock_a'
        >>> normalize_path("/data/stock_a")
        '/data/stock_a'
    """
    if not raw or not raw.strip():
        return raw

    path = raw.strip()

    # 步骤 1: Windows → WSL
    if _is_windows_path(path):
        path = _windows_to_wsl(path)
        logger.info("[PathNorm] Windows→WSL: %s → %s", raw, path)

    # 步骤 2: WSL → Container
    if path.startswith("/mnt/"):
        original = path
        path = _wsl_to_container(path)
        if path != original:
            logger.info("[PathNorm] WSL→Container: %s → %s", original, path)

    return path


def validate_container_path(path: str, allowed_roots: list[str]) -> str | None:
    """校验容器路径是否在允许的根目录范围内

    Args:
        path: 已转换的容器路径
        allowed_roots: 允许的根路径列表（如 ["/data", "/app"]）

    Returns:
        校验通过返回 path，否则返回 None
    """
    from pathlib import Path

    target = Path(path).resolve()
    for root in allowed_roots:
        if str(target).startswith(root):
            return path
    return None


def get_volume_mapping_info() -> list[dict]:
    """返回卷映射信息（供前端展示给用户参考）"""
    return [
        {"host_path": wsl, "container_path": container}
        for wsl, container in VOLUME_MOUNTS
    ]
