"""SQLite保存済みHigh Breakout候補を戦略へ供給する。"""

from datetime import date

from app.strategy.high_breakout_candidate_repository import (
    HighBreakoutCandidateNotFoundError,
    HighBreakoutCandidateRepository,
)
from app.strategy.high_breakout_models import HighBreakoutCandidate


class RepositoryHighBreakoutCandidateProvider:
    def __init__(
        self,
        repository: HighBreakoutCandidateRepository,
    ) -> None:
        self.repository = repository

    def __call__(
        self,
        code: str,
        trading_date: date,
    ) -> HighBreakoutCandidate | None:
        try:
            return self.repository.get(
                code=code,
                trading_date=trading_date,
            )
        except HighBreakoutCandidateNotFoundError:
            return None
