import json
import os
import shutil
import subprocess
import tempfile
import warnings
from collections.abc import Callable
from importlib import import_module
from json import JSONDecodeError
from pathlib import Path
from threading import Event
from typing import Any

import tidalapi
from requests import HTTPError

from tidal_dl_ng.helper.decorator import SingletonMeta
from tidal_dl_ng.helper.path import path_config_base, path_file_settings, path_file_token
from tidal_dl_ng.model.cfg import Settings as ModelSettings
from tidal_dl_ng.model.cfg import Token as ModelToken


class BaseConfig:
    data: ModelSettings | ModelToken
    file_path: str
    cls_model: ModelSettings | ModelToken
    path_base: str = path_config_base()

    def save(self, config_to_compare: str = None) -> None:
        data_json = self.data.to_json()

        # If old and current config is equal, skip the write operation.
        if config_to_compare == data_json:
            return

        # Try to create the base folder.
        os.makedirs(self.path_base, exist_ok=True)

        with open(self.file_path, encoding="utf-8", mode="w") as f:
            # Save it in a pretty format
            obj_json_config = json.loads(data_json)
            json.dump(obj_json_config, f, indent=4)

    def set_option(self, key: str, value: Any) -> None:
        value_old: Any = getattr(self.data, key)

        if type(value_old) == bool:  # noqa: E721
            value = True if value.lower() in ("true", "1", "yes", "y") else False  # noqa: SIM210
        elif type(value_old) == int and type(value) != int:  # noqa: E721
            value = int(value)

        setattr(self.data, key, value)

    def read(self, path: str) -> bool:
        result: bool = False
        settings_json: str = ""

        try:
            with open(path, encoding="utf-8") as f:
                settings_json = f.read()

            self.data = self.cls_model.from_json(settings_json)
            result = True
        except (JSONDecodeError, TypeError, FileNotFoundError, ValueError) as e:
            if isinstance(e, ValueError):
                path_bak = path + ".bak"

                # First check if a backup file already exists. If yes, remove it.
                if os.path.exists(path_bak):
                    os.remove(path_bak)

                # Move the invalid config file to the backup location.
                shutil.move(path, path_bak)
                # TODO: Implement better global logger.
                print(
                    "Something is wrong with your config. Maybe it is not compatible anymore due to a new app version."
                    f" You can find a backup of your old config here: '{path_bak}'. A new default config was created."
                )

            self.data = self.cls_model()

        # Call save in case of we need to update the saved config, due to changes in code.
        self.save(settings_json)

        return result


class Settings(BaseConfig, metaclass=SingletonMeta):
    def __init__(self):
        self.cls_model = ModelSettings
        self.file_path = path_file_settings()
        self.read(self.file_path)


KEYRING_SERVICE = "tidal-dl-ng-1"
KEYRING_ACCOUNT = "tidal-oauth"


