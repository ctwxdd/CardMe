import Foundation
import AppKit

@main
struct StreamingCheck {
    @MainActor static func main() async {
        let session = RescueSession()
        let stream = Pipe()
        let lines = (0..<100).map { "FILE\t{\"path\":\"photo-\($0).jpg\",\"status\":\"decode_error\"}\n" }.joined()
        stream.fileHandleForWriting.write(Data(lines.utf8))
        try! stream.fileHandleForWriting.close()
        let reader = Task.detached { session.readOutput(stream) }
        for _ in 0..<200 where session.damaged.isEmpty {
            try! await Task.sleep(nanoseconds: 5_000_000)
        }
        assert(!session.damaged.isEmpty && session.damaged.count < 100, "Buffered photo events appeared all at once")
        await reader.value
        assert(session.damaged.count == 100)
        assert(session.damaged.map(\.id) == (0..<100).map { "photo-\($0).jpg" })
        assert(session.selectedID == "photo-0.jpg")
        print("100 buffered photo events displayed incrementally, in order, without loss.")
    }
}
