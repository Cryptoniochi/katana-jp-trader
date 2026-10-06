"""Review-only model for future production RecoveryManager composition.

Phase 6-D Step 6C-M records which already-created dependencies a future
RecoveryManager composition would require. It deliberately does not construct
RecoveryManager, a broker, or any broker-facing service.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RecoveryDependencyDisposition(StrEnum):
    """How a dependency may be handled by a future reviewed composition."""

    REUSE_EXISTING = "reuse_existing"
    INJECT_ONLY = "inject_only"


@dataclass(frozen=True, slots=True)
class RecoveryDependencyReviewItem:
    name: str
    disposition: RecoveryDependencyDisposition
    rationale: str


@dataclass(frozen=True, slots=True)
class ProductionRecoveryDependencyReview:
    """Static review of RecoveryManager's operational dependency surface."""

    items: tuple[RecoveryDependencyReviewItem, ...]

    @property
    def all_require_explicit_injection(self) -> bool:
        return all(
            item.disposition
            in {
                RecoveryDependencyDisposition.REUSE_EXISTING,
                RecoveryDependencyDisposition.INJECT_ONLY,
            }
            for item in self.items
        )


def build_production_recovery_dependency_review() -> ProductionRecoveryDependencyReview:
    """Return the approved Step 6C-M dependency classification."""

    return ProductionRecoveryDependencyReview(
        items=(
            RecoveryDependencyReviewItem(
                name="broker",
                disposition=RecoveryDependencyDisposition.INJECT_ONLY,
                rationale=(
                    "Broker access is operational and may perform network reads; "
                    "Step 6C-M must not choose or construct it."
                ),
            ),
            RecoveryDependencyReviewItem(
                name="health_service",
                disposition=RecoveryDependencyDisposition.INJECT_ONLY,
                rationale=(
                    "Recovery calls require_ready against the injected broker; "
                    "construction policy remains outside this step."
                ),
            ),
            RecoveryDependencyReviewItem(
                name="order_repository",
                disposition=RecoveryDependencyDisposition.REUSE_EXISTING,
                rationale=(
                    "The existing SQLite OrderRepository already supplies the "
                    "list_recent contract used by recovery."
                ),
            ),
            RecoveryDependencyReviewItem(
                name="execution_service",
                disposition=RecoveryDependencyDisposition.INJECT_ONLY,
                rationale=(
                    "Live execution reconciliation is broker-facing and must be "
                    "provided by a separately reviewed composition."
                ),
            ),
            RecoveryDependencyReviewItem(
                name="portfolio_service",
                disposition=RecoveryDependencyDisposition.INJECT_ONLY,
                rationale=(
                    "PortfolioService reads broker account and positions, so it "
                    "must not be silently constructed here."
                ),
            ),
            RecoveryDependencyReviewItem(
                name="portfolio_audit_service",
                disposition=RecoveryDependencyDisposition.INJECT_ONLY,
                rationale=(
                    "Portfolio audit is broker/local reconciliation and remains "
                    "an explicitly injected operational dependency."
                ),
            ),
            RecoveryDependencyReviewItem(
                name="portfolio_repository",
                disposition=RecoveryDependencyDisposition.REUSE_EXISTING,
                rationale=(
                    "The existing SQLite PortfolioRepository supplies the save "
                    "contract used by recovery."
                ),
            ),
        )
    )
