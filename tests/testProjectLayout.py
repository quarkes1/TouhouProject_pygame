"""分层约束：core/ 不得依赖 game/。

core/ 是「任何弹幕射击游戏都能用」的部分，game/ 才知道自己在做东方。
这条边界是 core/ 能脱离 pygame 窗口被独立测试的前提。
详见 docs/DESIGN.md「分层」。
"""

import ast
from pathlib import Path

import touhou

CORE_DIR = Path(touhou.__file__).parent / "core"
PACKAGE_ROOT = Path(touhou.__file__).parent


def packagePartsOf(path: Path) -> list[str]:
    """文件所属的包，按组件拆开（core/display.py -> ["touhou", "core"]）。"""
    return ["touhou", *path.relative_to(PACKAGE_ROOT).parts[:-1]]


def resolveImport(module: str | None, level: int, aliasName: str, packageParts: list[str]) -> str:
    """把一条 ImportFrom 还原成它实际指向的模块全名。

    相对导入（level > 0）以文件所在包为基准回退 level - 1 层：在 touhou.core
    下，from ..game import X（level=2）解析到 touhou.game。还原出全名后才能
    用同一套前缀判断，否则 from ..game、from touhou import game 这类写法
    都会从眼皮底下漏过去。
    """
    if level == 0:
        parts = ([module] if module else []) + [aliasName]
    else:
        baseParts = packageParts[: len(packageParts) - (level - 1)]
        parts = baseParts + ([module] if module else []) + [aliasName]
    return ".".join(part for part in parts if part)


def touchesGame(resolved: str) -> bool:
    return resolved == "touhou.game" or resolved.startswith("touhou.game.")


def collectGameImports(path: Path) -> list[str]:
    """找出一个文件里所有指向 touhou.game 的 import。

    覆盖三种形态：绝对导入（import touhou.game / from touhou.game import X）、
    相对导入（from ..game import X，包括 from .. import game），以及
    from touhou import game 这种从包名取子包的写法。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    packageParts = packagePartsOf(path)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if touchesGame(alias.name):
                    found.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                resolved = resolveImport(node.module, node.level, alias.name, packageParts)
                if touchesGame(resolved):
                    found.append(f"from {resolved} import ...")
    return found


def testCoreDoesNotImportGame():
    offenders = []
    for path in CORE_DIR.rglob("*.py"):
        for badImport in collectGameImports(path):
            offenders.append(f"{path.relative_to(CORE_DIR)}: {badImport}")
    assert offenders == [], f"core/ 不得依赖 game/，违规：{offenders}"
