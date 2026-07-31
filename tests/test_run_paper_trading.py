"""本番Paper Tradingランチャーのテスト。"""

from __future__ import annotations

from argparse import Namespace
from datetime import date, datetime, timezone
from io import StringIO
from pathlib import Path

import pytest

from app.run_paper_trading import (
    StopController,
    build_argument_parser,
    create_production_settings,
    create_runtime_notification_gateway,
    _extract_live_orb_diagnostics,
    _extract_market_data_diagnostics,
    _extract_paper_service_diagnostics,
    _finished_notification_message,
    _format_live_orb_diagnostics,
    _format_market_data_diagnostics,
    _format_money,
    _format_percentage,
    run,
)
from app.runtime.paper_trading_day_models import (
    PaperTradingDayStopReason,
)
from app.runtime.paper_trading_runtime_models import (
    PaperTradingDailySummary,
    PaperTradingRuntimeStatus,
)


NOW = datetime(
    2026,
    7,
    22,
    0,
    0,
    tzinfo=timezone.utc,
)


class FakeRecord:
    """ランチャーテスト用の日次保存レコード。"""

    trading_date = NOW.date()
    status = PaperTradingRuntimeStatus.COMPLETED
    created_at = NOW
    updated_at = NOW


class FakeResult:
    """ランチャーが参照する終日運用結果。"""

    def __init__(
        self,
        *,
        stop_reason=(
            PaperTradingDayStopReason.MARKET_CLOSED
        ),
        error_message: str | None = None,
    ) -> None:
        self.trading_date = date(2026, 7, 22)
        self.started_at = NOW
        self.completed_at = NOW
        self.stop_reason = stop_reason
        self.summary = PaperTradingDailySummary(
            trading_date=NOW.date(),
            started_at=NOW,
            completed_at=NOW,
            status=(
                PaperTradingRuntimeStatus.FAILED
                if stop_reason
                is PaperTradingDayStopReason.ERROR
                else PaperTradingRuntimeStatus.COMPLETED
            ),
            records=(),
            initial_equity=10_000_000.0,
            final_equity=10_100_000.0,
            error_message=error_message,
        )
        self.record = FakeRecord()
        self.error_message = error_message
        self.dashboard_published = False
        self.dashboard_error_message = None
        self.completed_post_run_hook_count = 0
        self.post_run_hook_error_messages = ()

    @property
    def cycle_count(self) -> int:
        return self.summary.cycle_count

    @property
    def net_profit_loss(self) -> float | None:
        return self.summary.net_profit_loss

    @property
    def return_rate(self) -> float | None:
        return self.summary.return_rate


