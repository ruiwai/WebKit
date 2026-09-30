#!/usr/bin/env python3
# Copyright (C) 2026 WebKit contributors. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Assemble and check a relocatable, ad-hoc-signed development release."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / 'WebKitBuild/CI-arm64'
LOGS = ROOT / 'WebKitBuild/CI-logs'
PACKAGE = ROOT / 'WebKitBuild/CI-package/MacOS12-arm64'
DIST = ROOT / 'dist'
FRAMEWORKS = ('JavaScriptCore', 'WebCore', 'WebKit', 'WebKitLegacy', 'WebGPU', 'WebInspectorUI')
DYLIBS = ('libANGLE-shared.dylib', 'libWebKitSwift.dylib', 'libwebrtc.dylib')
LAUNCHER = '''#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
products="$root/Release"
export DYLD_FRAMEWORK_PATH="$products" DYLD_LIBRARY_PATH="$products"
export __XPC_DYLD_FRAMEWORK_PATH="$products" __XPC_DYLD_LIBRARY_PATH="$products"
if [ "${1-}" = "--smoke-test" ]; then
    exec "$root/back-deployment-smoke" "$products"
fi
if [ "$#" -eq 0 ]; then set -- --url about:blank; fi
exec "$products/MiniBrowser.app/Contents/MacOS/MiniBrowser" "$@"
'''
NOTES = '''# Experimental macOS 12-targeted arm64 WebKit

Best-effort optimized development build: **not** Developer ID-signed, notarized,
or an up-to-date security-supported browser. Built on macOS 26 with Xcode 26.3;
this toolchain/optimization combination has not been certified on Monterey.
See BUILD-METADATA.json for the exact source, SDK, settings and any LTO fallback.
The project may disable LTO for individual targets even in the ThinLTO attempt.

Extract into a fresh directory, keep all relative links/frameworks/helpers, then:

    ./MacOS12-arm64/RunMiniBrowser.command --smoke-test
    ./MacOS12-arm64/RunMiniBrowser.command --url https://example.com/

Do not replace system frameworks. Launching MiniBrowser directly may use system
WebKit. The smoke checks local HTML/JS/Wasm/rendering, not remote networking.
CI smoke results are from macOS 26, **not** exhaustive macOS 12 validation.
Basic Monterey browsing was reported for the earlier Xcode 16.2 revision-3 build;
that result does not establish equivalence for this release. Test networking,
media, camera, DRM, sharing and stability separately before relying on it.
'''


def run(*command):
    try:
        return subprocess.check_output(command, cwd=ROOT, text=True, stderr=subprocess.STDOUT).strip()
    except subprocess.CalledProcessError as error:
        print(error.output, file=sys.stderr)
        raise


def version(text):
    names = ('MAJOR', 'MINOR', 'TINY', 'MICRO', 'NANO')
    values = []
    for name in names:
        matches = re.findall(rf'^{name}_VERSION = (\d+);$', text, re.M)
        if len(matches) != 1:
            raise ValueError(f'Missing or ambiguous {name}_VERSION')
        values.append(matches[0])
    return '.'.join(values)


def check_tag(number, ref_type, ref_name):
    if ref_type == 'tag' and ref_name != f'v{number}-macos12-arm64':
        raise ValueError(f'Tag does not match Configurations/Version.xcconfig: {ref_name}')


def prepare_project(text):
    # Xcode 26 creates this link itself. Leave Xcode 16 projects unchanged outside CI.
    phase = '\t\t\t\t1A07D2F51919AA8A00ECDA16 /* Make Frameworks Symbolic Link */,\n'
    if text.count(phase) != 1:
        raise ValueError('Unexpected WebKit project layout; review the Xcode 26 workaround')
    return text.replace(phase, '', 1)


