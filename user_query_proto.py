"""Canonical schema for a user query (definition only).

Every incoming query is converted to a UserQuery: NYC 311 rows, tenant messages, emails, SMS, phone
transcripts and portal requests. It holds structured fields (time, place, classification, status) and
unstructured content (free text, attachments). 311 rows have no free text, so `text` is None for them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

SCHEMA_VERSION = "1.0"


class Source(str, Enum):
    NYC_311 = "nyc_311"
    TENANT_MESSAGE = "tenant_message"
    EMAIL = "email"
    SMS = "sms"
    PHONE_TRANSCRIPT = "phone_transcript"
    PORTAL = "portal"


class Channel(str, Enum):
    ONLINE = "online"
    PHONE = "phone"
    MOBILE = "mobile"
    SMS = "sms"
    EMAIL = "email"
    PORTAL = "portal"
    UNKNOWN = "unknown"


class ReporterRole(str, Enum):
    TENANT = "tenant"
    PROSPECT = "prospect"
    NEIGHBOR = "neighbor"
    OWNER = "owner"
    UNKNOWN = "unknown"


class LocationScope(str, Enum):
    UNIT = "unit"
    ENTIRE_BUILDING = "entire_building"
    COMMON_AREA = "common_area"
    OTHER_UNIT = "other_unit"
    STREET = "street"


class Urgency(str, Enum):
    EMERGENCY = "emergency"
    URGENT = "urgent"
    ROUTINE = "routine"
    CITY = "city"


class Intent(str, Enum):
    REPORT_ISSUE = "report_issue"
    ASK_QUESTION = "ask_question"
    FOLLOW_UP = "follow_up"
    COMPLAINT = "complaint"
    REQUEST_CHANGE = "request_change"


class RiskFlag(str, Enum):
    PROPERTY_DAMAGE = "property_damage"
    HEALTH_SAFETY = "health_safety"
    VULNERABLE_OCCUPANT = "vulnerable_occupant"
    MULTIPLE_UNITS = "multiple_units"


class Status(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"


class ResolutionOutcome(str, Enum):
    CORRECTED = "corrected"
    VIOLATION_ISSUED = "violation_issued"
    NO_ACCESS = "no_access"
    DUPLICATE = "duplicate"
    NO_VIOLATION = "no_violation"
    OTHER = "other"


@dataclass
class SourceLabels:
    """Raw labels from the source system, kept verbatim for traceability (311: three nested columns)."""
    problem: str | None = None      # 311 "Problem (formerly Complaint Type)", e.g. "WATER LEAK"
    detail: str | None = None       # 311 "Problem Detail (formerly Descriptor)", e.g. "HEAVY FLOW"
    additional: str | None = None   # 311 "Additional Details", e.g. "AT WALL OR CEILING"


@dataclass
class UserQuery:
    # Identity and source (required)
    query_id: str
    source: Source
    created_at: datetime
    channel: Channel
    # Classification (required)
    category: str                   # taxonomy category, e.g. "habitability_repairs"
    incident_type: str              # taxonomy topic, e.g. "water_leak"
    urgency: Urgency
    intent: Intent
    status: Status
    # Identity and source (optional)
    source_record_id: str | None = None          # 311 "Unique Key"
    schema_version: str = SCHEMA_VERSION
    is_synthetic: bool = False
    # Time
    occurred_at: datetime | None = None          # when the issue started, if stated ("last night")
    updated_at: datetime | None = None           # 311 "Resolution Action Updated Date"
    closed_at: datetime | None = None            # 311 "Closed Date"
    # Who (contact details are not stored here; link to the tenant record instead)
    reporter_role: ReporterRole = ReporterRole.UNKNOWN
    tenant_id: str | None = None
    language: str | None = None
    # Where
    property_id: str | None = None
    building_id: str | None = None               # 311 "BBL"
    unit_id: str | None = None                   # never present in 311
    address: str | None = None
    zip: str | None = None
    city: str | None = None
    state: str | None = None
    district: str | None = None                  # 311 "Borough"
    lat: float | None = None
    lon: float | None = None
    location_scope: LocationScope | None = None
    # What (detail)
    incident_subtype: str | None = None          # 311 "Problem Detail"
    condition: str | None = None                 # 311 "Additional Details"
    source_labels: SourceLabels | None = None
    # Unstructured content
    text: str | None = None                      # verbatim message; None for 311
    attachments: list[str] = field(default_factory=list)
    risk_flags: list[RiskFlag] = field(default_factory=list)
    # Handling and outcome
    handled_by: str | None = None                # 311 "Agency", or a vendor / work order id
    resolution_text: str | None = None           # 311 "Resolution Description"
    resolution_outcome: ResolutionOutcome | None = None
    duplicate_of: str | None = None              # query_id of the original report
