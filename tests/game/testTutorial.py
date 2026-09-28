"""可游玩教学关卡的步骤控制。"""

import pygame

from touhou.game.tutorial import TutorialController


def testTutorialAdvancesOnlyInOrder():
    tutorial = TutorialController()

    assert not tutorial.observeKey(pygame.K_z)
    for key in (pygame.K_LEFT, pygame.K_LSHIFT, pygame.K_z, pygame.K_x, pygame.K_ESCAPE):
        assert tutorial.observeKey(key)

    assert tutorial.completed
    assert not tutorial.observeKey(pygame.K_ESCAPE)


def testTutorialAcceptsEveryArrowKey():
    for key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN):
        tutorial = TutorialController()
        assert tutorial.observeKey(key)


def testTutorialAcceptsEitherShiftKey():
    for key in (pygame.K_LSHIFT, pygame.K_RSHIFT):
        tutorial = TutorialController()
        tutorial.observeKey(pygame.K_UP)
        assert tutorial.observeKey(key)


def testCurrentPromptTracksTheNextRequiredAction():
    tutorial = TutorialController()

    assert tutorial.currentPrompt == "MOVE WITH ARROW KEYS"
    tutorial.observeKey(pygame.K_UP)
    assert tutorial.currentPrompt == "HOLD SHIFT FOR FOCUS"
