# Pulsebar

A small native macOS menu bar app for **SWPulse DNS**, **TG WS Proxy**, and optional **LAN sharing**. Three independent switches, English UI, and a `0_0` status face with colored eyes.

## Build on your Mac

Requires macOS 14+, Apple Silicon or Intel, Apple's Command Line Tools, and Homebrew Python 3.12 or later. The app is locally signed, not notarized. Intel compilation is supported but has not been tested on Intel hardware.

```sh
xcode-select --install
brew install python
```

Download this repository using **Code → Download ZIP**, extract it, open Terminal in the extracted folder, then run:

```sh
bash "Build and Install.command"
```

The builder fetches the latest stable releases from [AdGuard dnsproxy](https://github.com/AdguardTeam/dnsproxy) and [Flowseal TG WS Proxy](https://github.com/Flowseal/tg-ws-proxy), verifies the dnsproxy release digest, records source archive hashes, compiles the app and installs its services. Internet is required. Enter an administrator password only into the local Terminal prompt for the DNS service.

The app appears in your menu bar. Fresh installs start with the user-facing switches off. DNS and proxy preferences are preserved on updates. The local DNS daemon remains available on loopback even with the DNS switch off; the switch controls whether macOS uses it.

For compilation without installing:

```sh
/opt/homebrew/bin/python3 build.py --build-only
# Intel Homebrew: /usr/local/bin/python3
```

See [the full setup, use and uninstall manual](README.txt).

## Menu

- **SWPulse DNS**: use encrypted DNS; restore previous DNS when switched off.
- **Telegram proxy**: start or stop the local MTProto backend.
- **Share Telegram proxy**: independently allow devices on the physical private IPv4 subnet. Does not start the proxy by itself.
- **Connect Telegram**: connect this Mac, show a LAN QR code, view connection details, or explicitly reveal the access key.
- **Diagnostics**: run checks, repair managed DNS, or wait for a manual VPN disconnect.
- **Settings**: launch at login, credits.

`0_0`: both healthy. Blue left eye: Telegram. Purple right eye: DNS. Red `x`: failed enabled service. `x_x`: no enabled service passed its probe. `-.-`: off. `?_?`: unavailable state.

The app never disconnects the VPN. A green/healthy handshake is not a guarantee of account login, message delivery or every Telegram data center. Fake TLS configurations are not supported by the current health probe.

## Sharing with a friend

A private GitHub repository requires a GitHub account and an explicit collaborator invitation; its URL alone does not grant access. Alternatively, send the clean source ZIP produced by `python3 package.py`. It contains no installed settings or access keys. Each Mac generates its own secret, or locally imports its existing TG WS Proxy configuration.

Do not forward the Application Support folder, QR codes or connection links as part of the source kit. Logs and reports are local but can contain network details. See [security and audit notes](SECURITY.md).

## Development checks

```sh
python3 -m unittest discover -s tests -v
python3 package.py
```

The regression suite uses temporary files and mocks: it does not change DNS, VPN or running services. Build validation additionally requires macOS and Swift.

## Credits

- [SWPulse](https://swpulse.ru/#setup): DNS service and setup information.
- [AdGuard dnsproxy](https://github.com/AdguardTeam/dnsproxy): encrypted DNS client.
- [Flowseal TG WS Proxy](https://github.com/Flowseal/tg-ws-proxy): Telegram transport backend.

This repository contains the integration wrapper. Upstream code is downloaded at build time and retains its own license. No affiliation or endorsement is implied.
