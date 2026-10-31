"""The registration guide opened from the registration form matches the code (T044; F1-2)."""

from exitmap.providers import gmail, outlook
from exitmap.ui.dialogs import GUIDE_PATH


def test_guide_exists_where_the_registration_form_opens_it():
    assert GUIDE_PATH.is_file()


def test_guide_cites_the_scopes_redirect_and_permission_pages_used_by_the_code():
    guide = GUIDE_PATH.read_text(encoding="utf-8")
    assert gmail.READONLY_SCOPE in guide
    for scope in outlook.SCOPES:
        assert scope in guide
    assert f"http://{outlook.REDIRECT_HOST}" in guide
    assert gmail.PERMISSIONS_URL in guide
    assert outlook.PERMISSIONS_URL in guide
