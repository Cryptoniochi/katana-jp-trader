"""kabuステーションAPIとJSON Cacheから銘柄名を提供する。"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from app.market.kabu_station_client import (
    KabuStationClient,
    KabuStationClientSettings,
)
from app.market.kabu_station_models import (
    KabuStationConnectionError,
    KabuStationResponseError,
    KabuStationSymbol,
)


class SymbolNameReader:
    """銘柄名Cacheを読み、不足分をkabuステーションから補完する。"""

    def __init__(
        self,
        database_path: Path,
        *,
        cache_path: Path | None = None,
        env_file: Path | None = None,
        request_interval_seconds: float = 0.12,
        client: KabuStationClient | None = None,
    ) -> None:
        self.database_path = Path(database_path)
        project_directory = (
            self.database_path.resolve().parent.parent
        )
        self.cache_path = (
            Path(cache_path)
            if cache_path is not None
            else (
                project_directory
                / "reports"
                / "cache"
                / "symbol_names.json"
            )
        )
        self.env_file = (
            Path(env_file)
            if env_file is not None
            else project_directory / ".env"
        )
        self.request_interval_seconds = max(
            0.0,
            float(request_interval_seconds),
        )
        self._client = client

    def read_all(self) -> dict[str, str]:
        """保存済みCacheだけを読み込む。"""

        if not self.cache_path.exists():
            return {}

        try:
            payload = json.loads(
                self.cache_path.read_text(
                    encoding="utf-8"
                )
            )
        except (OSError, json.JSONDecodeError):
            return {}

        raw_names = (
            payload.get("names", {})
            if isinstance(payload, dict)
            else {}
        )

        if not isinstance(raw_names, dict):
            return {}

        return {
            str(code).strip(): str(name).strip()
            for code, name in raw_names.items()
            if str(code).strip()
            and str(name).strip()
        }

    def resolve(
        self,
        codes: Iterable[str],
    ) -> dict[str, str]:
        """Cacheを返し、不足コードはAPIから取得して保存する。"""

        normalized_codes = tuple(
            dict.fromkeys(
                self._normalize_code(code)
                for code in codes
                if str(code).strip()
            )
        )
        names = self.read_all()
        missing = [
            code
            for code in normalized_codes
            if code not in names
        ]

        if not missing:
            return {
                code: names[code]
                for code in normalized_codes
                if code in names
            }

        client = self._create_client()

        if client is None:
            return {
                code: names[code]
                for code in normalized_codes
                if code in names
            }

        changed = False

        for index, code in enumerate(missing):
            try:
                name = client.symbol_name(
                    KabuStationSymbol(code=code)
                )
            except (
                KabuStationConnectionError,
                KabuStationResponseError,
                RuntimeError,
                ValueError,
            ):
                # 1銘柄の取得失敗で後続銘柄まで打ち切らない。
                # 失敗した銘柄は次回API呼び出し時に再試行する。
                continue

            if name:
                names[code] = name
                changed = True

            if (
                self.request_interval_seconds > 0
                and index < len(missing) - 1
            ):
                time.sleep(
                    self.request_interval_seconds
                )

        if changed:
            self._write_cache(names)

        return {
            code: names[code]
            for code in normalized_codes
            if code in names
        }

    def _create_client(self) -> KabuStationClient | None:
        if self._client is not None:
            return self._client

        api_password = self._setting(
            "KABU_STATION_API_PASSWORD"
        )

        if not api_password:
            return None

        base_url = (
            self._setting(
                "KABU_STATION_BASE_URL"
            )
            or self._setting(
                "KABU_STATION_API_BASE_URL"
            )
            or "http://localhost:18080/kabusapi"
        )

        self._client = KabuStationClient(
            settings=KabuStationClientSettings(
                api_password=api_password,
                base_url=base_url,
                timeout_seconds=3.0,
                maximum_registered_symbols=50,
            )
        )
        return self._client

    def _setting(self, key: str) -> str | None:
        environment_value = os.environ.get(key)

        if environment_value:
            return environment_value.strip()

        if not self.env_file.exists():
            return None

        try:
            lines = self.env_file.read_text(
                encoding="utf-8"
            ).splitlines()
        except OSError:
            return None

        for line in lines:
            stripped = line.strip()

            if (
                not stripped
                or stripped.startswith("#")
                or "=" not in stripped
            ):
                continue

            name, value = stripped.split("=", 1)

            if name.strip() != key:
                continue

            normalized = value.strip().strip(
                '"'
            ).strip("'")
            return normalized or None

        return None

    def _write_cache(
        self,
        names: dict[str, str],
    ) -> None:
        payload = {
            "generated_at": (
                datetime.now(timezone.utc).isoformat()
            ),
            "source": "kabu-station-board",
            "names": dict(sorted(names.items())),
        }
        self.cache_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        temporary_path = self.cache_path.with_suffix(
            self.cache_path.suffix + ".tmp"
        )
        temporary_path.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        temporary_path.replace(self.cache_path)

    @staticmethod
    def _normalize_code(code: object) -> str:
        normalized = str(code).strip()

        if (
            not normalized.isdigit()
            or len(normalized) not in {4, 5}
        ):
            raise ValueError(
                "銘柄コードは4桁または5桁の数字で"
                "指定してください。 "
                f"value={normalized}"
            )

        return normalized
