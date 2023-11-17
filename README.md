# submit-urls #

<!-- Bash script that refers to sitemap and submits URLs through Bing Webmaster
API -->

The `submit-urls-bing.sh` Bash script refers to the sitemap and submits the
URLs of newer entries than the last submission through the [Bing Webmaster
API](https://docs.microsoft.com/en-us/bingwebmaster/).

## Prerequisites ##

`submit-urls-bing.sh` has been tested for Blogger on Debian on WSL and uses the
following packages:

  * [curl](https://curl.se/) to retrieve the sitemap and submit URLs
  * `xq` included in the [`yq`](https://kislyuk.github.io/yq/) package to
    transcode XML to JSON
  * [jq](https://jqlang.github.io/jq/) to filter JSON data
  * [GnuPG](https://gnupg.org/index.html) to encrypt the configuration file

Install each package as needed.  For example:

``` shell
sudo apt install curl
python -m pip install yq -U
sudo apt install jq
sudo apt install gpg
```

## Usage ##

`submit-urls-bing.sh` will create and encrypt a
`~/.config/submit-urls-bing.cfg.gpg` configuration file if it does not exist.
It assumes that the default key of GnuPG is your OpenPGP key pair.

### Bing Webmaster ###

Prepare an [API
key](https://docs.microsoft.com/en-us/bingwebmaster/getting-access) for
authorization, and replace the values of the following variables in the
configuration file with yours:

  * `SITEMAP`
  * `SITE_URL`
  * `API_KEY`

Then:

``` shell
submit-urls-bing.sh
```

### Options ###

  * `-n`: do not perform a POST request
  * `-s`: work silently

## License ##

[MIT](LICENSE.md)

## Link ##

  * [*Bash Scripting to Submit Appropriate URLs through Bing Webmaster
    API*](https://carmine560.blogspot.com/2020/12/bash-scripting-to-submit-urls-through.html):
    a blog post for more details
