"""A-Cal community marketplace.

Shared, remixable configurations: agent specs, sync rule packs, negotiation
strategies, UI themes, and plugin configs. Every shared artifact carries
structured provenance metadata (from the meta-cognition protocol's methodology
output format) so the community can audit what it does before installing.
"""

from a_cal.marketplace.types import (
    MarketplaceItem,
    MarketplaceItemType,
    Provenance,
    InstallRecord,
    RemixRecord,
)
from a_cal.marketplace.store import MarketplaceStore

__all__ = [
    "MarketplaceItem",
    "MarketplaceItemType",
    "Provenance",
    "InstallRecord",
    "RemixRecord",
    "MarketplaceStore",
]
