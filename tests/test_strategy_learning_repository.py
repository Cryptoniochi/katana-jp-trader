"""StrategyLearningRepositoryのテスト。"""

from datetime import datetime, timezone
from pathlib import Path

from app.learning.strategy_learning_models import (
    StrategyLearningRecord,
)
from app.learning.strategy_learning_repository import (
    StrategyLearningRepository,
)


def test_repository_replaces_and_loads(
    tmp_path: Path,
) -> None:
    database = tmp_path / "katana.db"
    repository = StrategyLearningRepository(
        database
    )
    now = datetime.now(timezone.utc)

    repository.replace_all(
        (
            StrategyLearningRecord(
                code="7203",
                strategy_name="pullback-breakout-v1",
                trade_count=10,
                win_count=6,
                loss_count=4,
                breakeven_count=0,
                win_rate=0.6,
                gross_profit=30000.0,
                gross_loss=-12000.0,
                net_profit_loss=18000.0,
                profit_factor=2.5,
                expectancy=1800.0,
                average_return_rate=0.01,
                average_holding_minutes=30.0,
                sample_confidence=0.5,
                historical_score=8.0,
                eligible_for_feedback=True,
                updated_at=now,
            ),
        )
    )

    loaded = repository.load_for_code("7203")

    assert len(loaded) == 1
    assert loaded[0].historical_score == 8.0
    assert loaded[0].eligible_for_feedback
