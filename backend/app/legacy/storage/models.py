"""当前平台仍在使用的轻量领域模型。"""
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """事件类型"""
    NEWS = "news"  # 新闻
    ANNOUNCEMENT = "announcement"  # 公告
    SOCIAL = "social"  # 社交媒体
    MARKET = "market"  # 市场数据


class EventImportance(str, Enum):
    """事件重要性"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Event(BaseModel):
    """事件模型"""
    id: Optional[str] = None
    title: str = Field(..., description="事件标题")
    content: str = Field(..., description="事件内容")
    event_type: EventType = Field(..., description="事件类型")
    source: str = Field(..., description="数据源")
    source_url: Optional[str] = Field(None, description="来源URL")
    publish_time: datetime = Field(..., description="发布时间")
    collect_time: datetime = Field(default_factory=datetime.now, description="采集时间")

    # 事件属性
    importance: Optional[EventImportance] = Field(None, description="重要性")
    hotness: Optional[float] = Field(None, ge=0, le=1, description="热度分数")
    keywords: List[str] = Field(default_factory=list, description="关键词")
    entities: Dict[str, List[str]] = Field(default_factory=dict, description="实体识别结果")

    # 元数据
    metadata: Dict = Field(default_factory=dict, description="额外元数据")

    class Config:
        json_schema_extra = {
            "example": {
                "title": "某公司发布年度财报",
                "content": "某公司2025年营收增长30%...",
                "event_type": "announcement",
                "source": "eastmoney",
                "publish_time": "2026-03-09T10:00:00",
                "importance": "high",
                "hotness": 0.85,
                "keywords": ["财报", "营收", "增长"],
            }
        }


class Stock(BaseModel):
    """股票模型"""
    id: Optional[str] = None
    code: str = Field(..., description="股票代码")
    name: str = Field(..., description="股票名称")
    exchange: str = Field(..., description="交易所(SH/SZ)")

    # 基本信息
    industry: Optional[str] = Field(None, description="所属行业")
    sector: Optional[str] = Field(None, description="所属板块")
    market_cap: Optional[float] = Field(None, description="市值")

    # 公司信息
    company_id: Optional[str] = Field(None, description="关联公司ID")

    # 元数据
    metadata: Dict = Field(default_factory=dict, description="额外元数据")
    update_time: datetime = Field(default_factory=datetime.now, description="更新时间")

    class Config:
        json_schema_extra = {
            "example": {
                "code": "600519",
                "name": "贵州茅台",
                "exchange": "SH",
                "industry": "白酒",
                "sector": "食品饮料",
            }
        }
