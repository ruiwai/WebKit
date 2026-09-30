#!/usr/bin/env python3
# Copyright (C) 2026 WebKit contributors. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('release', Path(__file__).with_name('macos12-release.py'))
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def test_progress_bar_size_mapping(self):
        text = (release.ROOT / 'Source/WebCore/platform/graphics/mac/controls/ProgressBarMac.mm').read_text()
        marker = 'auto coreUISizeForProgressBarSize = '
        self.assertEqual(text.count(marker), 1)
        mapping = text.split(marker, 1)[1].split('\n    };', 1)[0] + '\n};'
        source = '''#import <AppKit/AppKit.h>
static CFStringRef kCUISizeSmall = CFSTR("small");
static CFStringRef kCUISizeRegular = CFSTR("regular");
int main() {
    auto mapping = ''' + mapping + '''
    if (mapping(NSControlSizeMini) != kCUISizeSmall || mapping(NSControlSizeSmall) != kCUISizeSmall)
        return 1;
    if (mapping(NSControlSizeRegular) != kCUISizeRegular || mapping(NSControlSizeLarge) != kCUISizeRegular)
        return 2;
    if (mapping(static_cast<NSControlSize>(4)) != kCUISizeRegular || mapping(static_cast<NSControlSize>(99)) != kCUISizeRegular)
        return 3;
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            executable = str(Path(directory) / 'sizes')
            result = subprocess.run(['xcrun', '--sdk', 'macosx', 'clang++', '-x', 'objective-c++',
                                     '-std=c++20', '-Werror', '-mmacosx-version-min=12.0',
                                     '-framework', 'AppKit', '-', '-o', executable],
                                    input=source, capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stderr)
            subprocess.run([executable], check=True, timeout=30)

    def test_current_version(self):
        text = (release.ROOT / 'Configurations/Version.xcconfig').read_text()
        number = release.version(text)
        self.assertRegex(number, r'^\d+(\.\d+){4}$')
        release.check_tag(number, 'tag', f'v{number}-macos12-arm64')
        with self.assertRaises(ValueError):
            release.check_tag(number, 'tag', 'v0.0.0.0.0-macos12-arm64')
        release.check_tag(number, 'branch', 'webkit-619.1.x')
        with self.assertRaises(ValueError):
            release.version(text + '\nMAJOR_VERSION = 1;\n')

    def test_graph_workaround_is_narrow_and_fail_closed(self):
        text = (release.ROOT / 'Source/WebKit/WebKit.xcodeproj/project.pbxproj').read_text()
        result = release.prepare_project(text)
        removed = '\t\t\t\t1A07D2F51919AA8A00ECDA16 /* Make Frameworks Symbolic Link */,\n'
        self.assertEqual(result, text.replace(removed, ''))
        self.assertEqual(len(text.splitlines()) - len(result.splitlines()), 1)
        with self.assertRaises(ValueError):
            release.prepare_project(result)

    def test_build_fallback_control_flow(self):
        # Mock commands verify ordering/failure propagation, not compiler behavior.
        for failure in ('none', 'thin', 'all', 'source'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                fake = root / 'xcodebuild'
                fake.write_text('''#!/usr/bin/env python3
import json, os, sys
with open(os.environ['XCODE_CALLS'], 'a') as stream:
    stream.write(json.dumps(sys.argv[1:]) + '\\n')
mode = next(value for value in sys.argv if value.startswith('WK_LTO_MODE='))
if os.environ['FAIL_MODE'] == 'source':
    print("fixture.cpp:1:1: error: missing declaration")
    sys.exit(1)
sys.exit(1 if os.environ['FAIL_MODE'] == 'all' or mode == 'WK_LTO_MODE=' + os.environ['FAIL_MODE'] else 0)
''')
                fake.chmod(0o755)
                for name in ('xcrun', 'codesign'):
                    command = root / name
                    command.write_text('#!/bin/sh\nexit 0\n')
                    command.chmod(0o755)
                environment = dict(os.environ, PATH=str(root) + os.pathsep + os.environ['PATH'],
                                   FAIL_MODE=failure, XCODE_CALLS=str(root / 'calls'), BUILD_JOBS='1')
                result = subprocess.run(['bash', str(release.ROOT / '.github/scripts/build-macos12-arm64.sh')],
                                        cwd=root, env=environment, capture_output=True, text=True, timeout=30)
                calls = [json.loads(line) for line in (root / 'calls').read_text().splitlines()]
                mode_file = root / 'WebKitBuild/CI-logs/lto-mode.txt'
                if failure in ('all', 'source'):
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(mode_file.exists())
                    self.assertEqual(len(calls), 1 if failure == 'source' else 2)
                else:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(mode_file.read_text().strip(), 'none' if failure == 'thin' else 'thin')
                    successful = calls[-8:]
                    self.assertEqual([call[call.index('-scheme') + 1] for call in successful],
                                     ['bmalloc', 'WTF', 'libwebrtc', 'JavaScriptCore', 'WebGPU', 'ANGLE (dynamic)', 'WebCore', 'Everything up to MiniBrowser'])
                    for call in successful:
                        self.assertIn('GCC_OPTIMIZATION_LEVEL=3', call)


if __name__ == '__main__':
    unittest.main()
