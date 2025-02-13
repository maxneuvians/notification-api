import uuid
from unittest.mock import ANY

import pytest
from flask import json, url_for

from app.config import QueueNames
from app.models import (
    EMAIL_TYPE,
    KEY_TYPE_NORMAL,
    KEY_TYPE_TEAM,
    KEY_TYPE_TEST,
    LETTER_TYPE,
    NOTIFICATION_CREATED,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_PENDING_VIRUS_CHECK,
    NOTIFICATION_SENDING,
    SMS_TYPE,
    Job,
    Notification,
)
from app.schema_validation import validate
from app.v2.errors import RateLimitError
from app.v2.notifications.notification_schemas import post_letter_response
from tests import create_authorization_header
from tests.app.db import create_letter_contact, create_service, create_template
from tests.conftest import set_config_values

test_address = {
    "address_line_1": "test 1",
    "address_line_2": "test 2",
    "postcode": "test pc",
}


def letter_request(
    client,
    data,
    service_id,
    key_type=KEY_TYPE_NORMAL,
    _expected_status=201,
    precompiled=False,
):
    if precompiled:
        url = url_for("v2_notifications.post_precompiled_letter_notification")
    else:
        url = url_for("v2_notifications.post_notification", notification_type=LETTER_TYPE)
    resp = client.post(
        url,
        data=json.dumps(data),
        headers=[
            ("Content-Type", "application/json"),
            create_authorization_header(service_id=service_id, key_type=key_type),
        ],
    )
    json_resp = json.loads(resp.get_data(as_text=True))
    assert resp.status_code == _expected_status, json_resp
    return json_resp


@pytest.mark.skip(reason="Deprecated: LETTER CODE")
@pytest.mark.parametrize("reference", [None, "reference_from_client"])
def test_post_letter_notification_returns_201(client, sample_letter_template, mocker, reference):
    mock = mocker.patch("app.celery.tasks.letters_pdf_tasks.create_letters_pdf.apply_async")
    data = {
        "template_id": str(sample_letter_template.id),
        "personalisation": {
            "address_line_1": "Her Royal Highness Queen Elizabeth II",
            "address_line_2": "Buckingham Palace",
            "address_line_3": "London",
            "postcode": "SW1 1AA",
            "name": "Lizzie",
        },
    }

    if reference:
        data.update({"reference": reference})

    resp_json = letter_request(client, data, service_id=sample_letter_template.service_id)

    assert validate(resp_json, post_letter_response) == resp_json
    assert Job.query.count() == 0
    notification = Notification.query.one()
    assert notification.status == NOTIFICATION_CREATED
    assert resp_json["id"] == str(notification.id)
    assert resp_json["reference"] == reference
    assert resp_json["content"]["subject"] == sample_letter_template.subject
    assert resp_json["content"]["body"] == sample_letter_template.content
    assert "v2/notifications/{}".format(notification.id) in resp_json["uri"]
    assert resp_json["template"]["id"] == str(sample_letter_template.id)
    assert resp_json["template"]["version"] == sample_letter_template.version
    assert (
        "services/{}/templates/{}".format(sample_letter_template.service_id, sample_letter_template.id)
        in resp_json["template"]["uri"]
    )
    assert not resp_json["scheduled_for"]
    assert not notification.reply_to_text
    mock.assert_called_once_with([str(notification.id)], queue=QueueNames.CREATE_LETTERS_PDF)


@pytest.mark.skip(reason="Deprecated: LETTER CODE")
def test_post_letter_notification_sets_postage(client, notify_db_session, mocker):
    service = create_service(service_permissions=[LETTER_TYPE])
    template = create_template(service, template_type="letter", postage="first")
    mocker.patch("app.celery.tasks.letters_pdf_tasks.create_letters_pdf.apply_async")
    data = {
        "template_id": str(template.id),
        "personalisation": {
            "address_line_1": "Her Royal Highness Queen Elizabeth II",
            "address_line_2": "Buckingham Palace",
            "address_line_3": "London",
            "postcode": "SW1 1AA",
            "name": "Lizzie",
        },
    }

    resp_json = letter_request(client, data, service_id=service.id)

    assert validate(resp_json, post_letter_response) == resp_json
    notification = Notification.query.one()
    assert notification.postage == "first"