class Tidal(BaseConfig, metaclass=SingletonMeta):
    session: tidalapi.Session
    token_from_storage: bool = False
    settings: Settings
    is_pkce: bool

    def __init__(self, settings: Settings = None):
        self.cls_model = ModelToken
        tidal_config: tidalapi.Config = tidalapi.Config(item_limit=10000)
        self.session = tidalapi.Session(tidal_config)
        self.file_path = path_file_token()
        self.settings = settings if settings is not None else Settings()
        self.token_from_storage = self.read(self.file_path)

        if settings:
            self.settings = settings
            self.settings_apply()

    def _keyring(self, *, for_logout=False):
        if not for_logout and not self.settings.data.use_keyring:
            return None
        try:
            return import_module("keyring")
        except ModuleNotFoundError as exc:
            if exc.name != "keyring":
                raise
            return None

    def read(self, path: str) -> bool:
        token_path = Path(path)
        self.data = ModelToken()
        backend = self._keyring()
        if backend is not None:
            try:
                stored = backend.get_password(KEYRING_SERVICE, KEYRING_ACCOUNT)
                if stored and not token_path.exists():
                    self.data = ModelToken.from_json(stored)
                    return bool(self.data.access_token)
            except Exception:  # A local keyring may be unavailable or locked.
                stored = None

        try:
            if os.name != "nt":
                token_path.chmod(0o600)
            self.data = ModelToken.from_json(token_path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError):
            return False

        if not self.data.access_token:
            return False
        if backend is not None:
            try:
                backend.set_password(KEYRING_SERVICE, KEYRING_ACCOUNT, self.data.to_json())
                token_path.unlink()
            except Exception:
                warnings.warn("Could not move the saved TIDAL login to the OS keyring.", RuntimeWarning, stacklevel=2)
        return True

    def save(self, config_to_compare: str = None) -> None:
        token_path = Path(self.file_path)
        payload = self.data.to_json()
        backend = self._keyring()
        if backend is not None:
            try:
                backend.set_password(KEYRING_SERVICE, KEYRING_ACCOUNT, payload)
            except Exception:  # Keep the existing file fallback if the keyring fails.
                backend = None
            else:
                token_path.unlink(missing_ok=True)
                return

        token_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=token_path.parent) as directory:
            temp = Path(directory) / token_path.name
            descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(descriptor)
            if os.name == "nt":
                try:
                    self._restrict_windows_token(temp)
                except (OSError, subprocess.CalledProcessError):
                    warnings.warn(
                        "Could not secure the TIDAL login file. The current login is available for this session only.",
                        RuntimeWarning,
                        stacklevel=2,
                    )
                    return
            temp.write_text(payload, encoding="utf-8")
            temp.replace(token_path)

    @staticmethod
    def _restrict_windows_token(path: Path):
        system_root = os.environ.get("SystemRoot", "")
        system_directory = Path(system_root) / "System32"
        if not system_directory.is_absolute():
            msg = "Windows system directory is unavailable."
            raise OSError(msg)
        sid = subprocess.check_output(
            [str(system_directory / "whoami.exe"), "/user", "/fo", "csv", "/nh"],  # noqa: S603
            text=True,
            encoding="utf-8",
            errors="replace",
        ).strip().rsplit(",", 1)[-1].strip('"')
        subprocess.run(
            [str(system_directory / "icacls.exe"), str(path), "/inheritance:r", "/grant:r", f"*{sid}:(F)"],  # noqa: S603
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _remove_token(self):
        removed = True
        try:
            Path(self.file_path).unlink(missing_ok=True)
        except OSError:
            warnings.warn("Could not remove the saved TIDAL login file.", RuntimeWarning, stacklevel=2)
            removed = False

        try:
            backend = self._keyring(for_logout=True)
            if backend is not None and backend.get_password(KEYRING_SERVICE, KEYRING_ACCOUNT) is not None:
                backend.delete_password(KEYRING_SERVICE, KEYRING_ACCOUNT)
        except Exception:
            warnings.warn("Could not verify removal of the saved TIDAL login from the OS keyring.", RuntimeWarning, stacklevel=2)
            removed = False
        return removed

    def settings_apply(self, settings: Settings = None) -> bool:
        if settings:
            self.settings = settings

        self.session.audio_quality = self.settings.data.quality_audio
        self.session.video_quality = tidalapi.VideoQuality.high

        return True

    def login_token(self, do_pkce: bool = False) -> bool:
        result = False
        self.is_pkce = do_pkce

        if self.token_from_storage:
            try:
                result = self.session.load_oauth_session(
                    self.data.token_type,
                    self.data.access_token,
                    self.data.refresh_token,
                    self.data.expiry_time,
                    is_pkce=do_pkce,
                )
            except (HTTPError, JSONDecodeError):
                result = False
                # Remove token file. Probably corrupt or invalid.
                self._remove_token()

                print(
                    "Either there is something wrong with your credentials / account or some server problems on TIDALs "
                    "side. Anyway... Try to login again by re-starting this app."
                )

        return result

    def login_finalize(self) -> bool:
        result = self.session.check_login()

        if result:
            self.token_persist()

        return result

    def token_persist(self) -> None:
        self.set_option("token_type", self.session.token_type)
        self.set_option("access_token", self.session.access_token)
        self.set_option("refresh_token", self.session.refresh_token)
        self.set_option("expiry_time", self.session.expiry_time)
        self.save()

    def login(self, fn_print: Callable) -> bool:
        is_token = self.login_token()
        result = False

        if is_token:
            fn_print("Yep, looks good! You are logged in.")

            result = True
        elif not is_token:
            fn_print("You either do not have a token or your token is invalid.")
            fn_print("No worries, we will handle this...")
            # Login method: Device linking
            self.session.login_oauth_simple(fn_print)
            # Login method: PKCE authorization (was necessary for HI_RES_LOSSLESS streaming earlier)
            # self.session.login_pkce(fn_print)

            is_login = self.login_finalize()

            if is_login:
                fn_print("The login was successful. I have stored your credentials (token).")

                result = True
            else:
                fn_print("Something went wrong. Did you login using your browser correctly? May try again...")

        return result

    def logout(self):
        removed = self._remove_token()
        self.token_from_storage = False
        self.data = ModelToken()
        return removed


class HandlingApp(metaclass=SingletonMeta):
    event_abort: Event = Event()
    event_run: Event = Event()

    def __init__(self):
        self.event_run.set()
