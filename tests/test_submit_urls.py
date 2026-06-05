"""Tests for the sitemap and submission workflow."""

import configparser
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from xml.parsers.expat import ExpatError

import pytest

import submit_urls


class _Response:
    def __init__(self, text=""):
        self.text = text

    def raise_for_status(self):
        return None


def _completed_process(returncode=0, stdout=b"", stderr=b""):
    return SimpleNamespace(
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def test_decrypt_data_returns_decrypted_bytes(tmp_path, monkeypatch):
    secret_path = tmp_path / "secret.bin"
    secret_path.write_bytes(b"payload")
    calls = []

    def fake_run(args, stdout, stderr, check, timeout):
        calls.append(
            {
                "args": args,
                "stdout": stdout,
                "stderr": stderr,
                "check": check,
                "timeout": timeout,
            }
        )
        return _completed_process(stdout=b"payload")

    monkeypatch.setattr(submit_urls.subprocess, "run", fake_run)
    assert submit_urls._decrypt_data(str(secret_path)) == b"payload"
    assert calls == [
        {
            "args": [
                "gpg",
                "--batch",
                "--yes",
                "--decrypt",
                str(secret_path),
            ],
            "stdout": submit_urls.subprocess.PIPE,
            "stderr": submit_urls.subprocess.PIPE,
            "check": False,
            "timeout": submit_urls.GPG_TIMEOUT_SECONDS,
        }
    ]


def test_parse_timestamp_normalizes_z_suffix():
    assert submit_urls.parse_timestamp("2024-01-01T00:00:00Z") == (
        submit_urls.parse_timestamp("2024-01-01T00:00:00+00:00")
    )


def test_parse_timestamp_treats_naive_values_as_utc():
    assert submit_urls.parse_timestamp("2024-01-01T00:00:00") == (
        submit_urls.parse_timestamp("2024-01-01T00:00:00+00:00")
    )


def test_get_sitemap_entries_fetches_url_items(monkeypatch):
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

    result = submit_urls.get_sitemap_entries("https://example.com/sitemap.xml")

    assert result == sitemap["urlset"]["url"]
    assert called == {
        "url": "https://example.com/sitemap.xml",
        "timeout": submit_urls.HTTP_TIMEOUT_SECONDS,
    }


def test_get_sitemap_entries_raises_on_http_error(monkeypatch):
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
        submit_urls.get_sitemap_entries("https://example.com/sitemap.xml")


def test_get_sitemap_entries_raises_on_http_timeout(monkeypatch):
    error = submit_urls.requests.exceptions.RequestException("timed out")

    def fake_get(url, timeout):
        raise error

    monkeypatch.setattr(submit_urls.requests, "get", fake_get)

    with pytest.raises(
        submit_urls.requests.exceptions.RequestException,
        match="timed out",
    ):
        submit_urls.get_sitemap_entries("https://example.com/sitemap.xml")


def test_get_sitemap_entries_propagates_xml_parse_error(monkeypatch):
    monkeypatch.setattr(
        submit_urls.requests,
        "get",
        lambda url, timeout: _Response("<xml />"),
    )

    def fail_parse(text):
        raise ExpatError("not well-formed")

    monkeypatch.setattr(submit_urls.xmltodict, "parse", fail_parse)

    with pytest.raises(ExpatError, match="not well-formed"):
        submit_urls.get_sitemap_entries("https://example.com/sitemap.xml")


def test_get_updated_entries_compares_timezone_aware_datetimes():
    result = submit_urls.get_updated_entries(
        [
            {
                "loc": "https://example.com/not-new",
                "lastmod": "2024-01-01T00:30:00+00:00",
            },
            {
                "loc": "https://example.com/new",
                "lastmod": "2024-01-01T00:00:00-01:00",
            },
        ],
        "2024-01-01T00:45:00+00:00",
    )

    assert result == [
        (
            submit_urls.parse_timestamp("2024-01-01T01:00:00+00:00"),
            "https://example.com/new",
        )
    ]


def test_get_updated_entries_compares_fractional_seconds():
    result = submit_urls.get_updated_entries(
        [
            {
                "loc": "https://example.com/new",
                "lastmod": "2024-01-01T00:00:00.000001+00:00",
            },
            {
                "loc": "https://example.com/same",
                "lastmod": "2024-01-01T00:00:00.000000+00:00",
            },
        ],
        "2024-01-01T00:00:00+00:00",
    )

    assert result == [
        (
            submit_urls.parse_timestamp("2024-01-01T00:00:00.000001+00:00"),
            "https://example.com/new",
        )
    ]


def test_get_updated_entries_resumes_within_same_timestamp_by_url():
    result = submit_urls.get_updated_entries(
        [
            {
                "loc": "https://example.com/a",
                "lastmod": "2024-01-01T00:00:00+00:00",
            },
            {
                "loc": "https://example.com/b",
                "lastmod": "2024-01-01T00:00:00+00:00",
            },
            {
                "loc": "https://example.com/c",
                "lastmod": "2024-01-01T00:00:00+00:00",
            },
        ],
        "2024-01-01T00:00:00+00:00",
        "https://example.com/b",
    )

    assert result == [
        (
            submit_urls.parse_timestamp("2024-01-01T00:00:00+00:00"),
            "https://example.com/c",
        )
    ]


def test_get_updated_entries_tracks_max_lastmod_independent_of_order():
    result = submit_urls.get_updated_entries(
        [
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
        ],
        "2024-01-01T12:00:00+00:00",
    )

    assert result == [
        (
            submit_urls.parse_timestamp("2024-01-02T00:00:00+00:00"),
            "https://example.com/second",
        ),
        (
            submit_urls.parse_timestamp("2024-01-05T00:00:00+00:00"),
            "https://example.com/first",
        ),
    ]


def test_get_updated_entries_returns_none_when_nothing_is_new():
    result = submit_urls.get_updated_entries(
        [
            {
                "loc": "https://example.com/current",
                "lastmod": "2024-01-01T00:00:00+00:00",
            }
        ],
        "2024-01-01T00:00:00+00:00",
    )

    assert result == []


def test_get_updated_entries_raises_for_malformed_sitemap():
    with pytest.raises(ValueError, match="missing 'loc' or 'lastmod'"):
        submit_urls.get_updated_entries(
            [{"loc": "https://example.com"}],
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


def test_submit_urls_to_google_raises_on_batch_execute_error(
    monkeypatch, capsys
):
    class _Batch:
        def add(self, item):
            self.item = item

        def execute(self):
            raise RuntimeError("execute failed")

    class _Notifications:
        def publish(self, body):
            return body

    class _Service:
        def new_batch_http_request(self, callback):
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

    with pytest.raises(submit_urls.SubmissionError, match="Google"):
        submit_urls.submit_urls_to_google(
            {"client_email": "demo@example.com"},
            {"https://example.com/a": "URL_UPDATED"},
        )

    assert "execute failed" in capsys.readouterr().out


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

    output = capsys.readouterr().out
    assert "Bing submission failed" in output
    assert "RequestException" in output
    assert "apikey=<redacted>" in output
    assert "secret" not in output


def test_submit_urls_to_bing_raises_on_invalid_json(monkeypatch, capsys):
    class _PostResponse:
        def raise_for_status(self):
            return None

        def json(self):
            raise ValueError("invalid json")

    monkeypatch.setattr(
        submit_urls.requests,
        "post",
        lambda url, data, headers, timeout: _PostResponse(),
    )

    with pytest.raises(submit_urls.SubmissionError, match="Bing"):
        submit_urls.submit_urls_to_bing(
            "secret",
            "https://example.com",
            ["https://example.com/a"],
        )

    output = capsys.readouterr().out
    assert "Bing submission failed" in output
    assert "ValueError" in output
    assert "apikey=<redacted>" in output
    assert "secret" not in output


def test_submit_urls_to_bing_raises_on_timeout(monkeypatch, capsys):
    error = submit_urls.requests.exceptions.RequestException("timed out")

    def fake_post(url, data, headers, timeout):
        raise error

    monkeypatch.setattr(submit_urls.requests, "post", fake_post)

    with pytest.raises(submit_urls.SubmissionError, match="Bing"):
        submit_urls.submit_urls_to_bing(
            "secret",
            "https://example.com",
            ["https://example.com/a"],
        )

    output = capsys.readouterr().out
    assert "Bing submission failed" in output
    assert "RequestException" in output
    assert "apikey=<redacted>" in output
    assert "secret" not in output


def test_submit_urls_to_bing_redacts_api_key_from_failure_output(
    monkeypatch, capsys
):
    error = submit_urls.requests.exceptions.RequestException(
        "failed for https://ssl.bing.com/webmaster/api.svc/json/"
        "SubmitUrlBatch?apikey=secret"
    )

    def fake_post(url, data, headers, timeout):
        raise error

    monkeypatch.setattr(submit_urls.requests, "post", fake_post)

    with pytest.raises(submit_urls.SubmissionError) as exc_info:
        submit_urls.submit_urls_to_bing(
            "secret",
            "https://example.com",
            ["https://example.com/a"],
        )

    output = capsys.readouterr().out
    assert "Bing submission failed" in output
    assert "apikey=<redacted>" in output
    assert "secret" not in output
    assert "secret" not in str(exc_info.value)
    assert exc_info.value.__cause__ is None


def test_load_google_key_raises_on_failed_decrypt(tmp_path, monkeypatch):
    key_path = tmp_path / "key.json.gpg"
    key_path.write_bytes(b"encrypted")

    monkeypatch.setattr(
        submit_urls.subprocess,
        "run",
        lambda *args, **kwargs: _completed_process(
            returncode=2,
            stderr=b"bad decrypt",
        ),
    )

    with pytest.raises(
        submit_urls.SubmissionError,
        match="GPG decryption failed: bad decrypt",
    ):
        submit_urls.load_google_key(str(key_path))


def test_load_google_key_raises_on_decrypt_timeout(tmp_path, monkeypatch):
    key_path = tmp_path / "key.json.gpg"
    key_path.write_bytes(b"encrypted")

    def timeout_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(submit_urls.subprocess, "run", timeout_run)

    with pytest.raises(
        submit_urls.SubmissionError,
        match="GPG decryption timed out",
    ):
        submit_urls.load_google_key(str(key_path))


def test_load_google_key_raises_on_invalid_json(tmp_path, monkeypatch):
    key_path = tmp_path / "key.json.gpg"
    key_path.write_bytes(b"encrypted")

    monkeypatch.setattr(
        submit_urls.subprocess,
        "run",
        lambda *args, **kwargs: _completed_process(stdout=b"not json"),
    )

    with pytest.raises(submit_urls.SubmissionError, match="valid JSON"):
        submit_urls.load_google_key(str(key_path))


def test_load_bing_api_key_returns_stripped_text(tmp_path, monkeypatch):
    key_path = tmp_path / "key.txt.gpg"
    key_path.write_bytes(b"encrypted")

    monkeypatch.setattr(
        submit_urls.subprocess,
        "run",
        lambda *args, **kwargs: _completed_process(stdout=b"secret-key \n"),
    )

    assert submit_urls.load_bing_api_key(str(key_path)) == "secret-key"


def test_main_returns_after_launcher_creation(monkeypatch):
    args = SimpleNamespace(n=False, BS=True)
    launcher_calls = []

    monkeypatch.setattr(submit_urls, "get_arguments", lambda: args)

    def fake_create_launchers_exit(received_args, script_path):
        launcher_calls.append((received_args, script_path))
        return True

    monkeypatch.setattr(
        submit_urls.file_utilities,
        "create_launchers_exit",
        fake_create_launchers_exit,
    )

    def fail_get_config_path(*args, **kwargs):
        raise AssertionError("get_config_path should not be called")

    monkeypatch.setattr(
        submit_urls.file_utilities,
        "get_config_path",
        fail_get_config_path,
    )
    monkeypatch.setattr(
        submit_urls,
        "get_sitemap_entries",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("get_sitemap_entries should not be called")
        ),
    )
    monkeypatch.setattr(
        submit_urls,
        "load_google_key",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("load_google_key should not be called")
        ),
    )
    monkeypatch.setattr(
        submit_urls,
        "submit_urls_to_google",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("submit_urls_to_google should not be called")
        ),
    )
    monkeypatch.setattr(
        submit_urls,
        "load_bing_api_key",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("load_bing_api_key should not be called")
        ),
    )
    monkeypatch.setattr(
        submit_urls,
        "submit_urls_to_bing",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("submit_urls_to_bing should not be called")
        ),
    )

    submit_urls.main()

    assert launcher_calls == [(args, submit_urls.__file__)]


