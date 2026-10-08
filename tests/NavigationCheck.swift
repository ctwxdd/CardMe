import Foundation
import AppKit

@main
struct NavigationCheck {
    @MainActor static func main() {
        let statisticsWereEnabled = UsageStatistics.shared.enabled
        defer { UsageStatistics.shared.enabled = statisticsWereEnabled }
        UsageStatistics.shared.enabled = false
        assert(CardDevices.isCardCandidate(internalDevice: true, removable: true, connection: "Secure Digital"))
        assert(CardDevices.isCardCandidate(internalDevice: false, removable: false, connection: "USB"))
        assert(!CardDevices.isCardCandidate(internalDevice: true, removable: false, connection: "Apple Fabric"))
        assert(!CardDevices.isCardCandidate(internalDevice: nil, removable: true, connection: "Virtual Interface"))
        let volume = URL(fileURLWithPath: "/Volumes/Card")
        let devices = CardDevice.grouped([
            CardDevice(id: "disk9", name: "Card", bytes: 128, volumes: []),
            CardDevice(id: "disk9", name: "Card", bytes: 128, volumes: [volume]),
            CardDevice(id: "disk9", name: "Card", bytes: 128, volumes: [volume]),
            CardDevice(id: "disk10", name: "Unmounted", bytes: 64, volumes: [])
        ])
        assert(devices.map(\.id) == ["disk9", "disk10"])
        assert(devices[0].volumes == [volume] && devices[0].bytes == 128)
        assert(devices[1].volumes.isEmpty)
        assert(CardDevice.grouped([]).isEmpty)
        let session = RescueSession()
        assert(!session.canShowSupport)
        assert(session.guidanceTitle == "Choose your memory card")
        session.running = true; session.scanning = true
        assert(session.guidanceTitle == "Scanning in progress")
        session.scanning = false
        assert(session.guidanceTitle == "Recovery in progress")
        let friendlyStatus = session.status
        session.receive(Data("Report: /private/technical-path\n{\"quality_counts\":{}}\n".utf8))
        assert(session.status == friendlyStatus && session.log.contains("technical-path"))
        session.receive(Data("Recovery 2/5: photo.jpg (thumbnail_only)\n".utf8))
        assert(session.status == "Rescuing your photos… 2 of 5 checked" && session.fraction == 0.4)
        session.receive(Data("Scanned 200 images...\n".utf8))
        assert(session.status == "Checking your photos… 200 checked")
        session.receive(Data("SCANNING\t{\"checked\":201}\n".utf8))
        assert(session.status == "Checking photos… 201 checked")
        session.running = false
        session.results = URL(fileURLWithPath: "/tmp/rescued")
        assert(!session.canShowSupport) // Scanning alone must not ask for support.
        session.folderRescued = true
        assert(session.canShowSupport)
        session.running = true; assert(!session.canShowSupport)
        session.running = false; session.error = "Save failed"; assert(!session.canShowSupport)
        session.error = nil; session.scanFolder = false; assert(!session.canShowSupport) // No found photos.
        session.scanFolder = true; session.folderRescued = false; session.results = nil
        let first = "a.jpg", second = "b.jpg", last = "c.jpg"
        session.receive(Data([first, second, last].map { "FILE\t{\"path\":\"\($0)\",\"status\":\"decode_error\"}\n" }.joined().utf8))
        assert(session.selectedID == first)
        assert(session.damaged.allSatisfy { !$0.fullSizeRecovered })
        session.scanReport = URL(fileURLWithPath: "/tmp/checked.json")
        assert(session.readyToRescue && session.guidanceTitle == "Ready to rescue")
        session.needsDeepRescue = true
        assert(!session.canSearchDeeper && session.readyToRescue) // Local folders have no whole-card action.
        session.selectedCard = devices[0]
        assert(session.canSearchDeeper && !session.readyToRescue)
        assert(session.guidanceTitle == "Search for missing photos")
        session.selectedCard = nil; session.needsDeepRescue = false; session.scanReport = nil
        session.moveSelection(1); assert(session.selectedID == second)
        session.moveSelection(1); assert(session.selectedID == last)
        session.moveSelection(1); assert(session.selectedID == last)
        session.moveSelection(-1); assert(session.selectedID == second)
        session.moveSelection(-1); assert(session.selectedID == first)
        session.moveSelection(-1); assert(session.selectedID == first)
        session.selectedID = nil
        session.moveSelection(-1); assert(session.selectedID == last)
        assert(session.selectedFileURL == nil)
        session.damaged = []
        session.moveSelection(1); assert(session.selectedFileURL == nil)
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try! FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let normalReport = folder.appendingPathComponent("normal-report.json")
        func normal(_ qualities: [String]) {
            let data = try! JSONSerialization.data(withJSONObject: ["photos": qualities.map { ["quality": $0] }])
            try! data.write(to: normalReport)
            session.assessNormalRecovery(normalReport)
        }
        assert(!session.needsDeepRescue)
        normal(["full_resolution_copy", "manual_review"]); assert(session.needsDeepRescue)
        normal(["full_resolution_copy", "thumbnail_only"]); assert(session.needsDeepRescue)
        normal(["camera_preview"]); assert(session.needsDeepRescue)
        normal(["full_resolution_copy"]); assert(!session.needsDeepRescue)
        normal(["full_resolution"]); assert(!session.needsDeepRescue)
        let inaccessibleScan = folder.appendingPathComponent("scan.json")
        try! Data("{\"unreadable_folders\":[{\"path\":\"DCIM\"}]}".utf8).write(to: inaccessibleScan)
        session.scanReport = inaccessibleScan
        normal(["full_resolution_copy"]); assert(session.needsDeepRescue)
        session.scanReport = nil
        normal(["full_resolution_copy"]); assert(!session.needsDeepRescue)
        normal([]); assert(session.needsDeepRescue)
        session.assessNormalRecovery(folder.appendingPathComponent("missing.json")); assert(session.needsDeepRescue)
        normal(["full_resolution_copy"]); assert(!session.needsDeepRescue)
        let emptyScan = folder.appendingPathComponent("empty-scan.json")
        try! Data("{\"images\":[],\"counts\":{}}".utf8).write(to: emptyScan)
        session.selectedCard = devices[0]
        session.readSummary(emptyScan, folderMode: true)
        assert(session.needsDeepRescue) // A mounted, freshly formatted card must expose Deep Rescue.
        session.needsDeepRescue = false
        try! Data("{\"images\":[],\"counts\":{\"ok_image_header\":1}}".utf8).write(to: emptyScan)
        session.readSummary(emptyScan, folderMode: true)
        assert(!session.needsDeepRescue) // A fresh healthy scan must keep normal recovery available.
        session.receive(Data("CARVING\t{\"done\":512,\"total\":1024,\"found\":3}\n".utf8))
        assert(session.fraction == 0.5 && session.status.contains("3 found"))
        session.receive(Data("FILE\t{\"path\":\"Photo-000000001000.JPG\",\"quality\":\"carved_jpeg\",\"output\":\"/tmp/found.jpg\"}\n".utf8))
        assert(session.damaged.last?.detail == "Found · please review")
        let cardSession = RescueSession()
        cardSession.scanCard(at: folder)
        assert(cardSession.source == folder && cardSession.scanFolder)
        cardSession.scanCard(at: folder.appendingPathComponent("disconnected-card"))
        assert(cardSession.source == folder && cardSession.error != nil)
        // A fresh valid selection still routes directly to scanning after an unavailable card.
        let secondCard = folder.appendingPathComponent("second-card")
        try! FileManager.default.createDirectory(at: secondCard, withIntermediateDirectories: true)
        cardSession.scanCard(at: secondCard)
        assert(cardSession.source == secondCard)
        let file = folder.appendingPathComponent("available.jpg")
        try! Data("fixture".utf8).write(to: file)
        session.damaged = [DamagedFile(id: "available", name: "available.jpg", detail: "fixture", url: file)]
        session.selectedID = "available"
        assert(session.selectedFileURL == file)
        try! FileManager.default.removeItem(at: file)
        assert(session.selectedFileURL == nil)
        let sourceFolder = folder.appendingPathComponent("originals")
        let destination = folder.appendingPathComponent("saved")
        try! FileManager.default.createDirectory(at: sourceFolder, withIntermediateDirectories: true)
        try! FileManager.default.createDirectory(at: destination, withIntermediateDirectories: true)
        let original = sourceFolder.appendingPathComponent("photo.png")
        try! Data("safe-original".utf8).write(to: original)
        do { try ResultExport.validate(source: sourceFolder, destination: sourceFolder); assertionFailure("Source output accepted") }
        catch { }
        let exported = try! ResultExport.copy(from: sourceFolder, to: destination)
        assert(try! Data(contentsOf: exported.appendingPathComponent("photo.png")) == Data("safe-original".utf8))
        let nextExport = try! ResultExport.copy(from: sourceFolder, to: destination)
        assert(exported != nextExport)
        session.damaged = []
        let outputEvent = try! JSONSerialization.data(withJSONObject: ["path": "/unavailable-card/damaged.jpg", "output": original.path, "quality": "full_resolution_copy"])
        session.receive(Data("FILE\t".utf8) + outputEvent + Data("\n".utf8))
        session.selectedID = "/unavailable-card/damaged.jpg"
        assert(session.damaged.last?.fullSizeRecovered == true)
        assert(session.selectedFileURL == original) // Open the recovered file, rather than the damaged source.
        session.rebindSavedPhotos(from: sourceFolder, to: exported)
        assert(session.selectedFileURL == exported.appendingPathComponent("photo.png"))
        session.rebindSavedPhotos(from: sourceFolder, to: nextExport)
        assert(session.selectedFileURL == exported.appendingPathComponent("photo.png")) // Unrelated URLs stay unchanged.
        assert(try! Data(contentsOf: original) == Data("safe-original".utf8))
        let outcomes: [[String: Any]] = [
            ["quality": "full_resolution", "output": original.path],
            ["quality": "full_resolution_copy", "output": original.path],
            ["quality": "camera_preview", "output": original.path],
            ["quality": "thumbnail_only", "output": original.path],
            ["quality": "manual_review", "output": original.path],
            ["quality": "manual_review"],
            ["quality": "full_resolution", "output": "/missing/output.jpg"]
        ]
        let totals = RecoveryOutcome(photos: outcomes, wholeCardSearch: false)
        assert(totals.fullSize == 2 && totals.previews == 1 && totals.thumbnails == 1)
        assert(totals.review == 1 && totals.unrecovered == 2 && totals.saved == 5)
        assert(RecoveryOutcome(photos: outcomes, wholeCardSearch: true).unrecovered == nil)
        let outcomeReport = folder.appendingPathComponent("outcome-report.json")
        try! JSONSerialization.data(withJSONObject: ["photos": outcomes]).write(to: outcomeReport)
        session.readSummary(outcomeReport, folderMode: false)
        let reviewEvent = try! JSONSerialization.data(withJSONObject: ["path": "review.jpg", "output": original.path, "quality": "manual_review"])
        session.receive(Data("FILE\t".utf8) + reviewEvent + Data("\n".utf8))
        assert(session.damaged.last?.fullSizeRecovered == false) // Saved for review is not confirmed recovery.
        for quality in ["camera_preview", "thumbnail_only", "carved_jpeg"] {
            let event = try! JSONSerialization.data(withJSONObject: ["path": "partial-" + quality, "output": original.path, "quality": quality])
            session.receive(Data("FILE\t".utf8) + event + Data("\n".utf8))
            assert(session.damaged.last?.fullSizeRecovered == false)
        }
        let missingEvent = try! JSONSerialization.data(withJSONObject: ["path": "missing.jpg", "output": "/missing/output.jpg", "quality": "full_resolution"])
        session.receive(Data("FILE\t".utf8) + missingEvent + Data("\n".utf8))
        assert(session.damaged.last?.fullSizeRecovered == false)
        assert(session.recoveryOutcome?.unrecovered == 2 && session.summary.contains("Not recovered: 2"))
        session.running = true; session.presentCompletion(); assert(!session.showingCompletion)
        session.running = false; session.presentCompletion(); assert(session.showingCompletion)
        session.folderRescued = true; session.results = exported; session.error = nil
        session.completionDismissed(); assert(session.showingSupportPrompt)
        session.showingSupportPrompt = false
        session.completionDismissed(); assert(!session.showingSupportPrompt) // Only once per completed run.
        session.recoveryOutcome = RecoveryOutcome(photos: [["quality": "manual_review"]], wholeCardSearch: false)
        session.presentCompletion(); session.completionDismissed()
        assert(!session.showingSupportPrompt) // Nothing recovered must not prompt for support.


        for available: Int64 in [0, 99, 100] {
            do { try ResultExport.requireCapacity(available: available, cardBytes: 100); assertionFailure("Insufficient space accepted") }
            catch { }
        }
        try! ResultExport.requireCapacity(available: 101, cardBytes: 100)
        session.source = sourceFolder; session.selectedCard = devices[0]
        session.results = exported; session.folderRescued = true; session.fullScan = true
        session.running = true
        session.startOver(); assert(session.source == sourceFolder && session.results == exported)
        session.running = false
        session.startOver()
        assert(session.source == nil && session.selectedCard == nil && session.results == nil)
        assert(session.damaged.isEmpty && session.selectedID == nil && session.scanReport == nil)
        assert(session.recoveryOutcome == nil && !session.showingCompletion && !session.showingSupportPrompt)
        assert(!session.folderRescued && !session.canContinueRecovery && !session.fullScan)
        assert(session.log.isEmpty && session.summary.isEmpty && session.fraction == nil)
        assert(session.guidanceTitle == "Choose your memory card")
        assert(try! Data(contentsOf: exported.appendingPathComponent("photo.png")) == Data("safe-original".utf8))
        session.startOver() // Resetting an already empty session remains safe.
        var movement = 0
        SystemPreview.shared.navigate = { movement += $0 }
        func key(_ code: UInt16) -> NSEvent {
            NSEvent.keyEvent(with: .keyDown, location: .zero, modifierFlags: [], timestamp: 0, windowNumber: 0, context: nil, characters: "", charactersIgnoringModifiers: "", isARepeat: false, keyCode: code)!
        }
        assert(SystemPreview.shared.previewPanel(nil, handle: key(125)) && movement == 1)
        assert(SystemPreview.shared.previewPanel(nil, handle: key(126)) && movement == 0)
        assert(!SystemPreview.shared.previewPanel(nil, handle: key(53)))
        SystemPreview.shared.navigate = nil
        print("Navigation, preview keys and file availability checks passed.")
    }
}
