import AppKit
import SwiftUI
import UniformTypeIdentifiers
import QuickLookUI
import CryptoKit

struct DamagedFile: Identifiable {
    let id: String
    var name: String
    var detail: String
    var url: URL?
    var fullSizeRecovered = false
}

struct RecoveryOutcome {
    var fullSize = 0
    var previews = 0
    var thumbnails = 0
    var review = 0
    var unrecovered: Int?
    var saved: Int { fullSize + previews + thumbnails + review }
    init(photos: [[String: Any]], wholeCardSearch: Bool) {
        var missing = 0
        for photo in photos {
            guard let output = photo["output"] as? String, FileManager.default.fileExists(atPath: output) else {
                missing += 1; continue
            }
            switch photo["quality"] as? String {
            case "full_resolution", "full_resolution_copy": fullSize += 1
            case "camera_preview": previews += 1
            case "thumbnail_only": thumbnails += 1
            default: review += 1
            }
        }
        unrecovered = wholeCardSearch ? nil : missing
    }
    var text: String {
        "Full-size photos: \(fullSize) · Previews only: \(previews) · Tiny thumbnails only: \(thumbnails)\nNot recovered: \(unrecovered.map(String.init) ?? "unknown") · Saved for review: \(review)"
    }
}

// Only fixed counters leave the app; recovery never waits for this service.
@MainActor
final class UsageStatistics: ObservableObject {
    static let shared = UsageStatistics()
    static let settingKey = "shareUsageStatistics"
    private let defaults: UserDefaults
    private let network: URLSession
    private let endpoint: URL
    private var tasks: [UUID: URLSessionDataTask] = [:]
    @Published var enabled: Bool {
        didSet {
            defaults.set(enabled, forKey: Self.settingKey)
            if !enabled { tasks.values.forEach { $0.cancel() }; tasks.removeAll() }
        }
    }
    init(defaults: UserDefaults = .standard, network: URLSession? = nil,
         endpoint: URL = URL(string: "https://pickology-control-plane.azurewebsites.net/api/v1/cardme/usage")!) {
        self.defaults = defaults
        self.endpoint = endpoint
        defaults.register(defaults: [Self.settingKey: true])
        enabled = defaults.bool(forKey: Self.settingKey)
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 5
        config.timeoutIntervalForResource = 8
        config.httpCookieStorage = nil
        config.urlCache = nil
        self.network = network ?? URLSession(configuration: config)
    }
    func send(_ event: String, mode: String = "none", outcome: RecoveryOutcome? = nil) {
        guard enabled, tasks.count < 8,
              ["app_open", "rescue_complete", "coffee_click"].contains(event),
              ["none", "normal", "deep"].contains(mode),
              (event == "rescue_complete") == (outcome != nil),
              (event == "rescue_complete") == (mode != "none") else { return }
        let id = UUID()
        let payload: [String: Any] = [
            "schema_version": 1, "event_id": id.uuidString.lowercased(), "event": event,
            "app_version": Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "development",
            "mode": mode, "full_size": outcome?.fullSize ?? 0,
            "previews": outcome?.previews ?? 0, "thumbnails": outcome?.thumbnails ?? 0,
            "review": outcome?.review ?? 0, "unrecovered": outcome?.unrecovered.map { $0 as Any } ?? NSNull()
        ]
        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: payload)
        let task = network.dataTask(with: request) { [weak self] _, _, _ in
            Task { @MainActor in self?.tasks.removeValue(forKey: id) }
        }
        tasks[id] = task
        task.resume()
    }
    func openCoffee() {
        send("coffee_click")
        NSWorkspace.shared.open(URL(string: "https://ko-fi.com/alittleseal")!)
    }
}

struct UsageSettingsView: View {
    @ObservedObject private var statistics = UsageStatistics.shared
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Privacy").font(.title2.bold())
            Toggle("Share usage statistics", isOn: $statistics.enabled)
            Text("Help improve CardMe by sharing app opens, rescue result counts and coffee-link clicks with our service. Enabled by default. No installation ID is used; photos, file names, paths and card details stay on your Mac.")
            Text("Turning this off stops future uploads. Already received reports are normally kept for 90 days. Network requests expose your IP address to the hosting service; infrastructure logs may retain request metadata.")
                .font(.callout).foregroundStyle(.secondary)
        }.padding(24).frame(width: 480).tint(.teal)
    }
}

@MainActor
final class SystemPreview: NSResponder, @preconcurrency QLPreviewPanelDataSource, @preconcurrency QLPreviewPanelDelegate {
    static let shared = SystemPreview()
    var item: URL?
    var navigate: ((Int) -> Void)?
    func show(_ url: URL) {
        item = url
        if let window = NSApp.mainWindow, window.nextResponder !== self {
            nextResponder = window.nextResponder
            window.nextResponder = self
        }
        guard let panel = QLPreviewPanel.shared() else { return }
        panel.updateController()
        panel.reloadData()
        if !panel.isVisible { panel.makeKeyAndOrderFront(nil) }
    }
    override func acceptsPreviewPanelControl(_ panel: QLPreviewPanel!) -> Bool { item != nil }
    override func beginPreviewPanelControl(_ panel: QLPreviewPanel!) { panel.dataSource = self; panel.delegate = self }
    override func endPreviewPanelControl(_ panel: QLPreviewPanel!) { panel.dataSource = nil; panel.delegate = nil }
    func previewPanel(_ panel: QLPreviewPanel!, handle event: NSEvent!) -> Bool {
        guard event.type == .keyDown else { return false }
        switch event.keyCode {
        case 125, 124: navigate?(1); return true
        case 126, 123: navigate?(-1); return true
        default: return false
        }
    }
    func numberOfPreviewItems(in panel: QLPreviewPanel!) -> Int { item == nil ? 0 : 1 }
    func previewPanel(_ panel: QLPreviewPanel!, previewItemAt index: Int) -> QLPreviewItem! { item as NSURL? }
}

@MainActor
final class RescueSession: ObservableObject {
    static let shared = RescueSession()
    static var directDownload: Bool { Bundle.main.object(forInfoDictionaryKey: "CardRescueDirectDownload") as? Bool == true }
    static var safetyCopyLimitation: String {
        if directDownload {
            return "We’ll make the safety copy for you, then recover from it. macOS may show “authopen” in its permission request; it opens the card only for reading. Keep the card connected until copying finishes."
        }
        return "This App Store build can recover from an existing copy, but cannot create the whole-card copy itself. Creating it requires a separate disk-imaging tool."
    }
    @Published var showingAbout = false
    @Published var showingCompletion = false
    @Published var showingSupportPrompt = false
    private var supportPromptPending = false
    @Published var recoveryOutcome: RecoveryOutcome?
    @Published var scanFolder = true
    @Published var scanReport: URL?
    @Published var folderRescued = false
    @Published var needsDeepRescue = false
    @Published var canContinueRecovery = false
    @Published var fullScan = false
    @Published var source: URL?
    @Published var selectedCard: CardDevice?
    @Published var safetyImage: URL?
    @Published var copyWarning: String?
    @Published var running = false
    @Published var scanning = false
    @Published var status = "Connect your memory card. We’ll help you take the next step."
    @Published var fraction: Double?
    @Published var log = ""
    @Published var summary = ""
    @Published var error: String?
    @Published var results: URL?
    var hasSavedPhotos: Bool {
        folderRescued && results != nil && (scanFolder || !damaged.isEmpty)
    }
    var canShowSupport: Bool { !running && error == nil && hasSavedPhotos }
    var canSearchDeeper: Bool { needsDeepRescue && selectedCard != nil }
    var readyToRescue: Bool {
        !running && !folderRescued && !canSearchDeeper && scanFolder && scanReport != nil && !damaged.isEmpty
    }
    var guidanceTitle: String {
        if running { return scanning ? "Scanning in progress" : "Recovery in progress" }
        if hasSavedPhotos { return "Photos saved" }
        if canSearchDeeper { return "Search for missing photos" }
        if canContinueRecovery { return "Continue recovery" }
        if error != nil { return "Recovery needs attention" }
        if readyToRescue { return "Ready to rescue" }
        if scanReport != nil { return "Photo check complete" }
        if source != nil || selectedCard != nil { return "Ready to check photos" }
        return "Choose your memory card"
    }
    @Published var damaged: [DamagedFile] = []
    @Published var selectedID: String?
    private var sourceAccess = false
    private var destination: URL?
    private var destinationAccess = false
    private var recoveryOutput: URL?
    @Published var hasPreviousRecovery = UserDefaults.standard.data(forKey: "recoverySource") != nil
    private var process: Process?
    private var pipe: Pipe?
    private var pending = Data()
    private var lines: [String] = []
    private var paused = false
    private var quitAfterStop = false
    private var recoveryMode = "normal"
    private var completionReported = false

