"""入口文件 - uvicorn 启动"""

import os
import uvicorn

if __name__ == "__main__":
    # Docker 环境中禁用 reload，本地开发时启用
    reload = os.getenv("RELOAD", "false").lower() == "true"
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8100,
        reload=reload,
        reload_dirs=["."] if reload else None,
        reload_excludes=["tests/*", "__pycache__/*", "*.pyc"] if reload else None,
        log_level="info",
    )
