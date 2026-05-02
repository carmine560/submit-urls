"""Test fixtures and dependency stubs for optional imports."""

from pathlib import Path
from types import ModuleType, SimpleNamespace
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _install_google_stubs():
    google = sys.modules.setdefault("google", ModuleType("google"))
    oauth2 = sys.modules.setdefault(
        "google.oauth2", ModuleType("google.oauth2")
    )
    service_account = ModuleType("google.oauth2.service_account")

    class _Credentials:
        @staticmethod
        def from_service_account_info(*args, **kwargs):
            return {"args": args, "kwargs": kwargs}

    service_account.Credentials = _Credentials
    oauth2.service_account = service_account
    google.oauth2 = oauth2
    sys.modules["google.oauth2.service_account"] = service_account


def _install_googleapiclient_stubs():
    googleapiclient = sys.modules.setdefault(
        "googleapiclient", ModuleType("googleapiclient")
    )
    discovery = ModuleType("googleapiclient.discovery")
    discovery.build = lambda *args, **kwargs: None
    googleapiclient.discovery = discovery
    sys.modules["googleapiclient.discovery"] = discovery


def _install_gnupg_stub():
    gnupg = ModuleType("gnupg")

    class _GPG:
        def decrypt(self, data):
            return SimpleNamespace(data=data)

        def decrypt_file(self, handle):
            return SimpleNamespace(data=handle.read())

        def encrypt(self, data, fingerprint, armor=False):
            return SimpleNamespace(ok=True, data=data.encode(), status="")

        def encrypt_file(self, source, fingerprint, armor=False, output=None):
            return SimpleNamespace(
                ok=True,
                data=b"",
                status="",
                output=output,
            )

        def list_keys(self):
            return [{"fingerprint": "stub"}]

    gnupg.GPG = _GPG
    sys.modules["gnupg"] = gnupg


def _install_requests_stub():
    requests = ModuleType("requests")

    class _RequestException(Exception):
        pass

    requests.get = lambda *args, **kwargs: None
    requests.post = lambda *args, **kwargs: None
    requests.exceptions = SimpleNamespace(RequestException=_RequestException)
    sys.modules["requests"] = requests


def _install_xmltodict_stub():
    xmltodict = ModuleType("xmltodict")
    xmltodict.parse = lambda text: {}
    sys.modules["xmltodict"] = xmltodict


def _install_prompt_toolkit_stubs():
    prompt_toolkit = ModuleType("prompt_toolkit")
    prompt_toolkit.ANSI = lambda value: value
    prompt_toolkit.prompt = lambda *args, **kwargs: ""
    completion = ModuleType("prompt_toolkit.completion")

    class _Completer:
        pass

    class _Completion:
        def __init__(self, text, start_position):
            self.text = text
            self.start_position = start_position

    completion.Completer = _Completer
    completion.Completion = _Completion
    prompt_toolkit.completion = completion
    sys.modules["prompt_toolkit"] = prompt_toolkit
    sys.modules["prompt_toolkit.completion"] = completion


if "google.oauth2.service_account" not in sys.modules:
    _install_google_stubs()
if "googleapiclient.discovery" not in sys.modules:
    _install_googleapiclient_stubs()
if "gnupg" not in sys.modules:
    _install_gnupg_stub()
if "requests" not in sys.modules:
    _install_requests_stub()
if "xmltodict" not in sys.modules:
    _install_xmltodict_stub()
if "prompt_toolkit" not in sys.modules:
    _install_prompt_toolkit_stubs()


def pytest_configure():
    """Keep the test hook defined for future shared pytest setup."""
