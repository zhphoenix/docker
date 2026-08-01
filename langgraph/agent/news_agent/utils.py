"""News Agent 共享工具函数"""

import json
import logging
import re

logger = logging.getLogger(__name__)

# 贪婪匹配最外层 [...] — 正确处理嵌套数组
_JSON_ARRAY_GREEDY = re.compile(r"\[[\s\S]*\]")


def extract_json_array(text: str) -> list[dict]:
    """从 LLM 输出中提取 JSON 数组

    策略：
    1. 直接解析（text 本身就是合法 JSON）
    2. 贪婪正则提取最外层 [...]（处理嵌套数组）
    3. 括号平衡扫描（兜底）
    """
    text = text.strip()

    # 策略 1: 直接解析
    if text.startswith("["):
        try:
            result = json.loads(text)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    # 策略 2: 贪婪正则（从第一个 [ 到最后一个 ]）
    match = _JSON_ARRAY_GREEDY.search(text)
    if match:
        try:
            result = json.loads(match.group())
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    # 策略 3: 括号平衡扫描
    start = text.find("[")
    if start == -1:
        return []
    depth = 0
    in_string = False
    escape_next = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape_next:
            escape_next = False
            continue
        if ch == "\\":
            if in_string:
                escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                candidate = text[start:i + 1]
                try:
                    result = json.loads(candidate)
                    if isinstance(result, list):
                        return result
                except json.JSONDecodeError:
                    break

    return []
