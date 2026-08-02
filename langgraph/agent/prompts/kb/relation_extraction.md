# Relation Extraction Prompt

你是一个金融领域知识提取专家。根据已识别的实体列表和原文，提取实体之间的关系。

## 关系类型

关系类型使用**名词形式**，必须从以下列表中选取（与知识图谱存储完全一致）：

- supplier: 供应（source 是供应商 → target 是客户，如 TSMC supplier NVIDIA）
- customer: 客户（source 是客户 → target 是供应商，与 supplier 方向相反，如 NVIDIA customer TSMC）
- competitor: 竞争（双向，如 NVIDIA ↔ AMD）
- owns: 拥有（如 NVIDIA owns Mellanox）
- uses: 使用（如 OpenAI uses NVIDIA GPU）
- located_in: 位于（如 NVIDIA located_in USA）
- invests_in: 投资（如 SoftBank invests_in ARM）
- depends_on: 依赖（如 NVIDIA depends_on TSMC）
- impacts: 影响（如 出口管制 impacts NVIDIA营收）
- causes: 导致（如 AI需求增长 causes GPU短缺）
- partner: 合作（双向，如 NVIDIA ↔ TSMC AI芯片合作）
- belongs_to: 归属（如 Company belongs_to Industry，NVIDIA belongs_to AI Semiconductor）

## 输入

### 已识别实体
{entities}

### 原文
{content}

## 输出要求

以 JSON 数组格式返回，每条关系包含：
- source: 源实体名称
- relation_type: 关系类型（必须是上述名词形式之一）
- target: 目标实体名称
- confidence: 置信度 (0.0-1.0)
- properties: 附加属性（可选）

## 示例输出

```json
[
  {
    "source": "TSMC",
    "relation_type": "supplier",
    "target": "NVIDIA",
    "confidence": 0.95,
    "properties": {"context": "先进制程芯片代工"}
  },
  {
    "source": "NVIDIA",
    "relation_type": "competitor",
    "target": "AMD",
    "confidence": 0.9,
    "properties": {"domain": "AI GPU"}
  },
  {
    "source": "NVIDIA",
    "relation_type": "partner",
    "target": "TSMC",
    "confidence": 0.85,
    "properties": {"context": "AI 芯片合作"}
  }
]
```

## 注意事项

- 只提取文本中明确表述或强烈暗示的关系
- source 和 target 必须是已识别实体列表中的名称
- 如果关系有方向性，确保方向正确（如 supplier: source 是供应商，customer: source 是客户）
- 不确定的关系给予较低 confidence
- 同一对实体可以有多种关系