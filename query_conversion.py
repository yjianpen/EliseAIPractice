"""Convert a raw user message into a UserQuery (user side of the agent ReAct loop).

Keyword rules only for now (no LLM call), so conversion is fast, free and deterministic.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime

from user_query_proto import Channel, Intent, ReporterRole, Source, Status, Urgency, UserQuery

# (incident_type, category, urgency, keywords). Order matters: the first match wins, so the most urgent
# topics come first.
TOPICS = [
    ("gas", "essential_services", Urgency.EMERGENCY, ["gas", "smell gas", "gas leak", "carbon monoxide"]),
    ("heat", "essential_services", Urgency.EMERGENCY, ["no heat", "heat", "heating", "radiator", "freezing"]),
    ("hot_water", "essential_services", Urgency.EMERGENCY, ["hot water", "water heater"]),
    ("water_leak", "habitability_repairs", Urgency.URGENT, ["leak", "leaked", "leaking", "flood", "flooding"]),
    ("pests", "health_hazards", Urgency.URGENT, ["mice", "mouse", "rats", "roaches", "bed bugs", "pests"]),
    ("mold", "health_hazards", Urgency.URGENT, ["mold", "mildew"]),
    ("noise", "quality_of_life", Urgency.ROUTINE, ["noise", "noisy", "loud", "music", "party"]),
    ("leasing", "leasing_costs", Urgency.ROUTINE, ["lease", "renewal", "renew", "move out", "sublet"]),
    ("rent_and_fees", "leasing_costs", Urgency.ROUTINE, ["rent", "fee", "fees", "deposit", "discount", "price"]),
    ("pets", "leasing_costs", Urgency.ROUTINE, ["pet", "pets", "dog", "cat"]),
    ("parking", "leasing_costs", Urgency.ROUTINE, ["parking", "garage"]),
    ("amenities", "building_life", Urgency.ROUTINE, ["gym", "package", "packages", "amenity", "amenities"]),
]
OTHER = ("other", "other", Urgency.ROUTINE)

INTENT_PATTERNS = [  # checked in order; the first match wins
    (Intent.FOLLOW_UP, r"\b(follow(ing)? up|any update|still (not|no|waiting)|again)\b"),
    (Intent.COMPLAINT, r"\b(complain|complaint|unacceptable|ridiculous|fed up)\b"),
    (Intent.REQUEST_CHANGE, r"\b(cancel|change my|switch|transfer|update my)\b"),
    (Intent.ASK_QUESTION, r"\?|\b(may i|can i|could i|is there|are there|how (much|do|long)|what|when|where)\b"),
]


def classify_incident(text: str) -> tuple[str, str, Urgency]:
    """Return (incident_type, category, urgency) for the first matching topic, or ('other', ...)."""
    lowered = text.lower()
    for incident_type, category, urgency, keywords in TOPICS:
        if any(re.search(rf"\b{re.escape(kw)}\b", lowered) for kw in keywords):
            return incident_type, category, urgency
    return OTHER


def detect_intent(text: str) -> Intent:
    """Follow-up, complaint, change request or question; anything else is treated as an issue report."""
    lowered = text.lower()
    for intent, pattern in INTENT_PATTERNS:
        if re.search(pattern, lowered):
            return intent
    return Intent.REPORT_ISSUE


def convert_message(text: str, channel: Channel = Channel.UNKNOWN, source: Source = Source.TENANT_MESSAGE,
                    tenant_id: str | None = None, property_id: str | None = None, unit_id: str | None = None,
                    created_at: datetime | None = None) -> UserQuery:
    """Build a UserQuery from a raw message plus whatever metadata the caller already knows."""
    incident_type, category, urgency = classify_incident(text)
    return UserQuery(
        query_id=f"q-{uuid.uuid4().hex[:12]}", source=source, created_at=created_at or datetime.now(),
        channel=channel, category=category, incident_type=incident_type, urgency=urgency,
        intent=detect_intent(text), status=Status.OPEN, text=text.strip(),
        reporter_role=ReporterRole.TENANT if tenant_id else ReporterRole.UNKNOWN,
        tenant_id=tenant_id, property_id=property_id, unit_id=unit_id)
