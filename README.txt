PULSEBAR — MAC MENU BAR APP

This is a locally built menu app with three independent switches:
  SWPulse              encrypted DNS via SWPulse
  TG WS Proxy          Telegram proxy on this Mac
  Share Telegram proxy   allow other LAN devices to use the Telegram proxy

No personal configuration, proxy secrets, user addresses or diagnostic reports
are included in this kit. Each Mac creates its own proxy secret, or imports its
existing standalone TG WS Proxy configuration locally.

REQUIREMENTS

macOS 14 or later; Apple Silicon or Intel; an administrator account for the
initial DNS-service installation; internet access while building.
The included build was tested on Apple Silicon. Intel is supported by the build
script but has not been tested on an Intel Mac.

1. Install Apple's Command Line Tools in Terminal:

   xcode-select --install

   Complete the macOS installation dialog. If the tools are already installed,
   this command will tell you.

2. Install Homebrew from its official site if needed:

   https://brew.sh

3. Install Python:

   brew install python

BUILD AND INSTALL

1. Unzip this kit into a normal local folder.
2. Double-click "Build and Install.command".
   Alternatively, in Terminal open the extracted folder and run:

   bash "Build and Install.command"

3. The builder downloads the latest stable GitHub releases of:

   https://github.com/AdguardTeam/dnsproxy
   https://github.com/Flowseal/tg-ws-proxy

   It checks the dnsproxy archive against the SHA-256 digest published by
   GitHub, downloads the tagged TG WS source, installs its core dependencies
   into a private Python environment, and compiles the menu app locally with
   Apple's Swift compiler. It does not install the separate TG tray app.

4. macOS may ask for the administrator password to install the DNS service.
   Enter it locally in Terminal. Nothing is sent to the kit author.

5. The menu app starts automatically. It is installed at:

   ~/Applications/SWPulse.app

   On a fresh installation services start disabled. Enable what you need in
   the menu. Existing installation settings are preserved during an update.

The downloaded versions and hashes are recorded in:
  ~/Library/Application Support/SWPulse/versions.json

The wrapper comes from this repository. Pull its changes before rebuilding.
Re-running the builder refreshes the two upstream projects.
It uses stable releases, not development branches. If GitHub is unavailable or
its rate limit is exceeded, the build stops rather than silently using an old
release. Keep a working internet connection/VPN available during the build.

USING THE THREE SWITCHES

SWPulse
  Enables the local encrypted DNS client for physical Wi-Fi/Ethernet services.
  Disabling it restores the DNS settings saved before it was enabled.
  DNS recovery reapplies the chosen settings after a VPN disconnects, while
  respecting manually changed DNS settings.

TG WS Proxy
  Starts/stops the background Telegram proxy on this Mac.
  "Connect Telegram > On this Mac" opens its connection link in Telegram.
  Confirm the connection in Telegram. The backend runs without a second tray
  icon. The proxy does not require access to your Telegram account or messages.

Share Telegram proxy
  Stores the LAN-sharing preference independently of the proxy switch.
  It does not start TG WS Proxy automatically.
  When the proxy is running, sharing listens on private IPv4 addresses of
  active physical Wi-Fi/Ethernet interfaces. It does not bind public IPs or
  VPN interfaces. Incoming clients must belong to the matching local subnet.
  Disabling sharing closes its listeners and existing shared connections.

  To connect a phone or another computer:
    - Enable TG WS Proxy and Share Telegram proxy.
    - Join the same local network on the other device.
    - Choose "Connect Telegram > On another device...".
    - Scan the QR code, or copy/open its Telegram proxy link on that device.
    - Confirm the proxy connection in Telegram.

  The Mac must remain awake and connected. Guest Wi-Fi/client isolation or
  firewall rules can prevent LAN access. No router port forwarding is needed.
  If macOS asks about incoming connections, allow the TG backend/Python only
  if you want to use the requested LAN-sharing feature.

CONNECTION DETAILS AND CREDITS

"Connection details..." shows:
  - SWPulse DNS-over-HTTPS endpoint and local DNS address;
  - Telegram host and port (the key is hidden by default);
  - available LAN addresses and current health results.

