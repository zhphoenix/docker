"""FinancialDataTool - 金融数据基础设施 Tool（纯 SDK 封装）

合规要点（09_Tool设计.md）:
  - Tool 只做 SDK 调用封装，不含市场路由/数据聚合等业务逻辑
  - 每个方法对应一个 SDK 调用，返回原始 dict
  - 使用 asyncio.to_thread() 避免阻塞事件循环
  - SDK import 失败时返回 {"error": "..."}，不抛异常
"""

import asyncio
import logging
from datetime import datetime, timezone

from config.settings import settings

logger = logging.getLogger(__name__)


class FinancialDataTool:
    """金融数据基础设施 Tool -- 纯 SDK 封装

    只负责调用 AKShare/yfinance SDK 获取原始数据。
    市场路由和数据聚合逻辑在 Skill 层处理。
    """

    def __init__(self):
        self.timeout = getattr(settings, "FINANCIAL_DATA_TIMEOUT", 30.0)

    async def get_cn_stock_quote(self, symbol: str) -> dict:
        """调用 AKShare 获取 A 股实时行情

        Args:
            symbol: A 股股票代码（如 "600519"）

        Returns:
            原始 dict，包含 price/change/change_pct 等字段。
            失败返回 {"error": "错误描述"}
        """
        try:
            import akshare as ak
        except ImportError:
            logger.error("akshare not installed")
            return {"error": "akshare not installed"}

        try:
            # akshare 是同步库，用 to_thread 避免阻塞
            df = await asyncio.to_thread(ak.stock_zh_a_spot_em)
            row = df[df["代码"] == symbol]
            if row.empty:
                return {"error": f"symbol {symbol} not found"}

            r = row.iloc[0]
            return {
                "symbol": str(r.get("代码", symbol)),
                "name": str(r.get("名称", "")),
                "price": float(r.get("最新价", 0) or 0),
                "change": float(r.get("涨跌额", 0) or 0),
                "change_pct": float(r.get("涨跌幅", 0) or 0),
                "volume": float(r.get("成交量", 0) or 0),
                "amount": float(r.get("成交额", 0) or 0),
                "source": "akshare",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            logger.exception("get_cn_stock_quote failed for %s", symbol)
            return {"error": str(e)}

    async def get_hk_stock_quote(self, symbol: str) -> dict:
        """调用 AKShare 获取港股实时行情

        Args:
            symbol: 港股代码（如 "00700"）

        Returns:
            原始 dict
        """
        try:
            import akshare as ak
        except ImportError:
            logger.error("akshare not installed")
            return {"error": "akshare not installed"}

        try:
            df = await asyncio.to_thread(ak.stock_hk_spot_em)
            row = df[df["代码"] == symbol]
            if row.empty:
                return {"error": f"symbol {symbol} not found"}

            r = row.iloc[0]
            return {
                "symbol": str(r.get("代码", symbol)),
                "name": str(r.get("名称", "")),
                "price": float(r.get("最新价", 0) or 0),
                "change": float(r.get("涨跌额", 0) or 0),
                "change_pct": float(r.get("涨跌幅", 0) or 0),
                "volume": float(r.get("成交量", 0) or 0),
                "amount": float(r.get("成交额", 0) or 0),
                "source": "akshare",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            logger.exception("get_hk_stock_quote failed for %s", symbol)
            return {"error": str(e)}

    async def get_us_stock_quote(self, symbol: str) -> dict:
        """调用 yfinance 获取美股实时行情

        Args:
            symbol: 美股 ticker（如 "AAPL"）

        Returns:
            原始 dict
        """
        try:
            import yfinance as yf
        except ImportError:
            logger.error("yfinance not installed")
            return {"error": "yfinance not installed"}

        try:
            def _fetch():
                ticker = yf.Ticker(symbol)
                info = ticker.fast_info
                return {
                    "symbol": symbol,
                    "name": str(getattr(info, "short_name", symbol)),
                    "price": float(getattr(info, "last_price", 0) or 0),
                    "change": float(getattr(info, "last_price", 0) or 0)
                              - float(getattr(info, "previous_close", 0) or 0),
                    "change_pct": 0.0,  # 由 Skill 层计算
                    "source": "yfinance",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }

            return await asyncio.to_thread(_fetch)
        except Exception as e:
            logger.exception("get_us_stock_quote failed for %s", symbol)
            return {"error": str(e)}

    async def get_forex_rate(self, base: str, target: str) -> dict:
        """调用 AKShare 获取汇率（数据源: 国家外汇管理局 safe）

        Args:
            base: 基础货币代码（如 "USD"）
            target: 目标货币代码（如 "CNY"）

        Returns:
            原始 dict，包含 rate/inverse_rate 等字段
        """
        try:
            import akshare as ak
        except ImportError:
            logger.error("akshare not installed")
            return {"error": "akshare not installed"}

        try:
            def _fetch():
                # 获取人民币汇率中间价
                df = ak.currency_boc_safe()
                # 查找目标货币
                row = df[df["货币名称"].str.contains(target, na=False)]
                if row.empty:
                    # 尝试用英文代码匹配
                    row = df[df["货币代码"].str.upper() == target.upper()]
                if row.empty:
                    return {"error": f"currency {target} not found"}

                r = row.iloc[0]
                rate = float(r.get("中间价", 0) or 0)
                return {
                    "base_currency": base,
                    "target_currency": target,
                    "rate": rate,
                    "inverse_rate": round(1.0 / rate, 8) if rate else 0,
                    "source": "akshare",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }

            return await asyncio.to_thread(_fetch)
        except Exception as e:
            logger.exception("get_forex_rate failed for %s/%s", base, target)
            return {"error": str(e)}


# 模块级单例
financial_data_tool = FinancialDataTool()
