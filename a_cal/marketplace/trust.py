"""Trust and moderation additions to marketplace types.

Adds content integrity hashing, flagging/reporting, trust scoring, and
verification status to marketplace items. This lets the community audit
configs before installing and report problematic content.
"""

from __future__ import annotations

import enum
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, UTC
from typing import Any


class VerificationStatus(str, enum.Enum):
    """Verification state of a marketplace item."""
    UNVERIFIED = "unverified"
    AUTHOR_VERIFIED = "author_verified"
    COMMUNITY_VERIFIED = "community_verified"
    FLAGGED = "flagged"
    REMOVED = "removed"


@dataclass
class FlagRecord:
    """A user report against a marketplace item.
    
    Flags can be for spam, malicious content, broken configs,
    license violations, or other concerns.
    """
    id: str = field(default_factory=lambda: str(__import__("uuid").uuid4()))
    item_id: str = ""
    flagged_by: str = ""  # user_id
    reason: str = ""  # spam, malicious, broken, license_violation, other
    detail: str = ""
    flagged_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    resolved: bool = False
    resolution: str = ""  # dismissed, removed, warning_issued
    resolved_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "item_id": self.item_id,
            "flagged_by": self.flagged_by,
            "reason": self.reason,
            "detail": self.detail,
            "flagged_at": self.flagged_at,
            "resolved": self.resolved,
            "resolution": self.resolution,
            "resolved_at": self.resolved_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FlagRecord:
        return cls(
            id=data.get("id", str(__import__("uuid").uuid4())),
            item_id=data.get("item_id", ""),
            flagged_by=data.get("flagged_by", ""),
            reason=data.get("reason", ""),
            detail=data.get("detail", ""),
            flagged_at=data.get("flagged_at", datetime.now(UTC).isoformat()),
            resolved=data.get("resolved", False),
            resolution=data.get("resolution", ""),
            resolved_at=data.get("resolved_at"),
        )


def compute_content_hash(config: dict[str, Any]) -> str:
    """Compute SHA-256 hash of a config dict for integrity verification.
    
    The hash is deterministic (sorted keys) so users can verify that
    a downloaded config matches what was published.
    """
    canonical = json.dumps(config, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def compute_trust_score(
    rating: float,
    rating_count: int,
    install_count: int,
    flag_count: int,
    verification_status: str,
    author_item_count: int = 0,
) -> float:
    """Compute a trust score (0.0–100.0) for a marketplace item.
    
    Factors:
    - Rating quality (weighted by count)
    - Install popularity
    - Verification status
    - Flag penalties
    - Author track record
    """
    score = 0.0
    
    # Rating component (0-40 points)
    if rating_count > 0:
        # More ratings = more confidence in the score
        confidence = min(rating_count / 10.0, 1.0)
        score += (rating / 5.0) * 40.0 * confidence
    else:
        score += 10.0  # neutral starting score for unrated items
    
    # Install popularity (0-25 points)
    if install_count > 0:
        import math
        score += min(math.log10(install_count + 1) * 10, 25.0)
    
    # Verification status (0-20 points)
    verification_scores = {
        VerificationStatus.UNVERIFIED.value: 5.0,
        VerificationStatus.AUTHOR_VERIFIED.value: 15.0,
        VerificationStatus.COMMUNITY_VERIFIED.value: 20.0,
        VerificationStatus.FLAGGED.value: 0.0,
        VerificationStatus.REMOVED.value: 0.0,
    }
    score += verification_scores.get(verification_status, 5.0)
    
    # Author track record (0-15 points)
    if author_item_count > 0:
        import math
        score += min(math.log10(author_item_count + 1) * 5, 15.0)
    
    # Flag penalties
    if flag_count > 0:
        score -= min(flag_count * 10, 50.0)
    
    return max(0.0, min(100.0, score))
