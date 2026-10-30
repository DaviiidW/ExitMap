import re

import pytest

from exitmap import errors
from exitmap.ui.strings_es import ERRORS

ALL_ERRORS = [
    obj
    for obj in vars(errors).values()
    if isinstance(obj, type) and issubclass(obj, errors.ExitMapError)
]

SECRET_ARGS = ("ya29.secret-token", "ana@example.com", "Asunto: tu factura")

# Patterns that would reveal email content, addresses or credentials.
SENSITIVE = re.compile(r"@|https?://|bearer|token|\{|\}|%s", re.IGNORECASE)


def test_every_error_is_covered():
    assert len(ALL_ERRORS) == len(ERRORS)


@pytest.mark.parametrize("error_cls", ALL_ERRORS, ids=lambda c: c.__name__)
def test_message_is_spanish_text_with_problem(error_cls):
    exc = error_cls()
    problem, solution = ERRORS[error_cls.key]

    assert exc.problem == problem and problem.strip()
    assert exc.solution == solution
    assert str(exc) == exc.user_message
    assert exc.user_message.startswith(problem)
    assert solution in exc.user_message


@pytest.mark.parametrize("error_cls", ALL_ERRORS, ids=lambda c: c.__name__)
def test_message_has_no_sensitive_data(error_cls):
    exc = error_cls(*SECRET_ARGS)

    assert not SENSITIVE.search(exc.user_message)
    for secret in SECRET_ARGS:
        assert secret not in str(exc)


def test_keys_are_unique():
    keys = [cls.key for cls in ALL_ERRORS]
    assert len(keys) == len(set(keys))


def test_message_without_solution_has_no_trailing_space():
    exc = errors.AccountAlreadyConnectedError()
    assert exc.user_message == ERRORS["account_already_connected"][0]


def test_most_errors_suggest_a_solution():
    without_solution = [cls for cls in ALL_ERRORS if not cls().solution]
    assert without_solution == [errors.AccountAlreadyConnectedError]
