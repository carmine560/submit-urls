"""Tests for the sitemap and submission workflow."""

import json

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