    func chooseSource(folder: Bool = true, cardRoot: URL? = nil, freshImageDestination: Bool = false) {
        guard !running else { return }
        if folder, let cardRoot, Self.directDownload {
            scanCard(at: cardRoot)
            return
        }
        let panel = NSOpenPanel()
        panel.canChooseFiles = !folder
        panel.canChooseDirectories = folder
        panel.allowsMultipleSelection = false
        panel.directoryURL = cardRoot
        panel.prompt = folder ? "Check photos" : "Use this copy"
        panel.message = folder ? "Choose a photo folder. It will only be read." : "Choose a safety copy of your card, such as card.img. We’ll search it for photos."
        // Disk images can have UTType.diskImage rather than UTType.data. Allow files; the engine validates their contents.
        if !folder { panel.allowedContentTypes = [.item] }
        if panel.runModal() == .OK, let chosen = panel.url {
            if let cardRoot {
                let root = cardRoot.resolvingSymlinksInPath().standardizedFileURL.path
                let path = chosen.resolvingSymlinksInPath().standardizedFileURL.path
                guard path == root || path.hasPrefix(root + "/") else {
                    error = "Choose the selected card or a folder inside it."; return
                }
            }
            if freshImageDestination {
                if destinationAccess { destination?.stopAccessingSecurityScopedResource() }
                destination = nil; destinationAccess = false
            }
            if cardRoot == nil { selectedCard = nil }
            useSource(chosen, folder: folder)
        }
    }
    func startOver() {
        guard !running else { return }
        if sourceAccess { source?.stopAccessingSecurityScopedResource() }
        sourceAccess = false; source = nil; scanFolder = true
        damaged = []; scanReport = nil; selectedID = nil; results = nil; recoveryOutcome = nil; supportPromptPending = false; showingSupportPrompt = false; showingCompletion = false; summary = ""; error = nil
        folderRescued = false; needsDeepRescue = false; canContinueRecovery = false
        recoveryOutput = nil
        if destinationAccess { destination?.stopAccessingSecurityScopedResource() }
        destination = nil; destinationAccess = false
        selectedCard = nil
        safetyImage = nil; copyWarning = nil
        log = ""; lines = []; pending = Data(); fraction = nil
        paused = false; fullScan = false; scanning = false
        status = "Connect your memory card. We’ll help you take the next step."
        SystemPreview.shared.item = nil
        SystemPreview.shared.navigate = nil
        QLPreviewPanel.shared()?.close()
    }
    func chooseCard(_ card: CardDevice) {
        guard !running else { return }
        startOver()
        selectedCard = card
        if let root = card.volumes.first {
            chooseSource(cardRoot: root)
        } else if Self.directDownload {
            needsDeepRescue = true
            status = "Your card is detected, but its files aren’t visible. We can try searching the whole card."
        }
    }
    func scanCard(at root: URL) {
        guard !running else { return }
        var isDirectory: ObjCBool = false
        guard FileManager.default.fileExists(atPath: root.path, isDirectory: &isDirectory),
              isDirectory.boolValue, FileManager.default.isReadableFile(atPath: root.path) else {
            needsDeepRescue = selectedCard != nil
            error = "We couldn’t read this card. Check that it’s still connected and allow removable-volume access if macOS asks."; return
        }
        useSource(root, folder: true)
    }
    private func useSource(_ chosen: URL, folder: Bool) {
        if sourceAccess { source?.stopAccessingSecurityScopedResource() }
        source = chosen
        sourceAccess = chosen.startAccessingSecurityScopedResource()
        scanFolder = folder
        canContinueRecovery = !folder
        recoveryOutput = nil
        if !folder, let bookmark = try? chosen.bookmarkData(options: [.withSecurityScope, .securityScopeAllowOnlyReadAccess], includingResourceValuesForKeys: nil, relativeTo: nil) {
            UserDefaults.standard.set(bookmark, forKey: "recoverySource")
            hasPreviousRecovery = true
        }
        if folder || prepareImageDestination() { start() }
    }
    func chooseSavedImage() {
        guard !running else { return }
        chooseSource(folder: false, freshImageDestination: true)
    }
    private func prepareImageDestination() -> Bool {
        guard let source else { return false }
        if destination == nil {
            let panel = NSOpenPanel()
            panel.canChooseFiles = false; panel.canChooseDirectories = true
            panel.canCreateDirectories = true; panel.allowsMultipleSelection = false
            panel.prompt = "Save photos here"
            panel.message = "Choose where to save recovered photos. The search starts after you choose a folder. Your saved card copy stays read only."
            guard panel.runModal() == .OK, let chosen = panel.url else { return false }
            destination = chosen
        }
        guard let destination else { return false }
        if !destinationAccess { destinationAccess = destination.startAccessingSecurityScopedResource() }
        do {
            try ResultExport.validate(source: source, destination: destination)
            if let selectedCard { try ResultExport.validate(destination: destination, card: selectedCard) }
            if recoveryOutput == nil {
                recoveryOutput = destination.appendingPathComponent("Rescued Photos " + UUID().uuidString, isDirectory: true)
            }
            if let bookmark = try? destination.bookmarkData(options: .withSecurityScope, includingResourceValuesForKeys: nil, relativeTo: nil) {
                UserDefaults.standard.set(bookmark, forKey: "recoveryDestination")
                UserDefaults.standard.set(recoveryOutput?.lastPathComponent, forKey: "recoveryOutputName")
            }
            return true
        } catch {
            if destinationAccess { destination.stopAccessingSecurityScopedResource() }
            self.destination = nil; destinationAccess = false
            self.error = "Choose a writable folder on a fixed disk or SSD, away from your card. Nothing was changed."
            return false
        }
    }
    func continueRecovery() {
        guard !running, canContinueRecovery, !scanFolder else { return }
        if prepareImageDestination() { start() }
    }
    func resumePrevious() {
        guard !running, let bookmark = UserDefaults.standard.data(forKey: "recoverySource") else { return }
        do {
            var stale = false
            let chosen = try URL(resolvingBookmarkData: bookmark, options: .withSecurityScope, relativeTo: nil, bookmarkDataIsStale: &stale)
            if stale { chooseSource(folder: false); return }
            if sourceAccess { source?.stopAccessingSecurityScopedResource() }
            source = chosen; sourceAccess = chosen.startAccessingSecurityScopedResource(); scanFolder = false
            selectedCard = nil; recoveryOutput = nil; canContinueRecovery = true
            if destinationAccess { destination?.stopAccessingSecurityScopedResource() }
            destination = nil; destinationAccess = false
            if let saved = UserDefaults.standard.data(forKey: "recoveryDestination"),
               let name = UserDefaults.standard.string(forKey: "recoveryOutputName"),
               name.hasPrefix("Rescued Photos "), !name.contains("/") {
                var staleDestination = false
                let folder = try URL(resolvingBookmarkData: saved, options: .withSecurityScope, relativeTo: nil, bookmarkDataIsStale: &staleDestination)
                if !staleDestination {
                    destination = folder
                    recoveryOutput = folder.appendingPathComponent(name, isDirectory: true)
                }
            }
            continueRecovery()
        } catch { self.error = "Choose the saved card image again to resume." }
    }
    // Consume each photo event separately so pipe buffering cannot publish 100 rows in one UI update.
    nonisolated func readOutput(_ stream: Pipe) {
        var buffer = Data()
        while true {
            let data = stream.fileHandleForReading.availableData
            if data.isEmpty { break }
            buffer.append(data)
            while let newline = buffer.firstIndex(of: 10) {
                let line = Data(buffer[...newline])
                buffer.removeSubrange(...newline)
                DispatchQueue.main.sync { self.receive(line) }
                if line.starts(with: Data("FILE\t".utf8)) { Thread.sleep(forTimeInterval: 1.0 / 60.0) }
            }
        }
        if !buffer.isEmpty {
            let tail = buffer
            DispatchQueue.main.sync { self.receive(tail) }
        }
    }
    func receive(_ data: Data) {
        pending.append(data)
        while let newline = pending.firstIndex(of: 10) {
            let line = String(decoding: pending[..<newline], as: UTF8.self)
            pending.removeSubrange(...newline)
            addLine(line)
        }
    }
    var selectedFileURL: URL? {
        guard let url = damaged.first(where: { $0.id == selectedID })?.url,
              FileManager.default.fileExists(atPath: url.path) else { return nil }
        return url
    }
    func revealSelected() {
        guard let url = selectedFileURL else { return }
        NSWorkspace.shared.activateFileViewerSelecting([url])
    }
    func moveSelection(_ delta: Int) {
        guard !damaged.isEmpty else { return }
        let index = selectedID.flatMap { id in damaged.firstIndex(where: { $0.id == id }) }
        let next = index.map { min(damaged.count - 1, max(0, $0 + delta)) } ?? (delta < 0 ? damaged.count - 1 : 0)
        selectedID = damaged[next].id
    }
    func previewSelected() {
        guard let row = damaged.first(where: { $0.id == selectedID }) else { return }
        guard let url = row.url, FileManager.default.fileExists(atPath: url.path) else {
            error = "A preview will be available after this photo is rescued."
            return
        }
        SystemPreview.shared.navigate = { [weak self] delta in
            self?.moveSelection(delta)
            self?.previewSelected()
        }
        SystemPreview.shared.show(url)
    }
    private func updateFile(_ object: [String: Any]) {
        guard let path = object["path"] as? String else { return }
        let quality = object["quality"] as? String
        let detail: String
        switch quality {
        case "full_resolution": detail = "Original photo saved"
        case "full_resolution_copy": detail = "Full-size photo saved"
        case "camera_preview": detail = "Smaller preview saved"
        case "thumbnail_only": detail = "Tiny thumbnail saved"
        case "carved_jpeg": detail = "Found · please review"
        case "manual_review": detail = object["output"] == nil ? "Not recovered" : "Saved · needs checking"
        default:
            switch object["status"] as? String {
            case "unsupported_or_unrecognized": detail = "Format needs review"
            case "read_error": detail = "Could not read"
            case "skipped_size_limit": detail = "Too large to check safely"
            case "suspect_thumbnail_mismatch", "suspect_warning": detail = "Please check this photo"
            default: detail = "Unable to open"
            }
        }
        let previewPath = object["output"] as? String ?? (path.hasPrefix("/") ? path : nil)
        let row = DamagedFile(id: path, name: URL(fileURLWithPath: path).lastPathComponent, detail: detail,
                              url: previewPath.map { URL(fileURLWithPath: $0) },
                              fullSizeRecovered: ["full_resolution", "full_resolution_copy"].contains(quality ?? "") && (object["output"] as? String).map { FileManager.default.fileExists(atPath: $0) } == true)
        if let index = damaged.firstIndex(where: { $0.id == path }) { damaged[index] = row } else { damaged.append(row) }
    }
    private func addLine(_ line: String) {
        if line.hasPrefix("SCANNING\t"), let data = String(line.dropFirst(9)).data(using: .utf8),
           let progress = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let checked = progress["checked"] as? Int {
            status = "Checking photos… \(checked) checked"
            return
        }
        if line.hasPrefix("CARVING\t"), let data = String(line.dropFirst(8)).data(using: .utf8),
           let progress = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let done = progress["done"] as? Double, let total = progress["total"] as? Double, total > 0 {
            fraction = done / total
            status = "Looking for your photos… \(Int(100 * done / total))% checked · \(progress["found"] as? Int ?? 0) found"
            return
        }
        if line.hasPrefix("IMAGING\t"), let data = String(line.dropFirst(8)).data(using: .utf8),
           let progress = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let done = progress["done"] as? Double, let total = progress["total"] as? Double, total > 0 {
            fraction = done / total
            status = "Keeping your card safe… \(Int(100 * done / total))% copied"
            return
        }
        if line.hasPrefix("FILE\t"), let data = String(line.dropFirst(5)).data(using: .utf8),
           let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            updateFile(object)
            if selectedID == nil { selectedID = damaged.first?.id }
            return
        }
        guard !line.isEmpty else { return }
        lines.append(line)
        if lines.count > 250 { lines.removeFirst(lines.count - 250) }
        log = lines.joined(separator: "\n")
        if line.hasPrefix("Recovery "), let token = line.split(separator: " ").dropFirst().first {
            let parts = token.replacingOccurrences(of: ":", with: "").split(separator: "/")
            if parts.count == 2, let done = Double(parts[0]), let total = Double(parts[1]), total > 0 {
                fraction = done / total
                status = "Rescuing your photos… \(Int(done)) of \(Int(total)) checked"
            }
        } else if line.hasPrefix("Scanned "), let count = line.split(separator: " ").dropFirst().first, Int(count) != nil {
            status = "Checking your photos… \(count) checked"
        }
    }
    func rescueFolder() {
        guard !running, source != nil, scanFolder, scanReport != nil else { return }
        let panel = NSOpenPanel()
        panel.canChooseFiles = false; panel.canChooseDirectories = true
        panel.canCreateDirectories = true; panel.allowsMultipleSelection = false
        panel.prompt = "Save photos here"
        panel.message = "Choose where to save the recovered photos. Recovery starts as soon as you choose a folder. Your card stays read only."
        guard panel.runModal() == .OK, let chosen = panel.url, let source else { return }
        let access = chosen.startAccessingSecurityScopedResource()
        do {
            try ResultExport.validate(source: source, destination: chosen)
            if let card = selectedCard ?? (try? ResultExport.card(at: source)) {
                try ResultExport.validate(destination: chosen, card: card)
            }
            if destinationAccess { destination?.stopAccessingSecurityScopedResource() }
            destination = chosen; destinationAccess = access
            start(rescueFolder: true)
            if !running && destinationAccess {
                chosen.stopAccessingSecurityScopedResource(); destinationAccess = false
            }
        } catch {
            if access { chosen.stopAccessingSecurityScopedResource() }
            self.error = "Choose a writable folder away from your card. Nothing was changed."
        }
    }
    func deepRescue() {
        guard !running else { return }
        let card: CardDevice
        do {
            if let selectedCard { card = selectedCard }
            else if let source, scanReport != nil { card = try ResultExport.card(at: source) }
            else { return }
        }
        catch { self.error = "We couldn’t identify a physical card. Choose your card and try again."; return }
        let cardBytes = card.bytes
        let size = ByteCountFormatter.string(fromByteCount: cardBytes, countStyle: .file)
        let explanation = NSAlert()
        explanation.messageText = "Search the whole card safely"
        explanation.informativeText = "We’ll read the whole card and save a safety copy called card.img in the folder you choose. Then we’ll search that copy for photos. Nothing on your card will be changed.\n\nThis takes longer and needs more than \(size) of free space, plus room for the rescued photos. We’ll check the space before starting.\n\nThis search supports JPEG photos and may also find small previews. Overwritten photos or photos split across different areas may not be recoverable. RAW photos aren’t supported.\n\n\(Self.safetyCopyLimitation)"
        explanation.addButton(withTitle: "Choose where to save…")
        explanation.addButton(withTitle: "Cancel")
        guard explanation.runModal() == .alertFirstButtonReturn else { return }
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.canCreateDirectories = true
        panel.allowsMultipleSelection = false
        panel.prompt = "Save here"
        panel.message = "Choose a folder on another drive with more than \(size) free. The card stays untouched."
        guard panel.runModal() == .OK, let chosen = panel.url else { return }
        let access = chosen.startAccessingSecurityScopedResource()
        do {
            try ResultExport.validate(destination: chosen, card: card)
            if let source, scanFolder { try ResultExport.validate(source: source, destination: chosen) }
            _ = try ResultExport.checkCapacity(at: chosen, cardBytes: cardBytes)
            if Self.directDownload {
                if destinationAccess { destination?.stopAccessingSecurityScopedResource() }
                destination = chosen; destinationAccess = access
                startImaging(card: card, destination: chosen)
                return
            }
            let next = NSAlert()
            next.messageText = "There is room for your safety copy"
            next.informativeText = "\(Self.safetyCopyLimitation) If you already have card.img, choose it to search for JPEG photos and save them into this folder. No copy has been created yet."
            next.addButton(withTitle: "Use existing safety copy…")
            next.addButton(withTitle: "Cancel")
            guard next.runModal() == .alertFirstButtonReturn else {
                if access { chosen.stopAccessingSecurityScopedResource() }
                return
            }
            if destinationAccess { destination?.stopAccessingSecurityScopedResource() }
            destination = chosen; destinationAccess = access
            chooseSource(folder: false)
            if destinationAccess && !running { chosen.stopAccessingSecurityScopedResource(); destinationAccess = false; destination = nil }
        } catch {
            if access { chosen.stopAccessingSecurityScopedResource() }
            if (error as NSError).code == CocoaError.fileWriteOutOfSpace.rawValue {
                self.error = "Not enough free space. Choose a drive with more than \(size) available, plus room for rescued photos. Nothing was copied."
            } else { self.error = "Choose a writable folder on another drive, away from the source card. Nothing was copied." }
        }
    }
    private func startImaging(card: CardDevice, destination: URL) {
        guard let resources = Bundle.main.resourceURL else { return }
        // ponytail: fresh image per attempt; add identity-verified resume when repeat copying is common.
        let folder = destination.appendingPathComponent("Card Safety Copy " + UUID().uuidString, isDirectory: true)
        let image = folder.appendingPathComponent("card.img")
        let task = Process()
        task.executableURL = resources.appendingPathComponent("python/bin/python3")
        task.arguments = ["-B", "-u", resources.appendingPathComponent("engine/image-card.py").path,
                          "--device", card.id, "--registry-id", String(card.registryID), "--bytes", String(card.bytes),
                          "--output", folder.path, "--tool", resources.appendingPathComponent("tools/ddrescue").path]
        var environment = ProcessInfo.processInfo.environment
        environment.removeValue(forKey: "PYTHONPATH")
        environment["PYTHONHOME"] = resources.appendingPathComponent("python").path
        environment["PYTHONNOUSERSITE"] = "1"; environment["PYTHONDONTWRITEBYTECODE"] = "1"
        task.environment = environment
        let stream = Pipe()
        task.standardOutput = stream; task.standardError = stream
        process = task; pipe = stream; scanning = false; running = true; paused = false; fraction = nil
        error = nil; copyWarning = nil; safetyImage = nil; pending = Data(); lines = []; log = ""
        status = "Preparing a safe copy. macOS may ask to read your card…"
        do {
            try task.run()
            DispatchQueue.global(qos: .userInitiated).async {
                self.readOutput(stream)
                task.waitUntilExit()
                DispatchQueue.main.async {
                    if !self.pending.isEmpty { self.addLine(String(decoding: self.pending, as: UTF8.self)); self.pending = Data() }
                    self.running = false; self.process = nil; self.pipe = nil
                    if FileManager.default.fileExists(atPath: image.path) { self.safetyImage = image }
                    if self.quitAfterStop { NSApp.reply(toApplicationShouldTerminate: true); return }
                    if task.terminationStatus == 0 {
                        if let data = try? Data(contentsOf: folder.appendingPathComponent("copy-report.json")),
                           let report = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                           let bad = report["unreadable_bytes"] as? Int64, bad > 0 {
                            self.copyWarning = "Some parts of the card could not be read. The safety copy and recovery map are saved; recovered photos may be incomplete."
                        }
                        self.useSource(image, folder: false)
                    } else {
                        self.status = self.paused ? "Stopped safely. The partial copy is preserved." : "Safety copying stopped. Your card is untouched."
                        self.error = self.paused ? nil : "We couldn’t finish the safety copy. Check the card reader and allow macOS to read your card, then try again. The activity log has more information."
                        if self.destinationAccess { destination.stopAccessingSecurityScopedResource() }
                        self.destinationAccess = false
                    }
                }
            }
        } catch {
            process = nil; pipe = nil; running = false; self.error = error.localizedDescription
            if destinationAccess { destination.stopAccessingSecurityScopedResource() }
            destinationAccess = false
        }
    }
    func rebindSavedPhotos(from source: URL, to saved: URL) {
        let prefix = source.standardizedFileURL.path + "/"
        for index in damaged.indices {
            guard let url = damaged[index].url, url.standardizedFileURL.path.hasPrefix(prefix) else { continue }
            damaged[index].url = saved.appendingPathComponent(String(url.standardizedFileURL.path.dropFirst(prefix.count)))
        }
    }
    private func exportResults(_ privateResults: URL) {
        guard let destination else { return }
        scanning = false; running = true; status = "Saving your rescued photos…"
        DispatchQueue.global(qos: .userInitiated).async {
            let outcome = Result { try ResultExport.copy(from: privateResults, to: destination) }
            DispatchQueue.main.async {
                self.running = false
                switch outcome {
                case .success(let saved):
                    self.results = saved
                    self.rebindSavedPhotos(from: privateResults, to: saved)
                    self.folderRescued = true
                    self.presentCompletion()
                    self.status = self.needsDeepRescue ? "Your rescued copies are saved. Some are smaller previews or still need checking; a deeper search may help." : "Your rescued photos are ready. Originals are untouched."
                case .failure:
                    self.folderRescued = false
                    self.results = nil
                    self.status = "Your recovered copies are safe on this Mac."
                    self.error = "We couldn’t save to that folder. Choose another folder and press Rescue again."
                }
                if self.destinationAccess { destination.stopAccessingSecurityScopedResource() }
                self.destinationAccess = false
                if self.quitAfterStop { NSApp.reply(toApplicationShouldTerminate: true) }
            }
        }
    }
    func start(rescueFolder: Bool = false) {
        guard !running, let source, let resources = Bundle.main.resourceURL else { return }
        if !scanFolder && !rescueFolder && recoveryOutput == nil && !prepareImageDestination() { return }
        if !rescueFolder { scanReport = nil; folderRescued = false; needsDeepRescue = false; damaged = []; selectedID = nil }
        error = nil; summary = ""; results = nil; recoveryOutcome = nil; supportPromptPending = false; showingSupportPrompt = false; showingCompletion = false; log = ""; lines = []; pending = Data(); fraction = nil; paused = false
        let storage = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("CardRescue", isDirectory: true)
        let identifier = SHA256.hash(data: Data(source.path.utf8)).prefix(8).map { String(format: "%02x", $0) }.joined()
        let output = (!scanFolder && !rescueFolder ? recoveryOutput : nil) ?? storage.appendingPathComponent(rescueFolder ? "Folder-" + (scanReport?.deletingPathExtension().lastPathComponent ?? identifier) : "Recovery-" + identifier, isDirectory: true)
        let temporary = storage.appendingPathComponent("Temporary", isDirectory: true)
        do { try FileManager.default.createDirectory(at: temporary, withIntermediateDirectories: true) }
        catch { self.error = error.localizedDescription; return }
        let engine = resources.appendingPathComponent("engine", isDirectory: true)
        let python = resources.appendingPathComponent("python/bin/python3")
        let task = Process()
        task.executableURL = python
        let card = rescueFolder && Self.directDownload ? selectedCard ?? (try? ResultExport.card(at: source)) : nil
        if let card { selectedCard = card }
        let script = rescueFolder ? (card == nil ? "rescue-folder.py" : "sd-rescue.py") : (scanFolder ? "scan-images.py" : "carve-photos.py")
        var arguments = ["-B", "-u", engine.appendingPathComponent(script).path]
        let report: URL
        if rescueFolder {
            guard let scanReport else { return }
            report = output.appendingPathComponent("pipeline-report.json")
            arguments += ["--source", source.path, "--scan", scanReport.path, "--output", output.path]
            if let card {
                arguments += ["--device", card.id, "--registry-id", String(card.registryID), "--bytes", String(card.bytes)]
            }
        } else if scanFolder {
            // Fresh scan report each run; recovery mode uses checkpoints instead.
            report = storage.appendingPathComponent("Scan-\(UUID().uuidString).json")
            arguments += [source.path, "--report", report.path]
            if fullScan { arguments.append("--full") }
        } else {
            report = output.appendingPathComponent("pipeline-report.json")
            arguments += ["--image", source.path, "--output", output.path]
        }
        task.arguments = arguments
        var environment = ProcessInfo.processInfo.environment
        // Isolate the bundled runtime from user Python settings and packages.
        environment.removeValue(forKey: "PYTHONPATH")
        environment["TMPDIR"] = temporary.path
        environment["PYTHONHOME"] = resources.appendingPathComponent("python").path
        environment["PYTHONNOUSERSITE"] = "1"
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        task.environment = environment
        let stream = Pipe()
        task.standardOutput = stream; task.standardError = stream
        let folderMode = scanFolder && !rescueFolder
        recoveryMode = folderMode || rescueFolder ? "normal" : "deep"
        completionReported = false
        let finish = {
            DispatchQueue.main.async {
                if !self.pending.isEmpty {
                    self.addLine(String(decoding: self.pending, as: UTF8.self)); self.pending = Data()
                }
                self.running = false; self.process = nil; self.pipe = nil
                if self.paused {
                    self.canContinueRecovery = !folderMode && !rescueFolder
                    self.status = folderMode ? "Scan stopped. Start again for a new report." : "Paused. Start again to resume verified outputs."
                } else if task.terminationStatus == 0 || task.terminationStatus == 2 {
                    if folderMode { self.scanReport = report }

                    self.results = folderMode ? report : output.appendingPathComponent("best_available")
                    self.fraction = 1
                    self.status = task.terminationStatus == 2 ? "Finished. Please check the saved photos." : (folderMode ? "Check complete. Your card is untouched." : "Rescue complete.")
                    self.readSummary(report, folderMode: folderMode)
                    if rescueFolder { self.assessNormalRecovery(report) }
                    let best = output.appendingPathComponent("best_available")
                    if !folderMode && !rescueFolder {
                        self.folderRescued = true
                        self.status = self.damaged.isEmpty ? "No JPEG photos found. Your card and safety copy are untouched." : "Your found photos are saved. Please check them before using them."
                        self.presentCompletion()
                    } else if rescueFolder && (try? FileManager.default.contentsOfDirectory(atPath: best.path))?.isEmpty == true {
                        self.results = nil; self.folderRescued = false
                        self.status = "These photos couldn’t be rescued from their files. We can try searching the whole card."
                        self.presentCompletion()
                    } else if rescueFolder { self.exportResults(best) }
                } else {
                    self.canContinueRecovery = !folderMode && !rescueFolder
                    if rescueFolder { self.needsDeepRescue = true }
                    self.status = "Stopped safely."
                    let diagnostic = self.lines.last ?? ""
                    if diagnostic.contains("PermissionError") || diagnostic.contains("Operation not permitted") {
                        self.error = "Some folders could not be read. Choose the card’s DCIM folder and try again."
                    } else if diagnostic.contains("does not match this card profile") {
                        self.error = "This card image is not supported by the current recovery method."
                    } else {
                        self.error = "We couldn’t finish this step. Check that your card and save drive are connected, then try again. The activity log has more information."
                    }
                }
                if !self.running && self.destinationAccess {
                    self.destination?.stopAccessingSecurityScopedResource(); self.destinationAccess = false
                }
                if self.quitAfterStop && !self.running { NSApp.reply(toApplicationShouldTerminate: true) }
            }
        }
        process = task; pipe = stream; scanning = folderMode; running = true; canContinueRecovery = false
        status = rescueFolder ? "Rescuing the available photos…" : (scanFolder ? "Checking your photos…" : "Looking for photos beyond the file list…")
        do {
            try task.run()
            DispatchQueue.global(qos: .userInitiated).async {
                self.readOutput(stream)
                task.waitUntilExit()
                finish()
            }
        } catch {
            process = nil; pipe = nil; running = false
            canContinueRecovery = !scanFolder && !rescueFolder
            self.error = error.localizedDescription; status = "Could not start."
        }
    }
    func presentCompletion() {
        guard !running, !quitAfterStop, recoveryOutcome != nil else { return }
        if !completionReported {
            completionReported = true
            UsageStatistics.shared.send("rescue_complete", mode: recoveryMode, outcome: recoveryOutcome)
        }
        supportPromptPending = (recoveryOutcome?.saved ?? 0) > 0
        showingCompletion = true
    }
    func completionDismissed() {
        guard supportPromptPending else { return }
        supportPromptPending = false
        showingSupportPrompt = canShowSupport && (recoveryOutcome?.saved ?? 0) > 0
    }
    func readSummary(_ report: URL, folderMode: Bool) {
        guard let data = try? Data(contentsOf: report), let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return }
        if folderMode, let images = object["images"] as? [[String: Any]] {
            for row in images where !(row["status"] as? String ?? "").hasPrefix("ok_") { updateFile(row) }
        } else if let photos = object["photos"] as? [[String: Any]] { photos.forEach(updateFile) }
        if folderMode, let counts = object["counts"] as? [String: Int] {
            let total = counts.values.reduce(0, +)
            let flagged = counts.filter { !$0.key.hasPrefix("ok_") }.values.reduce(0, +)
            summary = "\(total) photos checked · \(flagged) need attention"
            if total == 0 && selectedCard != nil { needsDeepRescue = true }
            if let unreadable = object["unreadable_folders"] as? [[String: Any]], !unreadable.isEmpty {
                summary += " · \(unreadable.count) folders could not be read"
                if flagged == 0 { needsDeepRescue = true }
            }
        } else if let photos = object["photos"] as? [[String: Any]] {
            recoveryOutcome = RecoveryOutcome(photos: photos, wholeCardSearch: object["method"] as? String == "contiguous_jpeg_carving_v1")
            summary = recoveryOutcome?.text ?? ""
        }
    }

    func assessNormalRecovery(_ report: URL) {
        guard let data = try? Data(contentsOf: report),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let photos = object["photos"] as? [[String: Any]], !photos.isEmpty else {
            needsDeepRescue = true; return
        }
        needsDeepRescue = photos.contains { !["full_resolution", "full_resolution_copy"].contains($0["quality"] as? String ?? "") }
        if let scanReport, let data = try? Data(contentsOf: scanReport),
           let scan = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let unreadable = scan["unreadable_folders"] as? [[String: Any]], !unreadable.isEmpty {
            needsDeepRescue = true
        }
    }
    func stop() {
        guard let process, process.isRunning else { return }
        paused = true; status = "Stopping after preserving completed work…"
        process.interrupt()
    }
    func requestQuit() -> NSApplication.TerminateReply {
        guard running else { return .terminateNow }
        quitAfterStop = true; stop(); return .terminateLater
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        MainActor.assumeIsolated { UsageStatistics.shared.send("app_open") }
    }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        MainActor.assumeIsolated { RescueSession.shared.requestQuit() }
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}

