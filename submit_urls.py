#!/usr/bin/env python3

"""Synchronize sitemap URLs with the Google and Bing indices."""

import argparse
import configparser
import io
import json
import os
import pprint
import subprocess
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse
from xml.parsers.expat import ExpatError

import requests
import xmltodict
from google.oauth2 import service_account
from googleapiclient.discovery import build

from core_utilities import config_io
from core_utilities import file_utilities

DEFAULT_SITEMAP_URL = "HTTPS://EXAMPLE.COM/SITEMAP.XML"
HTTP_TIMEOUT_SECONDS = 10
GPG_TIMEOUT_SECONDS = 30
GOOGLE_BATCH_SIZE = 100
BING_BATCH_SIZE = 500
PROVIDER_SECTIONS = ("Google", "Bing")
SITEMAP_ERROR_MESSAGES = {
    ExpatError: "Unable to parse sitemap XML",
    ValueError: "Invalid sitemap",
}


class SubmissionError(Exception):
    """Represent a failure while preparing or submitting URLs."""


class ConfigCreated(Exception):
    """Signal that a default config file was created for the user."""


# Config Helpers


def get_required_option(config, section, option):
    """Return a required config value or raise a clear validation error."""
    if not config.has_section(section):
        raise SubmissionError(f"Missing required config section '{section}'.")
    if not config.has_option(section, option):
        raise SubmissionError(
            f"Missing required config option '{section}.{option}'."
        )

    value = config.get(section, option).strip()
    if not value:
        raise SubmissionError(
            f"Config option '{section}.{option}' must not be empty."
        )
    return value


def get_required_boolean_option(config, section, option):
    """Return a required boolean config value or raise a clear error."""
    get_required_option(config, section, option)
    try:
        return config.getboolean(section, option)
    except ValueError as e:
        raise SubmissionError(
            f"Config option '{section}.{option}' must be a boolean value."
        ) from e


# Validation Helpers


def parse_timestamp(value):
    """Parse an ISO 8601 timestamp and normalize it to UTC."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def validate_url(value, option_name):
    """Validate a URL before any network work is attempted."""
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SubmissionError(
            f"Config option '{option_name}' must be a valid HTTP(S) URL."
        )
    if value == DEFAULT_SITEMAP_URL:
        raise SubmissionError(
            f"Config option '{option_name}' still uses the default "
            "placeholder value."
        )


def validate_secret_path(path, option_name):
    """Validate a configured secret path before any decryption work."""
    if not os.path.isfile(path):
        raise SubmissionError(
            f"Configured file '{option_name}' does not exist: {path}"
        )


def validate_config(config, validate_secrets=True):
    """Validate config values before network or GPG work begins."""
    sitemap_url = get_required_option(config, "Common", "sitemap_url")
    validate_url(sitemap_url, "Common.sitemap_url")

    google_can_submit = get_required_boolean_option(
        config, "Google", "can_submit"
    )
    if validate_secrets and google_can_submit:
        google_key_path = get_required_option(
            config, "Google", "json_key_path"
        )
        validate_secret_path(google_key_path, "Google.json_key_path")

    bing_can_submit = get_required_boolean_option(config, "Bing", "can_submit")
    if validate_secrets and bing_can_submit:
        bing_key_path = get_required_option(config, "Bing", "api_key_path")
        validate_secret_path(bing_key_path, "Bing.api_key_path")

    for section in get_enabled_provider_sections(config):
        get_checkpoint_urls(config, section)
        provider_last_submitted = get_required_option(
            config, section, "last_submitted"
        )
        try:
            parse_timestamp(provider_last_submitted)
        except ValueError as e:
            raise SubmissionError(
                f"Config option '{section}.last_submitted' must be an "
                "ISO 8601 timestamp."
            ) from e


# Sitemap Parsing


def get_sitemap_entries(sitemap_url):
    """Fetch sitemap URL entries."""
    response = requests.get(sitemap_url, timeout=HTTP_TIMEOUT_SECONDS)
    response.raise_for_status()
    sitemap = xmltodict.parse(response.text)
    url_items = sitemap.get("urlset", {}).get("url")
    if not url_items:
        raise ValueError("Sitemap does not contain any URL entries.")
    if isinstance(url_items, dict):
        url_items = [url_items]
    if not isinstance(url_items, list):
        raise ValueError("Sitemap URL entries must be a list or mapping.")
    return url_items


def get_updated_entries(url_items, last_submitted, submitted_urls=None):
    """Extract updated URLs newer than the given checkpoint."""
    last_submitted_at = parse_timestamp(last_submitted)
    newer = []
    for item in url_items:
        if not isinstance(item, dict):
            raise ValueError("Sitemap URL entry must be a mapping.")

        loc = item.get("loc")
        lastmod = item.get("lastmod")
        if not loc or not lastmod:
            raise ValueError(
                "Sitemap URL entry is missing 'loc' or 'lastmod'."
            )
        lastmod_at = parse_timestamp(lastmod)
        is_newer = lastmod_at > last_submitted_at or (
            submitted_urls is not None
            and lastmod_at == last_submitted_at
            and loc not in submitted_urls
        )
        if is_newer:
            newer.append((lastmod_at, loc))

    # Sort first by lastmod_at. If two entries have the same timestamp, sort by
    # loc.
    newer.sort(key=lambda entry: (entry[0], entry[1]))
    return newer


# Secret Loading


def _decrypt_data(path):
    """Decrypt and validate secret data loaded from a file."""
    try:
        decrypted = subprocess.run(
            [
                "gpg",
                "--batch",
                "--yes",
                "--decrypt",
                path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=GPG_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as e:
        raise SubmissionError(
            f"GPG decryption timed out after {GPG_TIMEOUT_SECONDS} seconds."
        ) from e
    except OSError as e:
        raise SubmissionError(f"Unable to run gpg: {e}") from e
    if decrypted.returncode:
        status = decrypted.stderr.decode("utf-8", errors="replace").strip()
        if not status:
            status = f"gpg exited with status {decrypted.returncode}"
        raise SubmissionError(f"GPG decryption failed: {status}")
    if not decrypted.stdout:
        raise SubmissionError("Decryption returned no data.")
    return decrypted.stdout


def load_google_key(path):
    """Load and validate the decrypted Google service account JSON."""
    try:
        return json.load(io.BytesIO(_decrypt_data(path)))
    except json.JSONDecodeError as e:
        raise SubmissionError("Google key is not valid JSON.") from e


def load_bing_api_key(path):
    """Load and validate the decrypted Bing API key."""
    return _decrypt_data(path).decode().strip()


# Submission


def get_enabled_provider_sections(config):
    """Return provider sections that are enabled for submission."""
    return [
        section
        for section in PROVIDER_SECTIONS
        if config[section].getboolean("can_submit")
    ]


def get_checkpoint_urls(config, section):
    """Return URLs submitted at a section's checkpoint timestamp."""
    value = config.get(section, "last_submitted_urls", fallback="").strip()
    if value:
        try:
            urls = json.loads(value)
        except json.JSONDecodeError as e:
            raise SubmissionError(
                f"Config option '{section}.last_submitted_urls' must be a "
                "JSON list of URLs."
            ) from e
        if not isinstance(urls, list) or not all(
            isinstance(url, str) and url for url in urls
        ):
            raise SubmissionError(
                f"Config option '{section}.last_submitted_urls' must be a "
                "JSON list of URLs."
            )
        return set(urls)

    legacy_url = config.get(section, "last_submitted_url", fallback="").strip()
    if legacy_url:
        return {legacy_url}
    return None


