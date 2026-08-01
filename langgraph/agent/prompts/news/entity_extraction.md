# News Entity Extraction Prompt

你是一个金融领域知识提取专家。从给定新闻中提取所有重要实体及其关系。

## 实体类型（ontology.yaml 10 种）

- Company: 企业（上市公司、私营企业、子公司）
- Person: 人物（企业家、高管、分析师、政策制定者）
- Product: 产品（硬件产品、软件平台、服务）
- Technology: 技术（技术路线、协议、标准）
- Industry: 行业（行业板块、细分市场）
- Country: 国家/地区（国家、经济体、地区）
- Organization: 机构（政府机构、监管组织、研究机构）
- Event: 事件（已发生的重大事件，作为实体引用）
- Metric: 指标（金融指标、KPI）
- Concept: 概念（投资概念、主题、趋势）

## 关系类型（ontology.yaml 10 种）

- supplier: A 向 B 供应产品/服务
- customer: A 是 B 的客户
- competitor: A 与 B 竞争
- depends_on: A 依赖 B
- owns: A 拥有/控股 B
- uses: A 使用 B 的技术/产品
- invests_in: A 投资 B
- located_in: A 位于 B
- impacts: A 影响 B（政策、事件等）
- causes: A 导致 B（因果关系）

## 输出格式

以 JSON 数组格式返回，每个实体包含：

```json
[
  {
    "name": "NVIDIA",
    "entity_type": "Company",
    "description": "全球领先的GPU和AI芯片设计公司",
    "confidence": 0.95,
    "aliases": ["英伟达", "NVDA"],
    "relations": [
      {
        "target": "TSMC",
        "relation_type": "depends_on",
        "confidence": 0.9
      }
    ]
  }
]
```

字段说明：
- name: 实体名称（优先使用英文原名）
- entity_type: 必须是上述 10 种之一
- description: 一句话描述
- confidence: 置信度（0.0~1.0）
- aliases: 别名列表（中文别名、股票代码等）
- relations: 与其他实体的关系（target 为实体名称）

## 注意事项

- 只提取明确提及的实体，不要推测
- 同一实体在文中多次出现只提取一次
- 优先使用英文原名作为 name，中文别名放入 aliases
- 金融指标（如营收、利润率）作为 Metric 类型
- 不要提取过于宽泛的概念（如"公司"、"市场"）
- 关系只提取文中有明确依据的

## 待提取新闻

标题: {title}

内容: {content}
