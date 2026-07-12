"""The A-Cal Conductor — routes user requests to specialist agents.

The conductor is the single entry point for user interaction (chat / command
bar / proactive). It:
  1. Classifies the user's intent (what do they want?).
  2. Routes to the right specialist (or handles directly for simple queries).
  3. Coordinates the federated swarm when specialists need to negotiate.
  4. Injects self-model context into specialist prompts.
  5. Returns results to the user in a unified response.

In the full atom deployment, this registers as a handler under atom's
AtomMetaAgent / IntentClassifier. In standalone mode, it does its own
lightweight intent classification and generates real, useful rule-based
responses (see ``standalone_responses.py``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from a_cal.agents.specs import (
    A_CAL_AGENTS_BY_NAME,
    AgentSpec,
    CognitiveTier,
    CONDUCTOR_SPEC,
    EMAIL_AGENT_SPEC,
    NEGOTIATE_AGENT_SPEC,
    SCHEDULE_AGENT_SPEC,
    SELF_MODEL_AGENT_SPEC,
    SYNC_AGENT_SPEC,
)
from a_cal.agents.standalone_responses import generate_standalone_response
from a_cal.integrations.atom_bridge import get_atom_adapters
from a_cal.settings.autonomy import AutonomyConfig, AutonomyLevel

logger = logging.getLogger(__name__)


def _get_plugin_runtime():
    """Lazy-load the plugin runtime singleton.

    Imported lazily so the conductor works even if the plugin directory
    doesn't exist yet, and so tests don't need to set up plugins.
    """
    try:
        from a_cal.developer.plugin_runtime import get_runtime
        return get_runtime()
    except Exception:
        return None


class IntentType(str, Enum):
    """What the user wants — drives specialist routing."""

    CHAT = "chat"
    SYNC = "sync"
    SCHEDULE = "schedule"
    EMAIL = "email"
    NEGOTIATE = "negotiate"
    SELF_MODEL = "self_model"
    UNKNOWN = "unknown"


@dataclass
class RoutingDecision:
    """The conductor's decision about how to handle a user request."""

    intent: IntentType
    specialist: Optional[AgentSpec]
    tier: CognitiveTier
    force_local: bool
    self_model_context: str = ""
    reasoning: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent.value,
            "specialist": self.specialist.name if self.specialist else None,
            "tier": self.tier.value,
            "force_local": self.force_local,
            "self_model_context": self.self_model_context,
            "reasoning": self.reasoning,
        }