def update_provider_checkpoint(config, section, chunk):
    """Record URLs submitted at the provider's newest checkpoint timestamp."""
    checkpoint_at = chunk[-1][0]
    if checkpoint_at == parse_timestamp(config[section]["last_submitted"]):
        checkpoint_urls = get_checkpoint_urls(config, section)
    else:
        checkpoint_urls = None
    checkpoint_urls = checkpoint_urls or set()
    checkpoint_urls.update(
        url for lastmod_at, url in chunk if lastmod_at == checkpoint_at
    )
    config[section]["last_submitted"] = checkpoint_at.isoformat()
    config[section]["last_submitted_urls"] = json.dumps(
        sorted(checkpoint_urls)
    )
    config[section].pop("last_submitted_url", None)


def submit_urls_to_google(key_dictionary, url_list):
    """Submit URLs to the Google index using a service account."""
    errors = []

    def handle_response(_, response, exception):
        """Handle the response or exception from each HTTP request."""
        if exception is not None:
            errors.append(exception)
            print(exception)
        else:
            print(response)

    try:
        credentials = service_account.Credentials.from_service_account_info(
            key_dictionary, scopes=["https://www.googleapis.com/auth/indexing"]
        )
        service = build("indexing", "v3", credentials=credentials)
        batch = service.new_batch_http_request(callback=handle_response)
    except Exception as e:
        raise SubmissionError("Google client setup failed.") from e

    for url, api_type in url_list.items():
        batch.add(
            service.urlNotifications().publish(
                body={"url": url, "type": api_type}
            )
        )

    try:
        batch.execute()
    except Exception as e:
        print(e)
        raise SubmissionError("Google submission failed.") from e
    if errors:
        raise SubmissionError("Google submission failed.")


