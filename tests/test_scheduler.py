"""自動運用Schedulerのテスト。"""

from io import StringIO

from app.scheduler import run


def test_health_ready_runs_market_session() -> None:
    calls = []

    def health_runner(
        argv,
        *,
        environ,
        output,
        error_output,
    ):
        calls.append(("health", argv))
        return 0

    def market_runner(
        argv,
        *,
        environ,
        output,
        error_output,
    ):
        calls.append(("market", argv))
        return 7

    exit_code = run(
        ["--maximum-cycles", "1"],
        environ={"TEST": "1"},
        output=StringIO(),
        error_output=StringIO(),
        health_check_runner=health_runner,
        market_session_runner=market_runner,
    )

    assert exit_code == 7
    assert calls == [
        ("health", ["--maximum-cycles", "1"]),
        ("market", ["--maximum-cycles", "1"]),
    ]


def test_health_failure_stops_scheduler() -> None:
    market_calls = []

    exit_code = run(
        [],
        output=StringIO(),
        error_output=StringIO(),
        health_check_runner=(
            lambda *args, **kwargs: 1
        ),
        market_session_runner=(
            lambda *args, **kwargs: market_calls.append(1)
        ),
    )

    assert exit_code == 1
    assert market_calls == []
