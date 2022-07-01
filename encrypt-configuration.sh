## @file
## @brief Read and write the encrypted configuration file.
## @param string \c initialize invokes \c ec_initialize_configuration.

if [ -d "$HOME/.config" ]; then
    readonly CONFIGURATION=$HOME/.config/$(basename "$0" .${0##*.}).cfg
else
    readonly CONFIGURATION=$HOME/.$(basename "$0" .${0##*.}).cfg
fi
readonly GPG_OPTIONS='--default-recipient-self --batch --yes'

## @fn ec_initialize_configuration()
## @brief Execute the existing encrypted configuration file, or create
## it.
ec_initialize_configuration() {
    if [ -f "$CONFIGURATION.gpg" ]; then
        eval "$(gpg -dq "$CONFIGURATION.gpg" || echo exit $?)"
    else
        read -p "$CONFIGURATION.gpg does not exist.  Create it? [Y/n] "
        if [ -z "$REPLY" ] || [[ $REPLY =~ ^[Yy] ]]; then
            cat <<EOF | gpg -e $GPG_OPTIONS -o "$CONFIGURATION.gpg" || exit
$default_configuration
EOF
            exit
        else
            exit
        fi
    fi
}
if [ "$1" == initialize ]; then
    ec_initialize_configuration
fi

## @fn ec_set_value()
## @brief Store the value of a variable in the encrypted
## configuration.
## @details Multiple pairs of parameters are allowed.
## @param $regex A regular expression for a variable.
## @param $replacement A replacement for the value.
ec_set_value() {
    if [ $# != 0 -a $(($# % 2)) == 0 ]; then
        cp "$CONFIGURATION.gpg" "$CONFIGURATION.gpg.bak" || exit
        local index=0
        local parameters=("$@")
        local sed_commands
        while [ "$index" -lt ${#parameters[*]} ]; do
            if [ -z "$sed_commands" ]; then
                sed_commands="s/^(\s*${parameters[index]}=).*$/\1${parameters[++index]//\//\\/}/"
            else
                sed_commands="$sed_commands; s/^(\s*${parameters[index]}=).*$/\1${parameters[++index]//\//\\/}/"
            fi
            ((++index))
        done
        gpg -dq "$CONFIGURATION.gpg.bak" |
            sed -E "$sed_commands" |
            gpg -e $GPG_OPTIONS -o "$CONFIGURATION.gpg" || exit
        rm "$CONFIGURATION.gpg.bak" || exit
    else
        echo Usage: ${FUNCNAME[0]} VARIABLE VALUE [VARIABLE VALUE ...] >&2
        exit 2
    fi
}