@pytest.mark.parametrize(
    "env",
    [
        "staging",
        "live",
    ],
)
def test_post_letter_notification_with_test_key_creates_pdf_and_sets_status_to_delivered(
    notify_api, client, sample_letter_template, mocker, env
):

    data = {
        "template_id": str(sample_letter_template.id),
        "personalisation": {
            "address_line_1": "Her Royal Highness Queen Elizabeth II",
            "address_line_2": "Buckingham Palace",
            "address_line_3": "London",
            "postcode": "SW1 1AA",
            "name": "Lizzie",
        },
        "reference": "foo",
    }

    fake_create_letter_task = mocker.patch("app.celery.letters_pdf_tasks.create_letters_pdf.apply_async")
    fake_create_dvla_response_task = mocker.patch("app.celery.research_mode_tasks.create_fake_letter_response_file.apply_async")

    with set_config_values(notify_api, {"NOTIFY_ENVIRONMENT": env}):
        letter_request(
            client,
            data,
            service_id=sample_letter_template.service_id,
            key_type=KEY_TYPE_TEST,
        )

    notification = Notification.query.one()

    fake_create_letter_task.assert_called_once_with([str(notification.id)], queue="research-mode-tasks")
    assert not fake_create_dvla_response_task.called
    assert notification.status == NOTIFICATION_DELIVERED


@pytest.mark.parametrize(
    "env",
    [
        "development",
        "preview",
    ],
)
def test_post_letter_notification_with_test_key_creates_pdf_and_sets_status_to_sending_and_sends_fake_response_file(
    notify_api, client, sample_letter_template, mocker, env
):

    data = {
        "template_id": str(sample_letter_template.id),
        "personalisation": {
            "address_line_1": "Her Royal Highness Queen Elizabeth II",
            "address_line_2": "Buckingham Palace",
            "address_line_3": "London",
            "postcode": "SW1 1AA",
            "name": "Lizzie",
        },
        "reference": "foo",
    }

    fake_create_letter_task = mocker.patch("app.celery.letters_pdf_tasks.create_letters_pdf.apply_async")
    fake_create_dvla_response_task = mocker.patch("app.celery.research_mode_tasks.create_fake_letter_response_file.apply_async")

    with set_config_values(notify_api, {"NOTIFY_ENVIRONMENT": env}):
        letter_request(
            client,
            data,
            service_id=sample_letter_template.service_id,
            key_type=KEY_TYPE_TEST,
        )

    notification = Notification.query.one()

    fake_create_letter_task.assert_called_once_with([str(notification.id)], queue="research-mode-tasks")
    assert fake_create_dvla_response_task.called
    assert notification.status == NOTIFICATION_SENDING


def test_post_letter_notification_returns_400_and_missing_template(client, sample_service_full_permissions):
    data = {"template_id": str(uuid.uuid4()), "personalisation": test_address}

    error_json = letter_request(
        client,
        data,
        service_id=sample_service_full_permissions.id,
        _expected_status=400,
    )

    assert error_json["status_code"] == 400
    assert error_json["errors"] == [{"error": "BadRequestError", "message": "Template not found"}]


def test_post_letter_notification_returns_400_for_empty_personalisation(
    client, sample_service_full_permissions, sample_letter_template
):
    data = {
        "template_id": str(sample_letter_template.id),
        "personalisation": {"address_line_1": "", "address_line_2": "", "postcode": ""},
    }

    error_json = letter_request(
        client,
        data,
        service_id=sample_service_full_permissions.id,
        _expected_status=400,
    )

    assert error_json["status_code"] == 400
    assert all([e["error"] == "ValidationError" for e in error_json["errors"]])
    assert set([e["message"] for e in error_json["errors"]]) == {
        "personalisation address_line_1 is required",
        "personalisation address_line_2 is required",
        "personalisation postcode is required",
    }


def test_notification_returns_400_for_missing_template_field(client, sample_service_full_permissions):
    data = {"personalisation": test_address}

    error_json = letter_request(
        client,
        data,
        service_id=sample_service_full_permissions.id,
        _expected_status=400,
    )

    assert error_json["status_code"] == 400
    assert error_json["errors"] == [{"error": "ValidationError", "message": "template_id is a required property"}]