class FakeBundle:
    """実行結果または例外を返すApplication Bundle。"""

    def __init__(
        self,
        result: FakeResult | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.result = (
            result
            if result is not None
            else FakeResult()
        )
        self.error = error
        self.run_count = 0

    def run(self):
        self.run_count += 1

        if self.error is not None:
            raise self.error

        return self.result


class FakeCompositionFactory:
    """Composition生成引数を記録するFactory。"""

    settings = None
    stop_requested = None
    bundle = FakeBundle()

    @classmethod
    def reset(
        cls,
        *,
        bundle: FakeBundle | None = None,
    ) -> None:
        cls.settings = None
        cls.stop_requested = None
        cls.bundle = (
            bundle
            if bundle is not None
            else FakeBundle()
        )

    @classmethod
    def create(
        cls,
        *,
        settings,
        now_provider=None,
        stop_requested=None,
    ):
        cls.settings = settings
        cls.stop_requested = stop_requested
        return cls.bundle



class FakeNotificationGateway:
    """Runtime通知要求を記録するFake Gateway。"""

    def __init__(
        self,
        *,
        error: Exception | None = None,
    ) -> None:
        self.error = error
        self.requests = []
        self.continue_on_error_values = []

    def send(
        self,
        request,
        *,
        continue_on_error=True,
    ):
        self.requests.append(request)
        self.continue_on_error_values.append(
            continue_on_error
        )

        if self.error is not None:
            raise self.error

        return object()


def no_notification_gateway(_environ):
    """外部通知なしのテスト用Factory。"""

    return None

def create_watchlist(
    tmp_path: Path,
) -> Path:
    """テスト用Watch Listを作成する。"""

    path = tmp_path / "watchlist.txt"
    path.write_text(
        "7203\n6758\n",
        encoding="utf-8",
    )
    return path


def test_stop_controller_records_request() -> None:
    """停止要求状態を保持する。"""

    controller = StopController()

    assert controller() is False
    assert controller.is_stop_requested is False

    controller.request_stop()

    assert controller() is True
    assert controller.is_stop_requested is True


def test_parser_accepts_direct_codes() -> None:
    """複数の直接指定銘柄を読み込む。"""

    parser = build_argument_parser()

    arguments = parser.parse_args(
        [
            "--code",
            "7203",
            "--code",
            "6758",
            "--maximum-cycles",
            "10",
        ]
    )

    assert arguments.code == [
        "7203",
        "6758",
    ]
    assert arguments.maximum_cycles == 10


def test_settings_loads_codes_from_watchlist(
    tmp_path: Path,
) -> None:
    """直接指定がない場合はWatch Listを使用する。"""

    watchlist_path = create_watchlist(
        tmp_path
    )
    parser = build_argument_parser()
    arguments = parser.parse_args(
        [
            "--watchlist",
            str(watchlist_path),
        ]
    )

    settings = create_production_settings(
        arguments,
        environ={"KABU_STATION_API_PASSWORD": "secret"},
    )

    assert settings.codes == (
        "7203",
        "6758",
    )
    assert settings.database_path == Path(
        "data/katana.db"
    )


def test_direct_codes_override_watchlist(
    tmp_path: Path,
) -> None:
    """直接指定銘柄はWatch Listより優先される。"""

    missing_watchlist = (
        tmp_path / "missing.txt"
    )
    parser = build_argument_parser()
    arguments = parser.parse_args(
        [
            "--watchlist",
            str(missing_watchlist),
            "--code",
            "9984",
        ]
    )

    settings = create_production_settings(
        arguments,
        environ={"KABU_STATION_API_PASSWORD": "secret"},
    )

    assert settings.codes == ("9984",)


def test_settings_reads_environment_values(
    tmp_path: Path,
) -> None:
    """環境変数から本番設定を読み込む。"""

    watchlist_path = create_watchlist(
        tmp_path
    )
    parser = build_argument_parser()
    arguments = parser.parse_args([])

    settings = create_production_settings(
        arguments,
        environ={
            "KABU_STATION_API_PASSWORD": "secret",
            "KATANA_DATABASE_PATH": str(
                tmp_path / "katana.db"
            ),
            "KATANA_WATCHLIST_PATH": str(
                watchlist_path
            ),
            "KATANA_INITIAL_CASH": "5000000",
            "KATANA_CYCLE_INTERVAL_SECONDS": "15",
            "KATANA_COMMISSION_PER_ORDER": "100",
            "KATANA_SLIPPAGE_RATE": "0.001",
        },
    )

    assert settings.database_path == (
        tmp_path / "katana.db"
    )
    assert settings.initial_cash == 5_000_000.0
    assert settings.cycle_interval_seconds == 15.0
    assert settings.commission_per_order == 100.0
    assert settings.slippage_rate == 0.001


def test_settings_rejects_invalid_environment_number(
    tmp_path: Path,
) -> None:
    """数値ではない環境変数を拒否する。"""

    watchlist_path = create_watchlist(
        tmp_path
    )
    parser = build_argument_parser()
    arguments = parser.parse_args([])

    with pytest.raises(
        ValueError,
        match="KATANA_INITIAL_CASH",
    ):
        create_production_settings(
            arguments,
            environ={
                "KATANA_WATCHLIST_PATH": str(
                    watchlist_path
                ),
                "KATANA_INITIAL_CASH": "invalid",
            },
        )


def test_run_creates_composition_and_executes_bundle(
    tmp_path: Path,
) -> None:
    """設定をCompositionへ渡して運用を実行する。"""

    watchlist_path = create_watchlist(
        tmp_path
    )
    bundle = FakeBundle(
        FakeResult(
            stop_reason=(
                PaperTradingDayStopReason
                .MAX_CYCLES_REACHED
            )
        )
    )
    FakeCompositionFactory.reset(
        bundle=bundle
    )
    output = StringIO()
    error_output = StringIO()

    exit_code = run(
        [
            "--database-path",
            str(tmp_path / "katana.db"),
            "--watchlist",
            str(watchlist_path),
            "--maximum-cycles",
            "1",
        ],
        composition_factory=(
            FakeCompositionFactory
        ),
        environ={"KABU_STATION_API_PASSWORD": "secret"},
        output=output,
        error_output=error_output,
        install_signals=False,
        notification_gateway_factory=(
            no_notification_gateway
        ),
    )

    assert exit_code == 0
    assert bundle.run_count == 1
    assert FakeCompositionFactory.settings is not None
    assert (
        FakeCompositionFactory
        .settings
        .database_path
        == tmp_path / "katana.db"
    )
    assert (
        FakeCompositionFactory.settings.codes
        == ("7203", "6758")
    )
    assert callable(
        FakeCompositionFactory.stop_requested
    )
    assert "Project KATANA" in output.getvalue()
    assert (
        "stop_reason=max_cycles_reached"
        in output.getvalue()
    )
    assert error_output.getvalue() == ""


@pytest.mark.parametrize(
    (
        "stop_reason",
        "expected_exit_code",
    ),
    [
        (
            PaperTradingDayStopReason.MARKET_CLOSED,
            0,
        ),
        (
            PaperTradingDayStopReason.STOP_REQUESTED,
            0,
        ),
        (
            PaperTradingDayStopReason.MAX_CYCLES_REACHED,
            0,
        ),
        (
            PaperTradingDayStopReason.CYCLE_FAILED,
            2,
        ),
        (
            PaperTradingDayStopReason.RESOURCE_CRITICAL,
            3,
        ),
        (
            PaperTradingDayStopReason.ERROR,
            1,
        ),
    ],
)
def test_run_returns_exit_code_for_stop_reason(
    tmp_path: Path,
    stop_reason: PaperTradingDayStopReason,
    expected_exit_code: int,
) -> None:
    """終了理由に対応したプロセス終了コードを返す。"""

    watchlist_path = create_watchlist(
        tmp_path
    )
    result = FakeResult(
        stop_reason=stop_reason,
        error_message=(
            "runtime failed"
            if stop_reason
            is PaperTradingDayStopReason.ERROR
            else None
        ),
    )
    FakeCompositionFactory.reset(
        bundle=FakeBundle(result)
    )

    exit_code = run(
        [
            "--watchlist",
            str(watchlist_path),
        ],
        composition_factory=(
            FakeCompositionFactory
        ),
        environ={"KABU_STATION_API_PASSWORD": "secret"},
        output=StringIO(),
        error_output=StringIO(),
        install_signals=False,
        notification_gateway_factory=(
            no_notification_gateway
        ),
    )

    assert exit_code == expected_exit_code


def test_run_returns_one_when_bundle_raises(
    tmp_path: Path,
) -> None:
    """Application実行例外を終了コード1へ変換する。"""

    watchlist_path = create_watchlist(
        tmp_path
    )
    FakeCompositionFactory.reset(
        bundle=FakeBundle(
            error=RuntimeError(
                "application failed"
            )
        )
    )
    error_output = StringIO()

    exit_code = run(
        [
            "--watchlist",
            str(watchlist_path),
        ],
        composition_factory=(
            FakeCompositionFactory
        ),
        environ={"KABU_STATION_API_PASSWORD": "secret"},
        output=StringIO(),
        error_output=error_output,
        install_signals=False,
        notification_gateway_factory=(
            no_notification_gateway
        ),
    )

    assert exit_code == 1
    assert (
        "application failed"
        in error_output.getvalue()
    )


def test_fail_fast_and_resource_flags_are_applied(
    tmp_path: Path,
) -> None:
    """安全運転に関するCLIフラグを設定へ反映する。"""

    watchlist_path = create_watchlist(
        tmp_path
    )
    parser = build_argument_parser()
    arguments: Namespace = parser.parse_args(
        [
            "--watchlist",
            str(watchlist_path),
            "--fail-fast",
            "--stop-on-cycle-failure",
            "--ignore-resource-critical",
        ]
    )

    settings = create_production_settings(
        arguments,
        environ={"KABU_STATION_API_PASSWORD": "secret"},
    )

    assert settings.continue_on_cycle_error is False
    assert settings.stop_on_cycle_failure is True
    assert settings.stop_on_resource_critical is False


def test_run_sends_started_and_finished_notifications(
    tmp_path: Path,
) -> None:
    """正常運用時に開始・終了通知を送る。"""

    watchlist_path = create_watchlist(
        tmp_path
    )
    FakeCompositionFactory.reset()
    gateway = FakeNotificationGateway()

    exit_code = run(
        [
            "--watchlist",
            str(watchlist_path),
        ],
        composition_factory=FakeCompositionFactory,
        environ={"KABU_STATION_API_PASSWORD": "secret"},
        output=StringIO(),
        error_output=StringIO(),
        install_signals=False,
        notification_gateway_factory=(
            lambda _environ: gateway
        ),
    )

    assert exit_code == 0
    assert len(gateway.requests) == 2
    assert gateway.requests[0].context["title"] == (
        "Paper Trading Started"
    )
    assert gateway.requests[0].metadata[
        "event_type"
    ] == "paper_trading_started"
    assert gateway.requests[1].context["title"] == (
        "Paper Trading Finished"
    )
    assert gateway.requests[1].metadata[
        "event_type"
    ] == "paper_trading_finished"
    assert gateway.continue_on_error_values == [
        True,
        True,
    ]


def test_run_sends_failure_notification_when_bundle_raises(
    tmp_path: Path,
) -> None:
    """Runtime例外をCRITICAL通知へ変換する。"""

    watchlist_path = create_watchlist(
        tmp_path
    )
    FakeCompositionFactory.reset(
        bundle=FakeBundle(
            error=RuntimeError(
                "application failed"
            )
        )
    )
    gateway = FakeNotificationGateway()

    exit_code = run(
        [
            "--watchlist",
            str(watchlist_path),
        ],
        composition_factory=FakeCompositionFactory,
        environ={"KABU_STATION_API_PASSWORD": "secret"},
        output=StringIO(),
        error_output=StringIO(),
        install_signals=False,
        notification_gateway_factory=(
            lambda _environ: gateway
        ),
    )

    assert exit_code == 1
    assert len(gateway.requests) == 2
    assert gateway.requests[1].context["title"] == (
        "Paper Trading Failed"
    )
    assert gateway.requests[1].metadata[
        "event_type"
    ] == "paper_trading_failed"


def test_notification_failure_does_not_stop_runtime(
    tmp_path: Path,
) -> None:
    """通知障害がPaper Tradingを停止させない。"""

    watchlist_path = create_watchlist(
        tmp_path
    )
    FakeCompositionFactory.reset()
    gateway = FakeNotificationGateway(
        error=RuntimeError(
            "notification unavailable"
        )
    )
    error_output = StringIO()

    exit_code = run(
        [
            "--watchlist",
            str(watchlist_path),
        ],
        composition_factory=FakeCompositionFactory,
        environ={"KABU_STATION_API_PASSWORD": "secret"},
        output=StringIO(),
        error_output=error_output,
        install_signals=False,
        notification_gateway_factory=(
            lambda _environ: gateway
        ),
    )

    assert exit_code == 0
    assert FakeCompositionFactory.bundle.run_count == 1
    assert (
        "外部通知の送信に失敗しました"
        in error_output.getvalue()
    )



def test_finished_notification_is_daily_summary() -> None:
    """終了通知に主要な日次指標を含める。"""

    result = FakeResult()

    message = _finished_notification_message(
        result
    )

    assert "Paper Trading Daily Summary" in message
    assert "取引日: 2026-07-22" in message
    assert "Runtime状態: completed" in message
    assert "サイクル数: 0" in message
    assert "シグナル数: 0" in message
    assert "約定数: 0" in message
    assert "初期純資産: 10,000,000.00円" in message
    assert "最終純資産: 10,100,000.00円" in message
    assert "日次損益: +100,000.00円" in message
    assert "日次収益率: +1.0000%" in message
    assert "エラー: なし" in message


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1000.0, "1,000.00円"),
        (-1000.0, "-1,000.00円"),
        (0.0, "0.00円"),
        (None, "N/A"),
    ],
)
def test_format_money(
    value,
    expected,
) -> None:
    """残高金額を桁区切り付きで整形する。"""

    assert _format_money(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1000.0, "+1,000.00円"),
        (-1000.0, "-1,000.00円"),
        (0.0, "0.00円"),
        (None, "N/A"),
    ],
)
def test_format_money_with_positive_sign(
    value,
    expected,
) -> None:
    """損益金額は正数へプラス記号を付ける。"""

    assert _format_money(
        value,
        show_positive_sign=True,
    ) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.012345, "+1.2345%"),
        (-0.012345, "-1.2345%"),
        (0.0, "0.0000%"),
        (None, "N/A"),
    ],
)
def test_format_percentage(
    value,
    expected,
) -> None:
    """比率を百分率表示へ整形する。"""

    assert _format_percentage(value) == expected


