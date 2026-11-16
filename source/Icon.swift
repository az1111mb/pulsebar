import AppKit
let directory = CommandLine.arguments[1]
try FileManager.default.createDirectory(atPath: directory, withIntermediateDirectories: true)
for (name, size) in [("icon_16x16",16),("icon_16x16@2x",32),("icon_32x32",32),("icon_32x32@2x",64),("icon_128x128",128),("icon_128x128@2x",256),("icon_256x256",256),("icon_256x256@2x",512),("icon_512x512",512),("icon_512x512@2x",1024)] {
    let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: size, pixelsHigh: size, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    let transform = NSAffineTransform()
    transform.scale(by: CGFloat(size) / 1024)
    transform.concat()
    let rect = NSRect(x: 64, y: 64, width: 896, height: 896)
    let tile = NSBezierPath(roundedRect: rect, xRadius: 204, yRadius: 204)
    let gradient = NSGradient(starting: NSColor(calibratedRed: 0.05, green: 0.66, blue: 0.68, alpha: 1), ending: NSColor(calibratedRed: 0.03, green: 0.28, blue: 0.37, alpha: 1))!
    gradient.draw(in: tile, angle: -65)
    let face = NSAttributedString(string: "0_0", attributes: [.font: NSFont.monospacedSystemFont(ofSize: 270, weight: .bold), .foregroundColor: NSColor.white])
    let size = face.size()
    face.draw(at: NSPoint(x: (1024-size.width)/2, y: (1024-size.height)/2))
    NSGraphicsContext.restoreGraphicsState()
    try rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: directory + "/" + name + ".png"))
}
