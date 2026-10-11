"""Checksum-valid exFAT photo entry hints found in the current image's scan chunks."""
import struct


def collect(data, base, heap, cluster, count):
    records = []
    for flags in (1, 3):
        cursor = 0
        signature = bytes((0xc0, flags, 0))
        while True:
            at = data.find(signature, cursor)
            if at < 0:
                break
            cursor = at + 1
            first = at - 32
            if first < 0 or (base + first - heap) % 32 or data[first] != 0x85:
                continue
            secondary = data[first+1]
            if not 2 <= secondary <= 18 or first + (secondary+1)*32 > len(data):
                continue
            entries = data[first:first+(secondary+1)*32]
            if struct.unpack_from('<H', entries, 4)[0] & 16:
                continue
            if any(entries[i] != 0xc1 for i in range(64,len(entries),32)):
                continue
            checksum = 0
            for i, value in enumerate(entries):
                if i not in (2,3):
                    checksum = (((checksum & 1) << 15) + (checksum >> 1) + value) & 65535
            if checksum != struct.unpack_from('<H',entries,2)[0]:
                continue
            stream = entries[32:64]
            name_length = stream[3]
            if not 1 <= name_length <= 255 or secondary != 1 + (name_length + 14)//15:
                continue
            names = b''.join(entries[i+2:i+32] for i in range(64,len(entries),32))
            try:
                name = names[:name_length*2].decode('utf-16-le')
            except UnicodeError:
                continue
            if '/' in name or '\\' in name or '\x00' in name or not name.lower().endswith(('.jpg','.jpeg')):
                continue
            start = struct.unpack_from('<I',stream,20)[0]
            length = struct.unpack_from('<Q',stream,24)[0]
            initialized = struct.unpack_from('<Q',stream,8)[0]
            if not 2 <= start < count+2 or not 0 < initialized == length <= 128*1024*1024:
                continue
            offset = heap + (start-2)*cluster
            if offset + length > heap + count*cluster:
                continue
            records.append({'offset':offset,'original_filename_hint':name,'directory_bytes_hint':length,
                            'directory_entry_offset':base+first,'directory_contiguous_hint':bool(flags & 2)})
    return records
