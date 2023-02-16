# submit-urls #

<!-- Bash script that refers to sitemap and submits URLs through Bing
Webmaster API -->

<!-- bash bing-api curl gnupg jq yq -->

`submit-urls-bing.sh` refers to the sitemap and submits the URLs of
newer entries than the last submission through the [Bing Webmaster
API](https://docs.microsoft.com/en-us/bingwebmaster/).

## Prerequisites ##

This script has been tested for Blogger on Debian on WSL 2 and uses
the following packages:

  * [curl](https://curl.se/) to retrieve the sitemap and submit URLs
  * `xq` included in the [yq](https://kislyuk.github.io/yq/) package
    to transcode XML to JSON
  * [jq](https://stedolan.github.io/jq/) to filter JSON data
  * [GnuPG](https://gnupg.org/index.html) to encrypt the configuration
    file

Install each package as needed.  For example:

``` shell
sudo apt install curl
pip install yq
sudo apt install jq
sudo apt install gpg
```

## Usage ##

If the configuration file `~/.config/submit-urls-bing.cfg.gpg` does
not exist, this script will create and encrypt it assuming that the
default key of GnuPG is your OpenPGP key pair.

### Bing Webmaster ###

Prepare an [API
key](https://docs.microsoft.com/en-us/bingwebmaster/getting-access)
for authorization, and replace the values of the following variables
in the configuration file with yours:

  * `SITEMAP`
  * `SITE_URL`
  * `API_KEY`

Then:

``` shell
submit-urls-bing.sh
```

![A screenshot of Windows Terminal where submit-urls-bing.sh was
executed.](https://dl.dropboxusercontent.com/s/z59v9eur56naaa9/20230210T190706.png)

### Options ###

  * `-n` (*dry run*) do not perform a POST request
  * `-s` (*silent*) work silently

## License ##

[MIT](LICENSE.md)

## Link ##

  * [*Bash Scripting to Submit Appropriate URLs through Bing Webmaster
    API*](https://carmine560.blogspot.com/2020/12/bash-scripting-to-submit-urls-through.html):
    a blog post for more details.
