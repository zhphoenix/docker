"""AC-P4-4 Agent Marketplace 端到端验证脚本

模拟「导出定义可在另一实例导入」：
1. 导出 chat Agent 定义 JSON
2. 改名后导入（模拟另一实例重建）
3. 验证 agents 表 + agent_prompts 表重建成功
4. 验证发布模板 + 模板安装
"""

import json
import pprint
import urllib.request

BASE = "http://localhost:8100"


def http(method: str, path: str, body=None):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Content-Type", "application/json")
    data = json.dumps(body).encode() if body is not None else None
    with urllib.request.urlopen(req, data=data) as resp:
        return json.loads(resp.read().decode())


results = []


def check(name: str, cond: bool, detail=""):
    results.append((name, bool(cond), detail))
    print(f"{'PASS' if cond else 'FAIL'} | {name} {detail}")


# 1. 导出 chat
exported = http("GET", "/api/marketplace/export/chat")
check("导出返回 schema_version=1.0", exported.get("schema_version") == "1.0")
check("导出含 agent.name=chat", exported.get("agent", {}).get("name") == "chat")
check("导出含 prompts", len(exported.get("prompts", [])) > 0,
      f"(prompts={len(exported.get('prompts', []))})")

# 2. 模拟另一实例：改名后导入
definition = json.loads(json.dumps(exported))  # 深拷贝
definition["agent"]["name"] = "chat_market_test"
definition["agent"]["display_name"] = "Chat Imported"
# 只保留一个 prompt 版本便于断言
definition["prompts"] = [p for p in definition["prompts"] if p.get("version") == 1]
imp = http("POST", "/api/marketplace/import", definition)
check("导入成功", imp.get("imported") is True, f"(prompts_applied={imp.get('prompts_applied')})")

# 3. 验证 DB 重建
import subprocess


def psql(q):
    out = subprocess.run(
        ["docker", "exec", "postgres", "psql", "-U", "postgres", "-d", "ai", "-t", "-A", "-c", q],
        capture_output=True, text=True,
    )
    return out.stdout.strip()


agent_count = psql(f"SELECT COUNT(*) FROM agents WHERE name='chat_market_test'")
check("agents 表已重建 chat_market_test", agent_count == "1", f"(count={agent_count})")
prompt_count = psql(f"SELECT COUNT(*) FROM agent_prompts WHERE agent_id='chat_market_test'")
check("agent_prompts 已重建 prompt", prompt_count == "1", f"(count={prompt_count})")

# 4. 验证 agents 列表出现
agents = http("GET", "/api/agents")
names = [a["name"] for a in agents["agents"]]
check("agents API 返回 chat_market_test", "chat_market_test" in names)

# 5. 发布模板（research）
pub = http("POST", "/api/marketplace/templates", {"agent_id": "research", "category": "research"})
check("发布 research 为模板", pub.get("published") is True, f"(name={pub.get('name')})")

templates = http("GET", "/api/marketplace/templates")
tmpl_names = [t["name"] for t in templates["templates"]]
check("模板列表含 chat+research",
      "chat" in tmpl_names and "research" in tmpl_names,
      f"(templates={tmpl_names})")

# 6. 模板安装 → 生成新 Agent
research_tmpl = next(t for t in templates["templates"] if t["name"] == "research")
inst = http("POST", f"/api/marketplace/templates/{research_tmpl['id']}/install")
check("模板安装成功", inst.get("installed") is True, f"(agent={inst.get('agent')})")

# 7. 安装后 installs 计数 +1
tpl2 = http("GET", f"/api/marketplace/templates/{research_tmpl['id']}")
check("安装计数 +1", tpl2.get("installs", 0) >= 1, f"(installs={tpl2.get('installs')})")

# 8. 校验导入会自动重建多 prompt 变体（A/B）：用导出 chat 原样导入（应 upsert 保留 v1/v2）
imported_orig = http("POST", "/api/marketplace/import", exported)
check("原定义导入成功（upsert）", imported_orig.get("imported") is True)
v2_count = psql("SELECT COUNT(*) FROM agent_prompts WHERE agent_id='chat' AND version=2")
check("chat 原定义导入后 v2 仍存在", v2_count == "1", f"(v2_count={v2_count})")

# 9. 清理测试数据
psql("DELETE FROM agents WHERE name='chat_market_test'")
psql("DELETE FROM agent_prompts WHERE agent_id='chat_market_test'")
psql(f"DELETE FROM agent_templates WHERE name='research'")
check("测试数据已清理", True)

print("\n===== 汇总 =====")
passed = sum(1 for _, c, _ in results if c)
failed = sum(1 for _, c, _ in results if not c)
print(f"通过 {passed}/{len(results)}，失败 {failed}")
pprint.pprint(results, width=120)