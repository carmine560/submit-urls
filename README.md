# submit-urls #

<!-- Bash and Python scripts that refer to sitemap and submit URLs through Bing
Webmaster API and Indexing API -->

The `submit_urls_bing.sh` Bash script and `submit_urls_google.py` Python script
refer to the sitemap and submit the URLs of newer entries than the last
submission through the [Bing Webmaster
API](https://docs.microsoft.com/en-us/bingwebmaster/) and the [Indexing
API](https://developers.google.com/search/apis/indexing-api/v3/quickstart).

> **Note**: I plan to merge the Bash scripts into the Python scripts in the
> `submit-urls` repository.

## `submit_urls_bing.sh` Prerequisites ##

`submit_urls_bing.sh` has been tested for Blogger on Debian Testing on WSL 2
and uses the following packages:

  * [curl](https://curl.se/) to retrieve the sitemap and submit URLs
  * `xq` included in the [`yq`](https://kislyuk.github.io/yq/) package to
    transcode XML to JSON
  * [jq](https://jqlang.github.io/jq/) to filter JSON data
  * [GnuPG](https://gnupg.org/index.html) to encrypt the configuration file

Install each package as needed. For example:

``` shell
sudo apt install curl
python -m pip install yq -U
sudo apt install jq
sudo apt install gpg
```

## `submit_urls_bing.sh` Usage ##

`submit_urls_bing.sh` will create and encrypt a
`~/.config/submit-urls/submit_urls_bing.cfg.gpg` configuration file if it does
not exist. It assumes that the default key of GnuPG is your OpenPGP key pair.

### Bing Webmaster API ###

Prepare your [API
key](https://docs.microsoft.com/en-us/bingwebmaster/getting-access) for
authorization, and replace the values of the following variables in the
configuration file with yours:

  * `SITEMAP`
  * `SITE_URL`
  * `API_KEY`

Then:

``` shell
submit_urls_bing.sh
```

### Options ###

  * `-n`: do not perform POST requests
  * `-s`: work silently

## `submit_urls_google.py` Prerequisites ##

`submit_urls_google.py` has been tested for Blogger on Debian Testing on WSL 2
and uses the following packages:

  * [`google-api-python-client`](https://github.com/googleapis/google-api-python-client/)
    to access Google APIs
  * [`pandas`](https://pandas.pydata.org/) to extract updated URLs from the
    sitemap
  * [`python-gnupg`](https://github.com/vsajip/python-gnupg) to invoke
    [GnuPG](https://gnupg.org/index.html) to decrypt your encrypted JSON key
    file for authorization
  * [`xmltodict`](https://github.com/martinblech/xmltodict) to convert the
    sitemap to a dictionary

Install each package as needed. For example:

``` shell
sudo apt install gpg
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt -U
```

## `submit_urls_google.py` Usage ##

`submit_urls_google.py` will create a
`~/.config/submit-urls/submit_urls_google.ini` configuration file if it does
not exist.

### Indexing API ###

First, prepare your [JSON key
file](https://developers.google.com/search/apis/indexing-api/v3/prereqs) for
authorization, and encrypt it using GnuPG with your OpenPGP key pair. Next,
replace the values of the following options in the configuration file with
yours:

  * `sitemap_url`
  * `json_key_file`

Then:

``` shell
submit_urls_google.py
```

### Options ###

  * `-n`: do not perform POST requests

## License ##

[MIT](LICENSE.md)

## Link ##

  * [*Bash Scripting to Submit Appropriate URLs through Bing Webmaster
    API*](https://carmine560.blogspot.com/2020/12/bash-scripting-to-submit-urls-through.html):
    a blog post for more details