def test_main_dry_run_allows_missing_provider_secret_files(
    monkeypatch, tmp_path, capsys
):
    config_path = tmp_path / "settings.ini"
    config = configparser.ConfigParser()
    config["Common"] = {
        "sitemap_url": "https://example.com/sitemap.xml",
        "last_submitted": "2024-01-01T00:00:00+00:00",
    }
    config["Google"] = {
        "can_submit": "1",
        "json_key_path": str(tmp_path / "missing-google.json.gpg"),
    }
    config["Bing"] = {
        "can_submit": "1",
        "api_key_path": str(tmp_path / "missing-bing.txt.gpg"),
    }
    with open(config_path, "w", encoding="utf-8") as f:
        config.write(f)

    monkeypatch.setattr(
        submit_urls,
        "get_arguments",
        lambda: SimpleNamespace(n=True),
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
        "get_sitemap_entries",
        lambda sitemap_url: [
            {
                "loc": "https://example.com/a",
                "lastmod": "2024-01-02T00:00:00+00:00",
            }
        ],
    )
    monkeypatch.setattr(
        submit_urls,
        "load_google_key",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("load_google_key should not be called")
        ),
    )
    monkeypatch.setattr(
        submit_urls,
        "load_bing_api_key",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("load_bing_api_key should not be called")
        ),
    )
    monkeypatch.setattr(
        submit_urls,
        "submit_urls_to_google",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("submit_urls_to_google should not be called")
        ),
    )
    monkeypatch.setattr(
        submit_urls,
        "submit_urls_to_bing",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("submit_urls_to_bing should not be called")
        ),
    )

    submit_urls.main()

    assert capsys.readouterr().out == (
        "{'https://example.com/a': 'URL_UPDATED'}\n"
    )