def test_format_live_orb_diagnostics_includes_rejection_counts() -> None:
    """実運用ORB診断を日次表示向けに整形する。"""

    from app.backtest.orb_signal_strategy import (
        OrbSignalDiagnosticSnapshot,
    )

    snapshot = OrbSignalDiagnosticSnapshot(
        evaluation_count=120,
        counts={
            "opening_range": 40,
            "no_price_breakout": 70,
            "breakout_volume_ratio": 9,
            "buy_signal": 1,
        },
    )

    message = _format_live_orb_diagnostics(snapshot)

    assert "ORB Live Diagnostics" in message
    assert "評価記録数: 120" in message
    assert "価格ブレイクなし: 70" in message
    assert "出来高倍率不足: 9" in message
    assert "BUY生成: 1" in message
    assert "主な見送り理由:" in message


def test_finished_notification_includes_live_orb_diagnostics() -> None:
    """終了通知へ実運用ORB診断を含める。"""

    from app.backtest.orb_signal_strategy import (
        OrbSignalDiagnosticSnapshot,
    )

    message = _finished_notification_message(
        FakeResult(),
        orb_diagnostics=OrbSignalDiagnosticSnapshot(
            evaluation_count=10,
            counts={
                "no_price_breakout": 9,
                "buy_signal": 1,
            },
        ),
    )

    assert "ORB Live Diagnostics" in message
    assert "価格ブレイクなし: 9" in message
    assert "BUY生成: 1" in message