private func actionLabel(_ title: String) -> some View {
    Text(title).frame(width: 140, height: 18).lineLimit(1)
}

private struct SupportLink: View {
    var body: some View {
        Button { UsageStatistics.shared.openCoffee() } label: {
            HStack(spacing: 6) {
                Image(systemName: "cup.and.saucer")
                Text("Buy me a coffee")
            }.frame(width: 140, height: 18)
        }
        .buttonStyle(.bordered)
        .help("If this helped, you’re welcome to buy me a coffee. Optional support via Ko-fi · Opens in your browser")
    }
}

struct RescueView: View {
    @ObservedObject var session = RescueSession.shared
    @State private var choosingCard = false
    @State private var activityExpanded = false
    private var hasSource: Bool { session.source != nil || session.selectedCard != nil }
    private var step: Int { session.hasSavedPhotos ? 3 : (hasSource ? 2 : 1) }
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 12) {
                Image(nsImage: NSImage(contentsOf: Bundle.main.resourceURL!.appendingPathComponent("cardme-mark.png")) ?? NSImage()).resizable().scaledToFit().frame(width: 40, height: 40)
                VStack(alignment: .leading, spacing: 3) {
                    Text("CardMe").font(.title2.bold())
                    Text("Photo recovery for memory cards.").font(.callout).foregroundStyle(.secondary)
                }
                Spacer()
                Button { session.showingAbout = true } label: { Image(systemName: "info.circle") }
                    .buttonStyle(.borderless).help("About CardMe and licenses").accessibilityLabel("About CardMe and licenses")
            }.fixedSize(horizontal: false, vertical: true)
            HStack(spacing: 16) {
                ForEach(Array(["Choose card", "Rescue photos", "View photos"].enumerated()), id: \.offset) { index, title in
                    HStack(spacing: 7) {
                        Image(systemName: index + 1 < step ? "checkmark.circle.fill" : "\(index + 1).circle.fill")
                        Text(title)
                    }
                    .font(.callout).foregroundStyle(index + 1 == step ? Color.primary : Color.secondary)
                    if index < 2 { Image(systemName: "chevron.right").font(.caption).foregroundStyle(.tertiary) }
                }
            }.accessibilityElement(children: .ignore)
                .accessibilityLabel("Step \(step) of 3: \(["Choose card", "Rescue photos", "View photos"][step - 1])")
            VStack(alignment: .leading, spacing: 14) {
                VStack(alignment: .leading, spacing: 12) {
                    if hasSource {
                        HStack {
                            if let source = session.source {
                                Label(session.selectedCard?.name ?? source.lastPathComponent, systemImage: session.scanFolder ? "externaldrive" : "doc")
                                    .font(.callout).foregroundStyle(.secondary).lineLimit(1).truncationMode(.middle)
                            } else if let card = session.selectedCard {
                                Label(card.name, systemImage: "externaldrive").font(.callout).foregroundStyle(.secondary)
                            }
                            Spacer()
                            if !session.running {
                                Button { choosingCard = true } label: { actionLabel("Change…") }.buttonStyle(.borderless)
                            }
                        }
                    }
                    Text(session.guidanceTitle).font(.system(size: 22, weight: .semibold))
                    if !hasSource {
                        Text("Connect your memory card to check for damaged or missing photos.")
                            .foregroundStyle(.secondary)
                    } else if session.running || session.error != nil || session.canContinueRecovery || session.canSearchDeeper {
                        Text(session.status).font(.callout).fixedSize(horizontal: false, vertical: true)
                    }
                    if session.running {
                        if let value = session.fraction { ProgressView(value: value) } else { ProgressView().progressViewStyle(.linear) }
                        Text("Keep the card and save drive connected until this step finishes.")
                            .font(.callout).foregroundStyle(.secondary)
                    }
                    if !session.summary.isEmpty { Text(session.summary).font(.callout).foregroundStyle(.secondary) }
                    if let warning = session.copyWarning {
                        Label(warning, systemImage: "exclamationmark.triangle").font(.callout).foregroundStyle(.orange)
                    }
                    if let error = session.error {
                        Label(error, systemImage: "exclamationmark.circle").font(.callout).textSelection(.enabled)
                    }
                    if !session.running && session.canSearchDeeper && !session.hasSavedPhotos {
                        Text("Search the whole card for missing photos. A safety copy is saved first; the next step explains the time and space needed.")
                            .font(.callout).foregroundStyle(.secondary)
                    } else if session.readyToRescue {
                        Text("Choose where to save the photos. Recovery starts automatically after you select a folder.")
                            .font(.callout).foregroundStyle(.secondary)
                    } else if !session.running && session.selectedCard != nil && session.scanReport != nil && session.damaged.isEmpty && !session.folderRescued {
                        Text("If photos are missing, try searching for deleted photos.")
                            .font(.callout).foregroundStyle(.secondary)
                    }
                    HStack(spacing: 12) {
                        if session.running {
                            Button(action: session.stop) { actionLabel(session.scanFolder ? "Stop safely" : "Pause safely") }
                        } else if session.hasSavedPhotos, let results = session.results {
                            if session.canShowSupport { SupportLink() }
                            Button { NSWorkspace.shared.open(results) } label: { actionLabel("View saved photos") }
                                .buttonStyle(.borderedProminent)
                        } else if session.canSearchDeeper {
                            Button(action: session.deepRescue) { actionLabel("Search deeper…") }.buttonStyle(.borderedProminent)
                        } else if session.readyToRescue {
                            Button(action: session.rescueFolder) { actionLabel("Rescue to…") }.buttonStyle(.borderedProminent)
                        } else if session.canContinueRecovery {
                            Button(action: session.continueRecovery) { actionLabel("Continue rescue") }.buttonStyle(.borderedProminent)
                        } else if hasSource && session.scanFolder {
                            Button { session.start() } label: { actionLabel("Check photos again") }.buttonStyle(.borderedProminent)
                        } else if !hasSource {
                            Button { choosingCard = true } label: { actionLabel("Choose card…") }.buttonStyle(.borderedProminent)
                        }
                    }
                    if !session.running && session.selectedCard != nil && session.scanReport != nil && (session.folderRescued || session.damaged.isEmpty) {
                        Button(action: session.deepRescue) {
                            Text(session.canSearchDeeper ? "Search for remaining photos…" : "Find deleted photos…")
                        }.buttonStyle(.link)
                    }
                }
                .padding(20).frame(maxWidth: .infinity, alignment: .leading)
                .background(.background, in: RoundedRectangle(cornerRadius: 12))
                .overlay(RoundedRectangle(cornerRadius: 12).stroke(.quaternary, lineWidth: 1))
                if !session.damaged.isEmpty {
                    PhotoReviewList(session: session, flexibleHeight: true)
                } else {
                    Spacer(minLength: 0)
                }
                if hasSource {
                    DisclosureGroup("Activity log and settings", isExpanded: $activityExpanded) {
                        VStack(alignment: .leading, spacing: 10) {
                            Toggle("Check photos more thoroughly next time (slower)", isOn: $session.fullScan).disabled(session.running)
                                .help("Decode every pixel on the next folder check")
                            Text("The quick check can miss some image damage. RAW photos aren’t checked. Open the saved photos to confirm the result.")
                                .font(.caption).foregroundStyle(.secondary)
                            if let image = session.safetyImage {
                                Button { NSWorkspace.shared.activateFileViewerSelecting([image]) } label: { actionLabel("Show safety copy") }
                            }
                            ScrollView {
                                Text(session.log.isEmpty ? "No activity yet." : session.log).font(.system(.caption, design: .monospaced))
                                    .textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
                            }.frame(height: 96)
                        }.padding(.top, 8).frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
            }.frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            VStack(alignment: .leading, spacing: 12) {
                Divider()
                HStack {
                    Label("Your card is read only. Recovery runs on this Mac.", systemImage: "lock.shield")
                        .font(.caption).foregroundStyle(.secondary)
                    Spacer()
                    Button(action: session.startOver) { actionLabel("Start over") }
                        .disabled(session.running)
                        .help("Return to choosing a card. Saved photos are kept.")
                    Button { NSApp.terminate(nil) } label: { actionLabel("Exit") }
                        .help("Stop safely and close CardMe")
                }
            }
        }.padding(24).frame(minWidth: 740, minHeight: 660)
            .background(ActivityWindowSizing(expanded: activityExpanded))
            .onChange(of: hasSource) { _, value in if !value { activityExpanded = false } }
            .buttonStyle(.bordered).controlSize(.regular).tint(.teal)
            .sheet(isPresented: $choosingCard) { CardChooser(session: session) }
            .sheet(isPresented: $session.showingAbout) { AboutView() }
            .sheet(isPresented: $session.showingCompletion, onDismiss: session.completionDismissed) {
                RecoveryCompleteView(session: session)
            }
            .alert("If this helped you, you’re welcome to buy me a coffee ☕️", isPresented: $session.showingSupportPrompt) {
                Button("Sure") { UsageStatistics.shared.openCoffee() }
                Button("Close", role: .cancel) { }
            }
    }
}

