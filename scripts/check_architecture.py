#!/usr/bin/env python3
"""Architecture Compliance Checker — 架构合规自动检查

基于 specs/architecture.yaml 中的规则，自动扫描代码检测违规。

检查规则:
- ARCH-003: rag_nodes/ 不得直接 import 基础设施库
- MCP-002: mcp-*/server/tools/ 不得直接 import asyncpg/qdrant_client
- PRM-004: 每个注册 Agent 必须有 prompts/{name}/system.md
- DEP-002: 禁止反向依赖（tools/ → rag_nodes/ → graph/ → agents/ → api/）

用法:
    python3 scripts/check_architecture.py
    python3 scripts/check_architecture.py --verbose
"""

import argparse
import os
import re
import sys
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
AGENT_ROOT = PROJECT_ROOT / "langgraph" / "agent"

# ──────────────────────────────────────────────
# 配置
# ──────────────────────────────────────────────

# ARCH-003: rag_nodes/ 禁止导入的基础设施库
FORBIDDEN_INFRA_IMPORTS = [
    "asyncpg",
    "qdrant_client",
    "minio",
    "httpx",
]

# MCP-002: MCP tools/ 禁止直接导入的库
MCP_FORBIDDEN_IMPORTS = [
    "asyncpg",
    "qdrant_client",
]

# DEP-002: 反向依赖检测（layer → 禁止导入的上层）
LAYER_HIERARCHY = [
    "api",
    "services",
    "agents",
    "graph",
    "rag_nodes",
    "tools",
    "config",
]

# 已注册的 Chat Agent（需要 prompts/{name}/system.md）
REGISTERED_AGENTS = ["chat", "research", "kb", "investment"]

# DEP-002 白名单：允许的跨层导入（(source_layer, target_module) 对）
DEP_002_ALLOWLIST = [
    ("rag_nodes", "services"),  # knowledge node 需调用审批服务
]

# ──────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────

class Violation:
    """违规记录"""

    def __init__(self, rule: str, file: str, line: int, message: str):
        self.rule = rule
        self.file = file
        self.line = line
        self.message = message

    def __str__(self):
        rel_path = os.path.relpath(self.file, PROJECT_ROOT)
        return f"  [{self.rule}] {rel_path}:{self.line} — {self.message}"


def get_python_files(directory: Path) -> list[Path]:
    """递归获取目录下所有 .py 文件（排除 __pycache__）"""
    if not directory.exists():
        return []
    return [
        f for f in directory.rglob("*.py")
        if "__pycache__" not in str(f)
    ]


def get_imports(file_path: Path) -> list[tuple[int, str]]:
    """提取文件中的 import 语句

    Returns:
        [(line_number, module_name), ...]
    """
    imports = []
    try:
        content = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return imports

    for i, line in enumerate(content.split("\n"), 1):
        stripped = line.strip()
        # from X.Y import Z
        m = re.match(r"^from\s+([\w.]+)\s+import", stripped)
        if m:
            imports.append((i, m.group(1)))
            continue
        # import X.Y
        m = re.match(r"^import\s+([\w.]+)", stripped)
        if m:
            imports.append((i, m.group(1)))

    return imports


# ──────────────────────────────────────────────
# 检查规则
# ──────────────────────────────────────────────

def check_arch_003(verbose: bool = False) -> list[Violation]:
    """ARCH-003: rag_nodes/ 不得直接 import 基础设施库"""
    violations = []
    rag_nodes_dir = AGENT_ROOT / "rag_nodes"

    for py_file in get_python_files(rag_nodes_dir):
        for line_no, module in get_imports(py_file):
            top_level = module.split(".")[0]
            if top_level in FORBIDDEN_INFRA_IMPORTS:
                violations.append(Violation(
                    rule="ARCH-003",
                    file=str(py_file),
                    line=line_no,
                    message=f"rag_nodes/ 禁止直接导入 '{module}'，应通过 tools/ 访问",
                ))

    if verbose and not violations:
        print("  [ARCH-003] ✓ rag_nodes/ 无基础设施直接导入")
    return violations


