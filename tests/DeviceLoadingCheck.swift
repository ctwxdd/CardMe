import Foundation
import AppKit

@main
struct DeviceLoadingCheck {
    static func main() {
        let devices = CardDevices()
        assert(devices.loading || devices.unavailable)
        let deadline = Date().addingTimeInterval(10)
        while devices.loading && Date() < deadline {
            RunLoop.main.run(until: Date().addingTimeInterval(0.05))
        }
        assert(!devices.loading, "Initial device enumeration did not finish")
        assert(Set(devices.devices.map(\.id)).count == devices.devices.count)
        print("Initial IOKit device snapshot finishes Loading; device identifiers are unique.")
    }
}
