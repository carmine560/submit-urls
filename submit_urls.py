#!/usr/bin/env python3

"""Synchronize sitemap URLs with the Google and Bing indices."""

from datetime import datetime, timezone
from urllib.parse import urlparse
import argparse
import configparser
import io
import json
import os
import pprint
import sys

from google.oauth2 import service_account
from googleapiclient.discovery import build
import gnupg
import requests
import xmltodict

from core_utilities import file_utilities

HTTP_TIMEOUT_SECONDS = 10
DEFAULT_SITEMAP_URL = "HTTPS://EXAMPLE.COM/SITEMAP.XML"


class SubmissionError(Exception):
    """Represent a failure while preparing or submitting URLs."""


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


def validate_config(config):
    """Validate config values before network or GPG work begins."""
    sitemap_url = get_required_option(config, "Common", "sitemap_url")
    validate_url(sitemap_url, "Common.sitemap_url")

    last_submitted = get_required_option(config, "Common", "last_submitted")
    try:
        parse_timestamp(last_submitted)
    except ValueError as e:
        raise SubmissionError(
            "Config option 'Common.last_submitted' must be an ISO 8601 "
            "timestamp."
        ) from e

    if get_required_boolean_option(config, "Google", "can_submit"):
        google_key_path = get_required_option(
            config, "Google", "json_key_path"
        )
        validate_secret_path(google_key_path, "Google.json_key_path")

    if get_required_boolean_option(config, "Bing", "can_submit"):
        bing_key_path = get_required_option(config, "Bing", "api_key_path")
        validate_secret_path(bing_key_path, "Bing.api_key_path")


def main():
    """Parse arguments, configure settings, and submit URLs."""
    args = get_arguments()

    file_utilities.create_launchers_exit(args, __file__)

    config_path = file_utilities.get_config_path(__file__)
    config = configure(config_path)
    validate_config(config)
    url_list, newest_submitted_at = add_entries(
        config["Common"]["sitemap_url"], config["Common"]["last_submitted"]
    )

    if not url_list:
        return
    if args.n:
        pprint.pprint(url_list)
        return

    gpg = gnupg.GPG()
    if config["Google"].getboolean("can_submit"):
        key_dictionary = load_google_key(
            config["Google"]["json_key_path"], gpg
        )
        submit_urls_to_google(key_dictionary, url_list)
    if config["Bing"].getboolean("can_submit"):
        api_key = load_bing_api_key(config["Bing"]["api_key_path"], gpg)
        parsed_url = urlparse(config["Common"]["sitemap_url"])
        submit_urls_to_bing(
            api_key,
            f"{parsed_url.scheme}://{parsed_url.netloc}",
            list(url_list.keys()),
        )

    config["Common"]["last_submitted"] = newest_submitted_at.isoformat()
    with open(config_path, "w") as f:
        config.write(f)


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
    config = configparser.ConfigParser()
    config["Common"] = {
        "sitemap_url": DEFAULT_SITEMAP_URL,
        "last_submitted": datetime.now(timezone.utc).isoformat(),
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
        config.read(config_path)
        return config
    else:
        with open(config_path, "w") as f:
            config.write(f)
            sys.exit()


def add_entries(sitemap_url, last_submitted):
    """Extract updated URLs and the newest submitted timestamp."""
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

    last_submitted_at = parse_timestamp(last_submitted)
    newer = {}
    newest_submitted_at = None
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
        if lastmod_at > last_submitted_at:
            newer[loc] = "URL_UPDATED"
            if newest_submitted_at is None or lastmod_at > newest_submitted_at:
                newest_submitted_at = lastmod_at

    return newer, newest_submitted_at


def decrypt_data(path, decrypt_function):
    """Decrypt and validate secret data loaded from a file."""
    with open(path, "rb") as f:
        decrypted = decrypt_function(f)

    if not getattr(decrypted, "ok", bool(getattr(decrypted, "data", b""))):
        status = getattr(decrypted, "status", "decryption failed")
        raise SubmissionError(status)
    if not decrypted.data:
        raise SubmissionError("Decryption returned no data.")
    return decrypted.data


def load_google_key(path, gpg):
    """Load and validate the decrypted Google service account JSON."""
    try:
        return json.load(
            io.BytesIO(
                decrypt_data(
                    path,
                    lambda file_object: gpg.decrypt_file(file_object),
                )
            )
        )
    except json.JSONDecodeError as e:
        raise SubmissionError("Google key is not valid JSON.") from e


def load_bing_api_key(path, gpg):
    """Load and validate the decrypted Bing API key."""
    return (
        decrypt_data(
            path,
            lambda file_object: gpg.decrypt(file_object.read()),
        )
        .decode()
        .strip()
    )


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

    credentials = service_account.Credentials.from_service_account_info(
        key_dictionary, scopes=["https://www.googleapis.com/auth/indexing"]
    )
    service = build("indexing", "v3", credentials=credentials)
    batch = service.new_batch_http_request(callback=handle_response)

    for url, api_type in url_list.items():
        batch.add(
            service.urlNotifications().publish(
                body={"url": url, "type": api_type}
            )
        )

    batch.execute()
    if errors:
        raise SubmissionError("Google submission failed.")


def submit_urls_to_bing(api_key, site_url, url_list):
    """Submit URLs to the Bing index using an API key."""
    try:
        response = requests.post(
            "https://ssl.bing.com/webmaster/api.svc/json/SubmitUrlBatch"
            f"?apikey={api_key}",
            data=json.dumps({"siteUrl": site_url, "urlList": url_list}),
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        print(response.json())
    except requests.exceptions.RequestException as e:
        print(e)
        raise SubmissionError("Bing submission failed.") from e


if __name__ == "__main__":
    main()
