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

## 五、检查清单

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

## 六、目录结构参考

```text
agent/
├── agents/
│   ├── base_agent.py          # 新增 Agent 继承此类
│   ├── chat_agent.py
│   ├── research_agent.py
│   └── investment_agent.py    # ← 新增
├── nodes/
│   ├── planner.py
│   ├── retrieve.py
│   ├── analyze_financial.py   # ← 新增
│   └── ...
├── tools/
│   ├── llm.py
│   ├── qdrant.py
│   ├── search.py              # ← 新增
│   └── ...
└── prompts/
    ├── planner.md
    ├── investment.md           # ← 新增
    └── ...
```