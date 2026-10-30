import logging

import pytest

from exitmap.logging_setup import LOG_FILE_NAME, LOGGER_NAME, setup_logging

SUBJECT = "Confirma tu cuenta de Netflix"
BODY = "Hola Ana, haz clic aquí para verificar"
ADDRESS = "ana.lopez@example.com"
ACCESS_TOKEN = "ya29.a0AfH6SMBx-simulated"
REFRESH_TOKEN = "1//0gSimulatedRefresh"
SECRETS = (SUBJECT, BODY, ADDRESS, ACCESS_TOKEN, REFRESH_TOKEN)


@pytest.fixture
def logger():
    yield logging.getLogger(LOGGER_NAME)
    for handler in list(logging.getLogger(LOGGER_NAME).handlers):
        if getattr(handler, "_exitmap", False):
            logging.getLogger(LOGGER_NAME).removeHandler(handler)
            handler.close()


def _flush(logger):
    for handler in logger.handlers:
        handler.flush()


def test_log_file_does_not_contain_sensitive_data(tmp_path, logger):
    log_path = setup_logging(tmp_path / "exitmap")
    child = logging.getLogger(f"{LOGGER_NAME}.providers.gmail")

    child.info("Processing message subject=%s", SUBJECT)
    child.info("Asunto: %s", SUBJECT)
    child.debug("body=%s", BODY)
    child.info("Message from %s", ADDRESS)
    child.info("Got access_token=%s refresh_token=%s", ACCESS_TOKEN, REFRESH_TOKEN)
    child.info("Request headers: Authorization: Bearer %s", ACCESS_TOKEN)
    try:
        raise RuntimeError(f"refresh failed for {ADDRESS} with {REFRESH_TOKEN}")
    except RuntimeError:
        child.exception("Token refresh error")
    child.warning("Analysis finished: 3 services")
    _flush(logger)

    content = log_path.read_text(encoding="utf-8")
    assert log_path == tmp_path / "exitmap" / LOG_FILE_NAME
    assert "Analysis finished: 3 services" in content
    assert "RuntimeError" in content
    for secret in SECRETS:
        assert secret not in content


def test_debug_is_not_written_by_default(tmp_path, logger):
    log_path = setup_logging(tmp_path)

    logger.debug("debug detail")
    logger.info("info detail")
    _flush(logger)

    content = log_path.read_text(encoding="utf-8")
    assert "debug detail" not in content
    assert "info detail" in content


def test_setup_twice_keeps_a_single_handler(tmp_path, logger):
    setup_logging(tmp_path / "first")
    log_path = setup_logging(tmp_path / "second")

    logger.info("only once")
    _flush(logger)

    ours = [h for h in logger.handlers if getattr(h, "_exitmap", False)]
    assert len(ours) == 1
    assert log_path.read_text(encoding="utf-8").count("only once") == 1
    assert "only once" not in (tmp_path / "first" / LOG_FILE_NAME).read_text(encoding="utf-8")