def test_notification_returns_400_if_address_doesnt_have_underscores(client, sample_letter_template):
    data = {
        "template_id": str(sample_letter_template.id),
        "personalisation": {
            "address line 1": "Her Royal Highness Queen Elizabeth II",
            "address-line-2": "Buckingham Palace",
            "postcode": "SW1 1AA",
        },
    }

    error_json = letter_request(client, data, service_id=sample_letter_template.service_id, _expected_status=400)

    assert error_json["status_code"] == 400
    assert len(error_json["errors"]) == 2
    assert {
        "error": "ValidationError",
        "message": "personalisation address_line_1 is a required property",
    } in error_json["errors"]
    assert {
        "error": "ValidationError",
        "message": "personalisation address_line_2 is a required property",
    } in error_json["errors"]


def test_returns_a_429_limit_exceeded_if_rate_limit_exceeded(client, sample_letter_template, mocker):
    persist_mock = mocker.patch("app.notifications.process_notifications.persist_notification")
    mocker.patch(
        "app.v2.notifications.post_notifications.check_rate_limiting",
        side_effect=RateLimitError("LIMIT", "INTERVAL", "TYPE"),
    )

    data = {
        "template_id": str(sample_letter_template.id),
        "personalisation": test_address,
    }

    error_json = letter_request(client, data, service_id=sample_letter_template.service_id, _expected_status=429)

    assert error_json["status_code"] == 429
    assert error_json["errors"] == [
        {
            "error": "RateLimitError",
            "message": "Exceeded rate limit for key type TYPE of LIMIT requests per INTERVAL seconds",
        }
    ]

    assert not persist_mock.called


@pytest.mark.parametrize(
    "service_args",
    [{"service_permissions": [EMAIL_TYPE, SMS_TYPE]}, {"restricted": True}],
)
def test_post_letter_notification_returns_403_if_not_allowed_to_send_notification(client, notify_db_session, service_args):
    service = create_service(**service_args)
    template = create_template(service, template_type=LETTER_TYPE)

    data = {"template_id": str(template.id), "personalisation": test_address}

    error_json = letter_request(client, data, service_id=service.id, _expected_status=400)
    assert error_json["status_code"] == 400
    assert error_json["errors"] == [
        {
            "error": "BadRequestError",
            "message": "Service is not allowed to send letters",
        }
    ]


def test_post_letter_notification_doesnt_accept_team_key(client, sample_letter_template, mocker):
    mocker.patch("app.celery.letters_pdf_tasks.create_letters_pdf.apply_async")
    data = {
        "template_id": str(sample_letter_template.id),
        "personalisation": {
            "address_line_1": "Foo",
            "address_line_2": "Bar",
            "postcode": "Baz",
        },
    }

    error_json = letter_request(
        client,
        data,
        sample_letter_template.service_id,
        key_type=KEY_TYPE_TEAM,
        _expected_status=403,
    )

    assert error_json["status_code"] == 403
    assert error_json["errors"] == [
        {
            "error": "BadRequestError",
            "message": "Cannot send letters with a team api key",
        }
    ]


def test_post_letter_notification_doesnt_send_in_trial(client, sample_trial_letter_template, mocker):
    mocker.patch("app.celery.letters_pdf_tasks.create_letters_pdf.apply_async")
    data = {
        "template_id": str(sample_trial_letter_template.id),
        "personalisation": {
            "address_line_1": "Foo",
            "address_line_2": "Bar",
            "postcode": "Baz",
        },
    }

    error_json = letter_request(client, data, sample_trial_letter_template.service_id, _expected_status=403)

    assert error_json["status_code"] == 403
    assert error_json["errors"] == [
        {
            "error": "BadRequestError",
            "message": "Cannot send letters when service is in trial mode",
        }
    ]


def test_post_letter_notification_is_delivered_but_still_creates_pdf_if_in_trial_mode_and_using_test_key(
    client, sample_trial_letter_template, mocker
):
    fake_create_letter_task = mocker.patch("app.celery.letters_pdf_tasks.create_letters_pdf.apply_async")

    data = {
        "template_id": sample_trial_letter_template.id,
        "personalisation": {
            "address_line_1": "Foo",
            "address_line_2": "Bar",
            "postcode": "Baz",
        },
    }

    letter_request(
        client,
        data=data,
        service_id=sample_trial_letter_template.service_id,
        key_type=KEY_TYPE_TEST,
    )

    notification = Notification.query.one()
    assert notification.status == NOTIFICATION_DELIVERED
    fake_create_letter_task.assert_called_once_with([str(notification.id)], queue="research-mode-tasks")


