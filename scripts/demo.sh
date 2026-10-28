#!/usr/bin/env bash
# A short tour of tforge on the configured account (run `tforge setup` first).
# Creates two tickets and a custom field, shows them off, then deletes them again.
# Uses about 20 API requests.
set -euo pipefail

FIELD=demo_priority
refs=()

# Print a command as you would type it, quoting arguments that contain spaces.
echo_cmd() {
    local out=() arg
    for arg in "$@"; do
        [[ $arg == *" "* ]] && arg="\"$arg\""
        out+=("$arg")
    done
    printf '\n\033[1;36m$ %s\033[0m\n' "${out[*]}"
}

run() {
    echo_cmd "$@"
    "$@"
}

# Run a create command, showing its output, and print the new ref (e.g. TF-700).
create() {
    echo_cmd "$@" >&2
    FORCE_COLOR=1 COLUMNS="${COLUMNS:-$(tput cols 2>/dev/null || echo 100)}" "$@" \
        | tee /dev/stderr | grep -oE 'TF-[0-9]+' | head -n1
}

cleanup() {
    printf '\n\033[2m# cleaning up\033[0m\n'
    # Delete the dependent ticket first.
    for ((i = ${#refs[@]} - 1; i >= 0; i--)); do
        tforge delete "${refs[i]}" -y || true
    done
    tforge fields delete "$FIELD" -y >/dev/null 2>&1 || true
}

run tforge status
trap cleanup EXIT

ci=$(create tforge create "Set up CI" -d "Lint and tests on every push")
refs+=("$ci")
release=$(create tforge create "Release v1" -s in_progress --dep "$ci")
refs+=("$release")

run tforge update "$ci" -s review
run tforge show "$release"
run tforge list -n 5
run tforge list -s review
run tforge list -n 2 --json

run tforge fields add "$FIELD"
run tforge update "$ci" -f "$FIELD=high"

printf '\n\033[2m# try the interactive browser yourself: tforge list -i\033[0m\n'
