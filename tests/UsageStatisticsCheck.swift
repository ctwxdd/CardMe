import Foundation

final class UsageProtocol: URLProtocol, @unchecked Sendable {
    static var requests: [URLRequest] = []
    static var cancellations = 0
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() { Self.requests.append(request) }
    override func stopLoading() { Self.cancellations += 1 }
}

@main
struct UsageStatisticsCheck {
    @MainActor static func main() async {
        let suite = "CardMeUsageTests-" + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [UsageProtocol.self]
        let network = URLSession(configuration: config)
        let stats = UsageStatistics(defaults: defaults, network: network, endpoint: URL(string: "https://usage.test")!)
        assert(stats.enabled)
        stats.enabled = false
        stats.send("app_open")
        try! await Task.sleep(nanoseconds: 30_000_000)
        assert(UsageProtocol.requests.isEmpty)
        stats.enabled = true
        stats.send("app_open")
        stats.send("rescue_complete", mode: "deep", outcome: RecoveryOutcome(photos: [], wholeCardSearch: true))
        stats.send("coffee_click")
        for result in ["completed", "failed", "cancelled"] {
            stats.send("scan_finished", mode: "normal", scan: ScanOutcome(total: 100, flagged: 3, result: result))
        }
        stats.send("scan_finished", mode: "normal", scan: ScanOutcome(total: 1, flagged: 2, result: "completed"))
        stats.send("scan_finished", mode: "deep", scan: ScanOutcome(total: 100, flagged: 3, result: "completed"))
        stats.send("unexpected")
        for _ in 0..<100 where UsageProtocol.requests.count < 6 { try! await Task.sleep(nanoseconds: 5_000_000) }
        assert(UsageProtocol.requests.count == 6)
        var ids = Set<String>()
        for request in UsageProtocol.requests {
            var data = request.httpBody
            if data == nil, let stream = request.httpBodyStream {
                stream.open(); defer { stream.close() }
                var buffer = [UInt8](repeating: 0, count: 2048); let count = stream.read(&buffer, maxLength: buffer.count)
                data = Data(buffer.prefix(max(count,0)))
            }
            let payload = try! JSONSerialization.jsonObject(with: data!) as! [String: Any]
            let scan = payload["event"] as? String == "scan_finished"
            let keys = ["schema_version","event_id","event","app_version","mode","full_size","previews","thumbnails","review","unrecovered"]
            assert(Set(payload.keys) == Set(keys + (scan ? ["scan_total", "scan_flagged", "scan_result"] : [])))
            assert(payload["schema_version"] as? Int == (scan ? 2 : 1))
            if scan { assert(payload["scan_total"] as? Int == 100 && payload["scan_flagged"] as? Int == 3) }
            assert(payload["unrecovered"] is NSNull)
            ids.insert(payload["event_id"] as! String)
        }
        assert(ids.count == 6)
        stats.enabled = false
        for _ in 0..<100 where UsageProtocol.cancellations < 6 { try! await Task.sleep(nanoseconds: 5_000_000) }
        assert(UsageProtocol.cancellations == 6)
        let restored = UsageStatistics(defaults: defaults, network: network)
        assert(!restored.enabled)
        stats.send("app_open")
        try! await Task.sleep(nanoseconds: 30_000_000)
        assert(UsageProtocol.requests.count == 6)
        network.invalidateAndCancel()
        print("Default-on, persistent opt-out, exact anonymous fields, per-report IDs and cancellation checked without network access.")
    }
}
