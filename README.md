# submit-urls #

<!-- Bash scripts that refer to sitemap and submit URLs through Bing Webmaster API -->

<!-- bash bing-api curl gnupg jq yq -->

Bash scripts that refer to the sitemap and submit the URLs of newer
entries than the last submission through the [Bing Webmaster
API](https://docs.microsoft.com/en-us/bingwebmaster/).

## Prerequisites ##

These scripts have been tested for Blogger on Debian bullseye on WSL 1
and use the following packages:

  * [curl](https://curl.se/) to retrieve the sitemap and submit URLs
  * xq included in the [yq](https://kislyuk.github.io/yq/) package to
    transcode XML to JSON
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

## Installation ##

Make sure that Bash can find these scripts in the directories of the
`PATH`.  For example:

``` shell
PATH=$HOME/path/to/submit-urls:$PATH
```

or

``` shell
cp -i *.sh ~/.local/bin
```

## Usage ##

If the configuration file `~/.config/SCRIPT_BASENAME.cfg.gpg` does not
exist, the following scripts will create and encrypt it assuming that
the default key of GnuPG is your OpenPGP key pair.

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

![A screenshot of GNOME Terminal where submit-urls-bing.sh was
executed.](https://dl.dropboxusercontent.com/s/sx3od1rkt5kvd2n/20210508T210815.png)

### Common Options ###

  * `-n` (*dry run*) do not perform a POST request
  * `-s` (*silent*) work silently

## License ##

[MIT](LICENSE.md)

## Links ##

  * [*Bash Scripting to Submit Appropriate URLs through Bing Webmaster
    API*](https://carmine560.blogspot.com/2020/12/bash-scripting-to-submit-urls-through.html):
    a blog post for more details.