// Resize the owning window while keeping its top edge and the user's chosen width.
struct ActivityWindowSizing: NSViewRepresentable {
    var expanded: Bool
    func makeNSView(context: Context) -> WindowView { WindowView() }
    func updateNSView(_ view: WindowView, context: Context) { view.setExpanded(expanded) }
    final class WindowView: NSView {
        private var expanded = false
        private var addedHeight: CGFloat = 190
        func setExpanded(_ value: Bool) {
            guard value != expanded else { return }
            expanded = value
            guard let window, let screen = window.screen else { return }
            var frame = window.frame
            let height = min(frame.height + (value ? 190 : -addedHeight), screen.visibleFrame.height)
            if value { addedHeight = height - frame.height }
            frame.origin.y += frame.height - height
            frame.size.height = height
            frame.origin.y = max(screen.visibleFrame.minY, min(frame.origin.y, screen.visibleFrame.maxY - height))
            // Apply after SwiftUI has laid out the disclosure content.
            DispatchQueue.main.async { window.setFrame(frame, display: true, animate: true) }
        }
    }
}

private struct PhotoReviewList: View {
    @ObservedObject var session: RescueSession
    var showsFinder = true
    var flexibleHeight = false
    @FocusState private var listFocused: Bool
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("\(session.folderRescued || !session.scanFolder ? "Photos to review" : "Photos to rescue") (\(session.damaged.count))").font(.headline)
                Spacer()
                Button(action: session.previewSelected) { actionLabel("Open photo") }.disabled(session.selectedFileURL == nil)
                if showsFinder {
                    Button(action: session.revealSelected) { actionLabel("Show in Finder") }.disabled(session.selectedFileURL == nil)
                }
            }
            Text("Select a photo. Press Space to open it, or ↑ ↓ to move through the list.")
                .font(.caption).foregroundStyle(.secondary)
            ScrollViewReader { proxy in
                List(session.damaged, selection: $session.selectedID) { row in
                    HStack {
                        Image(systemName: row.fullSizeRecovered ? "checkmark.circle.fill" : "exclamationmark.triangle")
                            .foregroundStyle(row.fullSizeRecovered ? Color.teal : Color.orange)
                            .accessibilityLabel(row.fullSizeRecovered ? "Full-size photo saved" : "Full-size photo not recovered")
                        Text(row.name)
                        Spacer()
                        Text(row.detail).foregroundStyle(.secondary)
                    }.tag(row.id).id(row.id)
                        .listRowBackground(row.fullSizeRecovered ? Color.teal.opacity(0.07) : Color.clear)
                        .contentShape(Rectangle())
                        .onTapGesture { session.selectedID = row.id; listFocused = true }
                }.frame(minHeight: flexibleHeight ? 140 : 180, maxHeight: flexibleHeight ? .infinity : 180)
                    .focused($listFocused)
                    .onKeyPress(.space) { session.previewSelected(); return .handled }
                    .onKeyPress(.downArrow) { session.moveSelection(1); return .handled }
                    .onKeyPress(.upArrow) { session.moveSelection(-1); return .handled }
                    .onChange(of: session.selectedID) { _, id in
                        if let id { proxy.scrollTo(id) }
                    }
                    .onAppear { listFocused = true }
            }
        }
    }
}

