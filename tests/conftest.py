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
    yield
    pygame.quit()