def test_extract_live_orb_diagnostics_from_bundle() -> None:
    """Bundleが保持するSignal Engineから診断集計を取得する。"""

    from app.backtest.orb_signal_strategy import (
        OrbSignalDiagnosticSnapshot,
    )

    expected = OrbSignalDiagnosticSnapshot(
        evaluation_count=5,
        counts={"no_price_breakout": 5},
    )

    class FakeSignalEngine:
        def diagnostic_snapshot(self):
            return expected

    class Bundle:
        signal_engine = FakeSignalEngine()

    assert _extract_live_orb_diagnostics(Bundle()) == expected


def test_extract_live_orb_diagnostics_returns_none_when_unavailable() -> None:
    """旧Bundleなど診断未対応の場合は安全にNoneを返す。"""

    class Bundle:
        pass

    assert _extract_live_orb_diagnostics(Bundle()) is None


def test_format_market_data_diagnostics_includes_flow_counts() -> None:
    """市場データ経路診断を終了通知向けに整形する。"""

    from app.live.live_orchestrator import (
        LiveMarketDataDiagnosticSnapshot,
    )
    from app.market.realtime_paper_trading_service import (
        RealtimePaperTradingDiagnosticSnapshot,
    )

    market_snapshot = LiveMarketDataDiagnosticSnapshot(
        cycle_count=643,
        decision_counts={
            "new_bars_saved": 12,
            "no_new_bar": 631,
        },
        fetched_bar_count=5000,
        new_bar_count=120,
        saved_bar_count=120,
        paper_trading_call_count=12,
        paper_trading_input_bar_count=120,
        signal_processed_bar_count=120,
        signal_skipped_duplicate_count=0,
        signal_count=2,
    )
    paper_snapshot = RealtimePaperTradingDiagnosticSnapshot(
        process_call_count=12,
        input_bar_count=120,
        signal_engine_call_count=120,
        signal_processed_bar_count=120,
        signal_skipped_duplicate_count=0,
        signal_count=2,
        queue_count=2,
        execution_count=2,
        portfolio_update_count=2,
        failed_process_count=0,
    )

    message = _format_market_data_diagnostics(
        market_snapshot,
        paper_snapshot,
    )

    assert "Market Data Diagnostics" in message
    assert "市場監視サイクル: 643" in message
    assert "NEW_BARS_SAVED: 12" in message
    assert "取得足数: 5000" in message
    assert "Paper Trading呼出: 12" in message
    assert "Signal Engine呼出: 120" in message
    assert "処理失敗: 0" in message


