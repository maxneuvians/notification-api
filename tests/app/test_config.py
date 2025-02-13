import importlib
import os
from unittest import mock

import pytest

from app import config
from app.config import QueueNames


def cf_conf():
    os.environ["ADMIN_BASE_URL"] = "cf"


@pytest.fixture
def reload_config():
    """
    Reset config, by simply re-running config.py from a fresh environment
    """
    old_env = os.environ.copy()

    yield

    os.environ = old_env
    importlib.reload(config)


def test_load_cloudfoundry_config_if_available(monkeypatch, reload_config):
    os.environ["ADMIN_BASE_URL"] = "env"
    monkeypatch.setenv("VCAP_SERVICES", "some json blob")
    monkeypatch.setenv("VCAP_APPLICATION", "some json blob")

    with mock.patch("app.cloudfoundry_config.extract_cloudfoundry_config", side_effect=cf_conf) as cf_config:
        # reload config so that its module level code (ie: all of it) is re-instantiated
        importlib.reload(config)

    assert cf_config.called

    assert os.environ["ADMIN_BASE_URL"] == "cf"
    assert config.Config.ADMIN_BASE_URL == "cf"


def test_load_config_if_cloudfoundry_not_available(monkeypatch, reload_config):
    os.environ["ADMIN_BASE_URL"] = "env"

    monkeypatch.delenv("VCAP_SERVICES", raising=False)

    with mock.patch("app.cloudfoundry_config.extract_cloudfoundry_config") as cf_config:
        # reload config so that its module level code (ie: all of it) is re-instantiated
        importlib.reload(config)

    assert not cf_config.called

    assert os.environ["ADMIN_BASE_URL"] == "env"
    assert config.Config.ADMIN_BASE_URL == "env"


def test_queue_names_all_queues_correct():
    # Need to ensure that all_queues() only returns queue names used in API
    queues = QueueNames.all_queues()
    assert len(queues) == 17
    assert (
        set(
            [
                QueueNames.PRIORITY,
                QueueNames.BULK,
                QueueNames.PERIODIC,
                QueueNames.DATABASE,
                QueueNames.PRIORITY_DATABASE,
                QueueNames.NORMAL_DATABASE,
                QueueNames.BULK_DATABASE,
                QueueNames.SEND_SMS,
                QueueNames.SEND_THROTTLED_SMS,
                QueueNames.SEND_EMAIL,
                QueueNames.RESEARCH_MODE,
                QueueNames.REPORTING,
                QueueNames.JOBS,
                QueueNames.RETRY,
                QueueNames.NOTIFY,
                # QueueNames.CREATE_LETTERS_PDF,
                QueueNames.CALLBACKS,
                # QueueNames.LETTERS,
                QueueNames.DELIVERY_RECEIPTS,
            ]
        )
        == set(queues)
    )


def test_get_safe_config(mocker, reload_config):
    mock_get_class_attrs = mocker.patch("notifications_utils.logging.get_class_attrs")
    mock_get_sensitive_config = mocker.patch("app.config.Config.get_sensitive_config")

    config.Config.get_safe_config()
    assert mock_get_class_attrs.called
    assert mock_get_sensitive_config.called


def test_get_sensitive_config():
    sensitive_config = config.Config.get_sensitive_config()
    assert sensitive_config
    for key in sensitive_config:
        assert key
