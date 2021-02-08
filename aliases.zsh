#!/opt/local/bin/zsh


alias ym='yabai -m'
alias yc='yabai -m config'
alias yr='yabai -m rule --add'
alias ys='yabai -m signal --add'

function yq() {
    local domain=$1
    shift
    ym query --$domain $@ 2> /dev/null
}

function yqs() {
    yq $@ > /dev/null
} 

function ywids() {
    yq windows | jq ".[] | select(.app == \"$1\").id"
}

function ywspace() {
    for wid in `ywids $1`; do
        ym window $wid --space $2
    done
}
