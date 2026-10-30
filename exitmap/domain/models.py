"""Domain models: relation types, service states and the main entities.

Enum values are the ones stored in SQLite (plan §3), so they must not change.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class State(StrEnum):
    """What the end user has done with a service (spec F7)."""

    PENDING = "pending"
    KEEP = "keep"
    UNSUBSCRIBED = "unsubscribed"
    ACCESS_REVOKED = "access_revoked"
    ACCOUNT_DELETED = "account_deleted"
    DISMISSED = "dismissed"


class RelationType(StrEnum):
    """Kind of relation between the end user and a service (spec §3)."""

    REGISTERED = "registered"
    SUBSCRIPTION = "subscription"
    ACCESS = "access"


class LinkSource(StrEnum):
    """Where the management link comes from (spec F4-3, F4-4)."""

    CATALOG = "catalog"
    EMAIL = "email"
    HOMEPAGE = "homepage"


class UnsubscribeMethod(StrEnum):
    """How the end user can unsubscribe (spec F5, plan §4 "Baja")."""

    ONE_CLICK = "one_click"
    WEB = "web"
    MAILTO = "mailto"


class Provider(StrEnum):
    """Supported email providers."""

    GMAIL = "gmail"
    OUTLOOK = "outlook"


@dataclass
class Account:
    """A connected email account."""

    provider: Provider
    email: str
    client_registration_ref: str | None = None
    last_complete_analysis_at: datetime | None = None
    created_at: datetime | None = None
    id: int | None = None


@dataclass
class Service:
    """A service (registrable domain) detected in one account."""

    account_id: int | None
    domain: str
    name: str
    relation_types: set[RelationType] = field(default_factory=set)
    first_email_at: datetime | None = None
    last_email_at: datetime | None = None
    email_count: int = 0
    state: State = State.PENDING
    state_changed_at: datetime | None = None
    has_alert: bool = False
    manage_url: str | None = None
    manage_url_source: LinkSource | None = None
    unsubscribe_method: UnsubscribeMethod | None = None
    unsubscribe_target: str | None = None
    id: int | None = None


@dataclass
class Evidence:
    """An email the detection of a service is based on (spec F4-2)."""

    provider_message_id: str
    subject: str
    sent_at: datetime
    relation_type: RelationType
    service_id: int | None = None
    id: int | None = None