def test_main_wraps_sitemap_fetch_error(monkeypatch, tmp_path):
    config_path = tmp_path / "settings.ini"
    config = configparser.ConfigParser()
    config["Common"] = {
        "sitemap_url": "https://example.com/sitemap.xml",
        "last_submitted": "2024-01-01T00:00:00+00:00",
    }
    config["Google"] = {
        "can_submit": "1",
        "json_key_path": str(tmp_path / "missing-google.json.gpg"),
    }
    config["Bing"] = {
        "can_submit": "0",
        "api_key_path": str(tmp_path / "missing-bing.txt.gpg"),
    }
    with open(config_path, "w", encoding="utf-8") as f:
        config.write(f)

    error = submit_urls.requests.exceptions.RequestException("timed out")

    monkeypatch.setattr(
        submit_urls,
        "get_arguments",
        lambda: SimpleNamespace(n=True),
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
        "get_sitemap_entries",
        lambda sitemap_url: (_ for _ in ()).throw(error),
    )

    with pytest.raises(
        submit_urls.SubmissionError, match="Unable to fetch sitemap"
    ) as exc_info:
        submit_urls.main()

    assert exc_info.value.__cause__ is error


def test_main_wraps_xml_parse_error(monkeypatch, tmp_path):
    config_path = tmp_path / "settings.ini"
    config = configparser.ConfigParser()
    config["Common"] = {
        "sitemap_url": "https://example.com/sitemap.xml",
        "last_submitted": "2024-01-01T00:00:00+00:00",
    }
    config["Google"] = {
        "can_submit": "1",
        "json_key_path": str(tmp_path / "missing-google.json.gpg"),
    }
    config["Bing"] = {
        "can_submit": "0",
        "api_key_path": str(tmp_path / "missing-bing.txt.gpg"),
    }
    with open(config_path, "w", encoding="utf-8") as f:
        config.write(f)

    error = ExpatError("not well-formed")

    monkeypatch.setattr(
        submit_urls,
        "get_arguments",
        lambda: SimpleNamespace(n=True),
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
        "get_sitemap_entries",
        lambda sitemap_url: (_ for _ in ()).throw(error),
    )

    with pytest.raises(
        submit_urls.SubmissionError, match="Unable to parse sitemap XML"
    ) as exc_info:
        submit_urls.main()

    assert exc_info.value.__cause__ is error


