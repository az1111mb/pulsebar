import AppKit
import CoreImage

let support = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/SWPulse")
let python = (try? String(contentsOf: support.appendingPathComponent("python-path.txt"), encoding: .utf8).trimmingCharacters(in: .whitespacesAndNewlines)) ?? "/opt/homebrew/bin/python3"

struct CommandResult { let code: Int32; let text: String }
func command(_ path: String, _ arguments: [String], timeout: Double = 25, started: ((Process) -> Void)? = nil) -> CommandResult {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: path)
    process.arguments = arguments
    let pipe = Pipe()
    process.standardOutput = pipe
    process.standardError = pipe
    do {
        try process.run()
        started?(process)
        DispatchQueue.global().asyncAfter(deadline: .now() + timeout) {
            if process.isRunning { process.terminate() }
        }
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        return CommandResult(code: process.terminationStatus, text: String(decoding: data, as: UTF8.self))
    } catch { return CommandResult(code: -1, text: error.localizedDescription) }
}

struct NetworkState {
    var enabled = false
    var mixed = false
    var effective = false
    var vpn = false
    var known = false
    var guardRunning = false
    var tgRunning = false
    var tgEnabled = false
    var tgSharing = false
    var lan: [String] = []
    var tgKnown = false
    var dnsHealthy = false
    var tgHealthy = false
    var dnsHealthText = "Not checked"
    var tgHealthText = "Not checked"
}

func networkState() -> NetworkState {
    var state = NetworkState()
    let output = command(python, [support.appendingPathComponent("swpulse.py").path, "status"])
    let lines = output.text.split(separator: "\n")
    state.known = output.code == 0 && !lines.isEmpty
    let count = lines.filter { $0.contains("127.0.0.1") }.count
    state.enabled = count > 0
    state.mixed = count > 0 && count != lines.count
    let dns = command("/usr/sbin/scutil", ["--dns"])
    let primary = dns.text.components(separatedBy: "resolver #2").first ?? ""
    state.effective = primary.contains("127.0.0.1")
    let route = command("/sbin/route", ["-n", "get", "45.134.218.34"])
    state.vpn = route.text.contains("interface: utun") || route.text.contains("interface: ppp") || route.text.contains("interface: ipsec")
    state.guardRunning = command("/bin/launchctl", ["print", "gui/\(getuid())/ru.swpulse.dns-guard"]).text.contains("state = running")
    let tg = command(python, [support.appendingPathComponent("tg_control.py").path, "status"])
    if let data = tg.text.data(using: .utf8), let object = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] {
        state.tgKnown = tg.code == 0
        state.tgEnabled = object["enabled"] as? Bool ?? false
        state.tgRunning = object["running"] as? Bool == true && object["listening"] as? Bool == true
        state.tgSharing = object["share"] as? Bool ?? false
        state.lan = object["lan"] as? [String] ?? []
    }
    var args = [support.appendingPathComponent("health.py").path]
    if state.enabled { args.append("--dns") }
    if state.effective { args.append("--effective") }
    if state.tgEnabled { args.append("--tg") }
    let health = command(support.appendingPathComponent("tg-venv/bin/python").path, args, timeout: 22)
    if let data = health.text.data(using: .utf8), let object = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] {
        let dns = object["dns"] as? [String: Any] ?? [:]
        let tg = object["tg"] as? [String: Any] ?? [:]
        state.dnsHealthy = dns["ok"] as? Bool ?? false
        state.tgHealthy = tg["ok"] as? Bool ?? false
        state.dnsHealthText = dns["detail"] as? String ?? "Disabled"
        state.tgHealthText = tg["detail"] as? String ?? "Disabled"
    }
    return state
}

