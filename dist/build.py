"""把游戏打包为可独立运行的 Windows 目录包。

运行：
    python dist\\build.py

产物：
    dist\\TouhouProject\\TouhouProject.exe

采用单目录模式而非单文件模式：游戏含有大量图片和音频，单目录模式无需在每次
启动时解压资源，启动更快，定位资源的问题也更直观。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIST_ROOT = PROJECT_ROOT / "dist"
PACKAGE_ROOT = DIST_ROOT / "TouhouProject"
BUILD_ROOT = PROJECT_ROOT / "build" / "pyinstaller"
ASSETS_ROOT = PROJECT_ROOT / "assets"
ENTRY_POINT = PROJECT_ROOT / "src" / "touhou" / "__main__.py"


def buildCommand() -> list[str]:
    """生成 PyInstaller 命令。"""
    return [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        "TouhouProject",
        "--distpath",
        str(DIST_ROOT),
        "--workpath",
        str(BUILD_ROOT / "work"),
        "--specpath",
        str(BUILD_ROOT / "spec"),
        "--paths",
        str(PROJECT_ROOT / "src"),
        "--add-data",
        f"{ASSETS_ROOT}{os.pathsep}assets",
        # BOSS 脚本路径来自关卡 JSON，静态分析无法发现这些动态导入。
        "--collect-submodules",
        "touhou.game.stage",
        str(ENTRY_POINT),
    ]


def main() -> None:
    """清理旧产物后，用当前解释器运行 PyInstaller。"""
    if not ENTRY_POINT.is_file():
        raise FileNotFoundError(f"找不到游戏入口：{ENTRY_POINT}")
    if not ASSETS_ROOT.is_dir():
        raise FileNotFoundError(f"找不到素材目录：{ASSETS_ROOT}")

    # 只删除明确的目录包，避免误删 dist/ 下的打包脚本或将来的其他产物。
    if PACKAGE_ROOT.exists():
        shutil.rmtree(PACKAGE_ROOT)

    command = buildCommand()

    print("开始构建：", " ".join(command))
    subprocess.run(command, check=True, cwd=PROJECT_ROOT)

    executable = PACKAGE_ROOT / "TouhouProject.exe"
    if not executable.is_file():
        raise RuntimeError(f"PyInstaller 未生成预期的可执行文件：{executable}")

    print(f"构建完成：{executable}")


if __name__ == "__main__":
    main()
