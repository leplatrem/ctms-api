# Test for metrics
from unittest.mock import Mock, patch

import pytest
from prometheus_client import CollectorRegistry, generate_latest
from prometheus_client.multiprocess import MultiProcessCollector
from prometheus_client.parser import text_string_to_metric_families
from pydantic import ValidationError
from structlog.testing import capture_logs

from ctms.app import app
from ctms.metrics import (
    get_metrics_reporting_registry,
    init_metrics,
    init_metrics_labels,
)

# Metric cardinatility numbers
# These numbers change as routes are added or changed
# Higher numbers = more ways to slice data, more storage, more processing time for summaries

# Cardinality of ctms_requests_total counter
METHOD_PATH_CODE_COMBINATIONS = 50

# Cardinality of ctms_requests_duration_seconds histogram
METHOD_PATH_CODEFAM_COMBOS = 36
DURATION_BUCKETS = 8
DURATION_COMBINATIONS = METHOD_PATH_CODEFAM_COMBOS * (DURATION_BUCKETS + 2)

# Base cardinatility of ctms_api_requests_total
# Actual is multiplied by the number of API clients
METHOD_API_PATH_COMBINATIONS = 17


@pytest.fixture
def setup_metrics():
    """Setup a metrics registry and metrics, use them in the app"""

    test_registry = CollectorRegistry()
    test_metrics = init_metrics(test_registry)
    # Because these methods are called from a middleware
    # we can't use dependency injection like with get_db
    with patch("ctms.app.get_metrics_registry", return_value=test_registry), patch(
        "ctms.app.get_metrics", return_value=test_metrics
    ):
        yield test_registry, test_metrics


@pytest.fixture
def registry(setup_metrics):
    """Get the test metrics registry"""
    test_registry, _ = setup_metrics
    return test_registry


@pytest.fixture
def metrics(setup_metrics):
    """Get the test metrics"""
    _, test_metrics = setup_metrics
    return test_metrics


def test_get_metrics_reporting_registry_standard():
    """get_metrics_reporting_registry() returns the passed registry."""
    passed_registry = CollectorRegistry()
    with patch("ctms.metrics.config.Settings") as settings:
        settings.return_value.prometheus_multiproc_dir = None
        the_registry = get_metrics_reporting_registry(passed_registry)
    assert the_registry is passed_registry


def test_get_metrics_reporting_registry_multiprocess(tmp_path):
    """get_metrics_reporting_registry() can register a multiprocessing collector."""
    passed_registry = CollectorRegistry()
    with patch("ctms.metrics.config.Settings") as settings:
        settings.return_value.prometheus_multiproc_dir = tmp_path
        the_registry = get_metrics_reporting_registry(passed_registry)
    assert the_registry is not passed_registry
    # pylint: disable=protected-access
    collectors = list(the_registry._collector_to_names.keys())
    assert len(collectors) == 1
    assert isinstance(collectors[0], MultiProcessCollector)


def test_get_metrics_reporting_registry_settings_error():
    """get_metrics_reporting_registry() handles invalid settings."""
    passed_registry = CollectorRegistry()
    with patch("ctms.metrics.config.Settings") as settings:
        settings.side_effect = ValidationError(errors=[], model=Mock)
        the_registry = get_metrics_reporting_registry(passed_registry)
    assert the_registry is passed_registry
    assert not the_registry._collector_to_names  # pylint: disable=protected-access


