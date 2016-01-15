import json
import uuid

from flask import url_for

from tests.app.conftest import sample_job as create_job


def test_get_jobs(notify_api, notify_db, notify_db_session, sample_template):

    _setup_jobs(notify_db, notify_db_session, sample_template)

    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            response = client.get(url_for('job.get_job'))
            assert response.status_code == 200
            resp_json = json.loads(response.get_data(as_text=True))
            assert len(resp_json['data']) == 5


def test_get_job_with_invalid_id_returns400(notify_api, notify_db,
                                            notify_db_session,
                                            sample_template):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            response = client.get(url_for('job.get_job', job_id='invalid_id'))
            assert response.status_code == 400
            resp_json = json.loads(response.get_data(as_text=True))
            assert resp_json == {'message': 'Invalid job id',
                                 'result': 'error'}


def test_get_job_with_unknown_id_returns404(notify_api, notify_db,
                                            notify_db_session,
                                            sample_template):
    random_id = str(uuid.uuid4())
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            response = client.get(url_for('job.get_job', job_id=random_id))
            assert response.status_code == 404
            resp_json = json.loads(response.get_data(as_text=True))
            assert resp_json == {'message': 'Job not found', 'result':
                                 'error'}


def test_get_job_by_id(notify_api, notify_db, notify_db_session,
                       sample_job):
    job_id = str(sample_job.id)
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            response = client.get(url_for('job.get_job', job_id=job_id))
            assert response.status_code == 200
            resp_json = json.loads(response.get_data(as_text=True))
            assert resp_json['data']['id'] == job_id


def test_post_job(notify_api, notify_db, notify_db_session, sample_template):
    job_id = uuid.uuid4()
    template_id = sample_template.id
    service_id = sample_template.service.id
    original_file_name = 'thisisatest.csv'
    data = {
        'id': str(job_id),
        'service': service_id,
        'template': template_id,
        'original_file_name': original_file_name
    }
    headers = [('Content-Type', 'application/json')]
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            response = client.post(
                url_for('job.create_job'),
                data=json.dumps(data),
                headers=headers)
    assert response.status_code == 201

    resp_json = json.loads(response.get_data(as_text=True))

    assert resp_json['data']['id'] == str(job_id)
    assert resp_json['data']['service'] == service_id
    assert resp_json['data']['template'] == template_id
    assert resp_json['data']['original_file_name'] == original_file_name


def _setup_jobs(notify_db, notify_db_session, template, number_of_jobs=5):
    for i in range(number_of_jobs):
        create_job(notify_db, notify_db_session, service=template.service,
                   template=template)
