#!/usr/bin/env python
import importlib.metadata
from pathlib import Path
from urllib.parse import urlparse

import requests
import toml
from packaging.version import InvalidVersion, Version

from tidal_dl_ng.constants import REQUESTS_TIMEOUT_SEC
from tidal_dl_ng.model.meta import ProjectInformation, ReleaseLatest


def metadata_project() -> ProjectInformation:
    result: ProjectInformation
    file_path: Path = Path(__file__)
    tmp_result: dict = {}

    paths: [Path] = [
        file_path.parent,
        file_path.parent.parent,
        file_path.parent.parent.parent,
    ]

    for pyproject_toml_dir in paths:
        pyproject_toml_file: Path = pyproject_toml_dir / "pyproject.toml"

        if pyproject_toml_file.exists() and pyproject_toml_file.is_file():
            tmp_result = toml.load(pyproject_toml_file)

            break

    if tmp_result:
        result = ProjectInformation(
            version=tmp_result["project"]["version"], repository_url=tmp_result["project"]["repository"]
        )
    else:
        try:
            meta_info = importlib.metadata.metadata(name_package())
            result = ProjectInformation(version=meta_info["Version"], repository_url=meta_info.get("Home-page") or "https://github.com/librerob/tidal-dl-ng-1")
        except:
            result = ProjectInformation(version="0.0.0", repository_url="https://anerroroccur.ed/sorry/for/that")

    return result


def version_app() -> str:
    metadata: ProjectInformation = metadata_project()
    version: str = metadata.version

    return version


def repository_url() -> str:
    metadata: ProjectInformation = metadata_project()
    url_repo: str = metadata.repository_url

    return url_repo


def repository_path() -> str:
    url_repo: str = repository_url()
    url_path: str = urlparse(url_repo).path

    return url_path


LATEST_RELEASE_URL = "https://api.github.com/repos/librerob/tidal-dl-ng-1/releases/latest"


def latest_version_information() -> ReleaseLatest | None:
    try:
        response = requests.get(LATEST_RELEASE_URL, timeout=REQUESTS_TIMEOUT_SEC)
        response.raise_for_status()
        data = response.json()
        tag, url, body = data["tag_name"], data["html_url"], data["body"]
        if not isinstance(tag, str) or Version(tag) == Version("0"):
            return None
        if not isinstance(url, str) or urlparse(url).scheme != "https" or urlparse(url).netloc != "github.com":
            return None
        if body is not None and not isinstance(body, str):
            return None
    except (requests.RequestException, ValueError, TypeError, KeyError):
        return None

    return ReleaseLatest(version=tag, url=url, release_info=body or "")


def name_package() -> str:
    package_name: str = __package__ or __name__

    return package_name


def is_dev_env() -> bool:
    package_name: str = name_package()
    result: bool = False

    # Check if package is running from source code == dev mode
    # If package is not running in Nuitka environment, try to import it from pip libraries.
    # If this also fails, it is dev mode.
    if "__compiled__" not in globals():
        try:
            importlib.metadata.version(package_name)
        except:
            # If package is not installed
            result = True

    return result


def name_app() -> str:
    app_name: str = name_package()
    is_dev: bool = is_dev_env()

    if is_dev:
        app_name = app_name + "-dev"

    return app_name


__name_display__ = name_app()
__version__ = version_app()


def update_available() -> tuple[bool, ReleaseLatest | None]:
    try:
        current = Version(__version__)
    except (InvalidVersion, TypeError):
        return False, None
    if current == Version("0"):
        return False, None

    latest = latest_version_information()
    return latest is not None and Version(latest.version) > current, latest
