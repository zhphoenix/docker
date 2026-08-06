"""pytest 会话级配置

在测试收集前加载项目根目录 .env 到环境变量，
使 config.settings 等模块级单例可正常初始化（pydantic-settings 环境变量优先于 env_file）。
根 .env 不存在时静默跳过，不影响仅依赖自带默认值的测试。
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录（langgraph/ 的上一级）
_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _ROOT / ".env"

if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE, override=False)