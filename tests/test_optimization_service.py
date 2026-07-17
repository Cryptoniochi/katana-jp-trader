"""ORB最適化グリッドのテスト。"""

from datetime import time

import pytest

from app.backtest.optimization_models import (
    OrbOptimizationGrid,
    OrbOptimizationParameters,
)
from app.backtest.optimization_service import (
    OrbOptimizationGridService,
)


def test_service_creates_cartesian_product() -> None:
    """候補値の直積を安定した順序で生成する。"""

    grid = OrbOptimizationGridService().create_grid(
        stop_loss_rates=(0.01, 0.02),
        take_profit_rates=(0.03, 0.04),
        opening_range_ends=(
            time(9, 10),
            time(9, 15),
        ),
    )

    assert grid.combination_count == 8
    assert grid.parameters[0] == (
        OrbOptimizationParameters(
            stop_loss_rate=0.01,
            take_profit_rate=0.03,
            opening_range_end=time(9, 10),
        )
    )
    assert grid.parameters[-1] == (
        OrbOptimizationParameters(
            stop_loss_rate=0.02,
            take_profit_rate=0.04,
            opening_range_end=time(9, 15),
        )
    )


def test_service_keeps_none_as_valid_candidate() -> None:
    """損切り・利確なしを候補として扱える。"""

    grid = OrbOptimizationGridService().create_grid(
        stop_loss_rates=(None, 0.02),
        take_profit_rates=(None,),
        opening_range_ends=(time(9, 15),),
    )

    assert grid.combination_count == 2
    assert grid.parameters[0].stop_loss_rate is None
    assert grid.parameters[0].take_profit_rate is None


def test_service_removes_duplicate_candidates() -> None:
    """同一候補を重複除去する。"""

    grid = OrbOptimizationGridService().create_grid(
        stop_loss_rates=(0.02, 0.02),
        take_profit_rates=(0.04, 0.04),
        opening_range_ends=(
            time(9, 15),
            time(9, 15),
        ),
    )

    assert grid.combination_count == 1


def test_parameter_id_is_stable() -> None:
    """同一パラメータから同じIDを生成する。"""

    parameter = OrbOptimizationParameters(
        stop_loss_rate=0.02,
        take_profit_rate=0.04,
        opening_range_end=time(9, 15),
    )

    assert parameter.parameter_id == (
        "sl-0p02_tp-0p04_or-0915"
    )


def test_parameter_id_supports_none() -> None:
    """未設定率をIDへ含める。"""

    parameter = OrbOptimizationParameters(
        stop_loss_rate=None,
        take_profit_rate=None,
        opening_range_end=time(9, 5),
    )

    assert parameter.parameter_id == (
        "sl-none_tp-none_or-0905"
    )


def test_grid_get_returns_parameter() -> None:
    """パラメータIDから組み合わせを取得する。"""

    parameter = OrbOptimizationParameters(
        stop_loss_rate=0.02,
        take_profit_rate=0.04,
        opening_range_end=time(9, 15),
    )
    grid = OrbOptimizationGrid(
        parameters=(parameter,)
    )

    assert grid.get(parameter.parameter_id) == parameter


def test_grid_get_rejects_unknown_id() -> None:
    """存在しないIDを拒否する。"""

    grid = OrbOptimizationGrid(parameters=())

    with pytest.raises(KeyError, match="存在しません"):
        grid.get("missing")


@pytest.mark.parametrize(
    "arguments",
    [
        {
            "stop_loss_rates": (),
            "take_profit_rates": (0.04,),
            "opening_range_ends": (time(9, 15),),
        },
        {
            "stop_loss_rates": (0.02,),
            "take_profit_rates": (),
            "opening_range_ends": (time(9, 15),),
        },
        {
            "stop_loss_rates": (0.02,),
            "take_profit_rates": (0.04,),
            "opening_range_ends": (),
        },
    ],
)
def test_service_rejects_empty_candidates(
    arguments: dict[str, object],
) -> None:
    """空の候補一覧を拒否する。"""

    with pytest.raises(ValueError, match="候補"):
        OrbOptimizationGridService().create_grid(
            **arguments
        )


def test_service_rejects_invalid_rates() -> None:
    """0以下の率を拒否する。"""

    with pytest.raises(ValueError, match="損切り率"):
        OrbOptimizationGridService().create_grid(
            stop_loss_rates=(0.0,),
            take_profit_rates=(0.04,),
            opening_range_ends=(time(9, 15),),
        )


def test_service_rejects_too_many_combinations() -> None:
    """組み合わせ件数上限を超えた場合は拒否する。"""

    with pytest.raises(ValueError, match="上限"):
        OrbOptimizationGridService().create_grid(
            stop_loss_rates=(0.01, 0.02),
            take_profit_rates=(0.03, 0.04),
            opening_range_ends=(
                time(9, 10),
                time(9, 15),
            ),
            maximum_combinations=7,
        )


def test_parameter_rejects_invalid_rate() -> None:
    """モデル単体でも不正な率を拒否する。"""

    with pytest.raises(ValueError, match="利確率"):
        OrbOptimizationParameters(
            stop_loss_rate=0.02,
            take_profit_rate=0.0,
            opening_range_end=time(9, 15),
        )
