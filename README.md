# submit-urls #

Bash scripts that incrementally submit URLs referring to the sitemap
through the Bing Webmaster API or the Yandex.Webmaster API.

## Installation ##

Make sure that Bash can find these scripts in the `PATH`.

### Requirements ###

These scripts use the following packages:

  - [curl](https://curl.se/) to retrieve the sitemap
  - xq included in the [yq](https://kislyuk.github.io/yq/) package to
    transcode XML to JSON
  - [jq](https://stedolan.github.io/jq/) to filter JSON data
  - [GnuPG](https://gnupg.org/index.html) to encrypt the configuration
    file

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
