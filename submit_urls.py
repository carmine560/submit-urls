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


class SubmissionError(Exception):
    """Represent a failure while preparing or submitting URLs."""


def main():
    """Parse arguments, configure settings, and submit URLs."""
    args = get_arguments()

    file_utilities.create_launchers_exit(args, __file__)

    config_path = file_utilities.get_config_path(__file__)
    config = configure(config_path)
    url_list = add_entries(
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

    config["Common"]["last_submitted"] = datetime.now(timezone.utc).isoformat()
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
        "sitemap_url": "HTTPS://EXAMPLE.COM/SITEMAP.XML",
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
    """Extract and return updated URLs from a sitemap."""
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

    newer = {}
    for item in url_items:
        if not isinstance(item, dict):
            raise ValueError("Sitemap URL entry must be a mapping.")

        loc = item.get("loc")
        lastmod = item.get("lastmod")
        if not loc or not lastmod:
            raise ValueError(
                "Sitemap URL entry is missing 'loc' or 'lastmod'."
            )
        if lastmod > last_submitted:
            newer[loc] = "URL_UPDATED"

    return newer


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