def test_main_wraps_malformed_sitemap_error(monkeypatch, tmp_path):
    config_path = tmp_path / "settings.ini"
    config = configparser.ConfigParser()
    config["Common"] = {
        "sitemap_url": "https://example.com/sitemap.xml",
        "last_submitted": "2024-01-01T00:00:00+00:00",
    }
    config["Google"] = {
        "can_submit": "1",
        "json_key_path": str(tmp_path / "missing-google.json.gpg"),
    }
    config["Bing"] = {
        "can_submit": "0",
        "api_key_path": str(tmp_path / "missing-bing.txt.gpg"),
    }
    with open(config_path, "w", encoding="utf-8") as f:
        config.write(f)

    monkeypatch.setattr(
        submit_urls,
        "get_arguments",
        lambda: SimpleNamespace(n=True),
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
        "get_sitemap_entries",
        lambda sitemap_url: [{"loc": "https://example.com/a"}],
    )

    with pytest.raises(
        submit_urls.SubmissionError, match="missing 'loc' or 'lastmod'"
    ) as exc_info:
        submit_urls.main()

    assert isinstance(exc_info.value.__cause__, ValueError)


def test_cli_reports_submission_error_without_traceback(tmp_path):
    config_dir = tmp_path / "xdg-config" / "submit-urls"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "submit_urls.ini"
    config = configparser.ConfigParser()
    config["Common"] = {
        "sitemap_url": "https://example.com/sitemap.xml",
        "last_submitted": "2024-01-01T00:00:00+00:00",
    }
    config["Google"] = {
        "can_submit": "1",
        "json_key_path": str(tmp_path / "missing-google.json.gpg"),
    }
    config["Bing"] = {
        "can_submit": "0",
        "api_key_path": str(tmp_path / "missing-bing.txt.gpg"),
    }
    with open(config_path, "w", encoding="utf-8") as f:
        config.write(f)

    env = os.environ.copy()
    env["XDG_CONFIG_HOME"] = str(tmp_path / "xdg-config")
    completed = subprocess.run(
        [sys.executable, str(Path(submit_urls.__file__))],
        cwd=Path(submit_urls.__file__).parent,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    assert completed.returncode == 1
    assert completed.stdout == ""
    assert "Configured file 'Google.json_key_path' does not exist" in (
        completed.stderr
    )
    assert "Traceback" not in completed.stderr


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
        "get_sitemap_entries",
        lambda sitemap_url: [{"loc": "https://example.com/a"}],
    )
    monkeypatch.setattr(
        submit_urls,
        "get_updated_entries",
        lambda url_items, last_submitted, last_submitted_url="": [
            (
                submit_urls.parse_timestamp("2024-01-02T00:00:00+00:00"),
                "https://example.com/a",
            )
        ],
    )
    monkeypatch.setattr(
        submit_urls,
        "load_google_key",
        lambda path: {"client_email": "demo@example.com"},
    )
    monkeypatch.setattr(
        submit_urls,
        "submit_urls_to_google",
        lambda key_dictionary, url_list: (_ for _ in ()).throw(
            submit_urls.SubmissionError("Google submission failed.")
        ),
    )
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

    checkpoint_calls = []
    sitemap_calls = []
    google_submissions = []
    bing_submissions = []
    state = {"run": 0}

    def fake_get_sitemap_entries(sitemap_url):
        sitemap_calls.append(sitemap_url)
        return [{"loc": "https://example.com/a"}]

    def fake_get_updated_entries(
        url_items, last_submitted, last_submitted_url=""
    ):
        checkpoint_calls.append(last_submitted)
        if state["run"] == 0:
            return [
                (
                    submit_urls.parse_timestamp("2024-01-02T00:00:00+00:00"),
                    "https://example.com/a",
                )
            ]
        if last_submitted == "2024-01-02T00:00:00+00:00":
            return []
        return [
            (
                submit_urls.parse_timestamp("2024-01-02T00:00:00+00:00"),
                "https://example.com/a",
            )
        ]

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
    monkeypatch.setattr(
        submit_urls,
        "get_sitemap_entries",
        fake_get_sitemap_entries,
    )
    monkeypatch.setattr(
        submit_urls,
        "get_updated_entries",
        fake_get_updated_entries,
    )
    monkeypatch.setattr(
        submit_urls,
        "load_google_key",
        lambda path: {"client_email": "demo@example.com"},
    )
    monkeypatch.setattr(
        submit_urls,
        "submit_urls_to_google",
        fake_submit_google,
    )
    monkeypatch.setattr(
        submit_urls,
        "load_bing_api_key",
        lambda path: "secret",
    )
    monkeypatch.setattr(
        submit_urls,
        "submit_urls_to_bing",
        fake_submit_bing,
    )
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
    assert sitemap_calls == [
        "https://example.com/sitemap.xml",
        "https://example.com/sitemap.xml",
    ]
    assert checkpoint_calls == [
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


def test_main_persists_google_checkpoint_after_successful_chunk(
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

    submissions = []

    def fake_submit_google(key_dictionary, url_list):
        submissions.append(dict(url_list))
        if len(submissions) == 2:
            raise submit_urls.SubmissionError("Google chunk failed.")

    monkeypatch.setattr(submit_urls, "GOOGLE_BATCH_SIZE", 2)
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
        "get_sitemap_entries",
        lambda sitemap_url: [
            {
                "loc": "https://example.com/c",
                "lastmod": "2024-01-04T00:00:00+00:00",
            },
            {
                "loc": "https://example.com/a",
                "lastmod": "2024-01-02T00:00:00+00:00",
            },
            {
                "loc": "https://example.com/b",
                "lastmod": "2024-01-03T00:00:00+00:00",
            },
        ],
    )
    monkeypatch.setattr(
        submit_urls,
        "load_google_key",
        lambda path: {"client_email": "demo@example.com"},
    )
    monkeypatch.setattr(
        submit_urls,
        "submit_urls_to_google",
        fake_submit_google,
    )

    with pytest.raises(submit_urls.SubmissionError, match="Google chunk"):
        submit_urls.main()

    reloaded = configparser.ConfigParser()
    reloaded.read(config_path, encoding="utf-8")
    assert submissions == [
        {
            "https://example.com/a": "URL_UPDATED",
            "https://example.com/b": "URL_UPDATED",
        },
        {"https://example.com/c": "URL_UPDATED"},
    ]
    assert reloaded["Google"]["last_submitted"] == (
        "2024-01-03T00:00:00+00:00"
    )
    assert reloaded["Common"]["last_submitted"] == (
        "2024-01-03T00:00:00+00:00"
    )


def test_main_resumes_google_chunk_with_same_lastmod_after_failure(
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

    submissions = []

    def fake_submit_google(key_dictionary, url_list):
        submissions.append(dict(url_list))
        if len(submissions) == 2:
            raise submit_urls.SubmissionError("Google chunk failed.")

    monkeypatch.setattr(submit_urls, "GOOGLE_BATCH_SIZE", 2)
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
        "get_sitemap_entries",
        lambda sitemap_url: [
            {
                "loc": "https://example.com/c",
                "lastmod": "2024-01-02T00:00:00+00:00",
            },
            {
                "loc": "https://example.com/a",
                "lastmod": "2024-01-02T00:00:00+00:00",
            },
            {
                "loc": "https://example.com/b",
                "lastmod": "2024-01-02T00:00:00+00:00",
            },
        ],
    )
    monkeypatch.setattr(
        submit_urls,
        "load_google_key",
        lambda path: {"client_email": "demo@example.com"},
    )
    monkeypatch.setattr(
        submit_urls,
        "submit_urls_to_google",
        fake_submit_google,
    )

    with pytest.raises(submit_urls.SubmissionError, match="Google chunk"):
        submit_urls.main()

    reloaded = configparser.ConfigParser()
    reloaded.read(config_path, encoding="utf-8")
    assert reloaded["Google"]["last_submitted"] == (
        "2024-01-02T00:00:00+00:00"
    )
    assert reloaded["Google"]["last_submitted_url"] == "https://example.com/b"

    submit_urls.main()

    assert submissions == [
        {
            "https://example.com/a": "URL_UPDATED",
            "https://example.com/b": "URL_UPDATED",
        },
        {"https://example.com/c": "URL_UPDATED"},
        {"https://example.com/c": "URL_UPDATED"},
    ]


def test_main_persists_bing_checkpoint_after_successful_chunk(
    monkeypatch, tmp_path
):
    config_path = tmp_path / "settings.ini"
    bing_key = tmp_path / "bing.txt.gpg"
    bing_key.write_bytes(b"encrypted")
    config = configparser.ConfigParser()
    config["Common"] = {
        "sitemap_url": "https://example.com/sitemap.xml",
        "last_submitted": "2024-01-01T00:00:00+00:00",
    }
    config["Google"] = {
        "can_submit": "0",
        "json_key_path": str(tmp_path / "google.json.gpg"),
    }
    config["Bing"] = {
        "can_submit": "1",
        "api_key_path": str(bing_key),
    }
    with open(config_path, "w", encoding="utf-8") as f:
        config.write(f)

    submissions = []

    def fake_submit_bing(api_key, site_url, url_list):
        submissions.append((site_url, list(url_list)))
        if len(submissions) == 2:
            raise submit_urls.SubmissionError("Bing chunk failed.")

    monkeypatch.setattr(submit_urls, "BING_BATCH_SIZE", 2)
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
        "get_sitemap_entries",
        lambda sitemap_url: [
            {
                "loc": "https://example.com/c",
                "lastmod": "2024-01-04T00:00:00+00:00",
            },
            {
                "loc": "https://example.com/a",
                "lastmod": "2024-01-02T00:00:00+00:00",
            },
            {
                "loc": "https://example.com/b",
                "lastmod": "2024-01-03T00:00:00+00:00",
            },
        ],
    )
    monkeypatch.setattr(
        submit_urls,
        "load_bing_api_key",
        lambda path: "secret",
    )
    monkeypatch.setattr(
        submit_urls,
        "submit_urls_to_bing",
        fake_submit_bing,
    )

    with pytest.raises(submit_urls.SubmissionError, match="Bing chunk"):
        submit_urls.main()

    reloaded = configparser.ConfigParser()
    reloaded.read(config_path, encoding="utf-8")
    assert submissions == [
        (
            "https://example.com",
            ["https://example.com/a", "https://example.com/b"],
        ),
        ("https://example.com", ["https://example.com/c"]),
    ]
    assert reloaded["Bing"]["last_submitted"] == ("2024-01-03T00:00:00+00:00")
    assert reloaded["Common"]["last_submitted"] == (
        "2024-01-03T00:00:00+00:00"
    )


