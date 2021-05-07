#!/bin/bash

## @file
## @brief Submit appropriate URLs through the Bing Webmaster API.
## @details Refer to the sitemap and submit the URLs of newer entries
## through the Bing Webmaster API.  See the following post for more
## details:
## https://carmine560.blogspot.com/2020/12/bash-scripting-to-submit-urls-through.html

. submit-urls-common.sh && suc_parse_parameters "$@" || exit
if [ -z "$curl_silent_options" ]; then
    curl_options=$curl_options' -w \n'
fi
readonly API_SERVICE=https://ssl.bing.com/webmaster/api.svc/json

default_configuration="readonly SITEMAP=https://example.com/sitemap.xml
readonly SITE_URL=https://example.com/
readonly API_KEY=API_KEY
last_submitted=$(date -u +%FT%TZ)"
. encrypted_configuration.sh && ec_initialize_configuration || exit

# Retrieve the sitemap and extract newer entries than the last
# submitted entry.
newer_list=$(curl $curl_options "$SITEMAP" |
                 xq |
                 jq ".urlset.url[] | select(.lastmod > \"$last_submitted\")" |
                 jq -s 'sort_by(.lastmod)') || exit
newer_length=$(echo $newer_list | jq length) || exit

# Request the remaining daily quota for URL submission.
read daily_quota monthly_quota \
     <<<$(curl -X GET $curl_options "$API_SERVICE/GetUrlSubmissionQuota?siteUrl=$SITE_URL&apikey=$API_KEY" |
              jq '.d | .DailyQuota, .MonthlyQuota' |
              paste - -) || exit

# Add newer entries that you can submit to a URL list.
suc_add_entries || exit
if [ "$silent" != true ]; then
    suc_display_status || exit
fi

# Submit the URL list and store the date of the last submitted entry.
if [ "$dry_run" != true -a ! -z "$url_list" ]; then
    curl -d "{\"siteUrl\": \"$SITE_URL\", \"urlList\": [${url_list//$DELIMITER/, }]}" \
         -H 'Content-Type: application/json; charset=utf-8' \
         -X POST $curl_options $curl_silent_options \
         $API_SERVICE/SubmitUrlBatch?apikey=$API_KEY || exit
    ec_set_value last_submitted "$lastmod"
fi
