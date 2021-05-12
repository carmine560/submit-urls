#!/bin/bash

## @file
## @brief Submit appropriate URLs through the Yandex.Webmaster API.
## @details Refer to the sitemap and submit the URLs of newer entries
## through the Yandex.Webmaster API.  For more details, see:
## https://github.com/carmine560/submit-urls

. submit-urls-common.sh && suc_parse_parameters "$@" || exit
if [ -z "$curl_silent_options" ]; then
    curl_options=$curl_options' -w \n'
fi
readonly API_SERVICE=https://api.webmaster.yandex.net/v4/user

default_configuration="readonly SITEMAP=https://example.com/sitemap.xml
access_token=ACCESS_TOKEN
readonly USER_ID=USER_ID
readonly HOST_ID=HOST_ID
last_submitted=$(date -u +%FT%TZ)"
. encrypted_configuration.sh initialize || exit

# Retrieve the sitemap and extract newer entries than the last
# submitted entry.
newer_list=$(curl $curl_options "$SITEMAP" |
                 xq |
                 jq ".urlset.url[] | select(.lastmod > \"$last_submitted\")" |
                 jq -s 'sort_by(.lastmod)') || exit
newer_length=$(echo $newer_list | jq length) || exit

# Request the remaining daily quota for URL submission.
daily_quota=$(curl -H "Authorization: OAuth $access_token" \
                   -X GET $curl_options \
                   $API_SERVICE/$USER_ID/hosts/$HOST_ID/recrawl/quota |
                  jq .quota_remainder) || exit

# Add newer entries that you can submit to a URL list.
suc_add_entries || exit
if [ "$silent" != true ]; then
    suc_display_status || exit
fi

# Submit the URL list and store the date of the last submitted entry.
if [ "$dry_run" != true -a ! -z "$url_list" ]; then
    readonly DEFAULT_IFS=$IFS
    IFS=$DELIMITER
    for url in $url_list; do
        if [ "$IFS" != "$DEFAULT_IFS" ]; then
            IFS=$DEFAULT_IFS
        fi
        curl -d "{\"url\": $url}" -H "Authorization: OAuth $access_token" \
             -H 'Content-Type: application/json; charset=utf-8' \
             -X POST $curl_options $curl_silent_options \
             $API_SERVICE/$USER_ID/hosts/$HOST_ID/recrawl/queue || exit
        ec_set_value last_submitted "$lastmod"
    done
fi