def test_finished_notification_includes_market_data_diagnostics() -> None:
    """終了通知へ市場データ経路診断を含める。"""

    from app.live.live_orchestrator import (
        LiveMarketDataDiagnosticSnapshot,
    )

    message = _finished_notification_message(
        FakeResult(),
        market_data_diagnostics=LiveMarketDataDiagnosticSnapshot(
            cycle_count=1,
            decision_counts={"no_new_bar": 1},
            fetched_bar_count=10,
            new_bar_count=0,
            saved_bar_count=0,
            paper_trading_call_count=0,
            paper_trading_input_bar_count=0,
            signal_processed_bar_count=0,
            signal_skipped_duplicate_count=0,
            signal_count=0,
        ),
    )

    assert "Market Data Diagnostics" in message
    assert "NO_NEW_BAR: 1" in message
    assert "Paper Trading呼出: 0" in message


def test_extract_market_and_paper_service_diagnostics() -> None:
    """Bundleから両方のデータフロー診断を取得する。"""

    from app.live.live_orchestrator import (
        LiveMarketDataDiagnosticSnapshot,
    )
    from app.market.realtime_paper_trading_service import (
        RealtimePaperTradingDiagnosticSnapshot,
    )

    market_expected = LiveMarketDataDiagnosticSnapshot(
        cycle_count=1,
        decision_counts={"no_new_bar": 1},
        fetched_bar_count=0,
        new_bar_count=0,
        saved_bar_count=0,
        paper_trading_call_count=0,
        paper_trading_input_bar_count=0,
        signal_processed_bar_count=0,
        signal_skipped_duplicate_count=0,
        signal_count=0,
    )
    paper_expected = RealtimePaperTradingDiagnosticSnapshot(
        process_call_count=0,
        input_bar_count=0,
        signal_engine_call_count=0,
        signal_processed_bar_count=0,
        signal_skipped_duplicate_count=0,
        signal_count=0,
        queue_count=0,
        execution_count=0,
        portfolio_update_count=0,
        failed_process_count=0,
    )

    class DiagnosticObject:
        def __init__(self, snapshot):
            self.snapshot = snapshot

        def diagnostic_snapshot(self):
            return self.snapshot

    class Bundle:
        live_orchestrator = DiagnosticObject(market_expected)
        realtime_paper_trading_service = DiagnosticObject(
            paper_expected
        )

    bundle = Bundle()

    assert _extract_market_data_diagnostics(bundle) == market_expected
    assert (
        _extract_paper_service_diagnostics(bundle)
        == paper_expected
    )


