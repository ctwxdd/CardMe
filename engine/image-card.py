#!/usr/bin/env python3
"""Read-only card imaging using Apple's authopen and a separately bundled ddrescue."""
import argparse
import array
import ctypes
import fcntl
import errno
import json
import os
from pathlib import Path
import re
import signal
import socket
import stat
import subprocess
import sys
import time

children = []
stopped = False


def stop(_signal, _frame):
    global stopped
    stopped = True
    for child in children:
        if child.poll() is None:
            child.send_signal(signal.SIGINT)


def device_identity(device):
    if not re.fullmatch(r'disk[0-9]+', device):
        raise ValueError('Select a whole physical card, not a partition.')
    import plistlib
    description = plistlib.loads(subprocess.check_output(['/usr/sbin/diskutil', 'info', '-plist', device]))
    if not description.get('WholeDisk') or description.get('VirtualOrPhysical') != 'Physical':
        raise ValueError('This is not a whole physical device.')
    if description.get('Internal') is not False and not description.get('RemovableMedia'):
        raise ValueError('Internal non-removable disks cannot be copied.')
    io = ctypes.CDLL('/System/Library/Frameworks/IOKit.framework/IOKit')
    io.IOBSDNameMatching.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_char_p]
    io.IOBSDNameMatching.restype = ctypes.c_void_p
    io.IOServiceGetMatchingService.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    io.IOServiceGetMatchingService.restype = ctypes.c_uint
    entry = io.IOServiceGetMatchingService(0, io.IOBSDNameMatching(0, 0, device.encode()))
    if not entry:
        raise ValueError('The selected card is no longer connected.')
    identity = ctypes.c_uint64()
    try:
        if io.IORegistryEntryGetRegistryEntryID(entry, ctypes.byref(identity)) != 0:
            raise ValueError('Could not identify the selected card.')
    finally:
        io.IOObjectRelease(entry)
    block_size = description['DeviceBlockSize']
    if not isinstance(block_size, int) or block_size < 512 or block_size > 65536 or block_size & (block_size - 1):
        raise ValueError('Unsupported physical sector size.')
    return identity.value, description['TotalSize'], block_size


def receive_read_descriptor(reader):
    reader.settimeout(1)
    while True:
        if stopped:
            raise InterruptedError('Copy stopped before card access was granted.')
        try:
            _, ancillary, flags, _ = reader.recvmsg(1, socket.CMSG_SPACE(array.array('i').itemsize))
            break
        except socket.timeout:
            continue
    descriptors = array.array('i')
    for level, kind, data in ancillary:
        if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
            descriptors.frombytes(data[:len(data) - len(data) % descriptors.itemsize])
    if flags & socket.MSG_CTRUNC or len(descriptors) != 1:
        for fd in descriptors:
            os.close(fd)
        raise PermissionError('macOS couldn’t open the card. It may be in use, disconnected, or access was not granted. No card data was changed.')
    fd = descriptors[0]
    if fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE != os.O_RDONLY:
        os.close(fd)
        raise PermissionError('Refusing a writable source descriptor.')
    return fd


def authorized_read(path):
    # Apple's helper obtains a read-only descriptor. Our process never runs as root.
    reader, writer = socket.socketpair()
    try:
        child = subprocess.Popen(['/usr/libexec/authopen', '-stdoutpipe', '-o', str(os.O_RDONLY), path], stdout=writer, stderr=sys.stderr)
        children.append(child)
        writer.close()
        return receive_read_descriptor(reader)
    finally:
        reader.close()
        writer.close()
        if 'child' in locals():
            if child.poll() is None:
                child.terminate()
            child.wait()
            children.remove(child)


def map_counts(path, total):
    counts = {status: 0 for status in '?*/-+'}
    end = 0
    if not path.exists():
        return counts
    for line in path.read_text().splitlines():
        parts = line.split()
        if not parts or parts[0].startswith('#'):
            continue
        if len(parts) != 3:
            raise ValueError('Invalid safety-copy progress map.')
        if parts[1] in counts:
            continue  # current-position header
        start, size = int(parts[0], 0), int(parts[1], 0)
        if start != end or size <= 0 or parts[2] not in counts:
            raise ValueError('Invalid safety-copy progress map.')
        # Raw devices have unknown length to ddrescue; their map extends beyond --size.
        counts[parts[2]] += min(size, max(0, total - start))
        end = start + size
    return counts


def read_card_range(fd, offset, length, total, sector_size):
    """Read a byte range through sector-aligned, bounded raw-device requests."""
    if fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE != os.O_RDONLY:
        raise ValueError('Refusing a writable source descriptor.')
    if offset < 0 or length < 0 or offset + length > total:
        raise ValueError('Recovery extent outside card.')
    if length == 0:
        return b''
    start = offset // sector_size * sector_size
    end = (offset + length + sector_size - 1) // sector_size * sector_size
    chunks = []
    position = start
    while position < end:
        size = min(1024 * 1024, end - position)
        chunk = os.pread(fd, size, position)
        if len(chunk) != size:
            raise OSError('The card could not fully read a required photo region.')
        chunks.append(chunk)
        position += size
    return b''.join(chunks)[offset - start:offset - start + length]


