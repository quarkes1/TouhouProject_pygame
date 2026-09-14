"""固定步长累积器。

逻辑恒以固定时长推进，与真实帧率解耦。这里只实现「给定真实经过时间，
应该跑几步」这个纯决策逻辑，不碰 pygame，因此可以被完整单元测试——
主循环里唯一难测的部分就是它。

用法：

    accumulator = FixedStepAccumulator(STEP_SECONDS, MAX_STEPS_PER_FRAME)
    while running:
        realDelta = clock.tick() / 1000
        for _ in range(accumulator.advance(realDelta)):
            world.update()
        render()
"""

# 统一开启延迟注解求值。本模块暂无自引用注解，但约定如此——避免将来新增
# 方法签名引用自身时在导入阶段崩溃。详见 vector2.py 的同类注释。
from __future__ import annotations

from typing import Final

DEFAULT_MAX_STEPS_PER_FRAME: Final = 5


class FixedStepAccumulator:
    def __init__(
        self, stepSeconds: float, maxStepsPerFrame: int = DEFAULT_MAX_STEPS_PER_FRAME
    ) -> None:
        if stepSeconds <= 0:
            raise ValueError(f"步长必须为正数，收到 {stepSeconds}")
        if maxStepsPerFrame < 1:
            raise ValueError(f"单帧最大步数至少为 1，收到 {maxStepsPerFrame}")

        self.stepSeconds = stepSeconds
        self.maxStepsPerFrame = maxStepsPerFrame
        self.pendingSeconds = 0.0
        self.droppedSeconds = 0.0

    def advance(self, realDeltaSeconds: float) -> int:
        """累加真实经过时间，返回本次应执行的逻辑步数。

        超过 maxStepsPerFrame 的积压会被整段丢弃并计入 droppedSeconds。
        保留积压的话，接下来每一帧都会再次触顶，游戏会长时间处于追赶状态，
        表现为慢动作。丢弃积压等于承认「这段时间追不回来了」，
        宁可让游戏变慢也不能让它卡死。
        """
        # 负数时间视为 0。int() 是向零截断的，不守卫的话 advance(STEP * -2.5)
        # 会返回 -2 步，并把 pendingSeconds 变成一笔负数欠账，害得后面几帧少跑。
        # 正常调用传不进负数，但这个类存在的前提就是「计时不可靠时也不能出错」，
        # 所以这是补全契约，不是防御性编程。
        if realDeltaSeconds <= 0:
            return 0

        self.pendingSeconds += realDeltaSeconds
        steps = int(self.pendingSeconds / self.stepSeconds)

        if steps > self.maxStepsPerFrame:
            self.droppedSeconds += (steps - self.maxStepsPerFrame) * self.stepSeconds
            self.pendingSeconds = 0.0
            return self.maxStepsPerFrame

        self.pendingSeconds -= steps * self.stepSeconds
        return steps

    def reset(self) -> None:
        """清空积压（暂停恢复、场景切换时用）。

        只清 pendingSeconds。droppedSeconds 是累计诊断计数，不清——
        它记录的是「这局一共丢了多少时间」，重置它会抹掉有用的事实。
        """
        self.pendingSeconds = 0.0