def test_parser_accepts_market_data_mode() -> None:
    arguments = build_argument_parser().parse_args(
        [
            "--code",
            "7203",
            "--market-data-mode",
            "kabu-station-realtime",
        ]
    )

    assert arguments.market_data_mode == "kabu-station-realtime"


def test_settings_loads_kabu_station_environment(
    tmp_path: Path,
) -> None:
    parser = build_argument_parser()
    arguments = parser.parse_args(
        [
            "--code",
            "7203",
            "--market-data-mode",
            "kabu-station-realtime",
            "--database-path",
            str(tmp_path / "katana.db"),
        ]
    )

    settings = create_production_settings(
        arguments,
        environ={
            "KABU_STATION_API_PASSWORD": "secret",
        },
    )

    assert settings.market_data_mode == (
        "kabu-station-realtime"
    )
    assert settings.kabu_station_api_password == "secret"


def test_settings_loads_risk_limits_from_cli(
    tmp_path: Path,
) -> None:
    parser = build_argument_parser()
    arguments = parser.parse_args(
        [
            "--code",
            "7203",
            "--database-path",
            str(tmp_path / "katana.db"),
            "--max-position-count",
            "1",
            "--max-position-value",
            "100000",
            "--max-total-exposure",
            "200000",
            "--minimum-cash-balance",
            "9000000",
            "--max-daily-loss",
            "1000",
            "--max-daily-entries",
            "1",
        ]
    )

    settings = create_production_settings(
        arguments,
        environ={"KABU_STATION_API_PASSWORD": "secret"},
    )

    assert settings.max_position_count == 1
    assert settings.max_position_value == 100000
    assert settings.max_total_exposure == 200000
    assert settings.minimum_cash_balance == 9000000
    assert settings.max_daily_loss == 1000
    assert settings.max_daily_entries == 1


