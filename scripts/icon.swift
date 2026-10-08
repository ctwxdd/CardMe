import AppKit
let output = CommandLine.arguments[1]
let image = NSImage(size: NSSize(width: 1024, height: 1024))
image.lockFocus()
NSColor(calibratedRed: 0.08, green: 0.30, blue: 0.55, alpha: 1).setFill()
NSBezierPath(roundedRect: NSRect(x: 48, y: 48, width: 928, height: 928), xRadius: 210, yRadius: 210).fill()
let card = NSBezierPath()
card.move(to: NSPoint(x: 294, y: 198)); card.line(to: NSPoint(x: 730, y: 198))
card.line(to: NSPoint(x: 730, y: 826)); card.line(to: NSPoint(x: 430, y: 826))
card.line(to: NSPoint(x: 294, y: 690)); card.close()
NSColor.white.setFill(); card.fill()
NSColor(calibratedRed: 0.10, green: 0.38, blue: 0.64, alpha: 1).setFill()
NSBezierPath(roundedRect: NSRect(x: 342, y: 272, width: 340, height: 290), xRadius: 22, yRadius: 22).fill()
NSColor(calibratedRed: 0.44, green: 0.80, blue: 0.76, alpha: 1).setFill()
let mountain = NSBezierPath()
mountain.move(to: NSPoint(x: 360, y: 304)); mountain.line(to: NSPoint(x: 454, y: 452))
mountain.line(to: NSPoint(x: 522, y: 366)); mountain.line(to: NSPoint(x: 580, y: 430))
mountain.line(to: NSPoint(x: 664, y: 304)); mountain.close(); mountain.fill()
NSColor.white.setFill(); NSBezierPath(ovalIn: NSRect(x: 580, y: 468, width: 44, height: 44)).fill()
NSColor(calibratedRed: 0.90, green: 0.73, blue: 0.34, alpha: 1).setFill()
for x in stride(from: 468, through: 660, by: 64) { NSBezierPath(roundedRect: NSRect(x: x, y: 680, width: 38, height: 100), xRadius: 7, yRadius: 7).fill() }
image.unlockFocus()
let data = NSBitmapImageRep(data: image.tiffRepresentation!)!.representation(using: .png, properties: [:])!
try data.write(to: URL(fileURLWithPath: output))
