"""打包脚本的关键配置。"""

import runpy
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def testBuildCollectsDynamicallyImportedStageModules():
    """关卡 JSON 里的脚本路径是动态导入，PyInstaller 必须显式收集。"""
    buildModule = runpy.run_path(str(PROJECT_ROOT / "dist" / "build.py"))

    command = buildModule["buildCommand"]()

    optionIndex = command.index("--collect-submodules")
    assert command[optionIndex + 1] == "touhou.game.stage"
