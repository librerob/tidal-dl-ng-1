import importlib
import pkgutil
from importlib.metadata import entry_points

import pytest
import requests

import tidal_dl_ng


def test_package_and_entry_points_import_without_network(monkeypatch):
    def unexpected_request(*args, **kwargs):
        pytest.fail("Package import attempted an HTTP request")

    monkeypatch.setattr(requests.sessions.Session, "request", unexpected_request)
    for module in pkgutil.walk_packages(tidal_dl_ng.__path__, "tidal_dl_ng."):
        importlib.import_module(module.name)

    for name in ("tdn", "tdng"):
        (entry_point,) = entry_points(group="console_scripts", name=name)
        assert callable(entry_point.load())
