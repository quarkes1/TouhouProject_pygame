"""分层约束：core/ 不得依赖 game/。

core/ 是「任何弹幕射击游戏都能用」的部分，game/ 才知道自己在做东方。
这条边界是 core/ 能脱离 pygame 窗口被独立测试的前提。
详见设计文档 §4.1。
"""

import ast
from pathlib import Path

import touhou

CORE_DIR = Path(touhou.__file__).parent / "core"


def collectGameImports(path: Path) -> list[str]:
    """找出一个文件里所有指向 touhou.game 的 import。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "touhou.game" or alias.name.startswith("touhou.game."):
                    found.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "touhou.game" or module.startswith("touhou.game."):
                found.append(f"from {module} import ...")
    return found


def testCoreDoesNotImportGame():
    offenders = []
    for path in CORE_DIR.rglob("*.py"):
        for badImport in collectGameImports(path):
            offenders.append(f"{path.relative_to(CORE_DIR)}: {badImport}")
    assert offenders == [], f"core/ 不得依赖 game/，违规：{offenders}"
