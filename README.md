# submit-urls #

Bash scripts that refer to the sitemap and submit the URLs of newer
entries through the [Bing Webmaster
API](https://docs.microsoft.com/en-us/bingwebmaster/) or
[Yandex.Webmaster API](https://yandex.com/dev/webmaster/).

## Installation ##

Make sure that Bash can find these scripts in the `PATH`.

### Requirements ###

These scripts use the following packages:

  - [curl](https://curl.se/) to retrieve the sitemap and submit URLs
  - xq included in the [yq](https://kislyuk.github.io/yq/) package to
    transcode XML to JSON
  - [jq](https://stedolan.github.io/jq/) to filter JSON data
  - [GnuPG](https://gnupg.org/index.html) to encrypt the configuration
    file that contains an API key or access token

Install each package as needed.  For example:

```bash
sudo apt install curl
sudo apt install jq
pip install yq
sudo apt install gpg
```

## Usage ##

Bing:

```bash
submit-urls-bing.sh
```

Yandex:

```bash
submit-urls-yandex.sh
```

## License ##

[MIT](LICENSE)

## Links ##

  - [Bash Scripting to Submit Appropriate URLs through Bing Webmaster API &#8212; carmine blog](https://carmine560.blogspot.com/2020/12/bash-scripting-to-submit-urls-through.html)
  - [Bash Scripting to Submit Appropriate URLs through Yandex.Webmaster API &#8212; carmine blog](https://carmine560.blogspot.com/2021/04/bash-scripting-to-submit-appropriate.html)
