"""kabuステーションAPIの実接続状態を直接確認する。"""

from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.settings import ROOT_DIR


DEFAULT_BASE_URL = "http://localhost:18080/kabusapi"
DEFAULT_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class KabuStationReadinessResult:
    """Readiness Probeの結果。"""

    state: str
    exit_code: int | None
    message: str



def probe_kabu_station_readiness(
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    environ: dict[str, str] | None = None,
    env_file: Path = ROOT_DIR / ".env",
) -> KabuStationReadinessResult:
    """トークンを発行せずTCP接続のみでReadinessを確認する。"""

    if timeout_seconds <= 0:
        raise ValueError(
            "タイムアウトは0より大きい必要があります。"
        )

    environment = _load_environment(
        environ=environ,
        env_file=env_file,
    )

    base_url = environment.get(
        "KABU_STATION_BASE_URL",
        DEFAULT_BASE_URL,
    ).strip().rstrip("/")

    from urllib.parse import urlparse

    parsed = urlparse(base_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 18080

    try:
        with socket.create_connection(
            (host, port),
            timeout=timeout_seconds,
        ):
            pass
    except socket.timeout:
        return KabuStationReadinessResult(
            state="timeout",
            exit_code=None,
            message="kabuステーションAPIへの接続がタイムアウトしました。",
        )
    except OSError as error:
        return KabuStationReadinessResult(
            state="disconnected",
            exit_code=1,
            message=f"kabuステーションAPIへ接続できません。 error={error}",
        )

    return KabuStationReadinessResult(
        state="connected",
        exit_code=0,
        message="kabuステーションAPI(TCP)接続確認済み。",
    )

def _load_environment(
    *,
    environ: dict[str, str] | None,
    env_file: Path,
) -> dict[str, str]:
    """OS環境を優先し、`.env`で不足値を補完する。"""

    resolved = dict(
        environ if environ is not None else os.environ
    )

    if not env_file.exists():
        return resolved

    text: str | None = None
    last_error: UnicodeError | None = None

    for encoding in ("utf-8-sig", "cp932", "utf-8"):
        try:
            text = env_file.read_text(encoding=encoding)
            break
        except UnicodeError as error:
            last_error = error

    if text is None:
        raise UnicodeError(
            ".envの文字コードを判定できません。"
        ) from last_error

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if (
            not line
            or line.startswith("#")
            or "=" not in line
        ):
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {"'", '"'}
        ):
            value = value[1:-1]

        resolved.setdefault(key, value)

    return resolved


def _read_http_error(error: HTTPError) -> str:
    try:
        body = error.read().decode(
            "utf-8",
            errors="replace",
        )
    except Exception:
        return str(error.reason)

    normalized = body.strip()
    return normalized[-500:] if normalized else str(error.reason)
