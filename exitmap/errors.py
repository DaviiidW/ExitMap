"""Exceptions with an understandable message for the end user (constitution 5).

Each exception maps to a fixed Spanish text in ``ui.strings_es``: what failed and the
most likely solution. Messages never include the exception's arguments or causes, so
technical details (which may hold email data or tokens) stay out of what the user sees.
"""

from exitmap.ui.strings_es import ERRORS


class ExitMapError(Exception):
    """Base class for every error shown to the end user."""

    key = "unexpected"

    @property
    def problem(self) -> str:
        return ERRORS[self.key][0]

    @property
    def solution(self) -> str:
        return ERRORS[self.key][1]

    @property
    def user_message(self) -> str:
        return f"{self.problem} {self.solution}".strip()

    def __str__(self) -> str:
        return self.user_message


class OfflineError(ExitMapError):
    key = "offline"


class PermissionExpiredError(ExitMapError):
    key = "permission_expired"


class AuthorizationDeniedError(ExitMapError):
    key = "authorization_denied"


class AuthorizationTimeoutError(ExitMapError):
    key = "authorization_timeout"


class AuthorizationInvalidError(ExitMapError):
    key = "authorization_invalid"


class InvalidRegistrationError(ExitMapError):
    key = "invalid_registration"


class RegistrationMissingError(ExitMapError):
    key = "registration_missing"


class ReconnectRequiredError(ExitMapError):
    key = "reconnect_required"


class AccountAlreadyConnectedError(ExitMapError):
    key = "account_already_connected"


class AnalysisInProgressError(ExitMapError):
    key = "analysis_in_progress"


class InvalidDateError(ExitMapError):
    key = "invalid_date"


class InvalidDateRangeError(ExitMapError):
    key = "invalid_date_range"


class UnsubscribeFailedError(ExitMapError):
    key = "unsubscribe_failed"


class CatalogError(ExitMapError):
    key = "catalog_invalid"


class WrongPasswordError(ExitMapError):
    key = "wrong_password"


class KeyringUnavailableError(ExitMapError):
    key = "keyring_unavailable"