struct RecoveryCompleteView: View {
    @ObservedObject var session: RescueSession
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            Text("Rescue complete").font(.title2.bold())
            if let outcome = session.recoveryOutcome {
                Grid(alignment: .leading, horizontalSpacing: 28, verticalSpacing: 10) {
                    result("Full-size photos", value: "\(outcome.fullSize) ✨")
                    result("Preview only", value: String(outcome.previews))
                    result("Tiny thumbnail only", value: String(outcome.thumbnails))
                    result("Not recovered", value: outcome.unrecovered.map(String.init) ?? "Unknown")
                    result("Saved · needs checking", value: String(outcome.review))
                }
                Text(outcome.unrecovered == nil ? "A whole-card search can’t tell how many photos were originally on the card. Found photos may include previews; please check the saved files." : "Previews and tiny thumbnails are smaller copies, not the original full-size photos.")
                    .font(.callout).foregroundStyle(.secondary)
                if session.hasSavedPhotos {
                    Text("Your photos are saved in the folder you chose. Your card was not changed.")
                        .font(.callout)
                }
            }
            if !session.damaged.isEmpty { PhotoReviewList(session: session, showsFinder: false) }
            HStack {
                Spacer()
                Button("Done") { dismiss() }
                    .keyboardShortcut(.defaultAction)
                    .buttonStyle(.borderedProminent)
            }
        }.padding(28).frame(width: 680).buttonStyle(.bordered).tint(.teal)
            .onExitCommand { dismiss() }
    }
    private func result(_ title: String, value: String) -> some View {
        GridRow {
            Text(title)
            Text(value).fontWeight(.semibold).monospacedDigit()
        }
    }
}

