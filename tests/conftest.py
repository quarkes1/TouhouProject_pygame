"""测试全局配置。

pygame 的显示与音频子系统在没有显示器/声卡的环境下会初始化失败，
用 SDL 的 dummy 驱动顶上，这样引擎层测试不必真的开出窗口。
"""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # 必须在设置环境变量之后导入
import pytest


@pytest.fixture(scope="session", autouse=True)
def initPygame():
    pygame.init()
    # 必须建一个显示表面。Surface.convert_alpha() 需要一个已设定的像素格式，
    # 否则抛 "No convert format has been set, try display.set_mode()"。
    # 尺寸 1×1 就够——它的作用只是提供格式信息，没有测试会去读它的尺寸；
    # 真正的窗口尺寸由 main.py 自己 set_mode。
    pygame.display.set_mode((1, 1))
    yield
    pygame.quit()
