#!/usr/bin/env python3

"""Synchronize local sitemap with remote URLs and update Google Index."""

from datetime import datetime, timezone
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

import file_utilities


def main():
    """Parse arguments, configure settings, and synchronize URLs."""
    parser = argparse.ArgumentParser()
    parser.add_argument('-n', action='store_true',
                        help='do not perform POST requests')
    args = parser.parse_args()

    config_path = file_utilities.get_config_path(__file__)
    config = configure(config_path)

    section = config['Common']
    SITEMAP_URL = section['sitemap_url']
    last_submitted = section['last_submitted']
    url_list = add_entries(SITEMAP_URL, last_submitted)

    if url_list:
        if args.n:
            pprint.pprint(url_list)
        else:
            JSON_KEY_FILE = section['json_key_file']
            gpg = gnupg.GPG()
            with open(JSON_KEY_FILE, 'rb') as f:
                decrypted_data = gpg.decrypt_file(f)

            submit_urls(json.load(io.BytesIO(decrypted_data.data)), url_list)

            section['last_submitted'] = datetime.now(timezone.utc).isoformat()
            with open(config_path, 'w') as f:
                config.write(f)


def configure(config_path):
    """Create or read a configuration file."""
    config = configparser.ConfigParser()
    config['Common'] = {
        'sitemap_url': 'HTTPS://EXAMPLE.COM/SITEMAP.XML',
        'last_submitted': datetime.now(timezone.utc).isoformat(),
        'json_key_file': os.path.join(os.path.dirname(config_path),
                                      'KEY_FILE.JSON.GPG')}
    if os.path.isfile(config_path):
        config.read(config_path)
        return config
    else:
        with open(config_path, 'w') as f:
            config.write(f)
            sys.exit()


def add_entries(SITEMAP_URL, last_submitted):
    """Extract and return updated URLs from a sitemap."""
    response = requests.get(SITEMAP_URL)
    sitemap = xmltodict.parse(response.text)

    entries = [[item['loc'], item['lastmod']]
               for item in sitemap['urlset']['url']]
    df = pd.DataFrame(entries, columns=('loc', 'lastmod'))
    newer = df[df.lastmod > last_submitted].copy()
    newer.lastmod = 'URL_UPDATED'

    return newer.set_index('loc')['lastmod'].to_dict()


def submit_urls(key_file_dict, url_list):
    """Submit URLs to Google Index using a service account."""
    SCOPES = ['https://www.googleapis.com/auth/indexing']
    credentials = service_account.Credentials.from_service_account_info(
        key_file_dict, scopes=SCOPES)
    service = build('indexing', 'v3', credentials=credentials)

    def insert_event(request_id, response, exception):
        """Handle the response or exception from each HTTP request."""
        if exception is not None:
            print(exception)
        else:
            print(response)

    batch = service.new_batch_http_request(callback=insert_event)
    for url, api_type in url_list.items():
        batch.add(service.urlNotifications().publish(
            body={'url': url, 'type': api_type}))

    batch.execute()


if __name__ == '__main__':
    main()