struct CardChooser: View {
    @ObservedObject var session: RescueSession
    @StateObject private var cards = CardDevices()
    @State private var selectedID: String?
    @Environment(\.dismiss) private var dismiss
    private var selected: CardDevice? { cards.devices.first { $0.id == selectedID } }
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Choose your card").font(.title2.bold())
            Text("Select your memory card below. CardMe will only read it.")
                .foregroundStyle(.secondary)
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    List(cards.loading ? [] : cards.devices, selection: $selectedID) { device in
                        HStack {
                            Image(systemName: "externaldrive")
                            VStack(alignment: .leading, spacing: 4) {
                                Text(device.volumes.isEmpty ? device.name : device.volumes.map(\.lastPathComponent).joined(separator: ", "))
                                Text("\(device.name) · \(ByteCountFormatter.string(fromByteCount: device.bytes, countStyle: .file)) · \(device.volumes.isEmpty ? "Files aren’t visible" : "Ready to check photos")")
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                            Spacer()
                        }.tag(device.id)
                    }.frame(height: 150)
                        .overlay {
                            if cards.loading {
                                HStack(spacing: 10) {
                                    ProgressView().controlSize(.small)
                                    Text("Loading connected devices…").foregroundStyle(.secondary)
                                }.accessibilityElement(children: .combine)
                            } else if cards.devices.isEmpty {
                                Text(cards.unavailable ? "macOS couldn’t provide the device list. You can still choose a photo folder." : "No card found. Connect your card with a working reader; it will appear here automatically.")
                                    .foregroundStyle(.secondary).multilineTextAlignment(.center).padding(20)
                            }
                        }
                    if let selected, selected.volumes.isEmpty {
                        Text(RescueSession.directDownload ? "The card is connected, but its files aren’t accessible. A whole-card search may find photos. A safety copy is required first." : "macOS detects this card, but its files aren’t accessible. \(RescueSession.safetyCopyLimitation) We won’t mount or repair your card.")
                            .font(.callout).foregroundStyle(.secondary)
                    } else if selected != nil {
                        Text(RescueSession.directDownload ? "The photos will be checked first. You can then choose where to save recovered copies." : "macOS will ask you to allow access to this card. Then we’ll check the photos.")
                            .font(.callout).foregroundStyle(.secondary)
                    }
                    DisclosureGroup("Use a folder or saved copy") {
                        VStack(alignment: .leading, spacing: 10) {
                            Text("You can also check photos in a folder or search a previously saved safety copy of a card.")
                                .font(.callout).foregroundStyle(.secondary)
                            HStack {
                                Button { dismiss(); session.chooseSource() } label: { actionLabel("Choose folder…") }
                                Button { dismiss(); session.chooseSavedImage() } label: { actionLabel("Use safety copy…") }
                                if session.hasPreviousRecovery {
                                    Button { dismiss(); session.resumePrevious() } label: { actionLabel("Continue rescue") }
                                }
                            }
                        }.padding(.top, 8)
                    }
                }.frame(maxWidth: .infinity, alignment: .leading)
            }.frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            HStack {
                Spacer()
                Button { dismiss() } label: { actionLabel("Cancel") }.keyboardShortcut(.cancelAction)
                Button {
                    guard let selected else { return }
                    dismiss()
                    session.chooseCard(selected)
                } label: { actionLabel(selected?.volumes.isEmpty == true && RescueSession.directDownload ? "Use this card" : "Check photos") }
                    .buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction)
                    .disabled(cards.loading || selected == nil || (selected?.volumes.isEmpty == true && !RescueSession.directDownload))
            }
        }.padding(20).frame(width: 600, height: 400).buttonStyle(.bordered).controlSize(.regular).tint(.teal)
    }
}