"Reveal proxy key..." displays the key explicitly. "Copy details" does not
include it. Keys and links copied with their dedicated buttons expire from
the clipboard after 60 seconds if the clipboard is unchanged. The QR code
and Telegram link contain the proxy secret. Share them only with the devices/people you intend to connect.
Do not include generated details, logs or state files when forwarding this kit.

"About & credits" links the SWPulse service, AdGuard dnsproxy and Flowseal
TG WS Proxy projects.

MENU BAR EYES

  0_0   both healthy: normal menu text color (white on a dark menu bar)
  0_0   left eye blue: only Telegram proxy is healthy
  0_0   right eye purple: only SWPulse is healthy
  x_x   enabled services are not responding (red)
  -.-   both services are disabled
  ?_?   status could not be read

If both services are enabled but one fails, the failing eye becomes a red x
while the healthy eye keeps its service color.

Health checks are refreshed approximately every 20 seconds, with bounded
network timeouts. SWPulse is checked using a fresh DNS query and the system's
DNS selection. Telegram is checked with an MTProto handshake; no login,
account credentials or messages are used. A healthy indicator does not certify
that every website, Telegram DC or account feature is available.

The current Telegram health probe supports the default dd-secret mode.
An imported custom Fake TLS configuration is reported as unsupported by the
probe, rather than falsely shown as healthy.

DIAGNOSTICS

"Run diagnostics" checks current routes, DNS and website access.
"Test without VPN..." waits for you to disconnect your VPN manually.
The app never turns your VPN off. You can cancel a pending test from the menu.

Quitting the menu app only hides its icon. Background services retain their
state. Use the individual switches to stop them. "Launch at login" controls
the menu app; enabled background services also resume at login/startup.

TROUBLESHOOTING

Port already in use:
  Quit the standalone TG WS Proxy app before enabling the integrated backend.

No LAN address / another device cannot connect:
  Use a normal private home/office LAN, not guest Wi-Fi. Check client isolation
  and the Mac firewall. Refresh the connection link if the Mac's IP changes.
  This implementation shares over IPv4 and the local subnet only.

SWPulse enabled but DNS overridden:
  A VPN or another DNS product may override it. Use Repair DNS after the VPN
  has disconnected, or wait briefly for DNS recovery. A browser with its own
  secure-DNS setting can also use a different resolver.

After a Homebrew Python upgrade:
  Re-run the build. Each build creates a new private Python environment.

UPDATING

Run "Build and Install.command" again. The builder checks GitHub again and
preserves local settings and the proxy secret. A private rollback snapshot protects user-space files during replacement.
An installation error restores them and attempts to restart previously enabled
services. The privileged DNS installer independently restores its previous
files if its own update fails. This is not a transaction across macOS services;
a successful DNS binary update remains if a later user-space step fails. This is not an unattended updater; review
build errors if an upstream project changes its integration API.

FILES CREATED

  ~/Applications/SWPulse.app
  ~/Library/Application Support/SWPulse/
  ~/Library/LaunchAgents/ru.swpulse.menubar.plist
  ~/Library/LaunchAgents/ru.swpulse.dns-guard.plist
  ~/Library/LaunchAgents/ru.swpulse.telegram.plist  (when TG is enabled)
  /usr/local/libexec/swpulse/dnsproxy
  /Library/LaunchDaemons/ru.swpulse.local-dns.plist

The initial DNS service requires administrator access because it binds port 53.
Daily switching and Telegram LAN sharing run under your macOS account.

UNINSTALLING

First turn off LAN sharing, TG WS Proxy and SWPulse in the menu. Disable
Launch at login, then quit the menu app. In Terminal:

  launchctl bootout gui/$(id -u)/ru.swpulse.dns-guard
  launchctl bootout gui/$(id -u)/ru.swpulse.telegram
  sudo launchctl bootout system/ru.swpulse.local-dns

A "service not found" message means that service is already stopped.
Then move the app, its LaunchAgent files and its Application Support folder to
Trash. Remove the DNS daemon's plist and executable with administrator access.
Do not delete the saved settings before disabling SWPulse, since they are used
to restore your previous DNS.

SOURCES

SWPulse configuration: https://swpulse.ru/#setup
DNS client: https://github.com/AdguardTeam/dnsproxy
Telegram proxy: https://github.com/Flowseal/tg-ws-proxy
Telegram transport: https://core.telegram.org/mtproto/mtproto-transports
