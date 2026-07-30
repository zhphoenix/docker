# Agent Development Guide

## 一、定位

指导如何新增 Agent、Node、Tool。

---

## 二、新增 Agent

### 2.1 步骤

1. 在 `agents/` 目录创建 Agent 文件
2. 定义 Agent 的 Graph（Workflow）
3. 在 Agent Dispatcher 中注册路由

### 2.2 示例：新增 Investment Agent

```python
# agents/investment_agent.py
from agents.base_agent import BaseAgent
from graph.builder import build_investment_graph

class InvestmentAgent(BaseAgent):
    """投研分析 Agent"""
    
    def __init__(self):
        self.graph = build_investment_graph()
    
    async def run(self, request):
        result = await self.graph.ainvoke({
            "question": request.messages[-1].content,
            "messages": request.messages,
            "plan": {},
            "documents": [],
            "tool_results": {},
            "answer": "",
            "reflect": {},
            "metadata": {"agent": "investment"}
        })
        return result
```

### 2.3 注册路由

```python
# graph/router.py
def dispatch_agent(request: ChatRequest) -> BaseAgent:
    if is_investment_task(request):
        return InvestmentAgent()
    elif is_research_task(request):
        return ResearchAgent()
    else:
        return ChatAgent()
```

---

## 三、新增 Node

### 3.1 步骤

1. 在 `nodes/` 目录创建 Node 文件
2. 定义 Node 函数（接收 State，返回更新）
3. 在 Graph 中注册 Node

### 3.2 示例：新增 analyze_financial Node

```python
# nodes/analyze_financial.py
from graph.state import AgentState
from tools.postgres import PostgresTool
from tools.llm import LLMTool

postgres_tool = PostgresTool()
llm_tool = LLMTool()

async def analyze_financial(state: AgentState) -> dict:
    """分析财务数据"""
    symbol = state["plan"].get("symbol")
    
    # 1. 从 PostgreSQL 获取财务数据
    financials = await postgres_tool.query(
        "SELECT * FROM financial_data WHERE symbol = $1",
        symbol
    )
    
    # 2. 调用 LLM 分析
    prompt = f"分析以下财务数据：{financials}"
    analysis = await llm_tool.chat([{"role": "user", "content": prompt}])
    
    # 3. 返回更新
    return {
        "tool_results": {"financial_analysis": analysis},
        "messages": [{"role": "assistant", "content": analysis}]
    }
```

### 3.3 注册到 Graph

```python
# graph/graph.py
from nodes.analyze_financial import analyze_financial

graph.add_node("analyze_financial", analyze_financial)
graph.add_edge("retrieve", "analyze_financial")
graph.add_edge("analyze_financial", "reason")
```

---

## 四、新增 Tool

### 4.1 步骤

1. 在 `tools/` 目录创建 Tool 文件
2. 定义 Tool 类（只访问基础设施）
3. 在 Node 中使用

### 4.2 示例：新增 WebSearch Tool

```python
# tools/search.py
import httpx
from config.settings import settings

class WebSearchTool:
    """Web 搜索工具"""
    
    def __init__(self):
        self.api_key = settings.SEARCH_API_KEY
        self.base_url = "https://api.search.example.com"
    
    async def search(self, query: str, limit: int = 5) -> list[dict]:
        """搜索"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/search",
                params={"q": query, "limit": limit},
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10.0
            )
            return response.json()["results"]
```

### 4.3 在 Node 中使用

```python
# nodes/retrieve.py
from tools.search import WebSearchTool

search_tool = WebSearchTool()

async def retrieve(state: AgentState) -> dict:
    # 语义检索
    qdrant_results = await qdrant_tool.search(...)
    
    # Web 搜索（如果需要）
    if state["plan"].get("need_web_search"):
        web_results = await search_tool.search(state["question"])
        qdrant_results.extend(web_results)
    
    return {"documents": qdrant_results}
```

---

## 六、Skill 层说明

Skill 是介于 Node 和 Tool 之间的**编排层**，负责聚合多个 Tool/Skill 的能力，实现业务逻辑。

| 层级 | 职责 | 示例 |
|------|------|------|
| Tool | 纯 SDK 封装，不含业务逻辑 | `FinancialDataTool.get_cn_stock_quote()` |
| Skill | 编排聚合，市场路由、数据格式转换 | `InvestmentResearchSkill.execute()` |
| Node | 单一职责，只修改 State | `query_rewrite` Node |

**新增 Skill 步骤**：

1. 在 `skills/` 目录创建 Skill 文件，继承 `BaseSkill`
2. 实现 `name`、`description`、`tags` 属性和 `execute()` 方法
3. 在 `skills/__init__.py` 中注册导出

```python
# skills/investment_research.py
class InvestmentResearchSkill(BaseSkill):
    """投资研究高级数据收集 Skill（编排层）"""
    
    def __init__(self):
        self._financial = financial_data_tool  # Tool: 纯 SDK 封装
        self._rag = RAGSearchSkill()           # Skill: 带过滤的 RAG
    
    async def execute(self, **kwargs) -> dict:
        # 市场路由、数据聚合等业务逻辑在此层实现
        ...
```

---

## 七、检查清单

新增 Agent/Node/Tool 时，确认：

| 检查项 | 说明 |
|--------|------|
| 职责单一 | 一个 Agent/Node/Tool 只做一件事 |
| 不跨层 | Node 不直接访问基础设施，Tool 不含业务逻辑 |
| State 驱动 | Node 只修改 State，不直接返回 |
| Prompt 独立 | Prompt 保存在 `prompts/` 目录 |
| 可测试 | 可 Mock 外部依赖进行单元测试 |
| 错误处理 | 明确的异常捕获和日志 |
| 配置驱动 | 连接信息从 settings 加载 |

---

## 八、目录结构参考

```text
agent/
├── agents/
│   ├── base_agent.py          # 新增 Agent 继承此类
│   ├── chat_agent.py
│   ├── research_agent.py
│   └── investment_agent.py    # ← 新增
├── nodes/
│   ├── planner.py
│   ├── query_rewrite.py       # ← 新增：LLM 驱动查询改写
│   ├── retrieve.py
│   ├── analyze_financial.py   # ← 新增
│   └── ...
├── tools/
│   ├── llm.py
│   ├── qdrant.py
│   ├── financial_data.py      # ← 新增：AKShare/yfinance SDK 封装
│   ├── search.py              # ← 新增
│   └── ...
├── skills/
│   ├── base_skill.py          # Skill 基类
│   ├── registry.py            # Skill 注册表
│   ├── rag_search.py          # RAG 检索 Skill（含权威度/时效过滤）
│   ├── investment_research.py # ← 新增：投资研究编排 Skill
│   ├── web_article_summary.py
│   └── master_analysis.py     # ← 新增：大师分析框架 Skill
├── schemas/
│   ├── state.py               # AgentState 定义
│   ├── financial.py           # ← 新增：股价/汇率卡片、权威度枚举、时效过滤
│   └── authority.py           # ← 新增：source_provider → 权威度映射
├── prompts/
│   ├── planner.md             # ← 已扩展：新增垂类参数、时间窗口等字段
│   ├── query_rewrite.md       # ← 新增：查询改写 Prompt
│   ├── earnings_call_analysis.md  # ← 新增：电话会议分析 Prompt
│   ├── investment.md           # ← 新增
│   └── ...
└── config/
    └── settings.py            # ← 已扩展：新增 FINANCIAL_DATA_TIMEOUT
```