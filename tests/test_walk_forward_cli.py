"""Walk-Forward CLI統合のテスト。"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.backtest.composite_score_models import (
    CompositeScoreWeights,
)
from app.backtest.historical_models import (
    HistoricalBar,
    HistoricalBarSeries,
    MarketTimeframe,
)
from app.backtest.run_backtest import (
    main,
    run_walk_forward,
)


JST = ZoneInfo("Asia/Tokyo")


def create_series(
    trading_day_count: int = 6,
) -> HistoricalBarSeries:
    """指定日数・各日1本の5分足系列を作成する。"""

    start = datetime(
        2026,
        7,
        1,
        9,
        0,
        tzinfo=JST,
    )

    return HistoricalBarSeries(
        code="7203",
        timeframe=MarketTimeframe.MINUTE_5,
        bars=tuple(
            HistoricalBar(
                code="7203",
                timeframe=MarketTimeframe.MINUTE_5,
                opened_at=start + timedelta(days=index),
                open_price=1000.0 + index,
                high_price=1010.0 + index,
                low_price=990.0 + index,
                close_price=1005.0 + index,
                volume=1000.0,
            )
            for index in range(trading_day_count)
        ),
    )


def base_arguments(
    report_directory: Path,
) -> list[str]:
    """Walk-Forward CLIの最小引数を返す。"""

    return [
        "--code",
        "7203",
        "--from",
        "2026-07-01",
        "--to",
        "2026-07-06",
        "--database",
        "market.db",
        "--walk-forward",
        "--training-days",
        "4",
        "--validation-days",
        "2",
        "--step-days",
        "1",
        "--walk-forward-report",
        str(report_directory),
        "--stop-loss-candidates",
        "0.01",
        "--take-profit-candidates",
        "0.02",
        "--opening-range-end-candidates",
        "09:15",
    ]


def test_cli_routes_walk_forward_arguments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CLI引数をWalk-Forward実行関数へ渡す。"""

    report_directory = tmp_path / "walk-forward"
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "app.backtest.run_backtest.load_series",
        lambda **_kwargs: create_series(),
    )

    def fake_run_walk_forward(**kwargs) -> int:
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(
        "app.backtest.run_backtest.run_walk_forward",
        fake_run_walk_forward,
    )

    exit_code = main(
        base_arguments(report_directory)
    )

    assert exit_code == 0
    assert captured["report_directory"] == report_directory
    assert captured["training_days"] == 4
    assert captured["validation_days"] == 2
    assert captured["step_days"] == 1
    assert captured["ranking_method"] == "net_profit"
    assert captured["stop_loss_candidates"] == (0.01,)
    assert captured["take_profit_candidates"] == (0.02,)
    assert (
        captured["opening_range_end_candidates"][0]
        .isoformat(timespec="minutes")
        == "09:15"
    )


def test_cli_supports_composite_walk_forward(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Compositeランキングと重みをCLIから渡す。"""

    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "app.backtest.run_backtest.load_series",
        lambda **_kwargs: create_series(),
    )

    def fake_run_walk_forward(**kwargs) -> int:
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(
        "app.backtest.run_backtest.run_walk_forward",
        fake_run_walk_forward,
    )

    arguments = base_arguments(tmp_path)
    arguments.extend(
        [
            "--ranking",
            "composite",
            "--weight-net-profit",
            "4",
            "--weight-profit-factor",
            "3",
            "--weight-win-rate",
            "2",
            "--weight-drawdown",
            "1",
        ]
    )

    assert main(arguments) == 0
    assert captured["ranking_method"] == "composite"

    weights = captured["composite_weights"].normalized
    assert weights.net_profit == pytest.approx(0.4)
    assert weights.profit_factor == pytest.approx(0.3)
    assert weights.win_rate == pytest.approx(0.2)
    assert weights.maximum_drawdown == pytest.approx(0.1)


def test_cli_rejects_optimize_with_walk_forward(
    tmp_path: Path,
) -> None:
    """通常最適化とWalk-Forwardの同時指定を拒否する。"""

    arguments = base_arguments(tmp_path)
    arguments.append("--optimize")

    with pytest.raises(SystemExit):
        main(arguments)


def test_cli_rejects_save_best_with_walk_forward(
    tmp_path: Path,
) -> None:
    """Walk-Forwardで--save-bestを指定できない。"""

    arguments = base_arguments(tmp_path)
    arguments.append("--save-best")

    with pytest.raises(SystemExit):
        main(arguments)


def test_run_walk_forward_rejects_short_series(
    tmp_path: Path,
) -> None:
    """必要取引日数に満たない系列を拒否する。"""

    with pytest.raises(
        ValueError,
        match="ウィンドウを作成できません",
    ):
        run_walk_forward(
            series=create_series(3),
            report_directory=tmp_path,
            initial_cash=1_000_000.0,
            quantity=100,
            force_exit_time=datetime.strptime(
                "15:30",
                "%H:%M",
            ).time(),
            commission=0.0,
            slippage_rate=0.0,
            stop_loss_candidates=(0.01,),
            take_profit_candidates=(0.02,),
            opening_range_end_candidates=(
                datetime.strptime(
                    "09:15",
                    "%H:%M",
                ).time(),
            ),
            ranking_method="net_profit",
            composite_weights=CompositeScoreWeights(),
            training_days=3,
            validation_days=2,
            step_days=None,
        )
