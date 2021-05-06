# submit-urls #

<!-- Bash scripts that refer to sitemap and submit URLs through Bing Webmaster or Yandex.Webmaster API -->

Bash scripts that refer to the sitemap and submit the URLs of newer
entries through the [Bing Webmaster
API](https://docs.microsoft.com/en-us/bingwebmaster/) or
[Yandex.Webmaster API](https://yandex.com/dev/webmaster/).

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

If the configuration file `~/.config/SCRIPT_NAME.gpg` does not exist,
the following script will create and encrypt the file assuming that
the default key of GnuPG is your OpenPGP key pair.

### Bing Webmaster ###

Prepare an [API
key](https://docs.microsoft.com/en-us/bingwebmaster/getting-access)
for authorization, and change the values of the variables in the
configuration file above.  Then:

``` shell
submit-urls-bing.sh
```

![Screenshot of GNOME Terminal where submit-urls-bing.sh was
executed.](https://dl.dropboxusercontent.com/s/uvdfl57t5jkhnc0/20210506T141204.png)

### Yandex.Webmaster ###

Prepare an [access
token](https://yandex.com/dev/oauth/doc/dg/tasks/get-oauth-token.html),
[user
ID](https://yandex.com/dev/webmaster/doc/dg/reference/user.html), and
[host
ID](https://yandex.com/dev/webmaster/doc/dg/reference/hosts.html) for
authorization and using the API, and change the values of the
variables in the configuration file above.  Then:

``` shell
submit-urls-yandex.sh
```

![Screenshot of GNOME Terminal where submit-urls-yandex.sh was
executed.](https://dl.dropboxusercontent.com/s/9970gmvzd9ujd2m/20210504T205404.png)

### Common Options ###

  * `-n`: *dry run*; retrieve the sitemap and show newer entries than
    the last submission but do not submit them.
  * `-s`: *silent*; do not show any output except for an error message
    from curl.

## Known Issue ##

`submit-urls-yandex.sh` repeats a request for each URL because the
[queue
method](https://yandex.com/dev/webmaster/doc/dg/reference/host-recrawl-post.html)
of the API does not seem to support arrays.

## License ##

[MIT](LICENSE)

## Links ##

Blog posts for more details:

  * [Bash Scripting to Submit Appropriate URLs through Bing Webmaster API](https://carmine560.blogspot.com/2020/12/bash-scripting-to-submit-urls-through.html)
  * [Bash Scripting to Submit Appropriate URLs through Yandex.Webmaster API](https://carmine560.blogspot.com/2021/04/bash-scripting-to-submit-appropriate.html)
