import Foundation
import DiskArbitration
import Combine
import IOKit

enum ResultExport {
    static func card(at source: URL) throws -> CardDevice {
        let volume = try source.resourceValues(forKeys: [.volumeURLKey]).volume ?? source
        guard let session = DASessionCreate(kCFAllocatorDefault),
              let disk = DADiskCreateFromVolumePath(kCFAllocatorDefault, session, volume as CFURL),
              let device = CardDevices.device(disk, session: session) else { throw CocoaError(.fileReadUnknown) }
        return device
    }
    static func cardSize(at source: URL) throws -> Int64 { try card(at: source).bytes }
    static func validate(destination: URL, card: CardDevice) throws {
        let values = try destination.resourceValues(forKeys: [.volumeIsReadOnlyKey, .volumeIsRemovableKey])
        let volume = try destination.resourceValues(forKeys: [.volumeURLKey]).volume ?? destination
        guard values.volumeIsReadOnly == false, values.volumeIsRemovable == false,
              let session = DASessionCreate(kCFAllocatorDefault),
              let disk = DADiskCreateFromVolumePath(kCFAllocatorDefault, session, volume as CFURL),
              let whole = CardDevices.physicalWhole(disk, session: session),
              let bsd = DADiskGetBSDName(whole), String(cString: bsd) != card.id else { throw CocoaError(.fileWriteNoPermission) }
    }
    static func requireCapacity(available: Int64, cardBytes: Int64) throws {
        guard cardBytes > 0, available > cardBytes else { throw CocoaError(.fileWriteOutOfSpace) }
    }
    static func checkCapacity(at destination: URL, cardBytes: Int64) throws -> Int64 {
        let values = try destination.resourceValues(forKeys: [.volumeAvailableCapacityKey])
        guard let available = values.volumeAvailableCapacity else { throw CocoaError(.fileReadUnknown) }
        try requireCapacity(available: Int64(available), cardBytes: cardBytes)
        return Int64(available)
    }
    static func validate(source: URL, destination: URL) throws {
        let input = source.resolvingSymlinksInPath().standardizedFileURL
        let output = destination.resolvingSymlinksInPath().standardizedFileURL
        let sourceValues = try input.resourceValues(forKeys: [.volumeURLKey, .isDirectoryKey])
        let sourceVolume = sourceValues.volume
        let destinationValues = try output.resourceValues(forKeys: [.volumeURLKey, .volumeIsReadOnlyKey, .volumeIsRemovableKey])
        guard destinationValues.volumeIsReadOnly == false,
              destinationValues.volumeIsRemovable == false,
              output != input, !output.path.hasPrefix(input.path + "/"),
              !(sourceValues.isDirectory == true && input.path.hasPrefix(output.path + "/")),
              !(input.path.hasPrefix("/Volumes/") && sourceVolume == destinationValues.volume &&
                sourceValues.isDirectory == true) else {
            throw CocoaError(.fileWriteNoPermission)
        }
    }
    static func copy(from source: URL, to destination: URL) throws -> URL {
        let manager = FileManager.default
        let output = destination.appendingPathComponent("Rescued Photos " + UUID().uuidString.prefix(8), isDirectory: true)
        // copyItem fails on an existing destination; originals and prior results are preserved.
        try manager.copyItem(at: source, to: output)
        return output
    }
}


struct CardDevice: Identifiable {
    let id: String
    let name: String
    let bytes: Int64
    let volumes: [URL]
    var registryID: UInt64 = 0

    static func grouped(_ members: [CardDevice]) -> [CardDevice] {
        Dictionary(grouping: members, by: \.id).values.map { group in
            let first = group[0]
            return CardDevice(id: first.id, name: first.name, bytes: first.bytes,
                              volumes: Array(Set(group.flatMap(\.volumes))).sorted { $0.path < $1.path }, registryID: first.registryID)
        }.sorted { $0.id.localizedStandardCompare($1.id) == .orderedAscending }
    }
}

// Disk Arbitration only observes devices. No mount, repair or raw-device operations.
final class CardDevices: ObservableObject {
    @Published private(set) var devices: [CardDevice] = []
    @Published private(set) var unavailable = false
    @Published private(set) var loading = true
    private var session: DASession?
    private var disks: [String: DADisk] = [:]

