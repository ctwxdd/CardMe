# Minimal CPython 3.12.14 for CardRescue

Unmodified upstream source: https://www.python.org/ftp/python/3.12.14/Python-3.12.14.tar.xz
SHA-256: `5c8462af5790baf43a321a1559dbe0db06d1be4300fb85fb53c40060668e548a`

Source, copyright notices and license texts are included in the accompanying archive. The app also includes Python-LICENSE.txt. CPython licenses allow redistribution with notices retained; this build does not link GNU readline.

Run `python3 scripts/build-runtime.py` from the repository with Xcode Command Line Tools. The included script builds the interpreter and records the disabled modules in Modules/Setup.local. No upstream source code is patched. The build uses macOS system expat and libffi, and disables readline, SSL, bzip2, lzma, decimal, Tk, curses, gdbm and dbm, which the recovery engine does not need. Hashing uses CPython's built-in implementations, including the source's HACL notices. Pillow is installed by the app builder from the separate pinned upstream arm64 CPython 3.12 wheel, preserving its full combined license file.

For a standalone reproduction outside the repository, place this archive under vendor/python/, and the included build-runtime.py under scripts/, create work/, then run the script. The installed runtime is under work/python-runtime/. Its libraries must resolve only to macOS system paths; the app builder checks this before distribution.
