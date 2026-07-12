"""A-Cal integration adapters for external platforms.

Currently supports atom (the AI agent backbone). When atom is available on
PYTHONPATH, A-Cal upgrades to encrypted token storage, atom's LLM service,
and intent classification. When atom is not available, A-Cal falls back to
standalone mode (SQLite, local LLM service, keyword-based intent).
"""
