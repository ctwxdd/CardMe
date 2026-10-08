import AppKit

@main
struct WindowSizingCheck {
    @MainActor static func main() {
        _ = NSApplication.shared
        guard let screen = NSScreen.main else { fatalError("A screen is required") }
        let window = NSWindow(contentRect: NSRect(x: 100, y: 100, width: 780, height: 660), styleMask: [.titled, .resizable], backing: .buffered, defer: false, screen: screen)
        let view = ActivityWindowSizing.WindowView()
        window.contentView = view
        func settle() { RunLoop.main.run(until: Date(timeIntervalSinceNow: 0.3)) }
        let original = window.frame
        for _ in 0..<3 {
            view.setExpanded(true); settle()
            assert(window.frame.width == original.width)
            assert(window.frame.height >= original.height)
            assert(window.frame.maxY <= screen.visibleFrame.maxY + 1)
            let expanded = window.frame
            view.setExpanded(true); settle()
            assert(window.frame == expanded) // Repeated layout must not grow the window again.
            view.setExpanded(false); settle()
            assert(abs(window.frame.height - original.height) < 1)
        }
        let tall = screen.visibleFrame
        window.setFrame(tall, display: false)
        view.setExpanded(true); settle()
        view.setExpanded(false); settle()
        assert(abs(window.frame.height - tall.height) < 1) // Clamping must not shrink on collapse.
        print("Activity window expansion, repeated updates and screen-clamped collapse passed.")
    }
}
