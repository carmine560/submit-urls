## @file
## @brief Perform intermediate processing of URL submission.

set -o pipefail
curl_options=-fSs
readonly DELIMITER=$'\n'

## @fn suc_parse_parameters()
## @brief Parse the positional parameters.
## @param $options Options.
suc_parse_parameters() {
    while getopts :ns OPT; do
        case $OPT in
            n|+n)
                dry_run=true
                ;;
            s|+s)
                silent=true
                curl_silent_options='-o /dev/null'
                ;;
            *)
                cat <<EOF >&2
Usage: ${0##*/} [+-ns}

  -n    do not perform a POST request
  -s    work silently
EOF
                exit 2
        esac
    done
    shift $((OPTIND - 1))
    OPTIND=1
}

## @fn suc_add_entries()
## @brief Add newer entries that you can submit to a URL list.
suc_add_entries() {
    local index=0
    local loc
    local unsubmitted_loc
    while [ "$index" -lt "$newer_length" ]; do
        if [ "$index" -lt "$daily_quota" ]; then
            loc=$(echo $newer_list | jq .[$index].loc) || exit
            lastmod=$(echo $newer_list | jq -r .[$index].lastmod) || exit
            if [ -z "$url_list" ]; then
                url_list=$loc
            else
                url_list=$url_list$DELIMITER$loc
            fi
        else
            unsubmitted_loc=$(echo $newer_list | jq .[$index].loc) || exit
            if [ -z "$unsubmitted_list" ]; then
                unsubmitted_list=$unsubmitted_loc
            else
                unsubmitted_list=$unsubmitted_list$DELIMITER$unsubmitted_loc
            fi
        fi
        # If the value of the expression is 0, the return status is 1.
        ((++index))
    done
}

## @fn suc_display_status()
## @brief Display the current status.
suc_display_status() {
    local sgr
    local -r POSITIVE=32
    local -r NEGATIVE=31
    local -r GRAYED_OUT=90
    local -r HORIZONTAL='%-22s%s\n'
    local -r VERTICAL='%s\n%s\n'
    if [ "$daily_quota" == 0 ]; then
        sgr=$NEGATIVE
    else
        sgr=$POSITIVE
    fi
    printf "$HORIZONTAL" 'Last submitted entry:' \
           "$(date -d "$last_submitted" -Iseconds) $(echo -e "\e[${GRAYED_OUT}m($last_submitted)\e[0m")"
    printf "$HORIZONTAL" 'Daily quota:' \
           $(echo -e "\e[${sgr}m$daily_quota\e[0m")
    if [ ! -z "$monthly_quota" ]; then
        if [ "$monthly_quota" == 0 ]; then
            sgr=$NEGATIVE
        else
            sgr=$POSITIVE
        fi
        printf "$HORIZONTAL" 'Monthly quota:' \
               $(echo -e "\e[${sgr}m$monthly_quota\e[0m")
    fi
    if [ ! -z "$url_list" ]; then
        if [ "$newer_length" -lt "$daily_quota" ]; then
            local expected_daily_quota=$(($daily_quota - $newer_length))
            sgr=$POSITIVE
        else
            local expected_daily_quota=0
            sgr=$NEGATIVE
        fi
        printf "$HORIZONTAL" 'Newest entry:' \
               "$(date -d "$lastmod" -Iseconds) $(echo -e "\e[${GRAYED_OUT}m($lastmod)\e[0m")"
        printf "$HORIZONTAL" 'Expected daily quota:' \
               $(echo -e "\e[${sgr}m$expected_daily_quota\e[0m")
        printf "$VERTICAL" 'URL list:' \
               "$(echo -e "\e[${POSITIVE}m${url_list//\"/}\e[0m")"
    fi
    if [ ! -z "$unsubmitted_list" ]; then
        printf "$VERTICAL" 'Unsubmitted URL list:' \
               "$(echo -e "\e[${NEGATIVE}m${unsubmitted_list//\"/}\e[0m")"
    fi
}