def test_main_resumes_bing_chunk_with_same_lastmod_after_failure(
    monkeypatch, tmp_path
):
    config_path = tmp_path / "settings.ini"
    bing_key = tmp_path / "bing.txt.gpg"
    bing_key.write_bytes(b"encrypted")
    config = configparser.ConfigParser()
    config["Common"] = {
        "sitemap_url": "https://example.com/sitemap.xml",
        "last_submitted": "2024-01-01T00:00:00+00:00",
    }
    config["Google"] = {
        "can_submit": "0",
        "json_key_path": str(tmp_path / "google.json.gpg"),
    }
    config["Bing"] = {
        "can_submit": "1",
        "api_key_path": str(bing_key),
    }
    with open(config_path, "w", encoding="utf-8") as f:
        config.write(f)

    submissions = []

    def fake_submit_bing(api_key, site_url, url_list):
        submissions.append((site_url, list(url_list)))
        if len(submissions) == 2:
            raise submit_urls.SubmissionError("Bing chunk failed.")

    monkeypatch.setattr(submit_urls, "BING_BATCH_SIZE", 2)
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
        "get_sitemap_entries",
        lambda sitemap_url: [
            {
                "loc": "https://example.com/c",
                "lastmod": "2024-01-02T00:00:00+00:00",
            },
            {
                "loc": "https://example.com/a",
                "lastmod": "2024-01-02T00:00:00+00:00",
            },
            {
                "loc": "https://example.com/b",
                "lastmod": "2024-01-02T00:00:00+00:00",
            },
        ],
    )
    monkeypatch.setattr(
        submit_urls,
        "load_bing_api_key",
        lambda path: "secret",
    )
    monkeypatch.setattr(
        submit_urls,
        "submit_urls_to_bing",
        fake_submit_bing,
    )

    with pytest.raises(submit_urls.SubmissionError, match="Bing chunk"):
        submit_urls.main()

    reloaded = configparser.ConfigParser()
    reloaded.read(config_path, encoding="utf-8")
    assert reloaded["Bing"]["last_submitted"] == ("2024-01-02T00:00:00+00:00")
    assert reloaded["Bing"]["last_submitted_url"] == "https://example.com/b"

    submit_urls.main()

    assert submissions == [
        (
            "https://example.com",
            ["https://example.com/a", "https://example.com/b"],
        ),
        ("https://example.com", ["https://example.com/c"]),
        ("https://example.com", ["https://example.com/c"]),
    ]


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

    def fail_get_sitemap_entries(*args, **kwargs):
        raise AssertionError("get_sitemap_entries should not be called")

    monkeypatch.setattr(
        submit_urls,
        "get_sitemap_entries",
        fail_get_sitemap_entries,
    )

    with pytest.raises(
        submit_urls.SubmissionError, match="default placeholder value"
    ):
        submit_urls.main()


