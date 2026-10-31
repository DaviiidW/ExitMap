"""List, detail and states of the detected services (spec F3, F4-1, F4-2, F7, F8-5).

- The list has one entry per service and account (F3-1), in three groups: services with
  an alert, then *pending* ones, then the rest; by name inside each group (F3-2).
- The search matches part of the name or the domain, ignoring case (F3-3). Filters by
  account, relation type and state are combined: all must hold (F3-4).
- Opening the detail removes the service's alert (F8-5).
- "Delete account" and "Revoke access" open the management link in the browser; the state
  does not change on its own (F6-1, F6-2).
"""

from dataclasses import dataclass, replace

from exitmap.app.unsubscribe import Opener, SystemOpener
from exitmap.domain.models import Account, Evidence, RelationType, Service, State
from exitmap.errors import ExitMapError
from exitmap.storage.db import Database


@dataclass(frozen=True)
class ServiceFilter:
    """Search text and filters; ``None`` means the filter is not applied."""

    text: str = ""
    account_id: int | None = None
    relation_type: RelationType | None = None
    state: State | None = None


def matches(service: Service, criteria: ServiceFilter) -> bool:
    """Whether ``service`` meets the search and every filter (F3-3, F3-4)."""
    text = criteria.text.strip().casefold()
    if text and text not in service.name.casefold() and text not in service.domain.casefold():
        return False
    if criteria.account_id is not None and service.account_id != criteria.account_id:
        return False
    if criteria.relation_type is not None and criteria.relation_type not in service.relation_types:
        return False
    if criteria.state is not None and service.state is not criteria.state:
        return False
    return True


def sort_key(service: Service) -> tuple[int, str, str, int]:
    """Alert first, then *pending*, then the rest; by name inside each group (F3-2)."""
    if service.has_alert:
        group = 0
    elif service.state is State.PENDING:
        group = 1
    else:
        group = 2
    return (group, service.name.casefold(), service.domain, service.account_id or 0)


@dataclass(frozen=True)
class ServiceDetail:
    """What the service page shows (F4-1, F4-2)."""

    service: Service
    account: Account
    evidence: list[Evidence]


class ServiceCatalogue:
    """Read and update the services saved in the database."""

    def __init__(self, db: Database, opener: Opener | None = None) -> None:
        self.db = db
        self.opener = opener or SystemOpener()

    def list(self, criteria: ServiceFilter = ServiceFilter()) -> list[Service]:
        """Services that meet ``criteria``, in the list order (F3-2..4).

        An empty list is the case "nothing matches" (F3-5).
        """
        services = [s for s in self.db.list_services() if matches(s, criteria)]
        return sorted(services, key=sort_key)

    def detail(self, service_id: int) -> ServiceDetail:
        """Data and evidence of a service; its alert is removed (F4-1, F4-2, F8-5)."""
        service = self._service(service_id)
        if service.has_alert:
            self.db.clear_alert(service_id)
            service = replace(service, has_alert=False)
        account = next(a for a in self.db.list_accounts() if a.id == service.account_id)
        return ServiceDetail(service, account, self.db.list_evidence(service_id))

    def set_state(self, service_id: int, state: State) -> Service:
        """Give a service one of the states of the table (F7-2)."""
        self._service(service_id)
        self.db.set_state(service_id, state)
        return self._service(service_id)

    def open_management(self, service_id: int) -> str:
        """Open the management link in the browser and return it (F6-1).

        The state is not changed: the user sets it after acting on the web (F6-2).
        """
        url = self._service(service_id).manage_url
        if not url:
            raise ExitMapError()
        self.opener.open_url(url)
        return url

    def _service(self, service_id: int) -> Service:
        service = self.db.get_service(service_id)
        if service is None:
            raise ExitMapError()
        return service
