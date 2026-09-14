"""资源路径解析。

开发环境下资源在项目根的 assets/ 下；pyinstaller 打包后 __file__ 指向
临时解压目录，两者结构完全不同，必须分开处理。
"""
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


def testLevelDataIsReachable():
    """关卡数据也要能通过同一套路径解析找到。"""
    path = paths.assetPath("levels", "level_1.json")
    assert path.is_file()
