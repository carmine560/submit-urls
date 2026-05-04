"""Tests for the sitemap and submission workflow."""

import json
import configparser
from types import SimpleNamespace

import pytest

import submit_urls


class _Response:
    def __init__(self, text=""):
        self.text = text

    def raise_for_status(self):
        return None


class _DecryptResult:
    def __init__(self, data=b"", ok=True, status=""):
        self.data = data
        self.ok = ok
        self.status = status


def test_decrypt_data_returns_decrypted_bytes(tmp_path):
    secret_path = tmp_path / "secret.bin"
    secret_path.write_bytes(b"payload")

    def fake_decrypt(file_object):
        return _DecryptResult(data=file_object.read(), ok=True)

    assert (
        submit_urls.decrypt_data(str(secret_path), fake_decrypt) == b"payload"
    )


def test_add_entries_returns_only_newer_urls(monkeypatch):
    sitemap = {
        "urlset": {
            "url": [
                {
                    "loc": "https://example.com/new",
                    "lastmod": "2024-01-02T00:00:00+00:00",
                },
                {
                    "loc": "https://example.com/old",
                    "lastmod": "2023-12-31T00:00:00+00:00",
                },
            ]
        }
    }
    called = {}

    def fake_get(url, timeout):
        called["url"] = url
        called["timeout"] = timeout
        return _Response("<xml />")

    monkeypatch.setattr(submit_urls.requests, "get", fake_get)
    monkeypatch.setattr(submit_urls.xmltodict, "parse", lambda text: sitemap)

    result = submit_urls.add_entries(
        "https://example.com/sitemap.xml",
        "2024-01-01T00:00:00+00:00",
    )

    assert result == {"https://example.com/new": "URL_UPDATED"}
    assert called == {
        "url": "https://example.com/sitemap.xml",
        "timeout": submit_urls.HTTP_TIMEOUT_SECONDS,
    }


def test_add_entries_raises_on_http_error(monkeypatch):
    error = submit_urls.requests.exceptions.RequestException("bad response")

    class _ErrorResponse:
        text = "<html />"

        def raise_for_status(self):
            raise error

    monkeypatch.setattr(
        submit_urls.requests,
        "get",
        lambda url, timeout: _ErrorResponse(),
    )

    with pytest.raises(
        submit_urls.requests.exceptions.RequestException,
        match="bad response",
    ):
        submit_urls.add_entries(
            "https://example.com/sitemap.xml",
            "2024-01-01T00:00:00+00:00",
        )


def test_add_entries_raises_for_malformed_sitemap(monkeypatch):
    monkeypatch.setattr(
        submit_urls.requests,
        "get",
        lambda url, timeout: _Response("<xml />"),
    )
    monkeypatch.setattr(
        submit_urls.xmltodict,
        "parse",
        lambda text: {"urlset": {"url": [{"loc": "https://example.com"}]}},
    )

    with pytest.raises(ValueError, match="missing 'loc' or 'lastmod'"):
        submit_urls.add_entries(
            "https://example.com/sitemap.xml",
            "2024-01-01T00:00:00+00:00",
        )


def test_configure_creates_default_config_and_exits(tmp_path):
    config_path = tmp_path / "settings.ini"

    with pytest.raises(SystemExit):
        submit_urls.configure(str(config_path))

    created = configparser.ConfigParser()
    created.read(config_path, encoding="utf-8")

    assert created["Common"]["sitemap_url"] == (
        "HTTPS://EXAMPLE.COM/SITEMAP.XML"
    )
    assert created["Google"]["json_key_path"].endswith("JSON_KEY.JSON.GPG")
    assert created["Bing"]["api_key_path"].endswith("api_key.txt.gpg")


