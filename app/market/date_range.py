"""履歴データ取込で使用する日付範囲処理。"""

from datetime import date, timedelta


def create_date_range(
    start_date: date,
    end_date: date,
) -> list[date]:
    """開始日から終了日までの日付一覧を返す。"""

    if start_date > end_date:
        raise ValueError("開始日は終了日以前にしてください。")

    day_count = (end_date - start_date).days

    return [start_date + timedelta(days=offset) for offset in range(day_count + 1)]


def split_dates(
    target_dates: list[date],
    chunk_size: int,
) -> list[list[date]]:
    """日付一覧を指定件数ごとのまとまりへ分割する。"""

    if chunk_size <= 0:
        raise ValueError("分割件数は0より大きい必要があります。")

    normalized_dates = sorted(set(target_dates))

    return [
        normalized_dates[index : index + chunk_size]
        for index in range(
            0,
            len(normalized_dates),
            chunk_size,
        )
    ]


def filter_date_range(
    target_dates: list[date],
    start_date: date,
    end_date: date,
) -> list[date]:
    """指定期間内の日付だけを返す。"""

    if start_date > end_date:
        raise ValueError("開始日は終了日以前にしてください。")

    return sorted(
        {
            target_date
            for target_date in target_dates
            if start_date <= target_date <= end_date
        }
    )