func statusFace(_ state: NetworkState) -> NSAttributedString {
        let font = NSFont.monospacedSystemFont(ofSize: 14, weight: .semibold)
        let face = NSMutableAttributedString(string: "", attributes: [.font: font])
        func append(_ text: String, _ color: NSColor) { face.append(NSAttributedString(string: text, attributes: [.font: font, .foregroundColor: color])) }
        if !state.known || !state.tgKnown {
            append("?_?", .secondaryLabelColor)
        } else if !state.enabled && !state.tgEnabled {
            append("-.-", .labelColor)
        } else if state.dnsHealthy && state.tgHealthy {
            append("0_0", .labelColor)
        } else if !state.dnsHealthy && !state.tgHealthy {
            append("x_x", .systemRed)
        } else {
            append(state.tgEnabled && !state.tgHealthy ? "x" : "0", state.tgHealthy ? .systemBlue : state.tgEnabled ? .systemRed : .labelColor)
            append("_", .labelColor)
            append(state.enabled && !state.dnsHealthy ? "x" : "0", state.dnsHealthy ? .systemPurple : state.enabled ? .systemRed : .labelColor)
        }
        return face
}

final class ServiceRow: NSView {
    let subtitle = NSTextField(labelWithString: "Checking…")
    let control = NSSwitch()
    init(_ title: String, target: AnyObject, action: Selector) {
        super.init(frame: NSRect(x: 0, y: 0, width: 310, height: 56))
        let label = NSTextField(labelWithString: title)
        label.font = .systemFont(ofSize: 13, weight: .semibold)
        label.frame = NSRect(x: 18, y: 29, width: 235, height: 19)
        subtitle.font = .systemFont(ofSize: 11)
        subtitle.textColor = .secondaryLabelColor
        subtitle.lineBreakMode = .byTruncatingTail
        subtitle.frame = NSRect(x: 18, y: 9, width: 240, height: 17)
        control.frame = NSRect(x: 264, y: 17, width: 38, height: 24)
        control.target = target; control.action = action
        control.setAccessibilityLabel(title)
        addSubview(label); addSubview(subtitle); addSubview(control)
    }
    required init?(coder: NSCoder) { fatalError("Not supported") }
    func update(on: Bool, enabled: Bool, text: String, color: NSColor = .secondaryLabelColor) {
        control.state = on ? .on : .off
        control.isEnabled = enabled
        subtitle.stringValue = text
        subtitle.textColor = color
        control.setAccessibilityValue(on ? "On" : "Off")
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate, NSMenuDelegate, NSWindowDelegate {
    var item: NSStatusItem!
    let menu = NSMenu()
    var state = NetworkState()
    var busy = false
    var refreshing = false
    var timer: Timer?
    var generation = 0
    var dnsRow: ServiceRow!
    var proxyRow: ServiceRow!
    var lanRow: ServiceRow!
    let connectionMenu = NSMenu()
    let toolsMenu = NSMenu()
    let settingsMenu = NSMenu()
    var destination: NSMenu?
    var vpnLine = NSMenuItem()
    var guardLine = NSMenuItem()
    var toggleItem = NSMenuItem()
    var checkItem = NSMenuItem()
    var directItem = NSMenuItem()
    var refreshItem = NSMenuItem()
    var startupItem = NSMenuItem()
    var cancelItem = NSMenuItem()
    var checkProcess: Process?
    var cancelled = false
    var tgItem = NSMenuItem()
    var sharingItem = NSMenuItem()
    var connectTGItem = NSMenuItem()
    var shareTGItem = NSMenuItem()
    var sharingWindow: NSWindow?
    var sharingLink = ""
    var window: NSWindow?
    var resultView: NSTextView?
    var lastText = ""
    let startupURL = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/LaunchAgents/ru.swpulse.menubar.plist")

    func applicationDidFinishLaunching(_ notification: Notification) {
        let others = NSRunningApplication.runningApplications(withBundleIdentifier: "ru.swpulse.menubar").filter { $0.processIdentifier != ProcessInfo.processInfo.processIdentifier }
        if !others.isEmpty { NSApp.terminate(nil); return }
        NSApp.setActivationPolicy(.accessory)
        item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item.button?.image = nil
        item.button?.title = "-.-"
        item.button?.font = .monospacedSystemFont(ofSize: 14, weight: .semibold)
        menu.delegate = self
        menu.autoenablesItems = false
        let header = NSMenuItem()
        let headerView = NSView(frame: NSRect(x: 0, y: 0, width: 310, height: 42))
        let name = NSTextField(labelWithString: "Pulsebar")
        name.font = .systemFont(ofSize: 15, weight: .bold)
        name.frame = NSRect(x: 18, y: 12, width: 170, height: 22)
        headerView.addSubview(name); header.view = headerView; menu.addItem(header)
        toggleItem = add("SWPulse", #selector(toggle))
        dnsRow = ServiceRow("SWPulse DNS", target: self, action: #selector(toggle)); toggleItem.view = dnsRow
        tgItem = add("TG WS Proxy", #selector(toggleTG))
        proxyRow = ServiceRow("Telegram proxy", target: self, action: #selector(toggleTG)); tgItem.view = proxyRow
        sharingItem = add("Share Telegram proxy", #selector(toggleSharing))
        lanRow = ServiceRow("Share Telegram proxy", target: self, action: #selector(toggleSharing)); sharingItem.view = lanRow
        menu.addItem(.separator())
        let connections = add("Connect Telegram")
        connections.submenu = connectionMenu; connections.isEnabled = true
        destination = connectionMenu
        connectTGItem = add("On this Mac", #selector(connectTG))
        shareTGItem = add("On another device…", #selector(shareTG))
        add("Connection details…", #selector(connectionDetails))
        add("Reveal proxy key…", #selector(revealSecret))
        destination = nil
        let diagnostics = add("Diagnostics")
        diagnostics.submenu = toolsMenu; diagnostics.isEnabled = true
        destination = toolsMenu
        vpnLine = add("Checking route…")
        guardLine = add("Checking DNS recovery…")
        toolsMenu.addItem(.separator())
        refreshItem = add("Repair DNS", #selector(repair))
        checkItem = add("Run diagnostics", #selector(checkNow))
        directItem = add("Test without VPN…", #selector(checkDirect))
        cancelItem = add("Cancel test", #selector(cancelCheck))
        add("Last test result", #selector(showLast))
        destination = nil
        let preferences = add("Settings")
        preferences.submenu = settingsMenu; preferences.isEnabled = true
        destination = settingsMenu
        startupItem = add("Launch at login", #selector(toggleStartup))
        add("About & credits", #selector(about))
        destination = nil
        menu.addItem(.separator())
        add("Quit Pulsebar", #selector(quit), key: "q")
        item.menu = menu
        updateMenu()
        refreshState()
        timer = Timer.scheduledTimer(withTimeInterval: 8, repeats: true) { [weak self] _ in self?.refreshState() }

    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        show("Pulsebar", "Open Menu for the three service switches, connection options and diagnostics.\n\nQuitting Pulsebar leaves background services in their current state.")
        return true
    }

    @discardableResult func add(_ title: String, _ action: Selector? = nil, key: String = "") -> NSMenuItem {
        let entry = NSMenuItem(title: title, action: action, keyEquivalent: key)
        entry.target = self
        entry.isEnabled = action != nil
        (destination ?? menu).addItem(entry)
        return entry
    }
    func menuWillOpen(_ menu: NSMenu) { updateMenu(); refreshState() }
    func refreshState() {
        guard !refreshing && !busy else { return }
        refreshing = true
        let requestedGeneration = generation
        DispatchQueue.global(qos: .utility).async {
            let fresh = networkState()
            DispatchQueue.main.async {
                self.refreshing = false
                guard requestedGeneration == self.generation else { self.refreshState(); return }
                self.state = fresh
                self.updateMenu()
            }
        }
    }
    func updateMenu() {
        let title = !state.known ? "Status unavailable" : state.mixed ? "Partially enabled" : state.enabled ? "Enabled" : "Disabled"
        vpnLine.title = state.vpn ? "VPN connected" : "Direct route to SWPulse"
        guardLine.title = state.guardRunning ? "DNS recovery after VPN is active" : "DNS recovery is not running"
        toggleItem.title = "SWPulse"
        toggleItem.state = state.enabled ? .on : .off
        tgItem.state = state.tgEnabled ? .on : .off
        sharingItem.state = state.tgSharing ? .on : .off
        tgItem.isEnabled = !busy && state.tgKnown
        sharingItem.isEnabled = !busy && state.tgKnown
        connectTGItem.isEnabled = !busy && state.tgRunning
        shareTGItem.isEnabled = !busy && state.tgRunning && state.tgSharing && !state.lan.isEmpty
        for entry in [toggleItem, refreshItem, checkItem, directItem] { entry.isEnabled = !busy && state.known }
        startupItem.state = FileManager.default.fileExists(atPath: startupURL.path) ? .on : .off
        cancelItem.isHidden = checkProcess == nil
        dnsRow.update(on: state.enabled, enabled: !busy && state.known,
                      text: busy ? "Updating…" : !state.known ? "Status unavailable" : state.mixed ? "Enabled on some networks" : state.enabled ? (state.dnsHealthy ? "Connected · encrypted DNS" : "Not responding") : "Off",
                      color: state.enabled ? (state.dnsHealthy ? .systemPurple : .systemRed) : .secondaryLabelColor)
        proxyRow.update(on: state.tgEnabled, enabled: !busy && state.tgKnown,
                        text: busy ? "Updating…" : !state.tgKnown ? "Status unavailable" : state.tgEnabled ? (state.tgHealthy ? "Connected · MTProto" : "Not responding") : "Off",
                        color: state.tgEnabled ? (state.tgHealthy ? .systemBlue : .systemRed) : .secondaryLabelColor)
        lanRow.update(on: state.tgSharing, enabled: !busy && state.tgKnown,
                      text: !state.tgSharing ? "Off · no access from other devices" : !state.tgRunning ? "Turn on Telegram proxy to share" : state.lan.isEmpty ? "Waiting for a private network" : "On · devices on your Wi-Fi / LAN")
        let face = statusFace(state)
        // Render individual glyph colors; template/tinted menu-bar titles can recolor the entire face.
        let image = NSImage(size: NSSize(width: 32, height: 20), flipped: false) { rect in
            let size = face.size()
            face.draw(at: NSPoint(x: (rect.width - size.width) / 2, y: (rect.height - size.height) / 2))
            return true
        }
        image.isTemplate = false
        item.button?.title = ""
        item.button?.image = image
        item.button?.setAccessibilityLabel("Pulsebar " + face.string)
        item.button?.toolTip = "SWPulse: \(title) · TG WS Proxy: \(state.tgRunning ? "enabled" : "disabled")"
    }
    @objc func toggle() { perform(state.enabled ? "off" : "on") }
    @objc func repair() { perform("refresh") }
    @objc func toggleTG() { tgAction(state.tgEnabled ? "off" : "on") }
    @objc func toggleSharing() { tgAction(state.tgSharing ? "share-off" : "share-on") }
    func tgAction(_ action: String) {
        guard !busy else { return }
        busy = true; generation += 1; updateMenu()
        DispatchQueue.global(qos: .userInitiated).async {
            let result = command(python, [support.appendingPathComponent("tg_control.py").path, action], timeout: 50)
            let fresh = networkState()
            DispatchQueue.main.async {
                self.busy = false; self.state = fresh; self.updateMenu()
                if result.code != 0 { self.show("TG WS Proxy", result.text) }
            }
        }
    }
    @objc func connectTG() { getTGLink(lan: false) }
    @objc func shareTG() { getTGLink(lan: true) }
    func getTGLink(lan: Bool) {
        DispatchQueue.global(qos: .utility).async {
            let result = command(python, [support.appendingPathComponent("tg_control.py").path, lan ? "link-lan" : "link-local"])
            let link = result.text.trimmingCharacters(in: .whitespacesAndNewlines)
            DispatchQueue.main.async {
                guard result.code == 0, let url = URL(string: link), url.scheme == "tg" else { self.show("Telegram connection", result.text); return }
                if lan { self.showSharing(link) } else { NSWorkspace.shared.open(url) }
            }
        }
    }
    func showSharing(_ link: String) {
        sharingWindow?.close()
        sharingLink = link
        let w = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 440, height: 450), styleMask: [.titled, .closable], backing: .buffered, defer: false)
        w.title = "Telegram on another device"
        w.delegate = self
        w.isReleasedWhenClosed = false
        w.center()
        let label = NSTextField(wrappingLabelWithString: "Join the same Wi-Fi or Ethernet network. Scan this QR code or open the link in Telegram.")
        label.frame = NSRect(x: 25, y: 365, width: 390, height: 62)
        w.contentView?.addSubview(label)
        let qrView = NSImageView(frame: NSRect(x: 95, y: 95, width: 250, height: 250))
        if let filter = CIFilter(name: "CIQRCodeGenerator") {
            filter.setValue(Data(link.utf8), forKey: "inputMessage")
            filter.setValue("M", forKey: "inputCorrectionLevel")
            if let output = filter.outputImage {
                let scaled = output.transformed(by: CGAffineTransform(scaleX: 8, y: 8))
                if let cg = CIContext().createCGImage(scaled, from: scaled.extent) { qrView.image = NSImage(cgImage: cg, size: NSSize(width: 250, height: 250)) }
            }
        }
        w.contentView?.addSubview(qrView)
        let note = NSTextField(labelWithString: "The link includes your proxy access key.")
        note.textColor = .secondaryLabelColor
        note.font = .systemFont(ofSize: 11)
        note.frame = NSRect(x: 30, y: 66, width: 390, height: 20)
        w.contentView?.addSubview(note)
        let copy = NSButton(title: "Copy link", target: self, action: #selector(copyTGLink))
        copy.bezelStyle = .rounded
        copy.frame = NSRect(x: 120, y: 22, width: 200, height: 32)
        w.contentView?.addSubview(copy)
        sharingWindow = w
        NSApp.activate(ignoringOtherApps: true)
        w.makeKeyAndOrderFront(nil)
    }
    func copyPrivate(_ value: String) {
        let board = NSPasteboard.general
        board.clearContents(); board.setString(value, forType: .string)
        let revision = board.changeCount
        DispatchQueue.main.asyncAfter(deadline: .now() + 60) {
            if board.changeCount == revision { board.clearContents() }
        }
    }
    @objc func copyTGLink() { copyPrivate(sharingLink) }
    @objc func revealSecret() {
        guard let data = try? Data(contentsOf: support.appendingPathComponent("tg-config.json")),
              let config = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
              let secret = config["secret"] as? String else { return }
        var key = "dd" + secret
        if let domain = config["fake_tls_domain"] as? String, !domain.isEmpty {
            key = "ee" + secret + domain.utf8.map { String(format: "%02x", $0) }.joined()
        }
        let alert = NSAlert()
        alert.messageText = "Proxy access key"
        alert.informativeText = key + "\n\nKeep this key private. Copied keys are cleared after 60 seconds if the clipboard is unchanged."
        alert.addButton(withTitle: "Close")
        alert.addButton(withTitle: "Copy key")
        NSApp.activate(ignoringOtherApps: true)
        if alert.runModal() == .alertSecondButtonReturn { copyPrivate(key) }
    }
    func windowWillClose(_ notification: Notification) {
        if notification.object as? NSWindow === sharingWindow {
            sharingLink = ""; sharingWindow?.contentView?.subviews.forEach { $0.removeFromSuperview() }
        }
    }

    @objc func connectionDetails() {
        guard let data = try? Data(contentsOf: support.appendingPathComponent("tg-config.json")), let config = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any], config["secret"] is String else {
            show("Connection details", "Telegram proxy settings are not available yet."); return
        }
        let port = config["port"] as? Int ?? 1443
        let addresses = state.lan.isEmpty ? "Enable TG WS Proxy and LAN sharing to see addresses." : state.lan.joined(separator: ", ")
        show("Connection details", "SWPulse\nDNS-over-HTTPS: https://dns.swpulse.ru/dns-query\nBootstrap IP: 45.134.218.34\nLocal DNS: 127.0.0.1:53\nStatus: \(state.dnsHealthText)\n\nTelegram · MTProto\nThis Mac: 127.0.0.1\nPort: \(port)\nSecret: hidden · use Reveal proxy key\nLAN: \(addresses)\nStatus: \(state.tgHealthText)\n\nKeep the proxy secret private. Your other devices use a LAN address, not 127.0.0.1.")
    }
    func perform(_ action: String) {
        guard !busy else { return }
        busy = true; generation += 1; updateMenu()
        DispatchQueue.global(qos: .userInitiated).async {
            let result = command(python, [support.appendingPathComponent("swpulse.py").path, action], timeout: 90)
            let fresh = networkState()
            DispatchQueue.main.async {
                self.busy = false; self.state = fresh; self.updateMenu()
                if result.code != 0 { self.show("Could not change DNS", result.text) }
            }
        }
    }
    @objc func checkNow() { check(direct: false) }
    @objc func checkDirect() { check(direct: true) }
    func check(direct: Bool) {
        guard !busy else { return }
        cancelled = false
        busy = true; generation += 1; updateMenu()
        show(direct ? "Test without VPN" : "Connection test", direct ? "Disconnect your VPN when ready.\n\nThe test waits up to 5 minutes and runs locally even if this chat loses connectivity. This app never disconnects your VPN." : "Checking DNS, SWPulse and ChatGPT connectivity…\n\nThis usually takes up to a minute. Your VPN stays as it is.")
        DispatchQueue.global(qos: .utility).async {
            var args = [support.appendingPathComponent("network_check.py").path]
            if direct { args.append("--wait-no-vpn") }
            let result = command(python, args, timeout: direct ? 420 : 110) { process in
                DispatchQueue.main.async { self.checkProcess = process; self.updateMenu() }
            }
            let text = result.code == 0 ? self.reportText() : result.text
            DispatchQueue.main.async {
                self.checkProcess = nil
                self.busy = false; self.updateMenu(); self.refreshState()
                self.show(self.cancelled ? "Test cancelled" : result.code == 0 ? "Test result" : "Test incomplete", self.cancelled ? "The test was cancelled. DNS and VPN settings were not changed." : text)
            }
        }
    }
    @objc func cancelCheck() {
        cancelled = true
        checkProcess?.terminate()
    }
    func reportText() -> String {
        let url = support.appendingPathComponent("reports/latest.json")
        guard let data = try? Data(contentsOf: url), let report = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any], let results = report["results"] as? [String: Any] else { return "No saved result yet. Choose Run diagnostics." }
        let via = (results["swpulse_system_check"] as? [String: Any])?["via"] as? Bool
        var lines = ["Test: \(report["time"] as? String ?? "")", "", via == true ? "✓ SWPulse received the system DNS request." : "SWPulse did not confirm the system DNS request."]
        for (key, name) in [("https_example.com", "Internet"), ("https_chatgpt.com", "ChatGPT website"), ("https_api.openai.com", "OpenAI API")] {
            let entry = results[key] as? [String: Any] ?? [:]
            let text = entry["text"] as? String ?? "No result"
            let code = text.components(separatedBy: "HTTP=").dropFirst().first?.prefix(3) ?? "—"
            if entry["exit"] as? Int == 0 && (code.hasPrefix("2") || code.hasPrefix("3")) { lines.append("✓ \(name): reachable.") }
            else if code == "000" || code == "—" { lines.append("✕ \(name): connection failed.") }
            else { lines.append("\(name): server returned HTTP \(code); service availability is not confirmed.") }
        }
        lines.append("\n" + (report["summary"] as? String ?? ""))
        lines.append("\nWebsite connectivity does not verify account login or sending messages.")
        return lines.joined(separator: "\n")
    }
    @objc func showLast() { show("Last test", reportText()) }
    func show(_ title: String, _ text: String) {
        if window == nil {
            let w = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 560, height: 380), styleMask: [.titled, .closable, .resizable, .miniaturizable], backing: .buffered, defer: false)
            w.isReleasedWhenClosed = false
            w.minSize = NSSize(width: 460, height: 300)
            w.center()
            let scroll = NSScrollView(frame: NSRect(x: 22, y: 62, width: 516, height: 296))
            scroll.autoresizingMask = [.width, .height]
            scroll.hasVerticalScroller = true
            scroll.drawsBackground = false
            let textView = NSTextView(frame: scroll.bounds)
            textView.isEditable = false
            textView.isSelectable = true
            textView.drawsBackground = false
            textView.font = .systemFont(ofSize: 14)
            textView.textColor = .labelColor
            textView.textContainerInset = NSSize(width: 0, height: 8)
            textView.autoresizingMask = [.width]
            textView.textContainer?.widthTracksTextView = true
            scroll.documentView = textView
            w.contentView?.addSubview(scroll)
            let copy = NSButton(title: "Copy details", target: self, action: #selector(copyResult))
            copy.bezelStyle = .rounded
            copy.frame = NSRect(x: 22, y: 18, width: 195, height: 30)
            w.contentView?.addSubview(copy)
            let controls = NSButton(title: "Menu", target: self, action: #selector(openControlMenu))
            controls.bezelStyle = .rounded
            controls.frame = NSRect(x: 244, y: 18, width: 90, height: 30)
            w.contentView?.addSubview(controls)
            let close = NSButton(title: "Close", target: self, action: #selector(closeResult))
            close.bezelStyle = .rounded
            close.frame = NSRect(x: 438, y: 18, width: 100, height: 30)
            close.autoresizingMask = [.minXMargin]
            close.keyEquivalent = "\r"
            w.contentView?.addSubview(close)
            window = w; resultView = textView
        }
        lastText = text
        window?.title = title
        resultView?.string = text
        NSApp.activate(ignoringOtherApps: true)
        window?.makeKeyAndOrderFront(nil)
    }
    @objc func copyResult() { NSPasteboard.general.clearContents(); NSPasteboard.general.setString(lastText, forType: .string) }
    @objc func closeResult() { window?.close() }
    @objc func openControlMenu() { window?.orderOut(nil); item.button?.performClick(nil) }
    @objc func toggleStartup() {
        do {
            if FileManager.default.fileExists(atPath: startupURL.path) {
                try FileManager.default.removeItem(at: startupURL)
            } else {
                let plist: [String: Any] = ["Label": "ru.swpulse.menubar", "ProgramArguments": ["/usr/bin/open", "-g", Bundle.main.bundlePath], "RunAtLoad": true]
                let data = try PropertyListSerialization.data(fromPropertyList: plist, format: .xml, options: 0)
                try FileManager.default.createDirectory(at: startupURL.deletingLastPathComponent(), withIntermediateDirectories: true)
                try data.write(to: startupURL, options: .atomic)
            }
            updateMenu()
        } catch { show("Launch at login", error.localizedDescription) }
    }
    @objc func about() { show("About & credits", "Pulsebar · 2.2\n\nLocally built menu bar app.\n\nDNS service: SWPulse\nhttps://swpulse.ru\n\nDNS client: AdGuard dnsproxy\nhttps://github.com/AdguardTeam/dnsproxy\n\nTelegram proxy: Flowseal TG WS Proxy\nhttps://github.com/Flowseal/tg-ws-proxy\n\nHealth checks verify a fresh DNS reply and a Telegram protocol handshake. They do not verify account login, messages or every website.\n\nQuitting hides the menu icon. Background services retain their state; disable their switches to stop using them.") }
    @objc func quit() {
        if busy { show("Operation in progress", "Wait for the operation to finish or cancel the test, then quit."); return }
        NSApp.terminate(nil)
    }
}

if CommandLine.arguments.contains("--check-icons") {
    var state = NetworkState()
    state.known = true; state.tgKnown = true
    assert(statusFace(state).string == "-.-")
    state.tgEnabled = true; state.tgHealthy = true
    let proxy = statusFace(state)
    assert(proxy.attribute(.foregroundColor, at: 0, effectiveRange: nil) as? NSColor == .systemBlue)
    assert(proxy.attribute(.foregroundColor, at: 2, effectiveRange: nil) as? NSColor == .labelColor)
    state.tgEnabled = false; state.tgHealthy = false; state.enabled = true; state.dnsHealthy = true
    let dns = statusFace(state)
    assert(dns.attribute(.foregroundColor, at: 0, effectiveRange: nil) as? NSColor == .labelColor)
    assert(dns.attribute(.foregroundColor, at: 2, effectiveRange: nil) as? NSColor == .systemPurple)
    state.tgEnabled = true; state.tgHealthy = true
    let both = statusFace(state)
    assert(both.attribute(.foregroundColor, at: 0, effectiveRange: nil) as? NSColor == .labelColor)
    assert(both.attribute(.foregroundColor, at: 2, effectiveRange: nil) as? NSColor == .labelColor)
    state.tgHealthy = false; state.dnsHealthy = false
    assert(statusFace(state).string == "x_x")
    print("PASS: off, proxy left eye, DNS right eye, both normal, failure")
    exit(0)
}
if CommandLine.arguments.contains("--self-check") {
    let s = networkState()
    print("known=\(s.known) enabled=\(s.enabled) effective=\(s.effective) vpn=\(s.vpn) guard=\(s.guardRunning) tg=\(s.tgRunning) share=\(s.tgSharing)")
    exit(s.known ? 0 : 1)
}
let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
