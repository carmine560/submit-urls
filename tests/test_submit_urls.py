"""Tests for the sitemap and submission workflow."""

import json
import configparser

import pytest

import submit_urls


class _Response:
    def __init__(self, text=""):
        self.text = text


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

    monkeypatch.setattr(
        submit_urls.requests,
        "get",
        lambda url: _Response("<xml />"),
    )
    monkeypatch.setattr(submit_urls.xmltodict, "parse", lambda text: sitemap)

    result = submit_urls.add_entries(
        "https://example.com/sitemap.xml",
        "2024-01-01T00:00:00+00:00",
    )

    assert result == {"https://example.com/new": "URL_UPDATED"}


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


def test_submit_urls_to_bing_posts_expected_payload(monkeypatch, capsys):
    called = {}

    class _PostResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"status": "ok"}

    def fake_post(url, data, headers):
        called["url"] = url
        called["data"] = data
        called["headers"] = headers
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
    assert "{'status': 'ok'}" in capsys.readouterr().out


def test_submit_urls_to_bing_exits_on_request_error(monkeypatch, capsys):
    error = submit_urls.requests.exceptions.RequestException("request failed")

    def fake_post(url, data, headers):
        raise error

    monkeypatch.setattr(submit_urls.requests, "post", fake_post)

    with pytest.raises(SystemExit) as excinfo:
        submit_urls.submit_urls_to_bing(
            "secret",
            "https://example.com",
            ["https://example.com/a"],
        )

    assert excinfo.value.code == 1
    assert "request failed" in capsys.readouterr().out
