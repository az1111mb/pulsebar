#!/bin/bash
set -euo pipefail
[[ $EUID -eq 0 && $# -eq 2 ]] || { echo 'Use the builder to install the DNS service'; exit 1; }
[[ -f "$1" && -x "$1" && -f "$2" ]] || { echo 'Missing DNS binary or service definition'; exit 1; }
/usr/bin/plutil -lint "$2" >/dev/null
"$1" --version >/dev/null
umask 077
stage=$(/usr/bin/mktemp -d /private/tmp/pulsebar-dns.XXXXXXXX)
binary=/usr/local/libexec/swpulse/dnsproxy
plist=/Library/LaunchDaemons/ru.swpulse.local-dns.plist
active=0
changed=0
/bin/launchctl print system/ru.swpulse.local-dns >/dev/null 2>&1 && active=1
[[ ! -f "$binary" ]] || /bin/cp "$binary" "$stage/old-binary"
[[ ! -f "$plist" ]] || /bin/cp "$plist" "$stage/old-plist"
/usr/bin/install -m 755 "$1" "$stage/new-binary"
/usr/bin/install -m 644 "$2" "$stage/new-plist"
cleanup() {
  result=$?
  trap - EXIT
  if [[ $result -ne 0 && $changed -eq 1 ]]; then
    /bin/launchctl bootout system/ru.swpulse.local-dns >/dev/null 2>&1 || true
    if [[ -f "$stage/old-binary" ]]; then /usr/bin/install -o root -g wheel -m 755 "$stage/old-binary" "$binary"; else /bin/rm -f "$binary"; fi
    if [[ -f "$stage/old-plist" ]]; then /usr/bin/install -o root -g wheel -m 644 "$stage/old-plist" "$plist"; else /bin/rm -f "$plist"; fi
    if [[ $active -eq 1 ]]; then /bin/launchctl bootstrap system "$plist" || true; fi
    echo 'DNS update failed; previous DNS files restored.' >&2
  fi
  /bin/rm -rf "$stage"
  exit "$result"
}
trap cleanup EXIT
[[ $active -eq 0 ]] || /bin/launchctl bootout system/ru.swpulse.local-dns
changed=1
/usr/bin/install -d -o root -g wheel -m 755 /usr/local/libexec/swpulse
/usr/bin/install -o root -g wheel -m 755 "$stage/new-binary" "$binary"
/usr/bin/install -o root -g wheel -m 644 "$stage/new-plist" "$plist"
/bin/launchctl bootstrap system "$plist"
