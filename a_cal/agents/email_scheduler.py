"""Email-to-schedule pipeline — scans emails for meeting proposals and suggests calendar actions.

This is the agentic bridge between the email system and the calendar. When a
user says "check my emails for meetings" or "what meetings did people propose?",
the conductor dispatches here. The pipeline:

  1. Scans email messages for scheduling-related content (meeting proposals,
     date/time mentions, RSVP requests, calendar invites).
  2. Extracts proposed meeting times using natural-language date/time patterns.
  3. Cross-references detected meetings with existing calendar events to find
     conflicts.
  4. Generates actionable scheduling suggestions (create event, decline,
     propose alternative time).

Works in rule-based mode (no LLM) for privacy and offline use. When an LLM
is connected, the conductor can use the extracted context for richer analysis.

Privacy: email content never leaves the local process in rule-based mode.
When an LLM is used, privacy-tiered routing forces email processing to local
models (enforced in the routing layer, not here).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone, UTC
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# --- Email depth levels (mirrors a_cal.settings.email.EmailDepth) ----------
# Duplicated here to avoid a circular import (settings imports nothing from
# agents, but keeping the values in sync is straightforward).

DEPTH_SYNC_NOTIFY = "sync_notify"
DEPTH_AGENT_MEDIATED = "agent_mediated"
DEPTH_FULL_TWO_WAY = "full_two_way"

_VALID_DEPTHS = {DEPTH_SYNC_NOTIFY, DEPTH_AGENT_MEDIATED, DEPTH_FULL_TWO_WAY}


# --- Scheduling keyword detection -------------------------------------------

SCHEDULING_KEYWORDS = [
    # Direct meeting requests
    "let's meet", "can we meet", "schedule a meeting", "set up a meeting",
    "book a time", "find a time", "when are you free", "when can we",
    "are you available", "do you have time", "let's chat", "let's talk",
    "catch up", "sync up", "standup", "stand up", "check in", "check-in",
    # RSVP / confirmation
    "please confirm", "rsvp", "accept", "decline", "tentative",
    "can you make it", "will you attend", "looking forward to seeing you",
    # Rescheduling
    "reschedule", "move our meeting", "push back", "move to",
    "need to cancel", "cancel our", "postpone",
    # Time proposals
    "how about", "does .work", "works for me", "that works",
    "proposed time", "suggested time", "my calendar is open",
]

# Patterns that strongly indicate a meeting proposal vs just mentioning time
STRONG_MEETING_SIGNALS = [
    "meeting", "call", "sync", "standup", "stand up", "catch up",
    "chat", "discussion", "review", "demo", "interview", "consultation",
    "appointment", "session", "workshop", "lunch", "coffee",
]

# Patterns indicating this is a calendar invite (not just a mention)
INVITE_SIGNALS = [
    "calendar invite", "event invitation", "you've been invited",
    "invited you to", "added you to", "please accept",
    "text/calendar", "method=request", "method=cancel",
]


# --- Date/time extraction ---------------------------------------------------

# Common date patterns in emails
DATE_PATTERNS = [
    # "Monday", "Tuesday", etc.
    (r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', "weekday"),
    # "July 15", "Jul 15", "15 July", "15 Jul"
    (r'\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t)?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(\d{1,2})(?:st|nd|rd|th)?\b', "month_day"),
    (r'\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t)?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b', "day_month"),
    # "7/15", "07/15/2024" (US format)
    (r'\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b', "slash_date"),
    # "2024-07-15" (ISO format)
    (r'\b(\d{4})-(\d{2})-(\d{2})\b', "iso_date"),
    # "next week", "this week", "tomorrow", "today"
    (r'\b(next week|this week|tomorrow|today|day after tomorrow)\b', "relative_date"),
    # "next Monday", "this Friday"
    (r'\b(next|this|coming)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', "relative_weekday"),
]

# Time patterns
TIME_PATTERNS = [
    # "3pm", "3:30pm", "15:00", "3:30 PM"
    (r'\b(\d{1,2}):(\d{2})\s*(am|pm)?(?=\b|\s|$)', "clock_time"),
    (r'(?<![:\d])(\d{1,2})\s*(am|pm)\b', "hour_ampm"),
    # "morning", "afternoon", "evening"
    (r'\b(morning|afternoon|evening|noon|midnight)\b', "period"),
    # "9 to 10", "9-10", "9:00-10:30"
    (r'\b(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s*(?:to|-|until|\u2013)\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b', "time_range"),
]

# Duration patterns
DURATION_PATTERNS = [
    (r'\bfor\s+(\d+)\s*(min(?:ute)?s?|hours?|hrs?)\b', "explicit_duration"),
    (r'\b(\d+)\s*min(?:ute)?s?\b', "minutes"),
    (r'\b(\d+)\s*(?:hours?|hrs?)\b', "hours"),
    (r'\bhalf\s*an\s*hour\b', "half_hour"),
    (r'\bquick\s*(?:chat|call|sync)\b', "quick"),
]

MONTH_MAP = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12,
}

WEEKDAY_MAP = {
    "monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "friday": 4, "fri": 4, "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}


@dataclass
class ExtractedTime:
    """A date/time extracted from an email."""
    raw_text: str
    date_text: str = ""
    time_text: str = ""
    duration_minutes: int | None = None
    estimated_start: datetime | None = None
    estimated_end: datetime | None = None
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_text": self.raw_text,
            "date_text": self.date_text,
            "time_text": self.time_text,
            "duration_minutes": self.duration_minutes,
            "estimated_start": self.estimated_start.isoformat() if self.estimated_start else None,
            "estimated_end": self.estimated_end.isoformat() if self.estimated_end else None,
            "confidence": self.confidence,
        }


@dataclass
class SchedulingDetection:
    """Result of scanning an email for scheduling content."""
    is_scheduling_related: bool
    is_meeting_proposal: bool
    is_calendar_invite: bool
    is_reschedule: bool
    is_cancellation: bool
    detected_keywords: list[str] = field(default_factory=list)
    extracted_times: list[ExtractedTime] = field(default_factory=list)
    proposed_by: str = ""  # email address of proposer
    subject: str = ""
    snippet: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_scheduling_related": self.is_scheduling_related,
            "is_meeting_proposal": self.is_meeting_proposal,
            "is_calendar_invite": self.is_calendar_invite,
            "is_reschedule": self.is_reschedule,
            "is_cancellation": self.is_cancellation,
            "detected_keywords": self.detected_keywords,
            "extracted_times": [t.to_dict() for t in self.extracted_times],
            "proposed_by": self.proposed_by,
            "subject": self.subject,
            "snippet": self.snippet,
            "confidence": self.confidence,
        }


@dataclass
class SchedulingSuggestion:
    """An actionable scheduling suggestion derived from emails."""
    type: str  # "create_event", "conflict_warning", "decline", "reschedule_propose"
    email_subject: str
    email_from: str
    proposed_time: ExtractedTime | None = None
    conflict_with: str | None = None  # title of conflicting event
    suggested_alternative: str | None = None
    confidence: float = 0.0
    message: str = ""
    # Draft reply text (populated at agent_mediated depth or above).
    draft_reply: str | None = None
    # Whether this suggestion may be auto-executed without per-action
    # confirmation (only at full_two_way depth).
    auto_action: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "email_subject": self.email_subject,
            "email_from": self.email_from,
            "proposed_time": self.proposed_time.to_dict() if self.proposed_time else None,
            "conflict_with": self.conflict_with,
            "suggested_alternative": self.suggested_alternative,
            "confidence": self.confidence,
            "message": self.message,
            "draft_reply": self.draft_reply,
            "auto_action": self.auto_action,
        }


# --- Core scanning functions ------------------------------------------------

def detect_scheduling_content(
    subject: str,
    snippet: str,
    body_text: str = "",
    has_calendar_invite: bool = False,
    from_address: str = "",
) -> SchedulingDetection:
    """Scan an email for scheduling-related content.

    Args:
        subject: Email subject line.
        snippet: First ~200 chars of the body.
        body_text: Full body text (if available).
        has_calendar_invite: Whether the email has a calendar invite attachment.
        from_address: Sender email address.

    Returns:
        SchedulingDetection with flags, keywords, and extracted times.
    """
    full_text = f"{subject} {snippet} {body_text}".lower()

    detected_keywords: list[str] = []
    for kw in SCHEDULING_KEYWORDS:
        if kw in full_text:
            detected_keywords.append(kw)

    is_meeting_proposal = any(sig in full_text for sig in STRONG_MEETING_SIGNALS)
    is_calendar_invite = has_calendar_invite or any(sig in full_text for sig in INVITE_SIGNALS)
    is_reschedule = "reschedule" in full_text or "move our meeting" in full_text or "push back" in full_text
    is_cancellation = "cancel" in full_text and ("meeting" in full_text or "appointment" in full_text)
    is_scheduling_related = (
        len(detected_keywords) > 0
        or is_meeting_proposal
        or is_calendar_invite
        or is_reschedule
        or is_cancellation
    )

    # Extract times from the full text
    extracted = extract_times(subject + " " + snippet + " " + body_text)

    # Confidence: based on number of signals
    signal_count = sum([
        len(detected_keywords) > 0,
        is_meeting_proposal,
        is_calendar_invite,
        is_reschedule,
        is_cancellation,
        len(extracted) > 0,
    ])
    confidence = min(1.0, signal_count * 0.2)

    return SchedulingDetection(
        is_scheduling_related=is_scheduling_related,
        is_meeting_proposal=is_meeting_proposal,
        is_calendar_invite=is_calendar_invite,
        is_reschedule=is_reschedule,
        is_cancellation=is_cancellation,
        detected_keywords=detected_keywords,
        extracted_times=extracted,
        proposed_by=from_address,
        subject=subject,
        snippet=snippet,
        confidence=confidence,
    )


def extract_times(text: str) -> list[ExtractedTime]:
    """Extract date/time references from text.

    Returns a list of ExtractedTime objects with estimated start/end times
    where possible. Estimation is conservative — confidence is low when
    only partial information (e.g. time but no date) is found.
    """
    results: list[ExtractedTime] = []
    text_lower = text.lower()
    now = datetime.now(UTC)

    # Find all date matches
    date_matches: list[tuple[str, str, datetime | None]] = []
    for pattern, ptype in DATE_PATTERNS:
        for m in re.finditer(pattern, text_lower):
            raw = m.group(0)
            est_date = _estimate_date(raw, ptype, m, now)
            date_matches.append((raw, ptype, est_date))

    # Find all time matches
    time_matches: list[tuple[str, str, tuple[int, int] | None]] = []
    for pattern, ptype in TIME_PATTERNS:
        for m in re.finditer(pattern, text_lower):
            raw = m.group(0)
            est_time = _estimate_time(raw, ptype, m)
            time_matches.append((raw, ptype, est_time))

    # Find duration
    duration_minutes: int | None = None
    for pattern, ptype in DURATION_PATTERNS:
        m = re.search(pattern, text_lower)
        if m:
            duration_minutes = _estimate_duration(raw=m.group(0), ptype=ptype, match=m)
            break
    if duration_minutes is None and any("quick" in kw for kw in [text_lower]):
        duration_minutes = 15

    # Combine date + time matches into ExtractedTime objects
    if date_matches and time_matches:
        for date_raw, _, est_date in date_matches:
            for time_raw, _, est_time in time_matches:
                if est_date and est_time:
                    start = est_date.replace(hour=est_time[0], minute=est_time[1])
                    end = start + timedelta(minutes=duration_minutes or 30)
                    results.append(ExtractedTime(
                        raw_text=f"{date_raw} {time_raw}",
                        date_text=date_raw,
                        time_text=time_raw,
                        duration_minutes=duration_minutes,
                        estimated_start=start,
                        estimated_end=end,
                        confidence=0.7,
                    ))
                elif est_date:
                    results.append(ExtractedTime(
                        raw_text=date_raw,
                        date_text=date_raw,
                        duration_minutes=duration_minutes,
                        estimated_start=est_date,
                        confidence=0.3,
                    ))
    elif date_matches:
        for date_raw, _, est_date in date_matches:
            if est_date:
                results.append(ExtractedTime(
                    raw_text=date_raw,
                    date_text=date_raw,
                    duration_minutes=duration_minutes,
                    estimated_start=est_date,
                    confidence=0.3,
                ))
    elif time_matches:
        for time_raw, _, est_time in time_matches:
            if est_time:
                start = now.replace(hour=est_time[0], minute=est_time[1], second=0, microsecond=0)
                end = start + timedelta(minutes=duration_minutes or 30)
                results.append(ExtractedTime(
                    raw_text=time_raw,
                    time_text=time_raw,
                    duration_minutes=duration_minutes,
                    estimated_start=start,
                    estimated_end=end,
                    confidence=0.2,
                ))

    return results


def _estimate_date(raw: str, ptype: str, match: re.Match, now: datetime) -> datetime | None:
    """Estimate a datetime from a date pattern match."""
    try:
        if ptype == "weekday":
            target_dow = WEEKDAY_MAP.get(raw)
            if target_dow is None:
                return None
            days_ahead = (target_dow - now.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7  # Next week, not today
            return now + timedelta(days=days_ahead)

        elif ptype == "month_day":
            month_str = match.group(1)
            day = int(match.group(2))
            month = MONTH_MAP.get(month_str[:3].lower())
            if month is None:
                return None
            year = now.year
            if month < now.month or (month == now.month and day < now.day):
                year += 1
            return datetime(year, month, day, tzinfo=UTC)

        elif ptype == "day_month":
            day = int(match.group(1))
            month_str = match.group(2)
            month = MONTH_MAP.get(month_str[:3].lower())
            if month is None:
                return None
            year = now.year
            if month < now.month or (month == now.month and day < now.day):
                year += 1
            return datetime(year, month, day, tzinfo=UTC)

        elif ptype == "slash_date":
            month = int(match.group(1))
            day = int(match.group(2))
            year = int(match.group(3)) if match.group(3) else now.year
            if year < 100:
                year += 2000
            return datetime(year, month, day, tzinfo=UTC)

        elif ptype == "iso_date":
            year = int(match.group(1))
            month = int(match.group(2))
            day = int(match.group(3))
            return datetime(year, month, day, tzinfo=UTC)

        elif ptype == "relative_date":
            if raw == "today":
                return now
            elif raw == "tomorrow":
                return now + timedelta(days=1)
            elif raw == "day after tomorrow":
                return now + timedelta(days=2)
            elif raw == "next week":
                return now + timedelta(weeks=1)
            elif raw == "this week":
                return now

        elif ptype == "relative_weekday":
            rel = match.group(1)
            dow_name = match.group(2)
            target_dow = WEEKDAY_MAP.get(dow_name)
            if target_dow is None:
                return None
            days_ahead = (target_dow - now.weekday()) % 7
            if rel == "next":
                days_ahead += 7 if days_ahead == 0 else 7
            elif rel == "this" and days_ahead == 0:
                days_ahead = 0  # Today
            return now + timedelta(days=days_ahead)

    except (ValueError, IndexError):
        return None
    return None


def _estimate_time(raw: str, ptype: str, match: re.Match) -> tuple[int, int] | None:
    """Estimate hour:minute from a time pattern match."""
    try:
        if ptype == "clock_time":
            hour = int(match.group(1))
            minute = int(match.group(2))
            ampm = match.group(3)
            if ampm and ampm.lower() == "pm" and hour < 12:
                hour += 12
            if ampm and ampm.lower() == "am" and hour == 12:
                hour = 0
            return (hour, minute)

        elif ptype == "hour_ampm":
            hour = int(match.group(1))
            ampm = match.group(2)
            if ampm.lower() == "pm" and hour < 12:
                hour += 12
            if ampm.lower() == "am" and hour == 12:
                hour = 0
            return (hour, 0)

        elif ptype == "period":
            period_map = {
                "morning": (9, 0),
                "afternoon": (14, 0),
                "evening": (18, 0),
                "noon": (12, 0),
                "midnight": (0, 0),
            }
            return period_map.get(raw)

        elif ptype == "time_range":
            # Just use the start time
            start_str = match.group(1)
            start_match = re.match(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', start_str)
            if start_match:
                hour = int(start_match.group(1))
                minute = int(start_match.group(2) or 0)
                ampm = start_match.group(3)
                if ampm and ampm.lower() == "pm" and hour < 12:
                    hour += 12
                if ampm and ampm.lower() == "am" and hour == 12:
                    hour = 0
                return (hour, minute)

    except (ValueError, IndexError):
        return None
    return None


def _estimate_duration(raw: str, ptype: str, match: re.Match) -> int | None:
    """Estimate duration in minutes from a duration pattern."""
    try:
        if ptype == "explicit_duration":
            amount = int(match.group(1))
            unit = match.group(2).lower()
            if "min" in unit:
                return amount
            elif "hour" in unit or "hr" in unit:
                return amount * 60
        elif ptype == "minutes":
            return int(match.group(1))
        elif ptype == "hours":
            return int(match.group(1)) * 60
        elif ptype == "half_hour":
            return 30
        elif ptype == "quick":
            return 15
    except (ValueError, IndexError):
        return None
    return None


# --- Conflict detection and suggestion generation ---------------------------

def check_conflicts(
    detection: SchedulingDetection,
    calendar_events: list[dict[str, Any]],
    depth: str = DEPTH_SYNC_NOTIFY,
) -> list[SchedulingSuggestion]:
    """Check if proposed meeting times conflict with existing events.

    Args:
        detection: The scheduling detection from an email.
        calendar_events: List of existing calendar events (dicts with
            "title", "start", "end" keys).

    Returns:
        List of scheduling suggestions (conflict warnings or create event).
    """
    suggestions: list[SchedulingSuggestion] = []

    for extracted in detection.extracted_times:
        if not extracted.estimated_start or not extracted.estimated_end:
            continue

        conflict_found = False
        for event in calendar_events:
            try:
                evt_start = _parse_event_time(event.get("start"))
                evt_end = _parse_event_time(event.get("end"))
                if evt_start and evt_end:
                    # Check for overlap
                    if (extracted.estimated_start < evt_end and extracted.estimated_end > evt_start):
                        conflict_found = True
                        conflict_suggestion = SchedulingSuggestion(
                            type="conflict_warning",
                            email_subject=detection.subject,
                            email_from=detection.proposed_by,
                            proposed_time=extracted,
                            conflict_with=event.get("title", "existing event"),
                            confidence=extracted.confidence * 0.9,
                            message=(
                                f"Meeting proposed in '{detection.subject}' conflicts with "
                                f"'{event.get('title', 'existing event')}' at {extracted.date_text} {extracted.time_text}. "
                                f"Would you like me to propose an alternative time?"
                            ),
                        )
                        if depth in (DEPTH_AGENT_MEDIATED, DEPTH_FULL_TWO_WAY):
                            conflict_suggestion.draft_reply = _draft_conflict_reply(
                                detection, event.get("title", "existing event"), extracted
                            )
                        if depth == DEPTH_FULL_TWO_WAY:
                            conflict_suggestion.auto_action = True
                        suggestions.append(conflict_suggestion)
                        break
            except (ValueError, TypeError):
                continue

        if not conflict_found:
            create_suggestion = SchedulingSuggestion(
                type="create_event",
                email_subject=detection.subject,
                email_from=detection.proposed_by,
                proposed_time=extracted,
                confidence=extracted.confidence,
                message=(
                    f"Ready to create: '{detection.subject}' proposed by {detection.proposed_by} "
                    f"for {extracted.date_text} {extracted.time_text}. "
                    f"No conflicts found. Shall I add it to your calendar?"
                ),
            )
            if depth in (DEPTH_AGENT_MEDIATED, DEPTH_FULL_TWO_WAY):
                create_suggestion.draft_reply = _draft_accept_reply(
                    detection, extracted
                )
            if depth == DEPTH_FULL_TWO_WAY:
                create_suggestion.auto_action = True
            suggestions.append(create_suggestion)

    return suggestions


def _draft_accept_reply(
    detection: SchedulingDetection,
    extracted: ExtractedTime,
) -> str:
    """Draft a reply accepting a meeting proposal (agent_mediated+)."""
    time_str = f"{extracted.date_text} {extracted.time_text}".strip()
    return (
        f"Hi {detection.proposed_by.split('@')[0]},\n\n"
        f"That works for me. I've added '{detection.subject}' to my calendar "
        f"for {time_str}. Looking forward to it.\n\n"
        f"Best"
    )


def _draft_conflict_reply(
    detection: SchedulingDetection,
    conflict_title: str,
    extracted: ExtractedTime,
) -> str:
    """Draft a reply proposing an alternative time due to a conflict (agent_mediated+)."""
    time_str = f"{extracted.date_text} {extracted.time_text}".strip()
    return (
        f"Hi {detection.proposed_by.split('@')[0]},\n\n"
        f"Thanks for the invite for {time_str}. Unfortunately I have a conflict "
        f"with '{conflict_title}' at that time. Could we find another slot? "
        f"I'm happy to suggest a few alternatives.\n\n"
        f"Best"
    )


def _parse_event_time(time_str: str) -> datetime | None:
    """Parse an event time string (ISO or common formats)."""
    if not time_str:
        return None
    try:
        # Try ISO format first
        return datetime.fromisoformat(time_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        pass
    try:
        return datetime.fromisoformat(time_str)
    except (ValueError, AttributeError):
        return None


def scan_emails_for_scheduling(
    emails: list[dict[str, Any]],
    calendar_events: list[dict[str, Any]],
    depth: str = DEPTH_SYNC_NOTIFY,
) -> dict[str, Any]:
    """Full email-to-schedule pipeline: scan emails, detect meetings, check conflicts.

    Args:
        emails: List of email message dicts with subject, from_address,
            snippet, has_calendar_invite fields.
        calendar_events: List of existing calendar events.
        depth: Email integration depth — one of ``sync_notify``,
            ``agent_mediated``, or ``full_two_way``. At ``sync_notify``
            the scan is read-only (detect + suggest). At
            ``agent_mediated`` draft replies are included. At
            ``full_two_way`` suggestions are marked auto-actionable.

    Returns:
        Dict with:
          - detections: List of SchedulingDetection for scheduling-related emails
          - suggestions: List of SchedulingSuggestion (create event / conflict warning)
          - summary: Human-readable summary string
          - stats: Counts (total_scanned, scheduling_related, proposals, conflicts)
          - depth: The depth level used for this scan
          - agent_actions_enabled: Whether draft replies were generated
          - autonomous_enabled: Whether suggestions are auto-actionable
    """
    if depth not in _VALID_DEPTHS:
        depth = DEPTH_SYNC_NOTIFY
    detections: list[SchedulingDetection] = []
    all_suggestions: list[SchedulingSuggestion] = []

    for email_msg in emails:
        detection = detect_scheduling_content(
            subject=email_msg.get("subject", ""),
            snippet=email_msg.get("snippet", ""),
            body_text=email_msg.get("body_text", ""),
            has_calendar_invite=email_msg.get("has_calendar_invite", False),
            from_address=email_msg.get("from_address", ""),
        )

        if detection.is_scheduling_related:
            detections.append(detection)
            suggestions = check_conflicts(detection, calendar_events, depth=depth)
            all_suggestions.extend(suggestions)

    # Generate summary
    stats = {
        "total_scanned": len(emails),
        "scheduling_related": len(detections),
        "meeting_proposals": sum(1 for d in detections if d.is_meeting_proposal),
        "calendar_invites": sum(1 for d in detections if d.is_calendar_invite),
        "reschedules": sum(1 for d in detections if d.is_reschedule),
        "cancellations": sum(1 for d in detections if d.is_cancellation),
        "conflicts": sum(1 for s in all_suggestions if s.type == "conflict_warning"),
        "create_ready": sum(1 for s in all_suggestions if s.type == "create_event"),
        "draft_replies": sum(1 for s in all_suggestions if s.draft_reply is not None),
        "auto_actions": sum(1 for s in all_suggestions if s.auto_action),
    }

    summary_parts: list[str] = []
    if stats["scheduling_related"] == 0:
        summary_parts.append("No scheduling-related emails found in your inbox.")
    else:
        summary_parts.append(
            f"Found {stats['scheduling_related']} scheduling-related email"
            f"{'s' if stats['scheduling_related'] != 1 else ''}."
        )
        if stats["meeting_proposals"]:
            summary_parts.append(f"{stats['meeting_proposals']} meeting proposal{'s' if stats['meeting_proposals'] != 1 else ''}.")
        if stats["calendar_invites"]:
            summary_parts.append(f"{stats['calendar_invites']} calendar invite{'s' if stats['calendar_invites'] != 1 else ''}.")
        if stats["conflicts"]:
            summary_parts.append(f"{stats['conflicts']} potential conflict{'s' if stats['conflicts'] != 1 else ''} detected.")
        if stats["create_ready"]:
            summary_parts.append(f"{stats['create_ready']} event{'s' if stats['create_ready'] != 1 else ''} ready to create.")

    return {
        "detections": [d.to_dict() for d in detections],
        "suggestions": [s.to_dict() for s in all_suggestions],
        "summary": " ".join(summary_parts),
        "stats": stats,
        "depth": depth,
        "agent_actions_enabled": depth in (DEPTH_AGENT_MEDIATED, DEPTH_FULL_TWO_WAY),
        "autonomous_enabled": depth == DEPTH_FULL_TWO_WAY,
    }