def test_submit_urls_to_google_batches_each_url(monkeypatch):
    calls = {}
    notifications = []

    class _Batch:
        def add(self, item):
            notifications.append(item)

        def execute(self):
            calls["executed"] = True

    class _Notifications:
        def publish(self, body):
            notifications.append(("body", body))
            return body

    class _Service:
        def new_batch_http_request(self, callback):
            calls["callback"] = callback
            return _Batch()

        def urlNotifications(self):
            return _Notifications()

    monkeypatch.setattr(
        submit_urls.service_account.Credentials,
        "from_service_account_info",
        lambda info, scopes: {"info": info, "scopes": scopes},
    )
    monkeypatch.setattr(
        submit_urls,
        "build",
        lambda api, version, credentials: _Service(),
    )

    submit_urls.submit_urls_to_google(
        {"client_email": "demo@example.com"},
        {
            "https://example.com/a": "URL_UPDATED",
            "https://example.com/b": "URL_DELETED",
        },
    )

    assert calls["executed"] is True
    assert callable(calls["callback"])
    assert notifications == [
        (
            "body",
            {
                "url": "https://example.com/a",
                "type": "URL_UPDATED",
            },
        ),
        {
            "url": "https://example.com/a",
            "type": "URL_UPDATED",
        },
        (
            "body",
            {
                "url": "https://example.com/b",
                "type": "URL_DELETED",
            },
        ),
        {
            "url": "https://example.com/b",
            "type": "URL_DELETED",
        },
    ]


def test_submit_urls_to_google_raises_on_batch_error(monkeypatch, capsys):
    class _Batch:
        def __init__(self, callback):
            self.callback = callback

        def add(self, item):
            self.item = item

        def execute(self):
            self.callback(None, None, RuntimeError("google failed"))

    class _Notifications:
        def publish(self, body):
            return body

    class _Service:
        def new_batch_http_request(self, callback):
            return _Batch(callback)

        def urlNotifications(self):
            return _Notifications()

    monkeypatch.setattr(
        submit_urls.service_account.Credentials,
        "from_service_account_info",
        lambda info, scopes: {"info": info, "scopes": scopes},
    )
    monkeypatch.setattr(
        submit_urls,
        "build",
        lambda api, version, credentials: _Service(),
    )

    with pytest.raises(submit_urls.SubmissionError, match="Google"):
        submit_urls.submit_urls_to_google(
            {"client_email": "demo@example.com"},
            {"https://example.com/a": "URL_UPDATED"},
        )

    assert "google failed" in capsys.readouterr().out


def test_submit_urls_to_bing_posts_expected_payload(monkeypatch, capsys):
    called = {}

    class _PostResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"status": "ok"}

    def fake_post(url, data, headers, timeout):
        called["url"] = url
        called["data"] = data
        called["headers"] = headers
        called["timeout"] = timeout
        return _PostResponse()

    monkeypatch.setattr(submit_urls.requests, "post", fake_post)

    submit_urls.submit_urls_to_bing(
        "secret",
        "https://example.com",
        ["https://example.com/a"],
    )

    assert called["url"].endswith("?apikey=secret")
    assert json.loads(called["data"]) == {
        "siteUrl": "https://example.com",
        "urlList": ["https://example.com/a"],
    }
    assert called["headers"] == {
        "Content-Type": "application/json; charset=utf-8",
    }
    assert called["timeout"] == submit_urls.HTTP_TIMEOUT_SECONDS
    assert "{'status': 'ok'}" in capsys.readouterr().out


def test_submit_urls_to_bing_raises_on_request_error(monkeypatch, capsys):
    error = submit_urls.requests.exceptions.RequestException("request failed")

    def fake_post(url, data, headers, timeout):
        raise error

    monkeypatch.setattr(submit_urls.requests, "post", fake_post)

    with pytest.raises(submit_urls.SubmissionError, match="Bing"):
        submit_urls.submit_urls_to_bing(
            "secret",
            "https://example.com",
            ["https://example.com/a"],
        )

    assert "request failed" in capsys.readouterr().out


def test_load_google_key_raises_on_failed_decrypt(tmp_path):
    key_path = tmp_path / "key.json.gpg"
    key_path.write_bytes(b"encrypted")

    class _Gpg:
        def decrypt_file(self, file_object):
            return _DecryptResult(ok=False, status="bad decrypt")

    with pytest.raises(submit_urls.SubmissionError, match="bad decrypt"):
        submit_urls.load_google_key(str(key_path), _Gpg())


def test_load_google_key_raises_on_invalid_json(tmp_path):
    key_path = tmp_path / "key.json.gpg"
    key_path.write_bytes(b"encrypted")

    class _Gpg:
        def decrypt_file(self, file_object):
            return _DecryptResult(data=b"not json")

    with pytest.raises(submit_urls.SubmissionError, match="valid JSON"):
        submit_urls.load_google_key(str(key_path), _Gpg())


