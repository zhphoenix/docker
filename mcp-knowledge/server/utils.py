"""共享工具函数"""

import uuid as _uuid
from datetime import date, datetime


def serialize(obj: dict) -> dict:
    """序列化 UUID/datetime 为字符串"""
    result = {}
    for k, v in obj.items():
        if isinstance(v, _uuid.UUID):
            result[k] = str(v)
        elif isinstance(v, (datetime, date)):
            result[k] = v.isoformat()
        else:
            result[k] = v
    return result
