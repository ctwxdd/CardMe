#!/usr/bin/env python3
"""Build a self-contained Apple Silicon macOS app using an installed CPython/Pillow."""
import argparse, hashlib, json, os, pathlib, plistlib, shutil, subprocess, zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
release = json.loads((ROOT / 'VERSION.json').read_text())
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--python-home', type=pathlib.Path, default=ROOT / 'work/python-runtime')
p.add_argument('--stage-only', action='store_true', help='Prepare resources for the Xcode target, without compiling the app.')
p.add_argument('--destination', type=pathlib.Path)
p.add_argument('--build-dir', type=pathlib.Path, default=ROOT / 'build', help='Store app, DMG and build staging on this disk.')
p.add_argument('--sign-identity', default='-')
p.add_argument('--direct-download', action='store_true', help='Build outside App Sandbox for direct distribution with read-only card imaging.')
p.add_argument('--dmg', action='store_true', help='Package the direct-download app in a read-only DMG.')
args = p.parse_args()
if args.dmg and (not args.direct_download or args.stage_only):
    p.error('--dmg requires --direct-download and cannot use --stage-only')
if args.direct_download and args.stage_only:
    p.error('The Xcode staging target is sandboxed; use the standalone builder for direct download.')
signing = ['--sign', args.sign_identity]
if args.sign_identity != '-':
    signing += ['--options', 'runtime', '--timestamp']
runtime = args.python_home.resolve()
python = runtime / 'bin/python3'
if not python.is_file():
    p.error('Run python3 scripts/build-runtime.py first, or pass --python-home for the audited CPython runtime.')
metadata = json.loads(subprocess.check_output([str(python), '-c', 'import sys,json,sysconfig; print(json.dumps({"version":f"{sys.version_info.major}.{sys.version_info.minor}","modlibs":sysconfig.get_config_var("MODLIBS")}))']))
if metadata['version'] != '3.12' or 'readline' in (metadata['modlibs'] or ''):
    p.error('Use the audited minimal CPython 3.12 build from scripts/build-runtime.py.')
version = metadata['version']
build_dir = args.build_dir.resolve()
build_dir.mkdir(parents=True, exist_ok=True)
app = build_dir / 'CardMe.app'
if args.stage_only:
    if args.destination is None:
        p.error('--stage-only requires --destination')
    resources = args.destination.resolve()
    resources.mkdir(parents=True, exist_ok=True)
    for name in ['engine', 'python', 'ThirdPartySources', 'ThirdPartyLicenses', 'tools']:
        if (resources / name).exists():
            shutil.rmtree(resources / name)
else:
    if app.exists():
        shutil.rmtree(app)
    macos = app / 'Contents/MacOS'
    resources = app / 'Contents/Resources'
    macos.mkdir(parents=True)
    resources.mkdir()
    subprocess.run(['xcrun', 'swiftc', '-parse-as-library', '-swift-version', '5', '-O', '-target', 'arm64-apple-macosx14.0', '-module-cache-path', str(build_dir / 'ModuleCache'), str(ROOT / 'Sources/CardRescue.swift'), str(ROOT / 'Sources/ResultExport.swift'), '-o', str(macos / 'CardRescue')], check=True)