def audit(root):
    root = root.resolve()
    magic = {bytes.fromhex(value) for value in ('feedface', 'cefaedfe', 'feedfacf', 'cffaedfe', 'cafebabe', 'bebafeca', 'cafebabf', 'bfbafeca')}
    count = 0
    for path in root.rglob('*'):
        if path.is_symlink():
            if not path.exists() or not path.resolve().is_relative_to(root):
                raise ValueError(f'Broken or escaping symlink: {path}')
            continue
        if not path.is_file():
            continue
        with path.open('rb') as stream:
            if stream.read(4) not in magic:
                continue
        if run('lipo', '-archs', str(path)) != 'arm64':
            raise ValueError(f'Non-arm64 binary: {path}')
        minimums = re.findall(r'\bminos (\S+)', run('otool', '-l', str(path)))
        if minimums != ['12.0']:
            raise ValueError(f'Unexpected deployment target: {path}: {minimums}')
        run('codesign', '--verify', '--strict', str(path))
        imports = run('xcrun', 'nm', '-m', '-u', str(path))
        if '__class_setCustomDeallocInitiation' in imports or '__objc_deallocOnMainThreadHelper' in imports:
            raise ValueError(f'Unexpected custom-deallocation hook import: {path}')
        count += 1
    for item in (root / 'Release').iterdir():
        if item.suffix in ('.framework', '.app', '.xpc'):
            run('codesign', '--verify', '--deep', '--strict', str(item))
    for name in ('jsc', 'JavaScriptCore.framework/Versions/A/Helpers/jsc',
                 'com.apple.WebKit.WebContent.xpc', 'com.apple.WebKit.WebContent.Development.xpc'):
        data = subprocess.check_output(['codesign', '-d', '--entitlements', ':-', str(root / 'Release' / name)], stderr=subprocess.DEVNULL)
        if plistlib.loads(data).get('com.apple.security.cs.allow-jit') is not True:
            raise ValueError(f'Missing JIT entitlement: {name}')
    if count != 23:
        raise ValueError(f'Unexpected Mach-O inventory ({count}, expected 23); review packaging')
    run('sh', '-n', str(root / 'RunMiniBrowser.command'))
    if not os.access(root / 'RunMiniBrowser.command', os.X_OK):
        raise ValueError('Launcher is not executable')
    return f'PASS: {count} arm64/minos-12.0 binaries, signatures, JIT entitlements, contained links and no custom-deallocation hook imports.\n'


def package(number):
    if PACKAGE.exists():
        raise ValueError(f'Package already exists; use a clean build directory: {PACKAGE}')
    products = BUILD / 'Release'
    helpers = sorted(products.glob('com.apple.WebKit*.xpc'))
    if len(helpers) != 6:
        raise ValueError(f'Expected six XPC bundles, got {len(helpers)}')
    release = PACKAGE / 'Release'
    release.mkdir(parents=True)
    names = ['MiniBrowser.app', 'jsc', *DYLIBS, *(name + '.framework' for name in FRAMEWORKS), *(path.name for path in helpers)]
    for name in names:
        run('ditto', str(products / name), str(release / name))
    shutil.copy2(BUILD / 'back-deployment-smoke', PACKAGE / 'back-deployment-smoke')
    (PACKAGE / 'RunMiniBrowser.command').write_text(LAUNCHER)
    (PACKAGE / 'RunMiniBrowser.command').chmod(0o755)
    (PACKAGE / 'README.md').write_text(NOTES)
    (release / 'WebCore.framework/Versions/A/Frameworks').mkdir(exist_ok=True)
    framework = release / 'WebKit.framework/Versions/A'
    for directory in ('XPCServices', 'Frameworks'):
        for link in (framework / directory).iterdir():
            target = link.resolve(strict=True)
            if not link.is_symlink() or target.parent != release:
                raise ValueError(f'Unexpected embedded helper layout: {link}')
            link.unlink()
            target.rename(link)
            target.symlink_to(link.relative_to(release))
    stubs = list(release.rglob('*.tbd'))
    for path in stubs:
        if not path.resolve().is_relative_to(release):
            raise ValueError(f'Escaping stub: {path}')
    for path in stubs:
        path.unlink()
    entitlement = LOGS / 'jsc.entitlements'
    entitlement.write_bytes(plistlib.dumps({'com.apple.security.cs.allow-jit': True}))
    for executable in (release / 'jsc', release / 'JavaScriptCore.framework/Versions/A/Helpers/jsc'):
        run('codesign', '--force', '--sign', '-', '--preserve-metadata=identifier,flags,runtime', '--entitlements', str(entitlement), str(executable))
    for name in FRAMEWORKS:
        run('codesign', '--force', '--sign', '-', '--preserve-metadata=identifier,entitlements,flags,runtime', str(release / (name + '.framework')))
    metadata = {
        'version': number, 'commit': run('git', 'rev-parse', 'HEAD'),
        'tag': os.environ.get('GITHUB_REF_NAME', ''),
        'run_url': f"{os.environ.get('GITHUB_SERVER_URL', '')}/{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}",
        'host': run('sw_vers', '-productVersion'), 'xcode': run('xcodebuild', '-version'),
        'sdk': run('xcrun', '--sdk', 'macosx', '--show-sdk-version'),
        'architecture': 'arm64', 'deployment_target': '12.0',
        'configuration': 'Release', 'c_cpp_optimization': '-O3',
        'c_cpp_extra_warning_flags': '-Wno-error=unused-but-set-variable',
        'swift_optimization': '-O, wholemodule',
        'requested_lto_mode': (LOGS / 'lto-mode.txt').read_text().strip(),
        'lto_note': 'Project-specific deployment gates remain in force; not necessarily enabled for every target.',
        'debug_symbols': False, 'signing': 'ad-hoc; not notarized',
        'ci_project_patch': (LOGS / 'xcode26-project.patch').read_text(),
        'monterey_validation': 'Not performed for this toolchain/optimization combination.',
    }
    (PACKAGE / 'BUILD-METADATA.json').write_text(json.dumps(metadata, indent=2) + '\n')
    result = audit(PACKAGE)
    (PACKAGE / 'VERIFICATION.txt').write_text(result)
    print(result, end='')


