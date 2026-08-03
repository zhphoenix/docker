#!/usr/bin/env python3
"""vault companies 目录治理脚本（安全去重）

背景：
  data/vault/companies/ 存在 7894 个目录，严重混乱：
  - 同一公司重复：000001 / 000001_平安银行 / 000001_長和
  - 全角空格/多余空格：000002_万  科Ａ / 000012_南  玻Ａ
  - 6 位 A 股代码与 5 位港股代码混存（000001 平安银行 vs 00001 長和）

设计原则：
  - 默认 dry-run，仅输出报告，不做任何改动
  - 显式 --apply 才执行（移动而非删除）
  - 重复目录移入 _archive/ 而非直接删除，保证可回退
  - 按"精确代码前缀"分组（严格区分 5 位/6 位，避免 A 股与港股误合并）

用法：
  python3 scripts/dedupe_vault.py                       # dry-run 报告
  python3 scripts/dedupe_vault.py --apply               # 执行合并
  python3 scripts/dedupe_vault.py --apply --archive-dir /tmp/vault_archive
"""

import argparse
import os
import re
import shutil
import sys
from collections import defaultdict

VAULT_COMPANIES = os.path.join(os.path.dirname(__file__), "..", "data", "vault", "companies")
DEFAULT_ARCHIVE = os.path.join(os.path.dirname(__file__), "..", "data", "vault", "_archive")

# 代码前缀：A 股 6 位，港股 5 位；统一用浮点意义区分（长度注入 key）
CODE_RE = re.compile(r"^(\d{5,6})")


def extract_code(name: str):
    """提取精确代码前缀。返回 (code_len, code) 元组作为 key，严格区分 5/6 位。"""
    m = CODE_RE.match(name.strip())
    if not m:
        return None
    code = m.group(1)
    return (len(code), code)


def normalize_name(name: str) -> str:
    """规范化目录名：去首尾空格、折叠全角/半角空格、去全角空格。"""
    n = name.strip()
    n = n.replace("\u3000", " ")  # 全角空格 -> 半角
    n = re.sub(r"\s+", " ", n)    # 折叠连续空格
    return n


def is_canonical(name: str) -> bool:
    """判断是否为规范目录名：`代码_公司名` 且内部无多余空格。"""
    n = normalize_name(name)
    if "_" not in n:
        return False
    code_part, company = n.split("_", 1)
    if not CODE_RE.match(code_part):
        return False
    # 无多余空格（公司名内部不应有空格）
    if " " in company:
        return False
    return True


def scan() -> dict:
    """扫描目录，建立 code_key -> [dirs] 映射。"""
    groups: dict = defaultdict(list)
    for name in sorted(os.listdir(VAULT_COMPANIES)):
        path = os.path.join(VAULT_COMPANIES, name)
        if not os.path.isdir(path):
            continue
        key = extract_code(name)
        if key is None:
            groups[("noncode", None)].append(name)
        else:
            groups[key].append(name)
    return groups


def plan() -> dict:
    """生成去重计划（不动文件系统）。"""
    groups = scan()
    report = {
        "total_dirs": 0,
        "groups": [],
        "duplicates_to_archive": [],
        "noncode_dirs": [],
        "warnings": [],
    }
    for name in os.listdir(VAULT_COMPANIES):
        if os.path.isdir(os.path.join(VAULT_COMPANIES, name)):
            report["total_dirs"] += 1

    for key, names in groups.items():
        if key[0] == "noncode":
            report["noncode_dirs"].extend(names)
            continue
        if len(names) <= 1:
            continue
        # 选择规范名目录为保留项
        canonical = [n for n in names if is_canonical(n)]
        if canonical:
            keep = canonical[0]
        else:
            # 无规范名，保留最名（含公司名）者，否则保留第一个
            with_name = [n for n in names if "_" in n]
            keep = (with_name or names)[0]
        dupes = [n for n in names if n != keep]
        report["groups"].append({
            "code_key": key,
            "keep": keep,
            "dupes": dupes,
        })
        for d in dupes:
            report["duplicates_to_archive"].append(d)
    return report


def apply(report: dict, archive_dir: str, verbose: bool = True) -> None:
    """执行移动：将重复目录移入 _archive/。"""
    os.makedirs(archive_dir, exist_ok=True)
    moved = 0
    for g in report["groups"]:
        keep = g["keep"]
        for d in g["dupes"]:
            src = os.path.join(VAULT_COMPANIES, d)
            dst = os.path.join(archive_dir, d)
            # 目标已存在则加后缀
            if os.path.exists(dst):
                dst = f"{dst}_{moved}"
            shutil.move(src, dst)
            moved += 1
            if verbose:
                print(f"  [move] {d} -> _archive/ (keep: {keep})")
    print(f"\nMoved {moved} duplicate dirs to {archive_dir}")
    return moved


def main() -> int:
    parser = argparse.ArgumentParser(description="vault companies 目录去重治理")
    parser.add_argument("--apply", action="store_true", help="执行移动（默认仅 dry-run 报告）")
    parser.add_argument("--archive-dir", default=DEFAULT_ARCHIVE, help="归档目录")
    parser.add_argument("--verbose", action="store_true", default=True)
    args = parser.parse_args()

    report = plan()
    print(f"vault companies 总目录数: {report['total_dirs']}")
    print(f"非代码目录（未处理）: {len(report['noncode_dirs'])}")
    print(f"涉及重复的代码组: {len(report['groups'])}")
    print(f"待归档重复目录: {len(report['duplicates_to_archive'])}")

    print("\n=== 重复组明细（前 30） ===")
    for g in report["groups"][:30]:
        print(f"  [{g['code_key'][1]}] keep={g['keep']} | dupes={g['dupes']}")

    if not args.apply:
        print("\n[dry-run] 未执行任何改动。加 --apply 执行合并。")
        return 0

    print(f"\n=== 执行归档到 {args.archive_dir} ===")
    apply(report, args.archive_dir, verbose=args.verbose)
    return 0


if __name__ == "__main__":
    sys.exit(main())