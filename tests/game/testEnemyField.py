"""敌机时刻表的完成判定。"""

import random

from touhou.core.vector2 import Vector2
from touhou.game.bulletField import BulletField
from touhou.game.enemyField import EnemyField
from touhou.game.entities.enemy import Enemy
from touhou.game.levelData import EnemySpawn, EnemyType


def makeSpawn(enemyType: EnemyType) -> EnemySpawn:
    return EnemySpawn(
        frame=10,
        enemyType=enemyType,
        path=(Vector2(100, 100),),
        durationFrames=60,
        hp=1,
        clearOnDeath=False,
        attacks=(),
    )


def testPendingSpawnMeansScheduleIsNotComplete(enemyType):
    field = EnemyField((makeSpawn(enemyType),), random.Random(0))
    assert not field.scheduleComplete()


def testActiveEnemyMeansScheduleIsNotComplete(enemyType):
    spawn = makeSpawn(enemyType)
    field = EnemyField((spawn,), random.Random(0))
    field.spawnCursor = 1
    field.active.append(Enemy(spawn))
    assert not field.scheduleComplete()


def testExhaustedEmptyScheduleIsComplete():
    field = EnemyField((), random.Random(0))
    field.update(BulletField(), Vector2.zero())
    assert field.scheduleComplete()
