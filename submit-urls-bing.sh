#!/bin/bash

## @file
## @brief Submit appropriate URLs through the Bing Webmaster API.
##
## Refer to the sitemap and submit the URLs of newer entries through
## the Bing Webmaster API.  See the following post for more details:
## https://carmine560.blogspot.com/2020/12/bash-scripting-to-submit-urls-through.html

. submit-urls-common.sh || exit
api_service=https://ssl.bing.com/webmaster/api.svc/json

default_configuration='sitemap=https://example.com/sitemap.xml
site_url=https://example.com/
api_key=API_KEY
last_submitted=$(date -u +%FT%TZ)'
. configuration.sh || exit
cfg_initialize_encryption

suc_parse_parameters "$@"
if [ -z "$curl_silent_options" ]; then
    curl_options=$curl_options' -w \n'
fi

# Retrieve the sitemap and extract newer entries than the last
# submitted entry.
newer_list=$(curl $curl_options "$sitemap" |
                 xq |
                 jq ".urlset.url[] | select(.lastmod > \"$last_submitted\")" |
                 jq -s 'sort_by(.lastmod)') || exit
newer_length=$(echo $newer_list | jq length) || exit

# Request the remaining daily quota for URL submission.
read daily_quota monthly_quota \
     <<<$(curl -X GET $curl_options "$api_service/GetUrlSubmissionQuota?siteUrl=$site_url&apikey=$api_key" |
              jq '.d | .DailyQuota, .MonthlyQuota' |
              paste - -) || exit

# Add newer entries that you can submit to a URL list.
suc_add_entries
if [ "$silent" != true ]; then
    suc_display_status
fi

# Submit the URL list and store the date of the last submitted entry.
if [ "$dry_run" != true -a ! -z "$url_list" ]; then
    curl -d "{\"siteUrl\": \"$site_url\", \"urlList\": [${url_list//$DELIMITER/, }]}" \
         -H 'Content-Type: application/json; charset=utf-8' \
         -X POST $curl_options $curl_silent_options \
         $api_service/SubmitUrlBatch?apikey=$api_key || exit
    cfg_set_encrypted_value last_submitted "$lastmod"
fi