def test_main_skips_sitemap_fetch_when_no_providers_enabled(
    monkeypatch, tmp_path
):
    config_path = tmp_path / "settings.ini"
    config = configparser.ConfigParser()
    config["Common"] = {
        "sitemap_url": "https://example.com/sitemap.xml",
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

    def fail_get_sitemap_entries(*args, **kwargs):
        raise AssertionError("get_sitemap_entries should not be called")

    monkeypatch.setattr(
        submit_urls,
        "get_sitemap_entries",
        fail_get_sitemap_entries,
    )

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
        "get_sitemap_entries",
        lambda sitemap_url: [{"loc": "https://example.com/a"}],
    )
    monkeypatch.setattr(
        submit_urls,
        "get_updated_entries",
        lambda url_items, last_submitted, last_submitted_url="": (
            [
                (
                    submit_urls.parse_timestamp("2024-01-02T00:00:00+00:00"),
                    "https://example.com/a",
                )
            ]
        ),
    )
    monkeypatch.setattr(
        submit_urls,
        "load_google_key",
        lambda path: (_ for _ in ()).throw(
            submit_urls.SubmissionError("bad decrypt")
        ),
    )

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
        "get_sitemap_entries",
        lambda sitemap_url: [
            {"loc": "https://example.com/a"},
            {"loc": "https://example.com/b"},
        ],
    )
    monkeypatch.setattr(
        submit_urls,
        "get_updated_entries",
        lambda url_items, last_submitted, last_submitted_url="": (
            [
                (
                    submit_urls.parse_timestamp("2024-01-05T00:00:00+00:00"),
                    "https://example.com/a",
                ),
                (
                    submit_urls.parse_timestamp("2024-01-05T00:00:00+00:00"),
                    "https://example.com/b",
                ),
            ]
        ),
    )
    monkeypatch.setattr(
        submit_urls,
        "load_google_key",
        lambda path: {"client_email": "demo@example.com"},
    )
    monkeypatch.setattr(
        submit_urls,
        "submit_urls_to_google",
        lambda key_dictionary, url_list: None,
    )
    monkeypatch.setattr(
        submit_urls,
        "load_bing_api_key",
        lambda path: "secret",
    )
    monkeypatch.setattr(
        submit_urls,
        "submit_urls_to_bing",
        lambda api_key, site_url, url_list: None,
    )
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

    def fake_get_updated_entries(
        url_items, last_submitted, last_submitted_url=""
    ):
        state["run"] += 1
        if state["run"] == 1:
            assert last_submitted == "2024-01-01T00:00:00+00:00"
            return [
                (
                    submit_urls.parse_timestamp("2024-01-05T00:00:00+00:00"),
                    "https://example.com/a",
                )
            ]
        assert last_submitted == "2024-01-05T00:00:00+00:00"
        return [
            (
                submit_urls.parse_timestamp("2024-01-07T00:00:00+00:00"),
                "https://example.com/b",
            )
        ]

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
        "get_sitemap_entries",
        lambda sitemap_url: [{"loc": "https://example.com/a"}],
    )
    monkeypatch.setattr(
        submit_urls,
        "get_updated_entries",
        fake_get_updated_entries,
    )
    monkeypatch.setattr(
        submit_urls,
        "load_google_key",
        lambda path: {"client_email": "demo@example.com"},
    )
    monkeypatch.setattr(
        submit_urls,
        "submit_urls_to_google",
        lambda key_dictionary, url_list: None,
    )
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
