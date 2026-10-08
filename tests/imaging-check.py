#!/usr/bin/env python3
"""Run the real bundled ddrescue on disposable fixtures, never on a card."""
import importlib.util
import os
from pathlib import Path
import signal
import tempfile
import threading
import sys
import socket
import shlex
import array
from unittest.mock import patch

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('imaging', root / 'engine/image-card.py')
imaging = importlib.util.module_from_spec(spec)
spec.loader.exec_module(imaging)
tool = Path(os.environ.get('CARDME_DDRESCUE', str(root / 'build/CardMe.app/Contents/Resources/tools/ddrescue')))
with tempfile.TemporaryDirectory(prefix='CardRescue-imaging-check-') as temporary:
    folder = Path(temporary)
    original = folder / 'source.bin'
    payload = bytes(range(256)) * 12288
    original.write_bytes(payload)
    before = original.stat()
    destination = imaging.destination_description(folder)
    assert destination['DeviceIdentifier'].startswith('disk')
    fd = os.open(original, os.O_RDONLY)
    for sector in [512, 4096]:
        pread = os.pread
        requests = []
        def aligned_read(source_fd, size, offset):
            assert size % sector == 0 and offset % sector == 0 and size <= 1024 * 1024
            requests.append((offset, size))
            return pread(source_fd, size, offset)
        with patch.object(imaging.os, 'pread', side_effect=aligned_read):
            assert imaging.read_card_range(fd, 123, 1048700, len(payload), sector) == payload[123:1048823]
        assert len(requests) == 2
        with patch.object(imaging.os, 'pread', return_value=b''):
            try:
                imaging.read_card_range(fd, 123, 100, len(payload), sector)
                raise AssertionError('Short card read accepted')
            except OSError:
                pass
    for offset, size in [(-1, 512), (0, -1), (len(payload) - 1, 2)]:
        try:
            imaging.read_card_range(fd, offset, size, len(payload), 512)
            raise AssertionError('Invalid card range accepted')
        except ValueError:
            pass
    sender, receiver = socket.socketpair()
    try:
        sender.sendmsg([b"x"], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [fd]))])
        received = imaging.receive_read_descriptor(receiver)
        assert os.pread(received, 512, 0) == payload[:512]
        os.close(received)
    finally:
        sender.close(); receiver.close()
    try:
        report = imaging.copy_fd(fd, len(payload), folder / 'complete', tool)
        assert report['unreadable_bytes'] == 0
        assert (folder / 'complete/card.img').read_bytes() == payload
        # A descriptor remains authorized even when its backing pathname cannot be reopened.
        original.chmod(0)
        try:
            protected = imaging.copy_fd(fd, len(payload), folder / 'protected', tool)
            assert protected['unreadable_bytes'] == 0
            assert (folder / 'protected/card.img').read_bytes() == payload
        finally:
            original.chmod(0o600)
        four_k = imaging.copy_fd(fd, len(payload), folder / 'four-k', tool, sector_size=4096)
        assert four_k['unreadable_bytes'] == 0 and (folder / 'four-k/card.img').read_bytes() == payload
        try:
            imaging.copy_fd(fd, len(payload), folder / 'complete', tool)
            raise AssertionError('Existing output accepted')
        except FileExistsError:
            pass
        testmap = folder / 'bad-sector.map'
        testmap.write_text('0x0 + 1\n0x0 0x200 +\n0x200 0x200 -\n0x400 ' + hex(len(payload)-1024) + ' +\n')
        wrapper = folder / 'bad-sector-tool'
        wrapper.write_text('#!/bin/sh\nexec ' + shlex.quote(str(tool)) + ' --test-mode=' + shlex.quote(str(testmap)) + ' "$@"\n')
        wrapper.chmod(0o755)
        bad = imaging.copy_fd(fd, len(payload), folder / 'bad', wrapper)
        assert bad['unreadable_bytes'] == 512
        saved = (folder / 'bad/card.img').read_bytes()
        assert len(saved) == len(payload) and saved[:512] == payload[:512] and saved[1024:] == payload[1024:]
        slow = folder / 'slow-tool'
        slow.write_text('#!/bin/sh\nexec ' + shlex.quote(str(tool)) + ' --max-read-rate=65536 "$@"\n')
        slow.chmod(0o755)
        timer = threading.Timer(0.3, lambda: imaging.stop(signal.SIGINT, None))
        timer.start()
        try:
            imaging.copy_fd(fd, len(payload), folder / 'stopped', slow)
            raise AssertionError('Cancellation ignored')
        except InterruptedError:
            assert (folder / 'stopped/card.img').exists()
            assert (folder / 'stopped/card.map').exists()
        finally:
            timer.join()
            imaging.stopped = False
        calls = 0
        def changed_card():
            global calls
            calls += 1
            if calls > 1:
                raise ValueError("Card connection changed")
        try:
            imaging.copy_fd(fd, len(payload), folder / 'changed', tool, verify=changed_card)
            raise AssertionError('Changed card accepted')
        except ValueError:
            assert not (folder / 'changed/copy-report.json').exists()
        assert not imaging.children
    finally:
        os.close(fd)
    writable = os.open(original, os.O_RDWR)
    try:
        try:
            imaging.read_card_range(writable, 0, 512, len(payload), 512)
            raise AssertionError('Writable raw source accepted')
        except ValueError:
            pass
        try:
            imaging.copy_fd(writable, len(payload), folder / 'unsafe', tool)
            raise AssertionError('Writable source accepted')
        except ValueError:
            assert not (folder / 'unsafe').exists()
    finally:
        os.close(writable)
    progress = folder / 'raw-device.map'
    # A raw device's progress map may extend past the requested byte count.
    total = 8 * 1024 * 1024
    done = total // 2
    progress.write_text(f'# current_pos current_status current_pass\n{done:#x} ? 1\n'
                        f'0x00000000 {done:#x} +\n{done:#x} 0x7FFFFFFFFFFFFFFF ?\n')
    counts = imaging.map_counts(progress, total)
    assert counts['+'] == done and counts['?'] == total - counts['+']
    assert sum(counts.values()) == total
    for status in '?*/-+':
        progress.write_text(f'0 + 1\n0 {total - 512} +\n{total - 512} 1024 {status}\n'
                            f'{total + 512} 1024 +\n')
        counts = imaging.map_counts(progress, total)
        assert sum(counts.values()) == total
        assert counts['+'] == (total if status == '+' else total - 512)
        assert (counts['+'] + counts['-'] == total) == (status in '+-')
    progress.write_text('0 512 +\n')
    assert imaging.map_counts(progress, total)['+'] == 512  # incomplete cannot certify completion
    assert imaging.map_counts(folder / 'missing.map', total)['+'] == 0
    for malformed in ['0x100 0x200 +\n', '0 512 +\n256 512 ?\n', '0 0 +\n',
                      '0 512 x\n', '0 512\n', f'0 {total} +\n{total + 1} 512 ?\n']:
        progress.write_text(malformed)
        try:
            imaging.map_counts(progress, total)
            raise AssertionError('Invalid map accepted')
        except ValueError:
            pass
    assert original.read_bytes() == payload and original.stat().st_mtime_ns == before.st_mtime_ns
print('Imaging checks passed: complete copy, bad-sector reporting, cancellation, conflicts and unchanged source.')