class ACalConductor:
    """The central orchestrator for A-Cal's agent system.

    In the full atom deployment, this is registered with AtomMetaAgent as the
    A-Cal intent handler. In standalone mode, it does lightweight keyword-based
    intent classification and generates real, useful rule-based responses.

    Args:
        self_model: SelfModel instance (optional in standalone).
        llm_service: atom's LLMService (None = no LLM, rule-based responses).
        user_id: User identifier.
        nervous_system: NervousSystemCoordinator (optional). When provided,
            every message flows through the bio-mimetic architecture and the
            routing trace is included in the response.
        event_store: Object with a ``get_unified_calendar(days)`` method
            (optional). Used for real slot-finding in standalone mode.
        provider_store: Object with ``list_providers()`` and
            ``list_sub_accounts()`` methods (optional).
    """

    _INTENT_KEYWORDS: Dict[IntentType, List[str]] = {
        # Self-model checked first so "what patterns do you see in my schedule?"
        # routes to self_model, not schedule (the word "schedule" would match
        # SCHEDULE keywords before SELF_MODEL gets checked).
        IntentType.SELF_MODEL: ["what do you know", "self model", "my patterns",
                                "what patterns", "patterns in", "my preferences",
                                "my goals", "settings", "privacy",
                                "delete what you know", "what have you learned",
                                "my habits", "my energy", "what do you know about me",
                                "what do you know about my"],
        IntentType.SYNC: ["sync", "pull", "refresh", "connect", "provider", "health",
                          "link account", "add account", "google calendar", "outlook",
                          "caldav", "sub-account", "sub account"],
        IntentType.SCHEDULE: ["schedule", "slot", "free", "busy", "conflict", "reschedule",
                              "move", "find time", "when am i", "cancel", "delete event",
                              "remove event", "book", "create event", "add event",
                              "meeting", "appointment", "create a", "set up",
                              # listing / viewing events
                              "what events", "what do i have", "what's on", "whats on",
                              "show me my", "list my", "my calendar", "my schedule",
                              "today", "tomorrow", "this week", "next week",
                              "what's my day", "whats my day", "my day",
                              "upcoming", "agenda", "do i have anything",
                              "any meetings", "what do i have on",
                              "show me the calendar", "calendar for",
                              "events on", "events for", "events today",
                              "do i have", "am i free", "am i busy"],
        IntentType.EMAIL: ["email", "inbox", "invite", "message", "reply", "draft",
                           "send email", "read email", "unread", "compose",
                           "mail", "check my inbox", "any new emails"],
        IntentType.NEGOTIATE: ["negotiate", "ask them", "coordinate", "propose to",
                               "reschedule with", "move with", "work out a time",
                               "find a time with", "coordinate with"],
    }

    def __init__(
        self,
        self_model: Any = None,
        llm_service: Any = None,
        user_id: str = "local-dev-user",
        nervous_system: Any = None,
        event_store: Any = None,
        provider_store: Any = None,
        autonomy_config: Optional[AutonomyConfig] = None,
    ) -> None:
        self.self_model = self_model
        self.llm_service = llm_service
        self.user_id = user_id
        # When atom is available, use its LLM-powered intent classifier
        # for more accurate routing. Falls back to keyword-based if absent.
        _, _, self._atom_intent = get_atom_adapters(workspace_id=user_id)
        self.nervous_system = nervous_system
        self.event_store = event_store
        self.provider_store = provider_store
        self.autonomy_config = autonomy_config or AutonomyConfig()
        self.spec = CONDUCTOR_SPEC

    def classify_intent(self, message: str) -> IntentType:
        """Classify user intent using atom's LLM classifier if available,
        otherwise fall back to keyword-based matching."""
        # Keyword-based is always available as the fast path and fallback.
        lower = message.lower()
        keyword_result = IntentType.CHAT
        for intent, keywords in self._INTENT_KEYWORDS.items():
            if any(kw in lower for kw in keywords):
                keyword_result = intent
                break

        # If atom's intent classifier is available, use it for ambiguous cases.
        # We run keyword first (instant), then let atom refine if it disagrees
        # with the default CHAT result or the message is complex enough.
        if self._atom_intent and keyword_result == IntentType.CHAT:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # We're inside an async context — can't await here.
                    # The async handle() method calls _classify_intent_async
                    # instead. Return keyword result for sync callers.
                    return keyword_result
                result = loop.run_until_complete(
                    self._atom_intent.classify(message)
                )
                if result and result.get("confidence", 0) > 0.6:
                    return self._map_atom_intent(result["category"])
            except Exception:
                pass

        # Allow loaded plugins to override the intent classification.
        # First plugin returning a non-None string wins.
        runtime = _get_plugin_runtime()
        if runtime is not None:
            try:
                override = runtime.on_intent_classified(message, keyword_result.value)
                if override is not None:
                    try:
                        return IntentType(override)
                    except ValueError:
                        logger.warning("Plugin returned unknown intent: %s", override)
            except Exception as exc:
                logger.debug("plugin on_intent_classified failed: %s", exc)

        return keyword_result

    @staticmethod
    def _map_atom_intent(category: str) -> IntentType:
        """Map atom's intent categories to A-Cal's IntentType."""
        mapping = {
            "chat": IntentType.CHAT,
            "workflow": IntentType.SCHEDULE,
            "task": IntentType.SCHEDULE,
        }
        return mapping.get(category, IntentType.CHAT)

    def route(self, message: str) -> RoutingDecision:
        """Decide which specialist handles this message and at what tier."""
        intent = self.classify_intent(message)
        specialist: Optional[AgentSpec] = None

        specialist_map = {
            IntentType.SYNC: SYNC_AGENT_SPEC,
            IntentType.SCHEDULE: SCHEDULE_AGENT_SPEC,
            IntentType.EMAIL: EMAIL_AGENT_SPEC,
            IntentType.NEGOTIATE: NEGOTIATE_AGENT_SPEC,
            IntentType.SELF_MODEL: SELF_MODEL_AGENT_SPEC,
        }
        specialist = specialist_map.get(intent)

        if specialist is None:
            specialist = self.spec
            tier = CognitiveTier.STANDARD
        else:
            tier = specialist.default_tier

        force_local = specialist.privacy_force_local if specialist else False
        if self.self_model and self.self_model.has_local_only_facts():
            if intent in (IntentType.SELF_MODEL, IntentType.EMAIL, IntentType.NEGOTIATE):
                force_local = True

        context = ""
        if self.self_model and self.self_model.settings.feed_into_agents:
            context = self.self_model.inject_into_prompt()

        return RoutingDecision(
            intent=intent,
            specialist=specialist,
            tier=tier,
            force_local=force_local,
            self_model_context=context,
            reasoning=f"Keyword classification -> {intent.value}",
        )

    def _get_calendar_data(self) -> Dict[str, Any]:
        """Fetch calendar events, providers, and sub-accounts from the store."""
        events: List[Dict[str, Any]] = []
        providers: List[Dict[str, Any]] = []
        sub_accounts: List[Dict[str, Any]] = []

        if self.event_store:
            try:
                raw_events = self.event_store.get_unified_calendar(14)
                events = raw_events if isinstance(raw_events, list) else []
            except Exception as exc:
                logger.debug("event_store fetch failed: %s", exc)

        if self.provider_store:
            try:
                providers = self.provider_store.list_providers()
                sub_accounts = self.provider_store.list_sub_accounts()
            except Exception as exc:
                logger.debug("provider_store fetch failed: %s", exc)

        return {"events": events, "providers": providers, "sub_accounts": sub_accounts}

    async def handle(self, message: str) -> Dict[str, Any]:
        """Handle a user message end-to-end.

        In standalone mode (no LLM), generates real, useful rule-based
        responses that interact with calendar data. When an LLM is available,
        dispatches to the specialist via the LLM service.

        If a nervous system coordinator is attached, every message flows
        through the bio-mimetic architecture and the routing trace is
        included in the response.
        """
        decision = self.route(message)

        # Route through the nervous system if available
        routing_trace: Optional[Dict[str, Any]] = None
        cas_modules_engaged: List[str] = []
        if self.nervous_system:
            try:
                trace = self.nervous_system.route_through_nervous_system(message)
                routing_trace = trace.to_dict()
                cas_modules_engaged = routing_trace.get("cas_modules_engaged", [])
            except Exception as exc:
                logger.debug("nervous system routing failed: %s", exc)

        # Resolve the effective autonomy level for this request.
        # Per-sub-account overrides apply when the conductor knows which
        # sub-account is involved; for now, the global default is used.
        autonomy_level = self.autonomy_config.resolve(None)
        suggest_only = autonomy_level == AutonomyLevel.SUGGEST_ONLY
        confirmation_required = autonomy_level == AutonomyLevel.CONFIRM
        # In SUGGEST_ONLY mode, pass event_store=None so the standalone
        # generators propose actions without executing mutations.
        effective_event_store = None if suggest_only else self.event_store

        if self.llm_service is None:
            # Standalone: generate real rule-based responses
            cal_data = self._get_calendar_data()
            result = generate_standalone_response(
                message=message,
                decision=decision,
                events=cal_data["events"],
                providers=cal_data["providers"],
                sub_accounts=cal_data["sub_accounts"],
                self_model=self.self_model,
                agents=self.list_specialists(),
                event_store=effective_event_store,
            )

            # Allow plugins to transform the response before returning.
            final_response = result["response"]
            runtime = _get_plugin_runtime()
            if runtime is not None:
                try:
                    transformed = runtime.on_conductor_response(
                        final_response,
                        {"intent": decision.intent.value, "standalone": True},
                    )
                    if transformed is not None:
                        final_response = transformed
                except Exception as exc:
                    logger.debug("plugin on_conductor_response failed: %s", exc)

            return {
                "user_id": self.user_id,
                "message": message,
                "routing": decision.to_dict(),
                "response": final_response,
                "actions": result["actions"],
                "routing_trace": routing_trace,
                "cas_modules_engaged": cas_modules_engaged,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "standalone": True,
                "autonomy_level": autonomy_level.value,
                "confirmation_required": confirmation_required,
            }

        # Hybrid mode: run the standalone response generator to perform
        # real calendar operations (create/reschedule/delete events, find
        # slots, check providers), then ask the LLM to craft a natural
        # language response with that context. This ensures agents actually
        # make changes (not just talk about them) while still getting the
        # LLM's richer reasoning and communication.
        cal_data = self._get_calendar_data()
        standalone_result = generate_standalone_response(
            message=message,
            decision=decision,
            events=cal_data["events"],
            providers=cal_data["providers"],
            sub_accounts=cal_data["sub_accounts"],
            self_model=self.self_model,
            agents=self.list_specialists(),
            event_store=effective_event_store,
        )

        # Build the LLM prompt with standalone context so the model knows
        # what operations were already performed and can reference them.
        specialist_prompt = decision.specialist.system_prompt if decision.specialist else self.spec.system_prompt
        # Augment the specialist's system prompt with anti-hallucination
        # directives. The standalone agent already performed real actions
        # (created events, found slots, listed providers) — the LLM's job
        # is to communicate those results naturally, not invent new ones.
        system_prompt = (
            f"{specialist_prompt}\n\n"
            f"IMPORTANT GROUND RULES:\n"
            f"- The [System context] below contains the REAL results of actions "
            f"already taken. Treat it as ground truth.\n"
            f"- Do NOT invent events, times, or dates that are not in the system "
            f"context. If the system found 0 events, say the schedule is clear.\n"
            f"- If an action was already performed (e.g. event created, slot found), "
            f"reference it directly. Do not repeat or contradict it.\n"
            f"- Keep responses concise (2-4 sentences). The user wants answers, "
            f"not essays.\n"
            f"- If you are unsure about something not in the system context, say so "
            f"rather than guessing."
        )
        action_summary = ""
        if standalone_result.get("actions"):
            action_lines = []
            for a in standalone_result["actions"]:
                a_type = a.get("type", "unknown")
                a_status = a.get("status", "")
                if a_status:
                    action_lines.append(f"- {a_type}: {a_status}")
                else:
                    action_lines.append(f"- {a_type}")
            action_summary = (
                "\n\n[Actions already performed by the system:]\n"
                + "\n".join(action_lines)
            )

        standalone_context = (
            f"[System context — what the rule-based agent found:]\n"
            f"{standalone_result['response']}"
            f"{action_summary}"
        )

        full_prompt = f"{standalone_context}\n\nUser request: {message}"
        if decision.self_model_context:
            full_prompt = f"{decision.self_model_context}\n{full_prompt}"

        try:
            llm_response = await self.llm_service.generate_response(
                prompt=full_prompt,
                system_prompt=system_prompt,
                task=decision.intent.value,
                tenant_id=self.user_id,
            )
        except Exception as exc:
            logger.error("conductor LLM dispatch failed: %r", exc)
            # Fall back to the standalone response if the LLM fails
            llm_response = standalone_result["response"]

        # Allow plugins to transform the LLM response before returning.
        runtime = _get_plugin_runtime()
        if runtime is not None:
            try:
                transformed = runtime.on_conductor_response(
                    llm_response,
                    {"intent": decision.intent.value, "standalone": False},
                )
                if transformed is not None:
                    llm_response = transformed
            except Exception as exc:
                logger.debug("plugin on_conductor_response failed: %s", exc)

        return {
            "user_id": self.user_id,
            "message": message,
            "routing": decision.to_dict(),
            "response": llm_response,
            "actions": standalone_result["actions"],
            "routing_trace": routing_trace,
            "cas_modules_engaged": cas_modules_engaged,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "standalone": False,
            "actions_source": "hybrid",
            "autonomy_level": autonomy_level.value,
            "confirmation_required": confirmation_required,
        }

    def list_specialists(self) -> List[Dict[str, Any]]:
        """Return all specialist specs (for the UI's agent overview)."""
        return [a.to_dict() for a in A_CAL_AGENTS_BY_NAME.values()]
