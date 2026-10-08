import AppKit
let output = CommandLine.arguments[1]
let source = URL(fileURLWithPath: #filePath).deletingLastPathComponent().appendingPathComponent("icon-source.png")
let artwork = NSImage(contentsOf: source)!
let image = NSImage(size: NSSize(width: 1024, height: 1024))
image.lockFocus()
artwork.draw(in: NSRect(x: 0, y: 0, width: 1024, height: 1024))
image.unlockFocus()
let data = NSBitmapImageRep(data: image.tiffRepresentation!)!.representation(using: .png, properties: [:])!
try data.write(to: URL(fileURLWithPath: output))