def test_settings_loads_risk_limits_from_environment(
    tmp_path: Path,
) -> None:
    parser = build_argument_parser()
    arguments = parser.parse_args(
        [
            "--code",
            "7203",
            "--database-path",
            str(tmp_path / "katana.db"),
        ]
    )

    settings = create_production_settings(
        arguments,
        environ={
            "KABU_STATION_API_PASSWORD": "secret",
            "KATANA_MAX_POSITION_COUNT": "2",
            "KATANA_MAX_POSITION_VALUE": "200000",
            "KATANA_MAX_TOTAL_EXPOSURE": "400000",
            "KATANA_MINIMUM_CASH_BALANCE": "8000000",
            "KATANA_MAX_DAILY_LOSS": "2000",
            "KATANA_MAX_DAILY_ENTRIES": "2",
        },
    )

    assert settings.max_position_count == 2
    assert settings.max_position_value == 200000
    assert settings.max_total_exposure == 400000
    assert settings.minimum_cash_balance == 8000000
    assert settings.max_daily_loss == 2000
    assert settings.max_daily_entries == 2


def test_parser_accepts_multiple_strategies() -> None:
    arguments = build_argument_parser().parse_args(
        [
            "--code",
            "7203",
            "--strategy",
            "orb",
            "--strategy",
            "pullback",
        ]
    )

    assert arguments.strategy == [
        "orb",
        "pullback",
    ]


def test_settings_reads_enabled_strategies_from_environment(
    tmp_path: Path,
) -> None:
    arguments = build_argument_parser().parse_args(
        [
            "--code",
            "7203",
            "--database-path",
            str(tmp_path / "katana.db"),
        ]
    )

    settings = create_production_settings(
        arguments,
        environ={
            "KABU_STATION_API_PASSWORD": "secret",
            "KATANA_ENABLED_STRATEGIES": "orb,pullback",
        },
    )

    assert settings.enabled_strategy_names == (
        "orb",
        "pullback",
    )


def test_parser_accepts_high_breakout_strategy() -> None:
    arguments = build_argument_parser().parse_args(
        [
            "--code",
            "7203",
            "--strategy",
            "high-breakout",
        ]
    )

    assert arguments.strategy == [
        "high-breakout",
    ]
