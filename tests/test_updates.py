from unittest.mock import Mock

import pytest
import requests

import tidal_dl_ng


@pytest.mark.parametrize(("tag", "available"), [("v0.25.0", True), ("v0.24.6", False), ("v0.22.0", False)])
def test_update_compares_versions(monkeypatch, tag, available):
    monkeypatch.setattr(tidal_dl_ng, "__version__", "0.24.6")
    response = Mock()
    response.json.return_value = {"tag_name": tag, "html_url": "https://github.com/librerob/tidal-dl-ng-1", "body": ""}
    get = Mock(return_value=response)
    monkeypatch.setattr(requests, "get", get)

    found, release = tidal_dl_ng.update_available()

    assert found is available
    assert release.version == tag
    get.assert_called_once_with(tidal_dl_ng.LATEST_RELEASE_URL, timeout=tidal_dl_ng.REQUESTS_TIMEOUT_SEC)


@pytest.mark.parametrize("payload", [None, {}, {"tag_name": "v0.0.0", "html_url": "https://github.com/example", "body": ""}, {"tag_name": "bad", "html_url": "https://github.com/example", "body": ""}])
def test_ignores_invalid_release(monkeypatch, payload):
    monkeypatch.setattr(tidal_dl_ng, "__version__", "0.24.6")
    response = Mock()
    response.json.return_value = payload
    monkeypatch.setattr(requests, "get", Mock(return_value=response))
    assert tidal_dl_ng.update_available() == (False, None)


def test_ignores_http_failure(monkeypatch):
    monkeypatch.setattr(tidal_dl_ng, "__version__", "0.24.6")
    response = Mock()
    response.raise_for_status.side_effect = requests.HTTPError
    monkeypatch.setattr(requests, "get", Mock(return_value=response))
    assert tidal_dl_ng.update_available() == (False, None)