struct AboutView: View {
    @Environment(\.dismiss) private var dismiss
    private let resources = Bundle.main.resourceURL
    private let licenses = [
        ("CardMe · MIT", "CardMe-MIT.txt"),
        ("GNU ddrescue 1.30 · GPL-2.0-or-later", "ddrescue-GPL-2.0.txt"),
        ("CPython · PSF and historical licenses", "Python-LICENSE.txt"),
        ("Pillow and image codecs · upstream licenses", "Pillow-and-codecs-LICENSE.txt")
    ]
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            VStack(alignment: .leading, spacing: 5) {
                Text("CardMe").font(.title.bold())
                Text("Version \(Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "Development")")
                    .font(.caption).foregroundStyle(.secondary)
            }
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text("Photo recovery runs locally. CardMe reads your card and saves copies on another drive. Photos are never uploaded. Optional usage statistics can be turned off in Settings.")
                    Text("Small, useful things. Free to use.")
                        .font(.headline)
                    Text("If this helped, you’re welcome to buy me a coffee.")
                        .font(.callout).foregroundStyle(.secondary)
                    SupportLink()
                    Text("Thank you for your support.").font(.callout).foregroundStyle(.secondary)
                    Text("Deep Rescue searches safety copies for contiguous JPEGs, including after deletion or quick formatting. Direct exFAT rescue can try surviving photo fragments. Arbitrary fragment reconstruction and RAW recovery are currently not supported.")
                        .font(.callout).foregroundStyle(.secondary)
                    DisclosureGroup("Licenses and acknowledgements") {
                        VStack(alignment: .leading, spacing: 16) {
                            if let resources,
                               let notices = try? String(contentsOf: resources.appendingPathComponent("ThirdPartyLicenses/Notices.md"), encoding: .utf8) {
                                DisclosureGroup("Third-party notices and copyrights") {
                                    VStack(alignment: .leading, spacing: 12) {
                                        ForEach(notices.components(separatedBy: "\n").filter { !$0.isEmpty }, id: \.self) { line in
                                            Text((try? AttributedString(markdown: line)) ?? AttributedString(line))
                                                .font(line.hasPrefix("#") ? .headline : .callout).textSelection(.enabled)
                                        }
                                    }
                                }
                            }
                            ForEach(licenses, id: \.1) { entry in
                                if let resources,
                                   let text = try? String(contentsOf: resources.appendingPathComponent("ThirdPartyLicenses/" + entry.1), encoding: .utf8) {
                                    DisclosureGroup(entry.0) {
                                        Text(text).font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                                            .frame(maxWidth: .infinity, alignment: .leading)
                                    }
                                }
                            }
                            Button("Show included source and build instructions") {
                                if let resources { NSWorkspace.shared.open(resources.appendingPathComponent("ThirdPartySources")) }
                            }
                            Button("Show license files") {
                                if let resources { NSWorkspace.shared.open(resources.appendingPathComponent("ThirdPartyLicenses")) }
                            }
                        }.padding(.top, 10).frame(maxWidth: .infinity, alignment: .leading)
                    }
                  }.frame(maxWidth: .infinity, alignment: .leading)
            }
            HStack { Spacer(); Button("Done") { dismiss() }.keyboardShortcut(.cancelAction) }
        }.padding(24).frame(width: 600, height: 560).buttonStyle(.bordered).tint(.teal)
    }
}

#if !TESTING
@main
struct CardRescueApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var delegate
    var body: some Scene {
        WindowGroup { RescueView() }.defaultSize(width: 780, height: 700)
            .commands {
                CommandGroup(replacing: .newItem) {}
                CommandGroup(replacing: .appInfo) {
                    Button("About CardMe…") { RescueSession.shared.showingAbout = true }
                }
            }
        Settings { UsageSettingsView() }
    }
}

#endif
