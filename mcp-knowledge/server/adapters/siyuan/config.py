"""SiYuan Adapter 连接配置

从 server.config.settings 读取（其值来自 .env / 环境变量），
提供集中式的 SiYuan 连接与限流参数。
"""

from dataclasses import dataclass, field

from server.config import settings


@dataclass(frozen=True)
class SiYuanConfig:
    """SiYuan 连接与限流配置"""

    base_url: str = field(default_factory=lambda: settings.SIYUAN_URL.rstrip("/"))
    token: str = field(default_factory=lambda: settings.SIYUAN_ACCESS_AUTH_CODE)
    concurrency: int = field(default_factory=lambda: settings.SIYUAN_CONCURRENCY)
    queue_size: int = field(default_factory=lambda: settings.SIYUAN_QUEUE_SIZE)
    max_retries: int = field(default_factory=lambda: settings.SIYUAN_MAX_RETRIES)
    timeout: float = field(default_factory=lambda: settings.SIYUAN_TIMEOUT)
    sync_user: str = field(default_factory=lambda: settings.SIYUAN_SYNC_USER)

    @property
    def headers(self) -> dict:
        """Show HTTP 请求头（含访问授权）"""
        h = {"User-Agent": f"ai-platform/{self.sync_user}"}
        if self.token:
            h["Authorization"] = f"Token {self.token}"
        return h


# 模块级单例
_siyuan_config: SiYuanConfig | None = None


def get_siyuan_config() -> SiYuanConfig:
    """获取全局唯一的 SiYuan 配置（惰性初始化）"""
    global _siyuan_config
    if _siyuan_config is None:
        _siyuan_config = SiYuanConfig()
    return _siyuan_config