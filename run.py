"""不安装、不配环境变量，直接从源码启动游戏。

    python run.py

## 为什么要有这个文件

`python -m touhou` 要求 `touhou` 这个包能被 import，而这在源码树里**默认不成立**
——包在 `src/` 下。绕开它的三条路各有各的坑：

- `pip install -e .` 能用，但要求先有 pip、先建虚拟环境，而且它把包装进了**某个
  具体的解释器**，换台机器得再来一遍。
- `PYTHONPATH=src python -m touhou` 只在 POSIX 上成立：Windows 的 cmd 要写
  `set PYTHONPATH=src`，PowerShell 又是 `$env:PYTHONPATH="src"`——**没有一条
  三平台通用的写法**。
- 非 editable 的 `pip install .` **根本跑不起来**（实测）：包被装进 site-packages
  之后，`core/paths.py` 那套「从本文件往上数三级找项目根」的算法会指向
  site-packages 的父目录，而 `assets/` 既不在那儿、也没被打进 wheel。

所以启动方式做成一个**仓库根目录下的脚本**：把它自己所在目录的 `src/` 挂进
`sys.path` 再启动。所有路径都由 `__file__` 推出来，**没有任何写死的绝对路径**
（`tests/testRun.py` 里有一条测试守着这件事），因此拷到哪台机器、从哪个目录调用
都一样。

## 报错的顺序是刻意的

先查解释器版本、再查源码与素材在不在、再查依赖装没装，**最后**才去 import 游戏。
反过来写的话，一台机器上装着好几个 python 时，玩家最先看到的会是
`ModuleNotFoundError: pygame`，而真正的原因可能是「你这个 python 是 3.8」或者
「你只拷了 src/、没拷 assets/」。三件事都排除了再 import，报出来的就一定是真问题。

## 关于「自动装依赖」

**没有**。缺 pygame 时只打印该跑哪条命令，不会背着玩家装东西——往别人的解释器里
装包是件该由他自己点头的事（他也可能想装官方 `pygame` 而不是 `pygame-ce`）。
"""

# 为注解开启延迟求值，理由见 core/vector2.py 的同类注释
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# 最低解释器版本。**必须与 pyproject.toml 的 requires-python 一致**，
# 两边各写了一份是因为它们给不同的人看：那个给 pip 看（决定装不装得上），
# 这个给玩家看（决定报不报错）。tests/testRun.py 有一条测试比对两处，
# 改了一边忘了另一边会红。
MINIMUM_PYTHON = (3, 13)

# 全部由本文件的位置推出来，没有一处写死。`resolve()` 顺带把
# `python run.py`（相对路径）与软链接都归一化掉。
REPO_ROOT = Path(__file__).resolve().parent
SRC_DIR = REPO_ROOT / "src"
ASSETS_DIR = REPO_ROOT / "assets"


def environmentComplaint() -> str | None:
    """启动不了的原因，能跑就返回 `None`。

    返回**第一条**不满足的，而不是把所有问题列一遍：第一句通常就是解法，
    一次报八条只会盖住它。
    """
    if sys.version_info < MINIMUM_PYTHON:
        required = ".".join(str(part) for part in MINIMUM_PYTHON)
        actual = ".".join(str(part) for part in sys.version_info[:3])
        return (
            f"这个游戏需要 Python {required} 或更高版本，当前是 {actual}。\n"
            f"  解释器在：{sys.executable}\n"
            f"  换个版本重跑即可。装了多个 Python 时，写清楚用哪一个，"
            f"比如 Windows 上 `py -3.13 run.py`。"
        )

    if not (SRC_DIR / "touhou").is_dir():
        return (
            f"找不到源码目录：{SRC_DIR}\n"
            f"  run.py 要和 src/、assets/ 一起放在项目根目录下。"
            f"如果你是解压来的，确认解压时把整个目录都留下来了。"
        )

    if not ASSETS_DIR.is_dir():
        return (
            f"找不到素材目录：{ASSETS_DIR}\n"
            f"  游戏的贴图、字体、关卡数据都在 assets/ 里，缺了它连窗口都开不出来。\n"
            f"  如果你是 clone 来的，可能是用了 --filter 之类的参数漏掉了一些文件。"
        )

    if not _hasModule("pygame"):
        # 给的是**相对路径**的命令：绝对路径在这儿能跑、抄给别人就不能，
        # 而这条消息的主要用途正是被抄走。当前用的是哪个解释器由上面那条
        # 版本消息负责报（那条报的是诊断信息，不是给你复制的命令）。
        return (
            "缺少依赖 pygame-ce（代码里 `import pygame` 用的就是它）。\n"
            "  在项目根目录下执行：python -m pip install -r requirements.txt\n"
            "  已经装了官方 pygame 的话也能跑（API 完全兼容），缺的只是 pygame-ce。"
        )

    return None


def _hasModule(name: str) -> bool:
    """这个模块能不能 import 到。

    `find_spec` 在父包已损坏之类的情况下会抛 `ModuleNotFoundError`，
    那同样算「没有」，不该让它冒到玩家面前。
    """
    try:
        return importlib.util.find_spec(name) is not None
    except ImportError:
        return False


def main() -> int:
    """启动游戏。返回退出码：0 = 正常玩完，1 = 起不来（原因已打在屏幕上）。"""
    complaint = environmentComplaint()
    if complaint is not None:
        print(complaint, file=sys.stderr)
        return 1

    # 只插这一条路径，不改 PYTHONPATH，也不装包——进程退出即消失，对机器零影响。
    # 插在最前面：万一别处也有一份叫 touhou 的包，用眼前这份。
    sys.path.insert(0, str(SRC_DIR))

    # 到这里环境已经验过，所以这里的 import 失败一定是别的问题（代码本身坏了），
    # 让它带着完整的 traceback 抛出来——那种错误需要的是堆栈，不是提示语。
    from touhou.main import main as launchGame

    launchGame()
    return 0


if __name__ == "__main__":
    sys.exit(main())
