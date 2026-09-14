"""资源路径解析。

开发环境下资源在项目根的 assets/ 下；pyinstaller 打包后 __file__ 指向
临时解压目录，两者结构完全不同，必须分开处理。
"""

import sys
from pathlib import Path

from touhou.core import paths


def testAssetPathPointsAtRealFile():
    """拿一个确实存在的素材验证路径拼对了。"""
    path = paths.assetPath("fonts", "DFPPOPCorn-W12.ttf")
    assert path.is_file(), f"路径解析错误，找不到 {path}"


def testAssetPathKeepsNestingOrder():
    path = paths.assetPath("sprites", "entities", "fairy_0.png")
    assert path.name == "fairy_0.png"
    assert path.parent.name == "entities"
    assert path.parent.parent.name == "sprites"
    assert path.parent.parent.parent.name == "assets"


def testAssetPathReturnsAbsolutePath():
    """必须是绝对路径——游戏可能从任意工作目录启动。"""
    assert paths.assetPath("fonts", "DFPPOPCorn-W12.ttf").is_absolute()


def testProjectRootContainsAssetsDirectory():
    assert (paths.projectRoot() / "assets").is_dir()


def testNotFrozenWhenNotPackaged():
    assert paths.isFrozen() is False


def testProjectRootUsesMeiPassWhenFrozen(monkeypatch):
    """打包后必须改用 pyinstaller 的临时解压目录。

    这条分支在开发环境下永远走不到，而它恰恰是 paths.py 存在的全部理由——
    没有它，打包出来的游戏一启动就找不到素材。所以必须用 monkeypatch
    模拟 sys.frozen 与 sys._MEIPASS 把它覆盖到，不能只靠人肉验证。
    """
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", "/fake/meipass", raising=False)

    assert paths.isFrozen() is True
    assert paths.projectRoot() == Path("/fake/meipass")


def testLevelDataIsReachable():
    """关卡数据也要能通过同一套路径解析找到。"""
    path = paths.assetPath("levels", "level_1.json")
    assert path.is_file()