def test_load_bing_api_key_returns_stripped_text(tmp_path):
    key_path = tmp_path / "key.txt.gpg"
    key_path.write_bytes(b"encrypted")

    class _Gpg:
        def decrypt(self, data):
            return _DecryptResult(data=b"secret-key \n")

    assert submit_urls.load_bing_api_key(str(key_path), _Gpg()) == "secret-key"


def test_main_does_not_update_last_submitted_on_google_failure(
    monkeypatch, tmp_path
):
    config_path = tmp_path / "settings.ini"
    config = configparser.ConfigParser()
    config["Common"] = {
        "sitemap_url": "https://example.com/sitemap.xml",
        "last_submitted": "2024-01-01T00:00:00+00:00",
    }
    config["Google"] = {
        "can_submit": "1",
        "json_key_path": str(tmp_path / "google.json.gpg"),
    }
    config["Bing"] = {
        "can_submit": "0",
        "api_key_path": str(tmp_path / "bing.txt.gpg"),
    }
    with open(config_path, "w", encoding="utf-8") as f:
        config.write(f)

    monkeypatch.setattr(
        submit_urls,
        "get_arguments",
        lambda: SimpleNamespace(n=False),
    )
    monkeypatch.setattr(
        submit_urls.file_utilities,
        "create_launchers_exit",
        lambda args, path: None,
    )
    monkeypatch.setattr(
        submit_urls.file_utilities,
        "get_config_path",
        lambda path: str(config_path),
    )
    monkeypatch.setattr(
        submit_urls,
        "add_entries",
        lambda sitemap_url, last_submitted: {
            "https://example.com/a": "URL_UPDATED"
        },
    )
    monkeypatch.setattr(
        submit_urls,
        "load_google_key",
        lambda path, gpg: {"client_email": "demo@example.com"},
    )
    monkeypatch.setattr(
        submit_urls,
        "submit_urls_to_google",
        lambda key_dictionary, url_list: (_ for _ in ()).throw(
            submit_urls.SubmissionError("Google submission failed.")
        ),
    )
    monkeypatch.setattr(submit_urls.gnupg, "GPG", lambda: object())

    with pytest.raises(
        submit_urls.SubmissionError, match="Google submission failed."
    ):
        submit_urls.main()

    reloaded = configparser.ConfigParser()
    reloaded.read(config_path, encoding="utf-8")
    assert reloaded["Common"]["last_submitted"] == (
        "2024-01-01T00:00:00+00:00"
    )


def test_main_does_not_update_last_submitted_on_decrypt_failure(
    monkeypatch, tmp_path
):
    config_path = tmp_path / "settings.ini"
    config = configparser.ConfigParser()
    config["Common"] = {
        "sitemap_url": "https://example.com/sitemap.xml",
        "last_submitted": "2024-01-01T00:00:00+00:00",
    }
    config["Google"] = {
        "can_submit": "1",
        "json_key_path": str(tmp_path / "google.json.gpg"),
    }
    config["Bing"] = {
        "can_submit": "0",
        "api_key_path": str(tmp_path / "bing.txt.gpg"),
    }
    with open(config_path, "w", encoding="utf-8") as f:
        config.write(f)

    monkeypatch.setattr(
        submit_urls,
        "get_arguments",
        lambda: SimpleNamespace(n=False),
    )
    monkeypatch.setattr(
        submit_urls.file_utilities,
        "create_launchers_exit",
        lambda args, path: None,
    )
    monkeypatch.setattr(
        submit_urls.file_utilities,
        "get_config_path",
        lambda path: str(config_path),
    )
    monkeypatch.setattr(
        submit_urls,
        "add_entries",
        lambda sitemap_url, last_submitted: {
            "https://example.com/a": "URL_UPDATED"
        },
    )
    monkeypatch.setattr(
        submit_urls,
        "load_google_key",
        lambda path, gpg: (_ for _ in ()).throw(
            submit_urls.SubmissionError("bad decrypt")
        ),
    )
    monkeypatch.setattr(submit_urls.gnupg, "GPG", lambda: object())

    with pytest.raises(submit_urls.SubmissionError, match="bad decrypt"):
        submit_urls.main()

    reloaded = configparser.ConfigParser()
    reloaded.read(config_path, encoding="utf-8")
    assert reloaded["Common"]["last_submitted"] == (
        "2024-01-01T00:00:00+00:00"
    )