def archive(number):
    # The workflow reaches this only after both native smoke commands succeeded.
    for name, marker in (('jsc-smoke.txt', 'PASS: JavaScript and Wasm validation'),
                         ('browser-smoke.txt', 'PASS: page snapshot')):
        if not (LOGS / name).is_file() or marker not in (LOGS / name).read_text():
            raise ValueError(f'Missing successful smoke log: {name}')
        shutil.copy2(LOGS / name, PACKAGE / name)
    DIST.mkdir(exist_ok=True)
    target = DIST / f'WebKit-{number}-macOS12-arm64.tar.gz'
    if target.exists():
        raise ValueError(f'Archive already exists: {target}')
    with tarfile.open(target, 'w:gz', dereference=False) as stream:
        stream.add(PACKAGE, arcname=PACKAGE.name)
    with tempfile.TemporaryDirectory(prefix='webkit-archive-') as temporary:
        # This is our own just-created archive, not downloaded/untrusted input.
        run('tar', '-xzf', str(target), '-C', temporary)
        verification = audit(Path(temporary) / PACKAGE.name)
    verification += 'PASS: archive extraction rechecked; JavaScript/Wasm and browser smoke on macOS 26.\nNOT TESTED: this optimized build on macOS 12.\n'
    (DIST / 'VERIFICATION.txt').write_text(verification)
    shutil.copy2(PACKAGE / 'BUILD-METADATA.json', DIST / 'BUILD-METADATA.json')
    (DIST / 'RELEASE.md').write_text(NOTES)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_name(target.name + '.sha256').write_text(f'{digest}  {target.name}\n')
    print(verification, end='')
    print(f'{target.name}: {digest}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('version', 'prepare', 'package', 'archive'))
    options = parser.parse_args()
    os.chdir(ROOT)
    number = version((ROOT / 'Configurations/Version.xcconfig').read_text())
    check_tag(number, os.environ.get('GITHUB_REF_TYPE'), os.environ.get('GITHUB_REF_NAME'))
    LOGS.mkdir(parents=True, exist_ok=True)
    if options.operation == 'version':
        print(number)
    elif options.operation == 'prepare':
        if not run('xcodebuild', '-version').startswith('Xcode 26.'):
            raise ValueError('This build-graph workaround is for Xcode 26 only')
        project = ROOT / 'Source/WebKit/WebKit.xcodeproj/project.pbxproj'
        project.write_text(prepare_project(project.read_text()))
    elif options.operation == 'package':
        package(number)
    else:
        archive(number)


if __name__ == '__main__':
    main()