def test_post_letter_notification_is_delivered_and_has_pdf_uploaded_to_test_letters_bucket_using_test_key(
    client, notify_user, mocker
):
    sample_letter_service = create_service(service_permissions=["letter"])
    mocker.patch("app.celery.letters_pdf_tasks.notify_celery.send_task")
    s3mock = mocker.patch(
        "app.v2.notifications.post_notifications.upload_letter_pdf",
        return_value="test.pdf",
    )
    data = {"reference": "letter-reference", "content": "bGV0dGVyLWNvbnRlbnQ="}
    letter_request(
        client,
        data=data,
        service_id=str(sample_letter_service.id),
        key_type=KEY_TYPE_TEST,
        precompiled=True,
    )

    notification = Notification.query.one()
    assert notification.status == NOTIFICATION_PENDING_VIRUS_CHECK
    s3mock.assert_called_once_with(ANY, b"letter-content", precompiled=True)


def test_post_letter_notification_persists_notification_reply_to_text(client, notify_db_session, mocker):
    mocker.patch("app.celery.letters_pdf_tasks.create_letters_pdf.apply_async")

    service = create_service(service_permissions=[LETTER_TYPE])
    service_address = "12 Main Street, London"
    letter_contact = create_letter_contact(service=service, contact_block=service_address, is_default=True)
    template = create_template(service=service, template_type="letter", reply_to=letter_contact.id)
    data = {
        "template_id": template.id,
        "personalisation": {
            "address_line_1": "Foo",
            "address_line_2": "Bar",
            "postcode": "Baz",
        },
    }
    letter_request(client, data=data, service_id=service.id, key_type=KEY_TYPE_NORMAL)

    notifications = Notification.query.all()
    assert len(notifications) == 1
    assert notifications[0].reply_to_text == service_address


def test_post_precompiled_letter_with_invalid_base64(client, notify_user, mocker):
    sample_service = create_service(service_permissions=["letter"])
    mocker.patch("app.v2.notifications.post_notifications.upload_letter_pdf")

    data = {"reference": "letter-reference", "content": "hi"}
    auth_header = create_authorization_header(service_id=sample_service.id)
    response = client.post(
        path="v2/notifications/letter",
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )

    assert response.status_code == 400, response.get_data(as_text=True)
    resp_json = json.loads(response.get_data(as_text=True))
    assert resp_json["errors"][0]["message"] == "Cannot decode letter content (invalid base64 encoding)"

    assert not Notification.query.first()


@pytest.mark.parametrize(
    "notification_postage, expected_postage",
    [("second", "second"), ("first", "first"), (None, "second")],
)
def test_post_precompiled_letter_notification_returns_201(client, notify_user, mocker, notification_postage, expected_postage):
    sample_service = create_service(service_permissions=["letter"])
    s3mock = mocker.patch("app.v2.notifications.post_notifications.upload_letter_pdf")
    mocker.patch("app.celery.letters_pdf_tasks.notify_celery.send_task")
    data = {"reference": "letter-reference", "content": "bGV0dGVyLWNvbnRlbnQ="}
    if notification_postage:
        data["postage"] = notification_postage
    auth_header = create_authorization_header(service_id=sample_service.id)
    response = client.post(
        path="v2/notifications/letter",
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )

    assert response.status_code == 201, response.get_data(as_text=True)

    s3mock.assert_called_once_with(ANY, b"letter-content", precompiled=True)

    notification = Notification.query.one()

    assert notification.billable_units == 0
    assert notification.status == NOTIFICATION_PENDING_VIRUS_CHECK
    assert notification.postage == expected_postage

    resp_json = json.loads(response.get_data(as_text=True))
    assert resp_json == {
        "id": str(notification.id),
        "reference": "letter-reference",
        "postage": expected_postage,
    }


def test_post_letter_notification_throws_error_for_invalid_postage(client, notify_user, mocker):
    sample_service = create_service(service_permissions=["letter"])
    data = {
        "reference": "letter-reference",
        "content": "bGV0dGVyLWNvbnRlbnQ=",
        "postage": "space unicorn",
    }
    auth_header = create_authorization_header(service_id=sample_service.id)
    response = client.post(
        path="v2/notifications/letter",
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )

    assert response.status_code == 400, response.get_data(as_text=True)
    resp_json = json.loads(response.get_data(as_text=True))
    assert resp_json["errors"][0]["message"] == "postage invalid. It must be either first or second."

    assert not Notification.query.first()
