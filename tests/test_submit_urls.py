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
        submit_urls._decrypt_data(str(secret_path), fake_decrypt) == b"payload"
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

    result, newest_submitted_at = submit_urls.add_entries(
        "https://example.com/sitemap.xml",
        "2024-01-01T00:00:00+00:00",
    )

    assert result == {"https://example.com/new": "URL_UPDATED"}
    assert newest_submitted_at == submit_urls.parse_timestamp(
        "2024-01-02T00:00:00+00:00"
    )
    assert called == {
        "url": "https://example.com/sitemap.xml",
        "timeout": submit_urls.HTTP_TIMEOUT_SECONDS,
    }


def test_add_entries_compares_timezone_aware_datetimes(monkeypatch):
    sitemap = {
        "urlset": {
            "url": [
                {
                    "loc": "https://example.com/not-new",
                    "lastmod": "2024-01-01T00:30:00+00:00",
                },
                {
                    "loc": "https://example.com/new",
                    "lastmod": "2024-01-01T00:00:00-01:00",
                },
            ]
        }
    }

    monkeypatch.setattr(
        submit_urls.requests,
        "get",
        lambda url, timeout: _Response("<xml />"),
    )
    monkeypatch.setattr(submit_urls.xmltodict, "parse", lambda text: sitemap)

    result, newest_submitted_at = submit_urls.add_entries(
        "https://example.com/sitemap.xml",
        "2024-01-01T00:45:00+00:00",
    )

    assert result == {"https://example.com/new": "URL_UPDATED"}
    assert newest_submitted_at == submit_urls.parse_timestamp(
        "2024-01-01T01:00:00+00:00"
    )


def test_add_entries_compares_fractional_seconds(monkeypatch):
    sitemap = {
        "urlset": {
            "url": [
                {
                    "loc": "https://example.com/new",
                    "lastmod": "2024-01-01T00:00:00.000001+00:00",
                },
                {
                    "loc": "https://example.com/same",
                    "lastmod": "2024-01-01T00:00:00.000000+00:00",
                },
            ]
        }
    }

    monkeypatch.setattr(
        submit_urls.requests,
        "get",
        lambda url, timeout: _Response("<xml />"),
    )
    monkeypatch.setattr(submit_urls.xmltodict, "parse", lambda text: sitemap)

    result, newest_submitted_at = submit_urls.add_entries(
        "https://example.com/sitemap.xml",
        "2024-01-01T00:00:00+00:00",
    )

    assert result == {"https://example.com/new": "URL_UPDATED"}
    assert newest_submitted_at == submit_urls.parse_timestamp(
        "2024-01-01T00:00:00.000001+00:00"
    )


def test_add_entries_tracks_max_lastmod_independent_of_order(monkeypatch):
    sitemap = {
        "urlset": {
            "url": [
                {
                    "loc": "https://example.com/second",
                    "lastmod": "2024-01-02T00:00:00+00:00",
                },
                {
                    "loc": "https://example.com/first",
                    "lastmod": "2024-01-05T00:00:00+00:00",
                },
                {
                    "loc": "https://example.com/old",
                    "lastmod": "2024-01-01T00:00:00+00:00",
                },
            ]
        }
    }

    monkeypatch.setattr(
        submit_urls.requests,
        "get",
        lambda url, timeout: _Response("<xml />"),
    )
    monkeypatch.setattr(submit_urls.xmltodict, "parse", lambda text: sitemap)

    result, newest_submitted_at = submit_urls.add_entries(
        "https://example.com/sitemap.xml",
        "2024-01-01T12:00:00+00:00",
    )

    assert result == {
        "https://example.com/second": "URL_UPDATED",
        "https://example.com/first": "URL_UPDATED",
    }
    assert newest_submitted_at == submit_urls.parse_timestamp(
        "2024-01-05T00:00:00+00:00"
    )


def test_add_entries_returns_none_when_nothing_is_new(monkeypatch):
    sitemap = {
        "urlset": {
            "url": [
                {
                    "loc": "https://example.com/current",
                    "lastmod": "2024-01-01T00:00:00+00:00",
                }
            ]
        }
    }

    monkeypatch.setattr(
        submit_urls.requests,
        "get",
        lambda url, timeout: _Response("<xml />"),
    )
    monkeypatch.setattr(submit_urls.xmltodict, "parse", lambda text: sitemap)

    result, newest_submitted_at = submit_urls.add_entries(
        "https://example.com/sitemap.xml",
        "2024-01-01T00:00:00+00:00",
    )

    assert result == {}
    assert newest_submitted_at is None


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