def copy_fd(fd, total, output, tool, verify=None, sector_size=512):
    if total <= 0 or fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE != os.O_RDONLY:
        raise ValueError('A positive size and read-only source are required.')
    output.mkdir(mode=0o700)  # exclusive private directory; never overwrite another image
    image, mapfile = output / 'card.img', output / 'card.map'
    # Reserve the image name exclusively. ddrescue subsequently fills this owned file.
    output_fd = os.open(image, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    errors_path = output / 'copy-errors.log'
    errors = errors_path.open('x')
    try:
        for phase, options in [('copy', ['-n']), ('retry', ['-r2'])]:
            if verify:
                verify()
            if phase == 'retry' and map_counts(mapfile, total)['+'] == total:
                break
            command = [str(tool), '--sector-size=' + str(sector_size), '--size=' + str(total), '--extend-outfile=' + str(total),
                       '--mapfile-interval=1,5', '--timeout=30', *options, '/dev/fd/' + str(fd), '/dev/fd/' + str(output_fd), str(mapfile)]
            child = subprocess.Popen(command, pass_fds=(fd, output_fd), stdout=subprocess.DEVNULL, stderr=errors)
            children.append(child)
            try:
                while child.poll() is None:
                    if verify:
                        verify()
                    if stopped:
                        child.send_signal(signal.SIGINT)
                    counts = map_counts(mapfile, total)
                    print('IMAGING\t' + json.dumps({'done': counts['+'], 'total': total, 'phase': phase}), flush=True)
                    time.sleep(0.5)
                if stopped:
                    raise InterruptedError('Copy stopped. The partial image and progress map are preserved.')
                if child.returncode != 0:
                    errors.flush()
                    with errors_path.open('rb') as diagnostic:
                        diagnostic.seek(max(0, errors_path.stat().st_size - 4096))
                        detail = diagnostic.read().decode('utf-8', errors='replace').strip()
                    raise OSError('Safety copying stopped. The partial copy and diagnostic log are preserved. ' + detail)
            finally:
                if child.poll() is None:
                    child.send_signal(signal.SIGINT)
                child.wait()
                children.remove(child)
        if verify:
            verify()
        counts = map_counts(mapfile, total)
        if counts['+'] + counts['-'] != total or image.stat().st_size != total:
            raise OSError('The card could not be fully read. Its partial safety copy is preserved.')
        saved = os.fstat(output_fd)
        named = image.stat()
        if (saved.st_dev, saved.st_ino) != (named.st_dev, named.st_ino):
            raise OSError('The destination changed during copying. The card is untouched.')
        os.fsync(output_fd)
        report = {'bytes': total, 'rescued_bytes': counts['+'], 'unreadable_bytes': counts['-'], 'image': str(image)}
        (output / 'copy-report.json').write_text(json.dumps(report, indent=2))
        print('IMAGING\t' + json.dumps({'done': counts['+'], 'total': total, 'phase': 'finished'}), flush=True)
        return report
    finally:
        errors.close()
        os.close(output_fd)


def destination_description(folder):
    # df resolves arbitrary subfolders to their mounted filesystem device.
    import plistlib
    rows = subprocess.check_output(['/bin/df', '-P', str(folder)], text=True).strip().splitlines()
    device = rows[-1].split()[0] if len(rows) > 1 else ''
    if not re.fullmatch(r'/dev/disk[0-9]+(?:s[0-9]+)*', device):
        raise ValueError('Choose a save folder on a local disk or SSD.')
    return plistlib.loads(subprocess.check_output(['/usr/sbin/diskutil', 'info', '-plist', device]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', required=True)
    parser.add_argument('--registry-id', type=int, required=True)
    parser.add_argument('--bytes', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--tool', type=Path, required=True)
    args = parser.parse_args()
    expected = (args.registry_id, args.bytes)
    identity = device_identity(args.device)
    if identity[:2] != expected:
        raise ValueError('The card changed. Select it again before recovery.')
    output = args.output.resolve()
    if output.exists() or not output.parent.is_dir():
        raise ValueError('A fresh safety-copy folder is required.')
    if os.statvfs(output.parent).f_bavail * os.statvfs(output.parent).f_frsize <= args.bytes:
        raise OSError('Not enough storage for the full card. Choose another drive.')
    # Independently reject a destination on the same physical card.
    dest = destination_description(output.parent)
    if dest.get('ParentWholeDisk') == args.device or any(s.get('APFSPhysicalStore', '').startswith(args.device + 's') for s in dest.get('APFSPhysicalStores', [])):
        raise ValueError('The safety copy must be saved on another physical device.')
    raw = '/dev/r' + args.device
    source_stat = os.stat(raw)
    if not stat.S_ISCHR(source_stat.st_mode):
        raise ValueError('The source must be a raw physical device.')
    print('Waiting for macOS permission to read your card…', flush=True)
    fd = authorized_read(raw)
    try:
        if device_identity(args.device)[:2] != expected or os.fstat(fd).st_rdev != source_stat.st_rdev:
            raise ValueError('The card changed while waiting for permission. Select it again.')
        try:
            fcntl.fcntl(fd, fcntl.F_NOCACHE, 1)
        except OSError as error:
            # Raw character devices already bypass caching and may reject this hint.
            if error.errno not in (errno.EINVAL, errno.ENOTSUP, errno.ENOTTY):
                raise
        def verify():
            if device_identity(args.device)[:2] != expected:
                raise ValueError('The card was disconnected or changed. Its partial safety copy is preserved.')
        copy_fd(fd, args.bytes, output, args.tool.resolve(), verify=verify, sector_size=identity[2])
    finally:
        os.close(fd)


if __name__ == '__main__':
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        main()
    except InterruptedError as error:
        print(str(error), flush=True)
        sys.exit(130)
    except subprocess.CalledProcessError:
        print("macOS couldn’t identify the card or save drive. Check the connection and select a local save folder again.", flush=True)
        sys.exit(1)
    except Exception as error:
        print(str(error), flush=True)
        sys.exit(1)