    init() {
        guard let session = DASessionCreate(kCFAllocatorDefault) else { unavailable = true; loading = false; return }
        self.session = session
        let context = Unmanaged.passUnretained(self).toOpaque()
        DARegisterDiskAppearedCallback(session, nil, { disk, context in
            guard let context else { return }
            let owner = Unmanaged<CardDevices>.fromOpaque(context).takeUnretainedValue()
            if let name = DADiskGetBSDName(disk) { owner.disks[String(cString: name)] = disk }
            owner.refresh()
        }, context)
        DARegisterDiskDisappearedCallback(session, nil, { disk, context in
            guard let context else { return }
            let owner = Unmanaged<CardDevices>.fromOpaque(context).takeUnretainedValue()
            if let name = DADiskGetBSDName(disk) { owner.disks.removeValue(forKey: String(cString: name)) }
            owner.refresh()
        }, context)
        DARegisterDiskDescriptionChangedCallback(session, nil, nil, { _, _, context in
            guard let context else { return }
            Unmanaged<CardDevices>.fromOpaque(context).takeUnretainedValue().refresh()
        }, context)
        DASessionScheduleWithRunLoop(session, CFRunLoopGetMain(), CFRunLoopMode.defaultMode.rawValue)
        DispatchQueue.main.async { [weak self] in self?.loadInitialDevices() }
    }

    private func loadInitialDevices() {
        guard let session else { return }
        var iterator: io_iterator_t = 0
        guard IOServiceGetMatchingServices(kIOMainPortDefault, IOServiceMatching("IOMedia"), &iterator) == KERN_SUCCESS else {
            unavailable = true; loading = false; return
        }
        defer { IOObjectRelease(iterator) }
        var media = IOIteratorNext(iterator)
        while media != 0 {
            if let disk = DADiskCreateFromIOMedia(kCFAllocatorDefault, session, media), let name = DADiskGetBSDName(disk) {
                disks[String(cString: name)] = disk
            }
            IOObjectRelease(media)
            media = IOIteratorNext(iterator)
        }
        refresh()
        loading = false
    }

    deinit {
        if let session {
            DASessionUnscheduleFromRunLoop(session, CFRunLoopGetMain(), CFRunLoopMode.defaultMode.rawValue)
        }
    }

    static func isCardCandidate(internalDevice: Bool?, removable: Bool, connection: String?) -> Bool {
        (internalDevice == false || removable) && connection != "Virtual Interface" && connection != "Disk Image"
    }

    static func physicalWhole(_ disk: DADisk, session: DASession) -> DADisk? {
        // APFS volumes have a synthetic whole disk. Walk through it to the physical store.
        var whole = DADiskCopyWholeDisk(disk)
        var entry = DADiskCopyIOMedia(disk)
        while entry != 0 {
            let isWhole = IORegistryEntryCreateCFProperty(entry, "Whole" as CFString, kCFAllocatorDefault, 0)?.takeRetainedValue() as? Bool
            if isWhole == true, let parentDisk = DADiskCreateFromIOMedia(kCFAllocatorDefault, session, entry) { whole = parentDisk }
            var parent: io_registry_entry_t = 0
            let result = IORegistryEntryGetParentEntry(entry, kIOServicePlane, &parent)
            IOObjectRelease(entry)
            entry = result == KERN_SUCCESS ? parent : 0
        }
        return whole
    }

    static func device(_ disk: DADisk, session: DASession) -> CardDevice? {
        guard let whole = physicalWhole(disk, session: session),
              let description = DADiskCopyDescription(whole) as? [String: Any],
              let bsd = DADiskGetBSDName(whole),
              let size = description[kDADiskDescriptionMediaSizeKey as String] as? NSNumber,
              size.int64Value > 0 else { return nil }
        let internalDevice = description[kDADiskDescriptionDeviceInternalKey as String] as? Bool
        let removable = description[kDADiskDescriptionMediaRemovableKey as String] as? Bool ?? false
        let connection = description[kDADiskDescriptionDeviceProtocolKey as String] as? String
        guard isCardCandidate(internalDevice: internalDevice, removable: removable, connection: connection) else { return nil }
        let media = DADiskCopyIOMedia(whole)
        guard media != 0 else { return nil }
        defer { IOObjectRelease(media) }
        var registryID: UInt64 = 0
        guard IORegistryEntryGetRegistryEntryID(media, &registryID) == KERN_SUCCESS else { return nil }
        let volumeDescription = DADiskCopyDescription(disk) as? [String: Any]
        let path = volumeDescription?[kDADiskDescriptionVolumePathKey as String] as? URL
        return CardDevice(id: String(cString: bsd),
                          name: description[kDADiskDescriptionMediaNameKey as String] as? String ?? L("External device"),
                          bytes: size.int64Value, volumes: path.map { [$0] } ?? [], registryID: registryID)
    }
    private func refresh() {
        guard let session else { return }
        devices = CardDevice.grouped(disks.values.compactMap { Self.device($0, session: session) })
    }
}
