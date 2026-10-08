import AppKit

// Shared vector artwork for the frameless in-app and website mark.
let output = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
let teal = NSColor(calibratedRed: 0, green: 0.29, blue: 0.28, alpha: 1).cgColor
let back = CGMutablePath()
back.move(to: CGPoint(x: 80, y: 20)); back.addLine(to: CGPoint(x: 460, y: 20))
back.addCurve(to: CGPoint(x: 510, y: 70), control1: CGPoint(x: 490, y: 20), control2: CGPoint(x: 510, y: 40))
back.addLine(to: CGPoint(x: 510, y: 85)); back.addLine(to: CGPoint(x: 100, y: 85))
back.addCurve(to: CGPoint(x: 70, y: 115), control1: CGPoint(x: 80, y: 85), control2: CGPoint(x: 70, y: 95))
back.addLine(to: CGPoint(x: 70, y: 410))
back.addCurve(to: CGPoint(x: 10, y: 355), control1: CGPoint(x: 30, y: 410), control2: CGPoint(x: 10, y: 395))
back.addLine(to: CGPoint(x: 10, y: 90))
back.addCurve(to: CGPoint(x: 80, y: 20), control1: CGPoint(x: 10, y: 45), control2: CGPoint(x: 35, y: 20)); back.closeSubpath()
let frame = CGMutablePath()
frame.move(to: CGPoint(x: 175, y: 105)); frame.addLine(to: CGPoint(x: 535, y: 105))
frame.addCurve(to: CGPoint(x: 600, y: 170), control1: CGPoint(x: 575, y: 105), control2: CGPoint(x: 600, y: 130))
frame.addLine(to: CGPoint(x: 600, y: 310)); frame.addLine(to: CGPoint(x: 556, y: 310)); frame.addLine(to: CGPoint(x: 556, y: 181))
frame.addCurve(to: CGPoint(x: 524, y: 149), control1: CGPoint(x: 556, y: 160), control2: CGPoint(x: 545, y: 149))
frame.addLine(to: CGPoint(x: 184, y: 149))
frame.addCurve(to: CGPoint(x: 152, y: 181), control1: CGPoint(x: 164, y: 149), control2: CGPoint(x: 152, y: 160))
frame.addLine(to: CGPoint(x: 152, y: 430))
frame.addCurve(to: CGPoint(x: 184, y: 462), control1: CGPoint(x: 152, y: 450), control2: CGPoint(x: 164, y: 462))
frame.addLine(to: CGPoint(x: 473, y: 462)); frame.addLine(to: CGPoint(x: 473, y: 506)); frame.addLine(to: CGPoint(x: 175, y: 506))
frame.addCurve(to: CGPoint(x: 108, y: 440), control1: CGPoint(x: 133, y: 506), control2: CGPoint(x: 108, y: 482))
frame.addLine(to: CGPoint(x: 108, y: 172))
frame.addCurve(to: CGPoint(x: 175, y: 105), control1: CGPoint(x: 108, y: 130), control2: CGPoint(x: 133, y: 105)); frame.closeSubpath()
let arrow = CGMutablePath()
arrow.move(to: CGPoint(x: 218, y: 294))
arrow.addCurve(to: CGPoint(x: 427, y: 227), control1: CGPoint(x: 231, y: 183), control2: CGPoint(x: 352, y: 154))
arrow.addLine(to: CGPoint(x: 441, y: 216))
arrow.addQuadCurve(to: CGPoint(x: 451, y: 220), control: CGPoint(x: 449, y: 210))
arrow.addLine(to: CGPoint(x: 459, y: 283))
arrow.addQuadCurve(to: CGPoint(x: 449, y: 292), control: CGPoint(x: 461, y: 296))
arrow.addLine(to: CGPoint(x: 392, y: 264))
arrow.addQuadCurve(to: CGPoint(x: 389, y: 253), control: CGPoint(x: 380, y: 260))
arrow.addLine(to: CGPoint(x: 402, y: 242))
arrow.addCurve(to: CGPoint(x: 261, y: 301), control1: CGPoint(x: 350, y: 198), control2: CGPoint(x: 275, y: 226))
arrow.closeSubpath()
var rotation = CGAffineTransform(translationX: 340, y: 305).rotated(by: .pi).translatedBy(x: -340, y: -305)
let lower = arrow.copy(using: &rotation)!
let card = CGMutablePath()
card.move(to: CGPoint(x: 518, y: 327)); card.addLine(to: CGPoint(x: 604, y: 327)); card.addLine(to: CGPoint(x: 680, y: 399)); card.addLine(to: CGPoint(x: 680, y: 531))
card.addQuadCurve(to: CGPoint(x: 650, y: 561), control: CGPoint(x: 680, y: 561)); card.addLine(to: CGPoint(x: 520, y: 561))
card.addQuadCurve(to: CGPoint(x: 490, y: 531), control: CGPoint(x: 490, y: 561)); card.addLine(to: CGPoint(x: 490, y: 357))
card.addQuadCurve(to: CGPoint(x: 518, y: 327), control: CGPoint(x: 490, y: 327)); card.closeSubpath()
for x in [524, 562, 600] { card.addRoundedRect(in: CGRect(x: x, y: 363, width: 24, height: 50), cornerWidth: 6, cornerHeight: 6) }
let shapes: [CGPath] = [back, frame, arrow, lower, card]
let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: 700, pixelsHigh: 580, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
let graphics = NSGraphicsContext(bitmapImageRep: bitmap)!
NSGraphicsContext.saveGraphicsState(); NSGraphicsContext.current = graphics
let ctx = graphics.cgContext
ctx.translateBy(x: 0, y: 580); ctx.scaleBy(x: 1, y: -1); ctx.setFillColor(teal)
for path in shapes { ctx.addPath(path); ctx.drawPath(using: .eoFill) }
NSGraphicsContext.restoreGraphicsState()
try bitmap.representation(using: .png, properties: [:])!.write(to: output.appendingPathComponent("cardme-mark.png"))
func svgPath(_ path: CGPath) -> String {
    var d = ""
    path.applyWithBlock { item in
        let e = item.pointee, p = e.points
        func point(_ i: Int) -> String { "\(Int(p[i].x.rounded())) \(Int(p[i].y.rounded()))" }
        switch e.type {
        case .moveToPoint: d += "M\(point(0))"
        case .addLineToPoint: d += "L\(point(0))"
        case .addQuadCurveToPoint: d += "Q\(point(0)) \(point(1))"
        case .addCurveToPoint: d += "C\(point(0)) \(point(1)) \(point(2))"
        case .closeSubpath: d += "Z"
        @unknown default: break
        }
    }
    return d
}
let svg = "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 700 580\" fill=\"#004A47\" fill-rule=\"evenodd\">" + shapes.map { "<path d=\"\(svgPath($0))\"/>" }.joined() + "</svg>\n"
try svg.write(to: output.appendingPathComponent("cardme-mark.svg"), atomically: true, encoding: .utf8)
assert(bitmap.colorAt(x: 0, y: 0)!.alphaComponent == 0)
print("Frameless vector and transparent PNG generated from shared geometry.")
