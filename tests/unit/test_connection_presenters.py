"""No connection notice and accounts to reconnect (spec §5; plan §4)."""

from exitmap.domain.models import Account, Provider
from exitmap.errors import (
    AuthorizationDeniedError,
    OfflineError,
    PermissionExpiredError,
    ReconnectRequiredError,
)
from exitmap.ui import strings_es as text
from exitmap.ui.presenters import ConnectionStatus, needs_reconnect, reconnect_message


def test_offline_until_the_next_request_that_works():
    status = ConnectionStatus()
    assert not status.offline and status.notice is None
    status.record(OfflineError())
    assert status.offline and status.notice == text.OFFLINE_NOTICE
    status.record(AuthorizationDeniedError())  # says nothing about the network
    assert status.offline
    status.record(None)
    assert not status.offline and status.notice is None


def test_notice_names_the_actions_that_need_network():
    assert "Analizar" in text.OFFLINE_NOTICE and "baja automática" in text.OFFLINE_NOTICE
    assert "permiso" in text.OFFLINE_NOTICE


def test_needs_reconnect():
    assert needs_reconnect(PermissionExpiredError())
    assert needs_reconnect(ReconnectRequiredError())
    assert not needs_reconnect(OfflineError())


def test_reconnect_message_names_the_account():
    account = Account(Provider.GMAIL, "ana@gmail.com")
    message = reconnect_message(PermissionExpiredError(), account)
    assert message.startswith(PermissionExpiredError().user_message)
    assert "Cuenta afectada: ana@gmail.com." in message
