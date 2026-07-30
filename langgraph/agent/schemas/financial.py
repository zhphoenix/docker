"""金融数据模型 - 结构化数据卡片 + 权威度 + 时效过滤

定义投资研究模块的核心数据模型：
  - ExchangeRateCard: 汇率数据卡片
  - StockPriceCard: 股价数据卡片
  - AuthorityLevel: 权威度分级枚举
  - TimeRange: 时效过滤参数
"""

from pydantic import BaseModel, Field
from datetime import datetime, date, timezone
from enum import Enum


class ExchangeRateCard(BaseModel):
    """汇率数据卡片

    包含双向换算和更新时间，用于实时汇率查询展示。
    """

    base_currency: str = Field(description="基础货币（如 USD）")
    target_currency: str = Field(description="目标货币（如 CNY）")
    rate: float = Field(description="汇率（1 base = rate target）")
    inverse_rate: float = Field(description="反向汇率（1 target = inverse base）")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="数据更新时间")
    source: str = Field(default="akshare", description="数据来源")


class StockPriceCard(BaseModel):
    """股价数据卡片

    包含股票代码、现价、涨跌额、涨跌幅及休市状态。
    """

    symbol: str = Field(description="股票代码")
    name: str = Field(default="", description="股票名称")
    price: float = Field(description="当前价格")
    change: float = Field(description="涨跌额")
    change_pct: float = Field(description="涨跌幅（%）")
    market_status: str = Field(default="closed", description="市场状态: open/closed/pre-market")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="数据更新时间")
    source: str = Field(default="akshare", description="数据来源")


class AuthorityLevel(str, Enum):
    """权威度分级

    基于 providers.yaml 中 official + status 字段组合映射：
      - VERY_HIGH: official=true & status=verified（如 cninfo、sec_edgar）
      - HIGH:      official=true & status=limited（如 nasdaq、reuters）
      - MEDIUM:    official=false & status=verified（如 akshare、eastmoney）
      - LOW:       其他（如 status=unavailable）
    """

    VERY_HIGH = "very_high"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TimeRange(BaseModel):
    """时效过滤参数

    精确到天级别，用于限定检索结果的时间窗口。
    """

    start_date: date | None = Field(default=None, description="起始日期（含）")
    end_date: date | None = Field(default=None, description="截止日期（含）")
