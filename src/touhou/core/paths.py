"""资源路径解析。

开发环境下资源在项目根的 assets/ 下，相对本文件往上数三级：
    src/touhou/core/paths.py -> core -> touhou -> src -> 项目根

pyinstaller 打包后 __file__ 指向临时解压目录，路径结构完全不同，
改用 sys._MEIPASS。两种环境必须分开处理，否则打包出来的游戏一启动
就找不到素材。
"""
import sys
from pathlib import Path


def isFrozen() -> bool:
    """是否运行在 pyinstaller 打包出的可执行文件里。

    pyinstaller 会在运行时注入 sys.frozen，开发环境下该属性不存在。
    """
    return getattr(sys, "frozen", False)


def projectRoot() -> Path:
    """项目根目录。打包后是临时解压目录。"""
    if isFrozen():
        # _MEIPASS 由 pyinstaller 在运行时注入，类型检查器不知道它存在，
        # 所以必须用 getattr 取——直接写 sys._MEIPASS 会让 mypy strict 报
        # attr-defined。而 getattr 传字面量属性名又会被 ruff 的 B009 拦下，
        # 两个工具的要求正好相反，因此这里必须显式豁免 B009。
        return Path(getattr(sys, "_MEIPASS"))  # noqa: B009
    return Path(__file__).resolve().parents[3]


def assetPath(*parts: str) -> Path:
    """拼出 assets/ 下某个资源的绝对路径。

    用法：
        assetPath("sprites", "entities", "marisa_forward.png")
    """
    return projectRoot() / "assets" / Path(*parts)
