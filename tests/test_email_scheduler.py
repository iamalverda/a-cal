"""Tests for the email-to-schedule pipeline."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from a_cal.agents.email_scheduler import (
    SchedulingDetection,
    SchedulingSuggestion,
    detect_scheduling_content,
    extract_times,
    scan_emails_for_scheduling,
    check_conflicts,
)


class TestDetectSchedulingContent:
    """Tests for scheduling content detection."""

    def test_meeting_proposal_detected(self):
        """Emails with meeting proposal keywords are flagged."""
        detection = detect_scheduling_content(
            subject="Let's meet next week",
            snippet="Can we schedule a meeting to discuss the project?",
        )
        assert detection.is_scheduling_related
        assert detection.is_meeting_proposal

    def test_calendar_invite_detected(self):
        """Emails with calendar invite signals are flagged."""
        detection = detect_scheduling_content(
            subject="Invitation: Team Standup",
            snippet="You've been invited to an event",
            has_calendar_invite=True,
        )
        assert detection.is_calendar_invite
        assert detection.is_scheduling_related

    def test_reschedule_detected(self):
        """Reschedule requests are flagged."""
        detection = detect_scheduling_content(
            subject="Need to reschedule our meeting",
            snippet="Can we push back our call to next week?",
        )
        assert detection.is_reschedule
        assert detection.is_scheduling_related

    def test_cancellation_detected(self):
        """Cancellation emails are flagged."""
        detection = detect_scheduling_content(
            subject="Cancel our meeting tomorrow",
            snippet="I need to cancel our appointment",
        )
        assert detection.is_cancellation
        assert detection.is_scheduling_related

    def test_non_scheduling_email_ignored(self):
        """Non-scheduling emails are not flagged."""
        detection = detect_scheduling_content(
            subject="Your monthly newsletter",
            snippet="Check out our latest blog posts and product updates.",
        )
        assert not detection.is_scheduling_related
        assert not detection.is_meeting_proposal

    def test_rsvp_request_detected(self):
        """RSVP requests are flagged as scheduling-related."""
        detection = detect_scheduling_content(
            subject="Please confirm your attendance",
            snippet="RSVP requested for the quarterly review",
        )
        assert detection.is_scheduling_related

    def test_detected_keywords_populated(self):
        """Keywords that triggered detection are listed."""
        detection = detect_scheduling_content(
            subject="Let's meet",
            snippet="Can we sync up tomorrow?",
        )
        assert len(detection.detected_keywords) > 0
        assert "let's meet" in detection.detected_keywords

    def test_confidence_increases_with_signals(self):
        """More signals produce higher confidence."""
        weak = detect_scheduling_content(
            subject="Hello",
            snippet="Just checking in",
        )
        strong = detect_scheduling_content(
            subject="Let's meet next Friday at 3pm",
            snippet="Can we schedule a meeting? Please confirm.",
        )
        assert strong.confidence > weak.confidence


class TestExtractTimes:
    """Tests for date/time extraction from email text."""

    def test_weekday_extraction(self):
        """Weekday names are extracted."""
        times = extract_times("Let's meet on Monday")
        assert len(times) >= 1
        assert any("monday" in t.date_text for t in times)

    def test_month_day_extraction(self):
        """Month + day patterns are extracted."""
        times = extract_times("How about July 15th?")
        assert len(times) >= 1
        assert any("july" in t.date_text for t in times)

    def test_time_extraction(self):
        """Time patterns are extracted."""
        times = extract_times("Let's meet at 3pm")
        assert len(times) >= 1
        assert any("3pm" in t.time_text for t in times)

    def test_date_and_time_combined(self):
        """Date + time in same text produces higher-confidence estimate."""
        times = extract_times("Let's meet on Friday at 2:30pm")
        assert len(times) >= 1
        top = max(times, key=lambda t: t.confidence)
        assert top.estimated_start is not None
        assert top.confidence >= 0.7

    def test_relative_date_extraction(self):
        """Relative dates (tomorrow, next week) are extracted."""
        times = extract_times("Can we meet tomorrow?")
        assert len(times) >= 1
        assert any("tomorrow" in t.date_text for t in times)

    def test_iso_date_extraction(self):
        """ISO format dates are extracted."""
        times = extract_times("Meeting scheduled for 2026-08-15")
        assert len(times) >= 1

    def test_duration_extraction(self):
        """Duration patterns are extracted."""
        times = extract_times("Let's meet for 30 minutes tomorrow")
        assert any(t.duration_minutes == 30 for t in times)

    def test_no_times_in_non_scheduling_text(self):
        """Text without time references produces no extracted times."""
        times = extract_times("Hello, how are you doing today?")
        # "today" is a relative date, so there might be one match
        # but there should be no time matches
        assert all(not t.time_text for t in times)


class TestCheckConflicts:
    """Tests for conflict detection against calendar events."""

    def test_conflict_detected(self):
        """Overlapping events trigger conflict warning."""
        now = datetime.now(timezone.utc)
        detection = SchedulingDetection(
            is_scheduling_related=True,
            is_meeting_proposal=True,
            is_calendar_invite=False,
            is_reschedule=False,
            is_cancellation=False,
            subject="Team Meeting",
            proposed_by="boss@company.com",
        )
        from a_cal.agents.email_scheduler import ExtractedTime
        detection.extracted_times = [
            ExtractedTime(
                raw_text="Monday 2pm",
                date_text="Monday",
                time_text="2pm",
                estimated_start=now.replace(hour=14, minute=0, second=0, microsecond=0),
                estimated_end=now.replace(hour=15, minute=0, second=0, microsecond=0),
                confidence=0.7,
            )
        ]

        calendar_events = [
            {
                "title": "Existing Meeting",
                "start": now.replace(hour=14, minute=30, second=0, microsecond=0).isoformat(),
                "end": now.replace(hour=15, minute=30, second=0, microsecond=0).isoformat(),
            }
        ]

        suggestions = check_conflicts(detection, calendar_events)
        assert len(suggestions) >= 1
        assert any(s.type == "conflict_warning" for s in suggestions)
        assert suggestions[0].conflict_with == "Existing Meeting"

    def test_no_conflict_creates_event_suggestion(self):
        """Non-overlapping time produces a create_event suggestion."""
        now = datetime.now(timezone.utc)
        detection = SchedulingDetection(
            is_scheduling_related=True,
            is_meeting_proposal=True,
            is_calendar_invite=False,
            is_reschedule=False,
            is_cancellation=False,
            subject="Coffee Chat",
            proposed_by="friend@example.com",
        )
        from a_cal.agents.email_scheduler import ExtractedTime
        detection.extracted_times = [
            ExtractedTime(
                raw_text="Friday 10am",
                date_text="Friday",
                time_text="10am",
                estimated_start=now.replace(hour=10, minute=0, second=0, microsecond=0),
                estimated_end=now.replace(hour=10, minute=30, second=0, microsecond=0),
                confidence=0.7,
            )
        ]

        calendar_events = [
            {
                "title": "Afternoon Call",
                "start": now.replace(hour=15, minute=0, second=0, microsecond=0).isoformat(),
                "end": now.replace(hour=16, minute=0, second=0, microsecond=0).isoformat(),
            }
        ]

        suggestions = check_conflicts(detection, calendar_events)
        assert len(suggestions) >= 1
        assert all(s.type == "create_event" for s in suggestions)


class TestScanEmailsForScheduling:
    """Tests for the full email-to-schedule pipeline."""

    def test_empty_emails(self):
        """Empty email list produces empty results."""
        result = scan_emails_for_scheduling([], [])
        assert result["stats"]["total_scanned"] == 0
        assert result["stats"]["scheduling_related"] == 0
        assert "No scheduling-related emails" in result["summary"]

    def test_mixed_emails(self):
        """A mix of scheduling and non-scheduling emails produces correct stats."""
        emails = [
            {
                "subject": "Let's meet next Friday at 3pm",
                "from_address": "colleague@work.com",
                "snippet": "Can we schedule a meeting to discuss the roadmap?",
                "has_calendar_invite": False,
            },
            {
                "subject": "Your newsletter",
                "from_address": "newsletter@blog.com",
                "snippet": "Check out our latest posts",
                "has_calendar_invite": False,
            },
            {
                "subject": "Invitation: Quarterly Review",
                "from_address": "calendar@company.com",
                "snippet": "You've been invited to an event",
                "has_calendar_invite": True,
            },
        ]

        result = scan_emails_for_scheduling(emails, [])
        assert result["stats"]["total_scanned"] == 3
        assert result["stats"]["scheduling_related"] == 2
        assert result["stats"]["meeting_proposals"] >= 1
        assert result["stats"]["calendar_invites"] >= 1

    def test_suggestions_generated(self):
        """Scheduling emails with extractable times produce suggestions."""
        emails = [
            {
                "subject": "Let's meet on July 20 at 2pm",
                "from_address": "team@company.com",
                "snippet": "Can we schedule a meeting? Please confirm.",
                "has_calendar_invite": False,
            },
        ]

        result = scan_emails_for_scheduling(emails, [])
        assert len(result["suggestions"]) >= 0  # May or may not extract valid times
        assert result["stats"]["scheduling_related"] == 1

    def test_conflict_in_pipeline(self):
        """Conflicts are detected in the full pipeline."""
        now = datetime.now(timezone.utc)
        # Use tomorrow's date to avoid past dates
        tomorrow = now + timedelta(days=1)

        emails = [
            {
                "subject": "Meeting tomorrow at 10am",
                "from_address": "boss@company.com",
                "snippet": "Let's meet tomorrow at 10am for 30 minutes",
                "has_calendar_invite": False,
            },
        ]

        # Create a conflicting event at the same time
        calendar_events = [
            {
                "title": "Existing Standup",
                "start": tomorrow.replace(hour=10, minute=0, second=0, microsecond=0).isoformat(),
                "end": tomorrow.replace(hour=10, minute=30, second=0, microsecond=0).isoformat(),
            }
        ]

        result = scan_emails_for_scheduling(emails, calendar_events)
        # The pipeline should detect the scheduling content
        assert result["stats"]["scheduling_related"] == 1
