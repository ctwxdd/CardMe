# Public JPEG regression material

These unmodified files come from [libjpeg-turbo](https://github.com/libjpeg-turbo/libjpeg-turbo/tree/43ea809765004508d8da72ebe562cf570c6a62b2/testimages), pinned at commit `43ea809765004508d8da72ebe562cf570c6a62b2`. `manifest.json` records exact source URLs, sizes and SHA-256 hashes. The test checks every hash before use and runs offline. Upstream authors retain their copyrights; these fixtures are not relicensed under CardMe's GPL.

- `testorig.jpg`, `testimgint.jpg`, `testimgari.jpg`: original IJG JPEG tests, under the IJG terms in `README.ijg`.
- `shira_bird8.bmp`: public photographic content from the libjpeg-turbo test suite, under the Modified (3-clause) BSD license in `LICENSE.md`.
- `vgl_5674_0098.png`: public detailed image content from the same suite, under the Modified BSD license. Its embedded ICC profile has separate unrestricted distribution terms.

The upstream `LICENSE.txt`, `LICENSE.md` and `README.ijg` are included verbatim. Refer to them for copyright, license and disclaimer notices.

Run from the repository root with the audited bundled CPython 3.12/Pillow runtime:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONHOME=/path/CardMe.app/Contents/Resources/python \
  /path/CardMe.app/Contents/Resources/python/bin/python3 -B tests/public-jpeg-check.py
```

Seven cases cover preservation of the public JPEG files, a derived progressive JPEG and synthetic two-part MPF reconstruction based on public image pixels. The reconstruction fixtures are resized/re-encoded to 2400×1600, with **synthetic** EXIF, thumbnail, MPF and indexed preview. They are not original Canon files, real corrupted-card images, or an independent camera dataset. Two bird fixtures use different cut positions and EXIF orientations. A high-detail image records the current conservative preview-agreement refusal, despite complete source bytes. Arithmetic JPEG records the current original-marker parser limitation and lossless decoded PNG fallback.

Reconstruction goes through the normal exFAT recovery entrypoint and real allocation/directory parsing, with sector-aligned reads, no private recipe and no historical card. Expected complete photo bytes are checked only after rescue returns. The test checks exact source extents, orientation, indexed preview, source preservation and temporary-file cleanup. Inputs and outputs live in an automatically cleaned temporary directory; a machine-readable result is saved to ignored `work/public-jpeg-regression.json`.

Expected limitation cases are explicitly classified; passing this suite does not mean those photos were reconstructed. The suite complements the existing synthetic three/four-fragment, ambiguity, cancellation and budget tests. It does not measure recovery rates, qualify real hardware, or prove support for arbitrary fragmentation. Original public files are never written to during the test and are not bundled in the consumer app.
