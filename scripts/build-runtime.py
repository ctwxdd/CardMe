#!/usr/bin/env python3
"""Build the app's minimal CPython with macOS libraries, without GNU readline."""
import hashlib
import os
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
source_archive = root / 'vendor/python/Python-3.12.14.tar.xz'
assert hashlib.sha256(source_archive.read_bytes()).hexdigest() == '5c8462af5790baf43a321a1559dbe0db06d1be4300fb85fb53c40060668e548a'
build = root / 'work/python-build'
build.mkdir(exist_ok=True)
source = build / 'Python-3.12.14'
if not source.exists():
    subprocess.run(['tar', '-xf', str(source_archive), '-C', str(build)], check=True)
prefix = root / 'work/python-runtime'
(source / 'Modules/Setup.local').write_text('*disabled*\nreadline _ssl _hashlib _bz2 _lzma _decimal _tkinter _curses _curses_panel _gdbm _dbm\n')
sdk = subprocess.check_output(['xcrun', '--show-sdk-path'], text=True).strip()
env = {**os.environ, 'PKG_CONFIG': '/usr/bin/false', 'CC': 'clang',
       'CFLAGS': '-O2 -arch arm64 -mmacosx-version-min=14.0',
       'LIBFFI_CFLAGS': '-I' + sdk + '/usr/include/ffi', 'LIBFFI_LIBS': '-lffi'}
subprocess.run(['./configure', '--prefix=' + str(prefix), '--without-ensurepip', '--with-system-expat', '--disable-test-modules'], cwd=source, env=env, check=True)
subprocess.run(['make', '-j8'], cwd=source, env=env, check=True)
# Installation byte-compilation is unnecessary: runtime sources ship as .py.
subprocess.run(['make', '-j8', 'install', 'compileall='], cwd=source, env=env, check=True)
subprocess.run([str(prefix / 'bin/python3'), '-c', "import ctypes,fcntl,hashlib,plistlib,socket,sysconfig; assert 'readline' not in sysconfig.get_config_var('MODLIBS'); print('Minimal CPython checked')"], check=True)
print(prefix)
