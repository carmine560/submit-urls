#!/bin/bash

## @file
## @brief Submit appropriate URLs through the Yandex.Webmaster API.
##
## Refer to the sitemap and submit the URLs of newer entries through
## the Yandex.Webmaster API.  See the following post for more details:
## https://carmine560.blogspot.com/2021/04/bash-scripting-to-submit-appropriate.html

. submit-urls-common.sh && suc_parse_parameters "$@" || exit
if [ -z "$curl_silent_options" ]; then
    curl_options=$curl_options' -w \n'
fi
readonly API_SERVICE=https://api.webmaster.yandex.net/v4/user

default_configuration="sitemap=https://example.com/sitemap.xml
access_token=ACCESS_TOKEN
user_id=USER_ID
host_id=HOST_ID
last_submitted=$(date -u +%FT%TZ)"
. configuration.sh && cfg_initialize_encryption || exit

# Retrieve the sitemap and extract newer entries than the last
# submitted entry.
newer_list=$(curl $curl_options "$sitemap" |
                 xq |
                 jq ".urlset.url[] | select(.lastmod > \"$last_submitted\")" |
                 jq -s 'sort_by(.lastmod)') || exit
newer_length=$(echo $newer_list | jq length) || exit

# Request the remaining daily quota for URL submission.
daily_quota=$(curl -H "Authorization: OAuth $access_token" \
                   -X GET $curl_options \
                   $API_SERVICE/$user_id/hosts/$host_id/recrawl/quota |
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
             $API_SERVICE/$user_id/hosts/$host_id/recrawl/queue || exit
    done
    cfg_set_encrypted_value last_submitted "$lastmod"
fi
