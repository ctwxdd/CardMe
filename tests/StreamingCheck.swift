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
        session.receive(Data("FILE\t{\"path\":\"Photo-000000000200.JPG\",\"offset\":512,\"quality\":\"carved_jpeg\"}\n".utf8))
        session.selectedID = "recovered-512"
        session.receive(Data("FILE\t{\"path\":\"IMG_1234.JPG\",\"offset\":512,\"quality\":\"carved_jpeg\",\"output\":\"/tmp/IMG_1234.JPG\"}\n".utf8))
        assert(session.damaged.count == 101)
        assert(session.damaged.last?.name == "IMG_1234.JPG")
        assert(session.damaged.last?.url?.path == "/tmp/IMG_1234.JPG")
        assert(session.selectedID == "recovered-512")
        session.receive(Data("FILE\t{\"path\":\"decoded.jpg\",\"quality\":\"full_resolution_copy\",\"output\":\"/tmp/decoded.rescued.png\"}\n".utf8))
        assert(session.damaged.last?.detail == L("Full-size image saved · PNG copy"))
        print("100 buffered photo events displayed incrementally, in order, without loss.")
    }
}
