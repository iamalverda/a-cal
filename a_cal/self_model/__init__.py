"""A-Cal self-model — the persistent, user-controlled model of the user.

This is a core differentiator (brainstorm Q2). The self-model learns about the
user at a depth *they* control, from simple pattern memory up to a full
longitudinal identity. It powers intent-aware scheduling, proactive suggestions,
and agent context injection.

Privacy is paramount:
  - All data is stored locally by default (JSON store; LanceDB when available).
  - Cloud sync is encrypted + opt-in, off by default.
  - Privacy-tiered routing forces personal/identity content to local models.
  - The user can see, edit, and delete everything the model knows about them.
  - The model is transparent — every inferred fact carries provenance.

Depth levels (escalating, opt-in):
  1. PATTERN_MEMORY  — what times you're busy, recurring meetings, cadence.
  2. ATTENTION_INTENT — what you pay attention to, what you're working toward,
     energy patterns, preferred meeting styles.
  3. LONGITUDINAL_IDENTITY — who you are across time, evolving goals,
     relationships, role transitions, life context.

Each level gates which fact *categories* are extracted. The user has granular
toggles within each level to enable/disable specific categories.
"""

from a_cal.self_model.types import (
    SelfModelDepth,
    FactCategory,
    PrivacyTier,
    SelfModelFact,
)
from a_cal.self_model.settings import SelfModelSettings
from a_cal.self_model.store import SelfModelStore
from a_cal.self_model.extractor import SelfModelExtractor
from a_cal.self_model.model import SelfModel

__all__ = [
    "SelfModelDepth",
    "FactCategory",
    "PrivacyTier",
    "SelfModelFact",
    "SelfModelSettings",
    "SelfModelStore",
    "SelfModelExtractor",
    "SelfModel",
]
