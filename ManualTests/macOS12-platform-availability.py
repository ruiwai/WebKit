#!/usr/bin/env python3
# Copyright (C) 2026 WebKit contributors. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Check deployment-target gates with a newer SDK; no target execution required."""

from pathlib import Path
import subprocess
import unittest


class PlatformAvailabilityTest(unittest.TestCase):
    def check_definitions(self, architecture, target, definitions):
        root = Path(__file__).resolve().parents[1]
        source = '#include <wtf/Platform.h>\n'
        for expression, expected in definitions.items():
            source += f'#if {expression} != {expected}\n#error Incorrect deployment gate for {expression}\n#endif\n'
        result = subprocess.run([
            'xcrun', '--sdk', 'macosx', 'clang++', '-x', 'c++',
            '-std=c++20', '-fsyntax-only', '-arch', architecture,
            f'-mmacosx-version-min={target}', '-I', str(root / 'Source/WTF'), '-'
        ], input=source, text=True, capture_output=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_objc_custom_dealloc_requires_macos13(self):
        for architecture in ('arm64', 'x86_64'):
            for target, expected in (('12.0', 0), ('12.7', 0), ('13.0', 1), ('14.0', 1)):
                with self.subTest(architecture=architecture, target=target):
                    self.check_definitions(architecture, target, {'HAVE(OBJC_CUSTOM_DEALLOC)': expected})

    def test_passkit_deployment_boundaries(self):
        for architecture in ('arm64', 'x86_64'):
            for target, payments, deferred in (('12.0', 0, 0), ('12.7', 0, 0), ('13.0', 1, 0), ('13.2', 1, 0), ('13.3', 1, 1), ('14.0', 1, 1)):
                with self.subTest(architecture=architecture, target=target):
                    self.check_definitions(architecture, target, {
                        'ENABLE(APPLE_PAY)': 1,
                        'HAVE(PASSKIT_FRAMEWORK)': 1,
                        'HAVE(PASSKIT_AUTOMATIC_RELOAD_SUMMARY_ITEM)': payments,
                        'HAVE(PASSKIT_RECURRING_PAYMENTS)': payments,
                        'HAVE(PASSKIT_AUTOMATIC_RELOAD_PAYMENTS)': payments,
                        'HAVE(PASSKIT_MULTI_MERCHANT_PAYMENTS)': payments,
                        'HAVE(PASSKIT_PAYMENT_ORDER_DETAILS)': payments,
                        'HAVE(PASSKIT_DEFERRED_PAYMENTS)': deferred,
                    })


if __name__ == '__main__':
    unittest.main()