def test_configure_creates_default_config_and_raises_config_created(tmp_path):
    config_path = tmp_path / "settings.ini"

    with pytest.raises(submit_urls.ConfigCreated):
        submit_urls.configure(str(config_path))

    created = configparser.ConfigParser()
    created.read(config_path, encoding="utf-8")

    assert created["Common"]["sitemap_url"] == (
        "HTTPS://EXAMPLE.COM/SITEMAP.XML"
    )
    assert created["Google"]["json_key_path"].endswith("JSON_KEY.JSON.GPG")
    assert created["Bing"]["api_key_path"].endswith("api_key.txt.gpg")


def test_validate_config_rejects_placeholder_sitemap_url(tmp_path):
    config = configparser.ConfigParser()
    config["Common"] = {
        "sitemap_url": "HTTPS://EXAMPLE.COM/SITEMAP.XML",
        "last_submitted": "2024-01-01T00:00:00+00:00",
    }
    config["Google"] = {
        "can_submit": "0",
        "json_key_path": str(tmp_path / "google.json.gpg"),
    }
    config["Bing"] = {
        "can_submit": "0",
        "api_key_path": str(tmp_path / "bing.txt.gpg"),
    }

    with pytest.raises(
        submit_urls.SubmissionError, match="default placeholder value"
    ):
        submit_urls.validate_config(config)


def test_validate_config_rejects_missing_enabled_secret_path(tmp_path):
    config = configparser.ConfigParser()
    config["Common"] = {
        "sitemap_url": "https://example.com/sitemap.xml",
        "last_submitted": "2024-01-01T00:00:00+00:00",
    }
    config["Google"] = {
        "can_submit": "1",
        "json_key_path": str(tmp_path / "missing.json.gpg"),
    }
    config["Bing"] = {
        "can_submit": "0",
        "api_key_path": str(tmp_path / "bing.txt.gpg"),
    }

    with pytest.raises(
        submit_urls.SubmissionError, match="Google.json_key_path"
    ):
        submit_urls.validate_config(config)


def test_validate_config_rejects_invalid_last_submitted(tmp_path):
    google_key = tmp_path / "google.json.gpg"
    google_key.write_bytes(b"encrypted")
    config = configparser.ConfigParser()
    config["Common"] = {
        "sitemap_url": "https://example.com/sitemap.xml",
        "last_submitted": "not-a-timestamp",
    }
    config["Google"] = {
        "can_submit": "1",
        "json_key_path": str(google_key),
    }
    config["Bing"] = {
        "can_submit": "0",
        "api_key_path": str(tmp_path / "bing.txt.gpg"),
    }

    with pytest.raises(
        submit_urls.SubmissionError, match="must be an ISO 8601 timestamp"
    ):
        submit_urls.validate_config(config)