def test_init_metrics_labels(dbsession, client_id_and_secret, registry, metrics):
    """Test that init_metric_labels populates variants"""
    init_metrics_labels(dbsession, app, metrics)

    metrics_text = generate_latest(registry).decode()
    families = list(text_string_to_metric_families(metrics_text))
    metrics_by_name = {
        "ctms_requests": None,
        "ctms_requests_created": None,
        "ctms_requests_duration_seconds": None,
        "ctms_requests_duration_seconds_created": None,
        "ctms_api_requests": None,
        "ctms_api_requests_created": None,
    }
    for metric in families:
        if metric.name in metrics_by_name:
            metrics_by_name[metric.name] = metric
    not_found = [name for name, metric in metrics_by_name.items() if metric is None]
    assert not_found == []

    def get_labels(metric_name, label_names):
        labels = []
        for sample in metrics_by_name[metric_name].samples:
            sample_label = sample[1]
            label = tuple(sample_label[name] for name in label_names)
            labels.append(label)
        return sorted(labels)

    # ctms_requests has a metric for every method / path / status code combo
    req_label_names = ("method", "path_template", "status_code")
    req_labels = get_labels("ctms_requests", req_label_names)
    reqc_labels = get_labels("ctms_requests_created", req_label_names)
    assert len(req_labels) == METHOD_PATH_CODE_COMBINATIONS
    assert req_labels == reqc_labels
    assert ("GET", "/", "307") in req_labels
    assert ("GET", "/openapi.json", "200") in req_labels
    assert ("GET", "/ctms/{email_id}", "200") in req_labels
    assert ("GET", "/ctms/{email_id}", "401") in req_labels
    assert ("GET", "/ctms/{email_id}", "404") in req_labels
    assert ("GET", "/ctms/{email_id}", "422") in req_labels
    assert ("GET", "/ctms/{email_id}", "422") in req_labels
    assert ("PATCH", "/ctms/{email_id}", "200") in req_labels
    assert ("PUT", "/ctms/{email_id}", "200") in req_labels

    # ctms_requests_duration_seconds has a metric for each
    # method / path / status code family combo
    dur_label_names = ("method", "path_template", "status_code_family")
    dur_labels = get_labels("ctms_requests_duration_seconds", dur_label_names)
    assert len(dur_labels) == DURATION_COMBINATIONS
    assert ("GET", "/", "3xx") in dur_labels

    # ctms_api_requests has a metric for each
    # (method / path / client_id / status code family) combo for API paths
    # where API paths are those requiring authentication
    api_label_names = ("method", "path_template", "client_id", "status_code_family")
    api_labels = get_labels("ctms_api_requests", api_label_names)
    apic_labels = get_labels("ctms_api_requests_created", api_label_names)
    assert len(api_labels) == METHOD_API_PATH_COMBINATIONS
    assert api_labels == apic_labels
    client_id, _ = client_id_and_secret
    assert ("GET", "/ctms/{email_id}", client_id, "2xx") in api_labels
    assert ("GET", "/ctms/{email_id}", client_id, "4xx") in api_labels


def assert_request_metric_inc(
    metrics_registry: CollectorRegistry,
    method: str,
    path_template: str,
    status_code: int,
    count: int = 1,
):
    """Assert ctms_requests_total with given labels was incremented"""
    labels = {
        "method": method,
        "path_template": path_template,
        "status_code": str(status_code),
        "status_code_family": str(status_code)[0] + "xx",
    }
    assert metrics_registry.get_sample_value("ctms_requests_total", labels) == count


def assert_duration_metric_obs(
    metrics_registry: CollectorRegistry,
    method: str,
    path_template: str,
    status_code_family: str,
    limit: float = 0.1,
    count: int = 1,
):
    """Assert ctms_requests_duration_seconds with given labels was observed"""
    base_name = "ctms_requests_duration_seconds"
    labels = {
        "method": method,
        "path_template": path_template,
        "status_code_family": status_code_family,
    }
    bucket_labels = labels.copy()
    bucket_labels["le"] = str(limit)
    assert (
        metrics_registry.get_sample_value(f"{base_name}_bucket", bucket_labels) == count
    )
    assert metrics_registry.get_sample_value(f"{base_name}_count", labels) == count
    assert metrics_registry.get_sample_value(f"{base_name}_sum", labels) < limit


def assert_api_request_metric_inc(
    metrics_registry: CollectorRegistry,
    method: str,
    path_template: str,
    client_id: str,
    status_code_family: str,
    count: int = 1,
):
    """Assert ctms_api_requests_total with given labels was incremented"""
    labels = {
        "method": method,
        "path_template": path_template,
        "client_id": client_id,
        "status_code_family": status_code_family,
    }
    assert metrics_registry.get_sample_value("ctms_api_requests_total", labels) == count


