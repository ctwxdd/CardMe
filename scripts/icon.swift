import AppKit
let output = CommandLine.arguments[1]
let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
let artwork = NSImage(contentsOf: root.appendingPathComponent("website/dist/assets/cardme-mark.png"))!
let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: 1024, pixelsHigh: 1024, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: bitmap)
NSColor(calibratedRed: 1, green: 1, blue: 0.97, alpha: 1).setFill()
NSBezierPath(roundedRect: NSRect(x: 80, y: 80, width: 864, height: 864), xRadius: 192, yRadius: 192).fill()
// Leave breathing room around the mark at Dock size.
artwork.draw(in: NSRect(x: 162, y: 222, width: 700, height: 580))
NSGraphicsContext.restoreGraphicsState()
assert(bitmap.colorAt(x: 0, y: 0)!.alphaComponent == 0)
try bitmap.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: output))