shutil.copytree(ROOT / 'engine', resources / 'engine', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
ranker = resources / 'engine/native/jpeg-ranker'
subprocess.run(['xcrun', 'clang++', '-O3', '-std=c++17', '-arch', 'arm64', '-mmacosx-version-min=14.0',
                str(ROOT / 'engine/native/jpeg-ranker.cpp'), '-o', str(ranker)], check=True)
subprocess.run(['codesign', '--force', *signing, str(ranker)], check=True)
shutil.copy2(ROOT / 'Config/PrivacyInfo.xcprivacy', resources / 'PrivacyInfo.xcprivacy')
shutil.copy2(ROOT / 'website/dist/assets/cardme-mark.png', resources / 'cardme-mark.png')
licenses = resources / 'ThirdPartyLicenses'
licenses.mkdir(exist_ok=True)
shutil.copy2(ROOT / 'THIRD_PARTY_NOTICES.md', licenses / 'Notices.md')
shutil.copy2(ROOT / 'LICENSE', licenses / 'CardMe-GPL-3.0.txt')
shutil.copy2(ROOT / 'NOTICE', licenses / 'CardMe-Copyright.txt')
sources = resources / 'ThirdPartySources'
sources.mkdir(exist_ok=True)
python_source = ROOT / 'vendor/python/Python-3.12.14.tar.xz'
if hashlib.sha256(python_source.read_bytes()).hexdigest() != '5c8462af5790baf43a321a1559dbe0db06d1be4300fb85fb53c40060668e548a':
    raise SystemExit('CPython source checksum mismatch')
shutil.copy2(python_source, sources / python_source.name)
shutil.copy2(ROOT / 'scripts/build-runtime.py', sources / 'build-runtime.py')
shutil.copy2(ROOT / 'vendor/python/BUILD.md', sources / 'Python-BUILD.md')
if args.direct_download:
    source_archive = ROOT / 'vendor/ddrescue/ddrescue-1.30.tar.lz'
    if hashlib.sha256(source_archive.read_bytes()).hexdigest() != '2264622d309d6c87a1cfc19148292b8859a688e9bc02d4702f5cd4f288745542':
        raise SystemExit('ddrescue source checksum mismatch')
    rescue_build = build_dir / 'ddrescue-build'
    if rescue_build.exists():
        shutil.rmtree(rescue_build)
    rescue_build.mkdir()
    subprocess.run(['tar', '-xf', str(source_archive), '-C', str(rescue_build)], check=True)
    rescue_source = rescue_build / 'ddrescue-1.30'
    subprocess.run(['patch', '-p1', '-i', str(ROOT / 'vendor/ddrescue/input-fd.patch')], cwd=rescue_source, check=True)
    subprocess.run(['./configure', 'CXX=clang++', 'CXXFLAGS=-O2 -arch arm64 -mmacosx-version-min=14.0'], cwd=rescue_source, check=True)
    subprocess.run(['make', '-j2', 'ddrescue'], cwd=rescue_source, check=True)
    tools = resources / 'tools'
    tools.mkdir()
    shutil.copy2(rescue_source / 'ddrescue', tools / 'ddrescue')
    links = subprocess.check_output(['otool', '-L', str(tools / 'ddrescue')], text=True)
    for line in links.splitlines()[1:]:
        if not line.strip().startswith(('/usr/lib/', '/System/Library/')):
            raise SystemExit('Non-portable ddrescue dependency')
    shutil.copy2(source_archive, sources / source_archive.name)
    shutil.copy2(ROOT / 'vendor/ddrescue/BUILD.md', sources / 'ddrescue-BUILD.md')
    shutil.copy2(ROOT / 'vendor/ddrescue/input-fd.patch', sources / 'input-fd.patch')
    shutil.copy2(rescue_source / 'COPYING', licenses / 'ddrescue-GPL-2.0.txt')
    shutil.copy2(rescue_source / 'AUTHORS', licenses / 'ddrescue-AUTHORS.txt')

embedded = resources / 'python'
(embedded / 'bin').mkdir(parents=True)
shutil.copy2(python.resolve(), embedded / 'bin/python3')
stdlib = runtime / 'lib' / ('python' + version)
shutil.copy2(stdlib / 'LICENSE.txt', licenses / 'Python-LICENSE.txt')
shutil.copytree(stdlib, embedded / 'lib' / stdlib.name, ignore=shutil.ignore_patterns('site-packages', '*.a', '__pycache__', '*.pyc', 'test', 'tests', 'idlelib', 'tkinter', 'ensurepip'))
site = embedded / 'lib' / stdlib.name / 'site-packages'
site.mkdir()
wheel = ROOT / 'vendor/pillow/pillow-12.3.0-cp312-cp312-macosx_11_0_arm64.whl'
if hashlib.sha256(wheel.read_bytes()).hexdigest() != 'ffd0c5368496f41b0944be820fcb7a838aa6e623d250b01acf2643939c3f99d7':
    raise SystemExit('Pillow wheel checksum mismatch')
with zipfile.ZipFile(wheel) as archive:
    archive.extractall(site)
shutil.copy2(site / 'pillow-12.3.0.dist-info/licenses/LICENSE', licenses / 'Pillow-and-codecs-LICENSE.txt')
# Python and its extensions must link only to macOS system libraries.
# CPython's executable is statically linked in this runtime; extension libraries
# must use @loader_path/@rpath or system paths to remain relocatable.
for path in embedded.rglob('*'):
    if path.is_file() and (path.suffix in {'.so', '.dylib'} or path == embedded / 'bin/python3'):
        links = subprocess.check_output(['otool', '-L', str(path)], text=True)
        for line in links.splitlines()[1:]:
            dependency = line.strip().split(' (')[0]
            if dependency.startswith('/DLC/PIL/.dylibs/') and (site / 'PIL/.dylibs' / pathlib.Path(dependency).name).is_file():
                if pathlib.Path(dependency).name == path.name:
                    subprocess.run(['install_name_tool', '-id', '@loader_path/' + pathlib.Path(dependency).name, str(path)], check=True, stderr=subprocess.DEVNULL)
                else:
                    subprocess.run(['install_name_tool', '-change', dependency, '@loader_path/' + pathlib.Path(dependency).name, str(path)], check=True, stderr=subprocess.DEVNULL)
                continue
            if dependency.startswith('/') and not dependency.startswith(('/usr/lib/', '/System/Library/')):
                raise SystemExit(f'Non-portable dependency: {path.name}: {dependency}')
# Normalize codec signatures after install_name_tool edits, before importing Pillow.
for path in embedded.rglob('*'):
    if path.is_file() and (path.suffix in {'.so', '.dylib'} or path == embedded / 'bin/python3'):
        subprocess.run(['codesign', '--force', '--sign', '-', str(path)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
# Prove Python/Pillow work from the relocated, isolated bundle.
env = {**os.environ, 'PYTHONHOME': str(embedded), 'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1'}
env.pop('PYTHONPATH', None)
subprocess.run([str(embedded / 'bin/python3'), '-B', str(resources / 'engine/scan-images.py'), '--self-test'], env=env, check=True)
subprocess.run([str(embedded / 'bin/python3'), '-B', str(resources / 'engine/decision-model.py'), '--self-test'], env=env, check=True)
if args.stage_only:
    for path in embedded.rglob('*'):
        if path.is_file() and path.suffix in {'.so', '.dylib'}:
            subprocess.run(['codesign', '--force', '--sign', args.sign_identity, str(path)], check=True, stderr=subprocess.DEVNULL)
    subprocess.run(['codesign', '--force', '--sign', args.sign_identity, '--entitlements', str(ROOT / 'Config/Helper.entitlements'), str(embedded / 'bin/python3')], check=True)
    print(resources)
    raise SystemExit(0)
iconset = build_dir / 'CardRescue.iconset'
iconset.mkdir(parents=True, exist_ok=True)
for icon in (ROOT / 'Sources/Assets.xcassets/AppIcon.appiconset').glob('*.png'):
    name = icon.name.replace('@1x', '')
    shutil.copy2(icon, iconset / name)
subprocess.run(['iconutil', '-c', 'icns', str(iconset), '-o', str(resources / 'CardRescue.icns')], check=True)
info = {'CFBundleName': 'CardMe', 'CFBundleDisplayName': 'CardMe', 'CFBundleIdentifier': 'com.nick.cardrescue',
        'CFBundleExecutable': 'CardRescue', 'CFBundleIconFile': 'CardRescue.icns', 'CFBundlePackageType': 'APPL', 'CFBundleShortVersionString': release['version'],
        'CFBundleVersion': str(release['build']), 'LSMinimumSystemVersion': '14.0', 'NSHighResolutionCapable': True,
        'NSRemovableVolumesUsageDescription': 'CardMe reads selected photos and saved card images. Recovery results are saved to your chosen fixed disk or SSD.',
        'NSDocumentsFolderUsageDescription': 'CardMe saves reports and rescued photos only to the folder you choose.',
        'NSDownloadsFolderUsageDescription': 'CardMe reads selected images and writes results to your chosen folder.',
        'LSApplicationCategoryType': 'public.app-category.photography',
        'CardRescueDirectDownload': args.direct_download}
if args.direct_download:
    info['CFBundleIdentifier'] = 'com.nick.cardrescue.direct'
    info['CFBundleDisplayName'] = 'CardMe'
with (app / 'Contents/Info.plist').open('wb') as out:
    plistlib.dump(info, out)
# Direct download omits sandbox/inheritance entitlements. Developer ID is optional for local builds.
for path in embedded.rglob('*'):
    if path.is_file() and (path.suffix in {'.so', '.dylib'} or path == embedded / 'bin/python3'):
        subprocess.run(['codesign', '--force', *signing, str(path)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
helper_entitlements = [] if args.direct_download else ['--entitlements', str(ROOT / 'Config/Helper.entitlements')]
app_entitlements = [] if args.direct_download else ['--entitlements', str(ROOT / 'Config/CardRescue.entitlements')]
subprocess.run(['codesign', '--force', *signing, *helper_entitlements, str(embedded / 'bin/python3')], check=True)
if args.direct_download:
    subprocess.run(['codesign', '--force', *signing, str(resources / 'tools/ddrescue')], check=True)
subprocess.run(['codesign', '--force', *signing, *app_entitlements, str(app)], check=True)
subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True)
print(app)
if args.dmg:
    import tempfile
    dmg = build_dir / 'CardMe.dmg'
    with tempfile.TemporaryDirectory(prefix='CardRescue-DMG-', dir=build_dir) as staging:
        staging = pathlib.Path(staging)
        shutil.copytree(app, staging / app.name, symlinks=True)
        (staging / 'Applications').symlink_to('/Applications')
        (staging / 'Read Me.txt').write_text(
            'Drag CardMe.app to Applications.\n\n'
            + ('This local build is not notarized for public distribution.\n' if args.sign_identity == '-' else '') +
            'It lists connected devices and scans accessible photos without writing to the card.\n'
            'Normal rescue reads flagged files. Deep Rescue first makes a whole-card safety copy; macOS may ask for authorization.\n'
            'GNU ddrescue source and licenses are inside the app: Contents/Resources/ThirdPartySources and ThirdPartyLicenses.\n'
            'Deleted or quickly formatted cards: Deep Rescue searches the safety copy for JPEG photos and can reassemble some two- or three-part camera JPEGs using their indexed previews.\n'
            'Original filenames may be unavailable. Found JPEGs can include previews; check the results.\n'
            'Other fragmented JPEGs, RAW files and overwritten data may remain unresolved. Rebuilt photos need checking.\n'
        )
        subprocess.run(['hdiutil', 'create', '-ov', '-format', 'UDZO', '-volname', 'CardMe', '-srcfolder', str(staging), str(dmg)], check=True)
    if args.sign_identity != '-':
        subprocess.run(['codesign', '--force', '--sign', args.sign_identity, '--timestamp', str(dmg)], check=True)
    print(dmg)