def test_validate_config_rejects_invalid_provider_last_submitted(tmp_path):
    google_key = tmp_path / "google.json.gpg"
    google_key.write_bytes(b"encrypted")
    config = configparser.ConfigParser()
    config["Common"] = {
        "sitemap_url": "https://example.com/sitemap.xml",
        "last_submitted": "2024-01-01T00:00:00+00:00",
    }
    config["Google"] = {
        "can_submit": "1",
        "json_key_path": str(google_key),
        "last_submitted": "not-a-timestamp",
    }
    config["Bing"] = {
        "can_submit": "0",
        "api_key_path": str(tmp_path / "bing.txt.gpg"),
    }

    with pytest.raises(
        submit_urls.SubmissionError,
        match="Google.last_submitted",
    ):
        submit_urls.validate_config(config)


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
    google_key = tmp_path / "google.json.gpg"
    google_key.write_bytes(b"encrypted")
    config = configparser.ConfigParser()
    config["Common"] = {
        "sitemap_url": "https://example.com/sitemap.xml",
        "last_submitted": "2024-01-01T00:00:00+00:00",
    }
    config["Google"] = {
        "can_submit": "1",
        "json_key_path": str(google_key),
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
        lambda sitemap_url, last_submitted: (
            {"https://example.com/a": "URL_UPDATED"},
            submit_urls.parse_timestamp("2024-01-02T00:00:00+00:00"),
        ),
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


def test_main_persists_successful_provider_on_partial_failure(
    monkeypatch, tmp_path
):
    config_path = tmp_path / "settings.ini"
    google_key = tmp_path / "google.json.gpg"
    google_key.write_bytes(b"encrypted")
    bing_key = tmp_path / "bing.txt.gpg"
    bing_key.write_bytes(b"encrypted")
    config = configparser.ConfigParser()
    config["Common"] = {
        "sitemap_url": "https://example.com/sitemap.xml",
        "last_submitted": "2024-01-01T00:00:00+00:00",
    }
    config["Google"] = {
        "can_submit": "1",
        "json_key_path": str(google_key),
    }
    config["Bing"] = {
        "can_submit": "1",
        "api_key_path": str(bing_key),
    }
    with open(config_path, "w", encoding="utf-8") as f:
        config.write(f)

    add_entries_calls = []
    google_submissions = []
    bing_submissions = []
    state = {"run": 0}

    def fake_add_entries(sitemap_url, last_submitted):
        add_entries_calls.append(last_submitted)
        if state["run"] == 0:
            return (
                {"https://example.com/a": "URL_UPDATED"},
                submit_urls.parse_timestamp("2024-01-02T00:00:00+00:00"),
            )
        if last_submitted == "2024-01-02T00:00:00+00:00":
            return ({}, None)
        return (
            {"https://example.com/a": "URL_UPDATED"},
            submit_urls.parse_timestamp("2024-01-02T00:00:00+00:00"),
        )

    def fake_submit_google(key_dictionary, url_list):
        google_submissions.append(dict(url_list))

    def fake_submit_bing(api_key, site_url, url_list):
        bing_submissions.append(list(url_list))
        if state["run"] == 0:
            state["run"] = 1
            raise submit_urls.SubmissionError("Bing submission failed.")

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
    monkeypatch.setattr(submit_urls, "add_entries", fake_add_entries)
    monkeypatch.setattr(
        submit_urls,
        "load_google_key",
        lambda path, gpg: {"client_email": "demo@example.com"},
    )
    monkeypatch.setattr(
        submit_urls,
        "submit_urls_to_google",
        fake_submit_google,
    )
    monkeypatch.setattr(
        submit_urls,
        "load_bing_api_key",
        lambda path, gpg: "secret",
    )
    monkeypatch.setattr(
        submit_urls,
        "submit_urls_to_bing",
        fake_submit_bing,
    )
    monkeypatch.setattr(submit_urls.gnupg, "GPG", lambda: object())

    with pytest.raises(
        submit_urls.SubmissionError, match="Bing submission failed."
    ):
        submit_urls.main()

    reloaded = configparser.ConfigParser()
    reloaded.read(config_path, encoding="utf-8")
    assert reloaded["Google"]["last_submitted"] == (
        "2024-01-02T00:00:00+00:00"
    )
    assert reloaded["Common"]["last_submitted"] == (
        "2024-01-01T00:00:00+00:00"
    )
    assert not reloaded["Bing"].get("last_submitted", fallback="")

    submit_urls.main()

    reloaded.read(config_path, encoding="utf-8")
    assert google_submissions == [
        {"https://example.com/a": "URL_UPDATED"},
    ]
    assert bing_submissions == [
        ["https://example.com/a"],
        ["https://example.com/a"],
    ]
    assert add_entries_calls == [
        "2024-01-01T00:00:00+00:00",
        "2024-01-01T00:00:00+00:00",
        "2024-01-02T00:00:00+00:00",
        "2024-01-01T00:00:00+00:00",
    ]
    assert reloaded["Google"]["last_submitted"] == (
        "2024-01-02T00:00:00+00:00"
    )
    assert reloaded["Bing"]["last_submitted"] == ("2024-01-02T00:00:00+00:00")
    assert reloaded["Common"]["last_submitted"] == (
        "2024-01-02T00:00:00+00:00"
    )


def test_main_fails_fast_before_network_on_invalid_config(
    monkeypatch, tmp_path
):
    config_path = tmp_path / "settings.ini"
    config = configparser.ConfigParser()
    config["Common"] = {
        "sitemap_url": "HTTPS://EXAMPLE.COM/SITEMAP.XML",
        "last_submitted": "2024-01-01T00:00:00+00:00",
    }
    config["Google"] = {
        "can_submit": "0",
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

    def fail_add_entries(*args, **kwargs):
        raise AssertionError("add_entries should not be called")

    monkeypatch.setattr(submit_urls, "add_entries", fail_add_entries)

    with pytest.raises(
        submit_urls.SubmissionError, match="default placeholder value"
    ):
        submit_urls.main()


def test_main_does_not_update_last_submitted_on_decrypt_failure(
    monkeypatch, tmp_path
):
    config_path = tmp_path / "settings.ini"
    google_key = tmp_path / "google.json.gpg"
    google_key.write_bytes(b"encrypted")
    config = configparser.ConfigParser()
    config["Common"] = {
        "sitemap_url": "https://example.com/sitemap.xml",
        "last_submitted": "2024-01-01T00:00:00+00:00",
    }
    config["Google"] = {
        "can_submit": "1",
        "json_key_path": str(google_key),
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
        lambda sitemap_url, last_submitted: (
            {"https://example.com/a": "URL_UPDATED"},
            submit_urls.parse_timestamp("2024-01-02T00:00:00+00:00"),
        ),
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


def test_main_persists_newest_submitted_lastmod(monkeypatch, tmp_path):
    config_path = tmp_path / "settings.ini"
    google_key = tmp_path / "google.json.gpg"
    google_key.write_bytes(b"encrypted")
    bing_key = tmp_path / "bing.txt.gpg"
    bing_key.write_bytes(b"encrypted")
    config = configparser.ConfigParser()
    config["Common"] = {
        "sitemap_url": "https://example.com/sitemap.xml",
        "last_submitted": "2024-01-01T00:00:00+00:00",
    }
    config["Google"] = {
        "can_submit": "1",
        "json_key_path": str(google_key),
    }
    config["Bing"] = {
        "can_submit": "1",
        "api_key_path": str(bing_key),
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
        lambda sitemap_url, last_submitted: (
            {
                "https://example.com/a": "URL_UPDATED",
                "https://example.com/b": "URL_UPDATED",
            },
            submit_urls.parse_timestamp("2024-01-05T00:00:00+00:00"),
        ),
    )
    monkeypatch.setattr(
        submit_urls,
        "load_google_key",
        lambda path, gpg: {"client_email": "demo@example.com"},
    )
    monkeypatch.setattr(
        submit_urls,
        "submit_urls_to_google",
        lambda key_dictionary, url_list: None,
    )
    monkeypatch.setattr(
        submit_urls,
        "load_bing_api_key",
        lambda path, gpg: "secret",
    )
    monkeypatch.setattr(
        submit_urls,
        "submit_urls_to_bing",
        lambda api_key, site_url, url_list: None,
    )
    monkeypatch.setattr(submit_urls.gnupg, "GPG", lambda: object())

    monkeypatch.setattr(
        submit_urls,
        "datetime",
        type(
            "_FixedDateTime",
            (),
            {
                "now": staticmethod(
                    lambda tz=None: submit_urls.parse_timestamp(
                        "2024-01-10T00:00:00+00:00"
                    )
                ),
                "fromisoformat": staticmethod(
                    submit_urls.datetime.fromisoformat
                ),
            },
        ),
    )

    submit_urls.main()

    reloaded = configparser.ConfigParser()
    reloaded.read(config_path, encoding="utf-8")
    assert reloaded["Google"]["last_submitted"] == (
        "2024-01-05T00:00:00+00:00"
    )
    assert reloaded["Bing"]["last_submitted"] == ("2024-01-05T00:00:00+00:00")
    assert reloaded["Common"]["last_submitted"] == (
        "2024-01-05T00:00:00+00:00"
    )


def test_main_uses_lastmod_checkpoint_to_avoid_clock_drift(
    monkeypatch, tmp_path
):
    config_path = tmp_path / "settings.ini"
    google_key = tmp_path / "google.json.gpg"
    google_key.write_bytes(b"encrypted")
    config = configparser.ConfigParser()
    config["Common"] = {
        "sitemap_url": "https://example.com/sitemap.xml",
        "last_submitted": "2024-01-01T00:00:00+00:00",
    }
    config["Google"] = {
        "can_submit": "1",
        "json_key_path": str(google_key),
    }
    config["Bing"] = {
        "can_submit": "0",
        "api_key_path": str(tmp_path / "bing.txt.gpg"),
    }
    with open(config_path, "w", encoding="utf-8") as f:
        config.write(f)

    state = {"run": 0}

    def fake_add_entries(sitemap_url, last_submitted):
        state["run"] += 1
        if state["run"] == 1:
            assert last_submitted == "2024-01-01T00:00:00+00:00"
            return (
                {"https://example.com/a": "URL_UPDATED"},
                submit_urls.parse_timestamp("2024-01-05T00:00:00+00:00"),
            )
        assert last_submitted == "2024-01-05T00:00:00+00:00"
        return (
            {"https://example.com/b": "URL_UPDATED"},
            submit_urls.parse_timestamp("2024-01-07T00:00:00+00:00"),
        )

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
    monkeypatch.setattr(submit_urls, "add_entries", fake_add_entries)
    monkeypatch.setattr(
        submit_urls,
        "load_google_key",
        lambda path, gpg: {"client_email": "demo@example.com"},
    )
    monkeypatch.setattr(
        submit_urls,
        "submit_urls_to_google",
        lambda key_dictionary, url_list: None,
    )
    monkeypatch.setattr(submit_urls.gnupg, "GPG", lambda: object())
    monkeypatch.setattr(
        submit_urls,
        "datetime",
        type(
            "_FixedDateTime",
            (),
            {
                "now": staticmethod(
                    lambda tz=None: submit_urls.parse_timestamp(
                        "2024-01-10T00:00:00+00:00"
                    )
                ),
                "fromisoformat": staticmethod(
                    submit_urls.datetime.fromisoformat
                ),
            },
        ),
    )

    submit_urls.main()
    submit_urls.main()

    reloaded = configparser.ConfigParser()
    reloaded.read(config_path, encoding="utf-8")
    assert reloaded["Common"]["last_submitted"] == (
        "2024-01-07T00:00:00+00:00"
    )