def assert_pending_acoustic_sync_inc(
    metrics_registry: CollectorRegistry,
    count: int = 1,
):
    """Assert ctms_pending_acoustic_sync_total was incremented"""
    assert (
        metrics_registry.get_sample_value("ctms_pending_acoustic_sync_total") == count
    )


def test_homepage_request(anon_client, registry):
    """A homepage request emits metrics for / and /docs"""
    anon_client.get("/")
    assert_request_metric_inc(registry, "GET", "/", 307)
    assert_request_metric_inc(registry, "GET", "/docs", 200)
    assert_duration_metric_obs(registry, "GET", "/", "3xx")
    assert_duration_metric_obs(registry, "GET", "/docs", "2xx")


def test_api_request(client, minimal_contact, registry):
    """An API request emits API metrics as well."""
    email_id = minimal_contact.email.email_id
    client.get(f"/ctms/{email_id}")
    path = "/ctms/{email_id}"
    assert_request_metric_inc(registry, "GET", path, 200)
    assert_duration_metric_obs(registry, "GET", path, "2xx")
    assert_api_request_metric_inc(registry, "GET", path, "test_client", "2xx")


def test_pending_sync(client, minimal_contact, registry):
    """An API requests that schedules an Acoustic contact sync emits a metric."""
    data = {"email": {"first_name": "CTMS", "last_name": "User"}}
    email_id = minimal_contact.email.email_id
    response = client.patch(f"/ctms/{email_id}", json=data)
    assert response.status_code == 200
    path = "/ctms/{email_id}"
    assert_request_metric_inc(registry, "PATCH", path, 200)
    assert_duration_metric_obs(registry, "PATCH", path, "2xx", limit=0.5)
    assert_api_request_metric_inc(registry, "PATCH", path, "test_client", "2xx")
    assert_pending_acoustic_sync_inc(registry)


@pytest.mark.parametrize(
    "email_id,status_code",
    (
        ("07259262-7902-489c-ad65-473336635a3b", 404),
        ("an-invalid-id", 422),
    ),
)
def test_bad_api_request(client, dbsession, registry, email_id, status_code):
    """An API request that returns a 404 emits metrics."""
    resp = client.get(f"/ctms/{email_id}")
    assert resp.status_code == status_code
    path = "/ctms/{email_id}"
    assert_request_metric_inc(registry, "GET", path, status_code)
    status_code_family = str(status_code)[0] + "xx"
    assert_api_request_metric_inc(
        registry, "GET", path, "test_client", status_code_family
    )


def test_crash_request(client, dbsession, registry):
    """An exception-raising API request emits metric with 500s."""
    path = "/__crash__"
    with pytest.raises(RuntimeError):
        client.get(path)
    assert_request_metric_inc(registry, "GET", path, 500)
    assert_api_request_metric_inc(registry, "GET", path, "test_client", "5xx")


def test_unknown_path(anon_client, dbsession, registry):
    """A unknown path does not emit metrics with labels."""
    path = "/unknown"
    resp = anon_client.get(path)
    assert resp.status_code == 404
    metrics_text = generate_latest(registry).decode()
    for family in text_string_to_metric_families(metrics_text):
        if len(family.samples) == 1:
            # This metric is emitted, maybe because there are no labels
            sample = family.samples[0]
            assert sample.name in (
                "ctms_pending_acoustic_sync_total",
                "ctms_pending_acoustic_sync_created",
            )
            assert sample.labels == {}
        else:
            assert len(family.samples) == 0


def test_get_metrics(anon_client, setup_metrics):
    """An anonoymous user can request metrics."""
    with capture_logs() as cap_logs:
        resp = anon_client.get("/metrics")
    assert resp.status_code == 200
    assert len(cap_logs) == 1
    assert "trivial" not in cap_logs[0]


def test_prometheus_metrics_is_logged_as_trivial(anon_client, setup_metrics):
    """When Prometheus requests metrics, it is logged as trivial."""
    headers = {"user-agent": "Prometheus/2.26.0"}
    with capture_logs() as cap_logs:
        resp = anon_client.get("/metrics", headers=headers)
    assert resp.status_code == 200
    assert len(cap_logs) == 1
    assert cap_logs[0]["trivial"] is True
