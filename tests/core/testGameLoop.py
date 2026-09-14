"""固定步长累积器。

弹幕游戏的一切都建立在「第 N 帧」这个概念上。变步长会导致：不同机器上
弹幕速度不一致；帧率抖动时高速子弹单帧跨过判定点造成穿透；录像无法复现。
详见设计文档 §5.1。
"""

import pytest

from touhou.core.gameLoop import FixedStepAccumulator

STEP = 1.0 / 60


@pytest.fixture
def accumulator() -> FixedStepAccumulator:
    return FixedStepAccumulator(stepSeconds=STEP, maxStepsPerFrame=5)


def testExactlyOneStepElapsedRunsOneStep(accumulator):
    assert accumulator.advance(STEP) == 1


def testThreeStepsElapsedRunsThreeSteps(accumulator):
    assert accumulator.advance(STEP * 3) == 3


def testLessThanOneStepRunsNothing(accumulator):
    assert accumulator.advance(STEP * 0.5) == 0


def testFractionalTimeAccumulatesAcrossCalls(accumulator):
    """两次各半帧，第二次应该凑出一整步。

    这条是固定步长的核心：误差不会丢失，也不会凭空多跑。
    """
    assert accumulator.advance(STEP * 0.5) == 0
    assert accumulator.advance(STEP * 0.5) == 1


def testAccumulatedRemainderIsPreserved(accumulator):
    """跑了 2 步之后剩下的零头要留着，不能丢。"""
    accumulator.advance(STEP * 2.5)
    assert accumulator.pendingSeconds == pytest.approx(STEP * 0.5)


def testLongStallIsCappedAtMaxSteps(accumulator):
    """卡顿 0.5 秒（30 帧的时长）最多只跑 5 步。

    不设上限的话这一帧要跑 30 步，渲染更慢、下一帧更卡，形成自我放大的
    死循环。宁可让游戏「变慢」也不能卡死。
    """
    assert accumulator.advance(0.5) == 5


def testCappedStallRecordsDroppedTime(accumulator):
    accumulator.advance(0.5)
    assert accumulator.droppedSeconds > 0


def testNoStallMeansNothingDropped(accumulator):
    accumulator.advance(STEP * 3)
    assert accumulator.droppedSeconds == 0.0


def testBacklogIsDiscardedAfterStallNotCarriedForward(accumulator):
    """卡顿后积压的时间要被丢弃，不能一帧帧慢慢补。

    如果积压被保留，接下来每一帧都会再次触顶，游戏会持续处于追赶状态，
    表现为长时间慢动作。
    """
    accumulator.advance(0.5)
    assert accumulator.pendingSeconds == 0.0
    assert accumulator.advance(STEP) == 1


def testRepeatedExactStepsDoNotDrift(accumulator):
    """连续 60 次精确的一帧，应该正好跑满 60 步，不能因浮点误差少跑。"""
    total = sum(accumulator.advance(STEP) for _ in range(60))
    assert total == 60
