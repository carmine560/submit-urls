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
import pandas as pd
import requests
import xmltodict

from shared_utilities import file_utilities


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
        with open(config["Google"]["json_key_path"], "rb") as f:
            key_dictionary = json.load(io.BytesIO(gpg.decrypt_file(f).data))

        submit_urls_to_google(key_dictionary, url_list)
    if config["Bing"].getboolean("can_submit"):
        with open(config["Bing"]["api_key_path"], "rb") as f:
            api_key = gpg.decrypt(f.read()).data.decode().strip()

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
    response = requests.get(sitemap_url)
    sitemap = xmltodict.parse(response.text)

    entries = [
        [item["loc"], item["lastmod"]] for item in sitemap["urlset"]["url"]
    ]
    df = pd.DataFrame(entries, columns=("loc", "lastmod"))
    newer = df[df.lastmod > last_submitted].copy()
    newer.lastmod = "URL_UPDATED"

    return newer.set_index("loc")["lastmod"].to_dict()


def submit_urls_to_google(key_dictionary, url_list):
    """Submit URLs to the Google index using a service account."""

    def handle_response(_, response, exception):
        """Handle the response or exception from each HTTP request."""
        if exception is not None:
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


def submit_urls_to_bing(api_key, site_url, url_list):
    """Submit URLs to the Bing index using an API key."""
    try:
        response = requests.post(
            "https://ssl.bing.com/webmaster/api.svc/json/SubmitUrlBatch"
            f"?apikey={api_key}",
            data=json.dumps({"siteUrl": site_url, "urlList": url_list}),
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        response.raise_for_status()
        print(response.json())
    except requests.exceptions.RequestException as e:
        print(e)
        sys.exit(1)


if __name__ == "__main__":
    main()
