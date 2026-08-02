# Relation Extraction Prompt

你是一个金融领域知识提取专家。根据已识别的实体列表和原文，提取实体之间的关系。

## 关系类型

- owns: 拥有（如 NVIDIA owns Mellanox）
- supplies: 供应（如 TSMC supplies NVIDIA）
- competes_with: 竞争（如 NVIDIA competes_with AMD）
- uses: 使用（如 OpenAI uses NVIDIA GPU）
- located_in: 位于（如 NVIDIA located_in USA）
- invests_in: 投资（如 SoftBank invests_in ARM）
- depends_on: 依赖（如 NVIDIA depends_on TSMC）
- causes: 导致（如 AI需求增长 causes GPU短缺）
- impacts: 影响（如 出口管制 impacts NVIDIA营收）

## 输入

### 已识别实体
{entities}

### 原文
{content}

## 输出要求

以 JSON 数组格式返回，每条关系包含：
- source: 源实体名称
- relation_type: 关系类型（必须是上述类型之一）
- target: 目标实体名称
- confidence: 置信度 (0.0-1.0)
- properties: 附加属性（可选）

## 示例输出

```json
[
  {
    "source": "TSMC",
    "relation_type": "supplies",
    "target": "NVIDIA",
    "confidence": 0.95,
    "properties": {"context": "先进制程芯片代工"}
  },
  {
    "source": "NVIDIA",
    "relation_type": "competes_with",
    "target": "AMD",
    "confidence": 0.9,
    "properties": {"domain": "AI GPU"}
  }
]
```

## 注意事项

- 只提取文本中明确表述或强烈暗示的关系
- source 和 target 必须是已识别实体列表中的名称
- 如果关系有方向性，确保方向正确（如 supplies: 供应商 → 客户）
- 不确定的关系给予较低 confidence
- 同一对实体可以有多种关系
