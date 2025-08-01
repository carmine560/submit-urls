# submit-urls #

<!-- Python script that refers to sitemap and submits URLs through Indexing API
and Bing Webmaster API -->

The `submit_urls.py` Python script refers to the sitemap and submits the URLs
of newer entries than the last submission through the [Indexing
API](https://developers.google.com/search/apis/indexing-api/v3/quickstart) and
the [Bing Webmaster API](https://docs.microsoft.com/en-us/bingwebmaster/).

## Prerequisites ##

`submit_urls.py` has been tested for Blogger on Debian Testing on WSL 2 and
requires the following packages:

  * [`google-api-python-client`](https://github.com/googleapis/google-api-python-client/)
    to access Google APIs
  * [`pandas`](https://pandas.pydata.org/) to extract updated URLs from the
    sitemap
  * [`python-gnupg`](https://github.com/vsajip/python-gnupg) to invoke
    [GnuPG](https://gnupg.org/index.html) for decrypting your encrypted JSON
    key file and API key file for authorization
  * [`xmltodict`](https://github.com/martinblech/xmltodict) to convert the
    sitemap to a dictionary

Install each package as needed. For example:

``` shell
sudo apt install gpg
git clone --recurse-submodules git@github.com:carmine560/submit-urls.git
cd submit-urls
# Run 'git submodule init' and 'git submodule update' if you cloned without
# '--recurse-submodules'.
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt -U
```

## Usage ##

`submit_urls.py` will create a `~/.config/submit-urls/submit_urls.ini`
configuration file if it does not already exist.

First, prepare your [JSON key
file](https://developers.google.com/search/apis/indexing-api/v3/prereqs) for
the Indexing API and [API
key](https://docs.microsoft.com/en-us/bingwebmaster/getting-access) file for
the Bing Webmaster API, and encrypt them using GnuPG with your OpenPGP key
pair. Next, replace the values of the following options in the configuration
file with your own:

  * `sitemap_url`
  * `json_key_path`
  * `api_key_path`

Then, execute:

``` shell
submit_urls.py
```

### Options ###

  * `-n`: do not perform POST requests
  * `-BS`: save a Bash script to `$HOME/Downloads` to launch this script and
    exit

## License ##

This project is licensed under the [MIT License](LICENSE). The `.gitignore`
file is sourced from [`gitignore`](https://github.com/github/gitignore), which
is licensed under the CC0-1.0 license.

## Link ##

  * [*Bash Scripting to Submit Appropriate URLs through Bing Webmaster
    API*](https://carmine560.blogspot.com/2020/12/bash-scripting-to-submit-urls-through.html):
    a blog post providing background on the original Bash script, now
    implemented in Python
