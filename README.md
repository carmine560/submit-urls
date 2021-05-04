# submit-urls #

<!-- Bash scripts that refer to sitemap and submit URLs through Bing Webmaster or Yandex.Webmaster API -->

Bash scripts that refer to the sitemap and submit the URLs of newer
entries than the last submission through the [Bing Webmaster
API](https://docs.microsoft.com/en-us/bingwebmaster/) or
[Yandex.Webmaster API](https://yandex.com/dev/webmaster/).

## Prerequisites ##

These scripts have been tested on Debian bullseye on WSL 1 and use the
following packages:

  - [curl](https://curl.se/) to retrieve the sitemap and submit URLs
  - xq included in the [yq](https://kislyuk.github.io/yq/) package to
    transcode XML to JSON
  - [jq](https://stedolan.github.io/jq/) to filter JSON data
  - [GnuPG](https://gnupg.org/index.html) to encrypt the configuration
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

If the configuration file `~/.config/SCRIPT_NAME.gpg` does not exist
when the following script is executed, the script will create and
encrypt the file assuming that the default key of GnuPG is your
OpenPGP key pair.

### Bing Webmaster ###

Prepare an API key for authorization, and change the values of the
variables in the configuration file above.  Then:

``` shell
submit-urls-bing.sh
```

### Yandex.Webmaster ###

Prepare an access token, user ID, and site ID for authorization and
calling the API, and change the values of the variables in the
configuration file above.  Then:

``` shell
submit-urls-yandex.sh
```

### Common Options ###

The option `-n` is dry run; the script retrieves the sitemap and shows
newer entries but does not submit them.  The option `-s` is silent;
the script does not show any output but still show an error message
from curl.

## License ##

[MIT](LICENSE)

## Links ##

Blog posts for more details:

  - [Bash Scripting to Submit Appropriate URLs through Bing Webmaster API](https://carmine560.blogspot.com/2020/12/bash-scripting-to-submit-urls-through.html)
  - [Bash Scripting to Submit Appropriate URLs through Yandex.Webmaster API](https://carmine560.blogspot.com/2021/04/bash-scripting-to-submit-appropriate.html)
