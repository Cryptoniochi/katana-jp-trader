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
    """`/token`へ直接接続し、実際のAPI状態を確認する。"""

    if timeout_seconds <= 0:
        raise ValueError(
            "タイムアウトは0より大きい必要があります。"
        )

    environment = _load_environment(
        environ=environ,
        env_file=env_file,
    )
    password = (
        environment.get("KABU_STATION_API_PASSWORD")
        or environment.get("KABUSTATION_API_PASSWORD")
        or ""
    ).strip()

    if not password:
        return KabuStationReadinessResult(
            state="disconnected",
            exit_code=1,
            message=(
                "KABU_STATION_API_PASSWORDが設定されていません。"
            ),
        )

    base_url = environment.get(
        "KABU_STATION_BASE_URL",
        DEFAULT_BASE_URL,
    ).strip().rstrip("/")
    token_url = f"{base_url}/token"
    payload = json.dumps(
        {"APIPassword": password}
    ).encode("utf-8")
    request = Request(
        token_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(
            request,
            timeout=timeout_seconds,
        ) as response:
            body = response.read().decode(
                "utf-8",
                errors="replace",
            )
    except HTTPError as error:
        detail = _read_http_error(error)
        return KabuStationReadinessResult(
            state="disconnected",
            exit_code=int(error.code),
            message=(
                "kabuステーションAPIのトークン取得に失敗しました。 "
                f"http_status={error.code} detail={detail}"
            ),
        )
    except (TimeoutError, socket.timeout):
        return KabuStationReadinessResult(
            state="timeout",
            exit_code=None,
            message=(
                "kabuステーションAPIへの接続が"
                "タイムアウトしました。"
            ),
        )
    except URLError as error:
        reason = getattr(error, "reason", error)
        return KabuStationReadinessResult(
            state="disconnected",
            exit_code=1,
            message=(
                "kabuステーションAPIへ接続できません。 "
                f"error={reason}"
            ),
        )
    except OSError as error:
        return KabuStationReadinessResult(
            state="disconnected",
            exit_code=1,
            message=(
                "kabuステーションAPIへ接続できません。 "
                f"error={error}"
            ),
        )

    try:
        decoded = json.loads(body)
    except json.JSONDecodeError:
        return KabuStationReadinessResult(
            state="error",
            exit_code=1,
            message=(
                "kabuステーションAPIから不正なJSONが返されました。"
            ),
        )

    token = decoded.get("Token")
    if not isinstance(token, str) or not token.strip():
        code = decoded.get("Code")
        message = decoded.get("Message")
        return KabuStationReadinessResult(
            state="disconnected",
            exit_code=1,
            message=(
                "kabuステーションAPIトークンを取得できませんでした。 "
                f"code={code} message={message}"
            ),
        )

    return KabuStationReadinessResult(
        state="connected",
        exit_code=0,
        message="kabuステーションAPI接続確認済み。",
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