def submit_urls_to_bing(api_key, site_url, url_list):
    """Submit URLs to the Bing index using an API key."""
    request_url = (
        "https://ssl.bing.com/webmaster/api.svc/json/SubmitUrlBatch"
        f"?apikey={api_key}"
    )
    redacted_url = (
        "https://ssl.bing.com/webmaster/api.svc/json/SubmitUrlBatch"
        "?apikey=<redacted>"
    )
    try:
        response = requests.post(
            request_url,
            data=json.dumps({"siteUrl": site_url, "urlList": url_list}),
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        print(response.json())
    except (requests.exceptions.RequestException, ValueError) as e:
        message = (
            f"Bing submission failed ({type(e).__name__}) for {redacted_url}."
        )
        print(message)
        raise SubmissionError(message) from None


# Entry Point


def get_arguments():
    """Parse and return command-line arguments."""
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    parser.add_argument(
        "-n", action="store_true", help="do not perform POST requests"
    )
    file_utilities.add_launcher_options(group)
    return parser.parse_args()


def configure(config_path):
    """Create or read a configuration file."""
    config = configparser.ConfigParser(interpolation=None)
    initial_checkpoint = datetime.now(timezone.utc).isoformat()
    config["Common"] = {
        "sitemap_url": DEFAULT_SITEMAP_URL,
    }
    config["Google"] = {
        "can_submit": "1",
        "json_key_path": os.path.join(
            os.path.dirname(config_path), "JSON_KEY.JSON.GPG"
        ),
    }
    config["Bing"] = {
        "can_submit": "1",
        "api_key_path": os.path.join(
            os.path.dirname(config_path), "api_key.txt.gpg"
        ),
    }

    if os.path.isfile(config_path):
        try:
            config.read(config_path)
        except configparser.Error as e:
            raise SubmissionError(
                f"Unable to parse configuration file '{config_path}': {e}"
            ) from e
        return config

    for section in PROVIDER_SECTIONS:
        config[section]["last_submitted"] = initial_checkpoint
    config_io.write_config(config, config_path)
    raise ConfigCreated


def submit_provider_updates(config, config_path, provider_updates):
    """Submit provider URL updates and persist successful chunk checkpoints."""
    failures = []

    google_entries = provider_updates.get("Google", [])
    if google_entries:
        try:
            key_dictionary = load_google_key(config["Google"]["json_key_path"])
            for i in range(0, len(google_entries), GOOGLE_BATCH_SIZE):
                chunk = google_entries[i : i + GOOGLE_BATCH_SIZE]
                submit_urls_to_google(
                    key_dictionary,
                    {url: "URL_UPDATED" for _, url in chunk},
                )
                update_provider_checkpoint(config, "Google", chunk)
                config_io.write_config(config, config_path)
        except SubmissionError as e:
            failures.append(f"Google: {e}")

    bing_entries = provider_updates.get("Bing", [])
    if bing_entries:
        try:
            api_key = load_bing_api_key(config["Bing"]["api_key_path"])
            parsed_url = urlparse(config["Common"]["sitemap_url"])
            site_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
            for i in range(0, len(bing_entries), BING_BATCH_SIZE):
                chunk = bing_entries[i : i + BING_BATCH_SIZE]
                submit_urls_to_bing(
                    api_key,
                    site_url,
                    [url for _, url in chunk],
                )
                update_provider_checkpoint(config, "Bing", chunk)
                config_io.write_config(config, config_path)
        except SubmissionError as e:
            failures.append(f"Bing: {e}")

    if failures:
        raise SubmissionError(
            f"Provider submission failures: {'; '.join(failures)}"
        )


def main():
    """Parse arguments, configure settings, and submit URLs."""
    args = get_arguments()

    if file_utilities.create_launchers_exit(args, __file__):
        return

    config_path = file_utilities.get_config_path(__file__)
    config = configure(config_path)
    validate_config(config, validate_secrets=not args.n)
    enabled_sections = get_enabled_provider_sections(config)
    if not enabled_sections:
        config_io.write_config(config, config_path)
        return

    try:
        url_items = get_sitemap_entries(config["Common"]["sitemap_url"])
    except requests.exceptions.RequestException as e:
        raise SubmissionError(f"Unable to fetch sitemap: {e}") from e
    except (ExpatError, ValueError) as e:
        raise SubmissionError(f"{SITEMAP_ERROR_MESSAGES[type(e)]}: {e}") from e

    provider_updates = {}
    preview_urls = {}
    for section in enabled_sections:
        try:
            url_list = get_updated_entries(
                url_items,
                config[section]["last_submitted"],
                get_checkpoint_urls(config, section),
            )
        except ValueError as e:
            raise SubmissionError(f"Invalid sitemap: {e}") from e
        provider_updates[section] = url_list
        preview_urls.update({url: "URL_UPDATED" for _, url in url_list})

    if not preview_urls:
        config_io.write_config(config, config_path)
        return
    if args.n:
        pprint.pprint(preview_urls)
        return

    submit_provider_updates(config, config_path, provider_updates)


if __name__ == "__main__":
    try:
        main()
    except ConfigCreated:
        sys.exit()
    except SubmissionError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
