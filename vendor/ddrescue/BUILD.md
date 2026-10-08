# GNU ddrescue 1.30 corresponding source

The accompanying `ddrescue-1.30.tar.lz` is the unmodified upstream complete source, including COPYING, AUTHORS, configure, Makefile.in, documentation and test sources.

Source: https://ftp.gnu.org/gnu/ddrescue/ddrescue-1.30.tar.lz
SHA-256: `2264622d309d6c87a1cfc19148292b8859a688e9bc02d4702f5cd4f288745542`
License: GPL version 2 or, at your option, any later version.

Build on Apple Silicon with Xcode Command Line Tools:

```sh
tar -xf ddrescue-1.30.tar.lz
cd ddrescue-1.30
patch -p1 -i ../input-fd.patch
./configure CXX=clang++ 'CXXFLAGS=-O2 -arch arm64 -mmacosx-version-min=14.0'
make -j2 ddrescue
```

CardRescue invokes the patched executable as a separate program, does not link it into Swift or Python, and does not remove or restrict the user's GPL rights. The builder signs the executable for macOS distribution after compilation. The included input-fd.patch, by CardRescue contributors on October 7, 2026, changes input opening for /dev/fd/N to dup an already-open read-only descriptor. macOS otherwise rechecks permissions when reopening an authorized raw device. Normal filename input and all recovery algorithms remain upstream code. The patch is GPL-2.0-or-later and must accompany the source archive. This build recipe, the patch and the complete source archive accompany each direct-download app containing the binary, under Contents/Resources/ThirdPartySources. License and author notices accompany it under ThirdPartyLicenses.