def check_mcp_002(verbose: bool = False) -> list[Violation]:
    """MCP-002: MCP Server tools/ 不得直接 import asyncpg/qdrant_client"""
    violations = []

    mcp_dirs = [
        PROJECT_ROOT / "mcp-knowledge" / "server" / "tools",
        PROJECT_ROOT / "mcp-news" / "server" / "tools",
    ]

    for tools_dir in mcp_dirs:
        for py_file in get_python_files(tools_dir):
            for line_no, module in get_imports(py_file):
                top_level = module.split(".")[0]
                if top_level in MCP_FORBIDDEN_IMPORTS:
                    violations.append(Violation(
                        rule="MCP-002",
                        file=str(py_file),
                        line=line_no,
                        message=f"MCP tools/ 禁止直接导入 '{module}'，应通过 storage/ 访问",
                    ))

    if verbose and not violations:
        print("  [MCP-002] ✓ MCP tools/ 无数据库直接导入")
    return violations


def check_prm_004(verbose: bool = False) -> list[Violation]:
    """PRM-004: 每个注册 Agent 必须有 prompts/{name}/system.md"""
    violations = []
    prompts_dir = AGENT_ROOT / "prompts"

    for agent_name in REGISTERED_AGENTS:
        system_md = prompts_dir / agent_name / "system.md"
        if not system_md.exists():
            violations.append(Violation(
                rule="PRM-004",
                file=str(prompts_dir),
                line=0,
                message=f"Agent '{agent_name}' 缺少 prompts/{agent_name}/system.md",
            ))

    if verbose and not violations:
        print(f"  [PRM-004] ✓ 所有 {len(REGISTERED_AGENTS)} 个 Agent 有 system prompt")
    return violations


def check_dep_002(verbose: bool = False) -> list[Violation]:
    """DEP-002: 禁止反向依赖

    层级（上→下）: api → agents → graph → rag_nodes → tools → config
    规则: 下层不得 import 上层
    """
    violations = []

    # 构建层级索引（数字越小越上层）
    layer_rank = {name: idx for idx, name in enumerate(LAYER_HIERARCHY)}

    # 检查每个层级目录
    for layer_name, rank in layer_rank.items():
        layer_dir = AGENT_ROOT / layer_name
        if not layer_dir.exists():
            continue

        for py_file in get_python_files(layer_dir):
            for line_no, module in get_imports(py_file):
                top_level = module.split(".")[0]
                # 只检查项目内部模块
                if top_level not in layer_rank:
                    continue
                target_rank = layer_rank[top_level]
                # 反向依赖: 下层（rank 大）import 上层（rank 小）
                if target_rank < rank:
                    # 检查白名单
                    if (layer_name, top_level) in DEP_002_ALLOWLIST:
                        continue
                    violations.append(Violation(
                        rule="DEP-002",
                        file=str(py_file),
                        line=line_no,
                        message=f"反向依赖: {layer_name}/ 不得 import {top_level}/（上层模块）",
                    ))

    if verbose and not violations:
        print("  [DEP-002] ✓ 无反向依赖")
    return violations


# ──────────────────────────────────────────────
# 主入口
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Architecture Compliance Checker")
    parser.add_argument("--verbose", "-v", action="store_true", help="显示通过的检查项")
    args = parser.parse_args()

    print("=" * 60)
    print("  Architecture Compliance Check")
    print(f"  Root: {PROJECT_ROOT}")
    print("=" * 60)
    print()

    all_violations: list[Violation] = []

    checks = [
        ("ARCH-003", check_arch_003),
        ("MCP-002", check_mcp_002),
        ("PRM-004", check_prm_004),
        ("DEP-002", check_dep_002),
    ]

    for rule_id, check_fn in checks:
        violations = check_fn(verbose=args.verbose)
        all_violations.extend(violations)

    # 输出结果
    print()
    if all_violations:
        print(f"❌ 发现 {len(all_violations)} 处违规:")
        print()
        for v in all_violations:
            print(v)
        print()
        sys.exit(1)
    else:
        print("✅ 所有检查通过，无架构违规。")
        sys.exit(0)


if __name__ == "__main__":
    main()
