"""教学关卡的有序键位引导。"""

from __future__ import annotations

from dataclasses import dataclass

import pygame


@dataclass(frozen=True, slots=True)
class TutorialStep:
    prompt: str
    keys: frozenset[int]


class TutorialController:
    """只跟踪教学进度；实际操作仍由正常游戏系统处理。"""

    steps = (
        TutorialStep(
            "MOVE WITH ARROW KEYS",
            frozenset((pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN)),
        ),
        TutorialStep("HOLD SHIFT FOR FOCUS", frozenset((pygame.K_LSHIFT, pygame.K_RSHIFT))),
        TutorialStep("PRESS Z TO SHOOT", frozenset((pygame.K_z,))),
        TutorialStep("PRESS X TO USE A BOMB", frozenset((pygame.K_x,))),
        TutorialStep("PRESS ESC TO PAUSE", frozenset((pygame.K_ESCAPE,))),
    )

    def __init__(self) -> None:
        self.stepIndex = 0

    @property
    def completed(self) -> bool:
        return self.stepIndex >= len(self.steps)

    @property
    def currentPrompt(self) -> str:
        return "TRAINING COMPLETE" if self.completed else self.steps[self.stepIndex].prompt

    def observeKey(self, key: int) -> bool:
        if self.completed or key not in self.steps[self.stepIndex].keys:
            return False
        self.stepIndex += 1
        return True
