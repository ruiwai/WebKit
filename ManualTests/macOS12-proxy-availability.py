#!/usr/bin/env python3
# Copyright (C) 2026 WebKit contributors. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Run the production proxy setter with and without the newer Cocoa selector.

This isolated test runs on the build host without a WebKit build or Monterey.
It uses the real method body and RetainPtr, with a small session fixture and
Objective-C test doubles for old/new NSURLSessionConfiguration objects.
"""

from pathlib import Path
import subprocess
import tempfile
import unittest


class ProxyAvailabilityTest(unittest.TestCase):
    def test_proxy_configuration_selector(self):
        root = Path(__file__).resolve().parents[1]
        implementation = (root / 'Source/WebKit/NetworkProcess/cocoa/NetworkSessionCocoa.mm').read_text()
        signature = 'void NetworkSessionCocoa::applyProxyConfigurationToSessionConfiguration(NSURLSessionConfiguration *configuration)'
        self.assertEqual(implementation.count(signature), 1, 'Update the fixture extraction if the production method is renamed or moved')
        method = signature + implementation.split(signature, 1)[1].split('\n}\n', 1)[0] + '\n}\n'
        source = r'''
#import <Foundation/Foundation.h>
#import <Network/NSURLSession+Network.h>
#include <vector>
#include <wtf/RetainPtr.h>

@interface LegacyConfiguration : NSObject
@property (copy) NSDictionary *connectionProxyDictionary;
@end
@implementation LegacyConfiguration
@end

@interface ModernConfiguration : LegacyConfiguration
@property (copy) NSArray *proxyConfigurations;
@end
@implementation ModernConfiguration
@end

struct Configurations : std::vector<RetainPtr<NSObject>> {
    bool isEmpty() const { return empty(); }
};
struct NetworkSessionCocoa {
    Configurations m_nwProxyConfigs;
    void applyProxyConfigurationToSessionConfiguration(NSURLSessionConfiguration *);
};
''' + method + r'''
int main()
{
    @autoreleasepool {
        @try {
            NetworkSessionCocoa session;
            auto token = [NSObject new];
            for (bool hasProxy : { false, true }) {
                session.m_nwProxyConfigs.clear();
                if (hasProxy)
                    session.m_nwProxyConfigs.push_back(token);

                auto legacy = [LegacyConfiguration new];
                legacy.connectionProxyDictionary = @{ @"HTTPEnable": @1 };
                session.applyProxyConfigurationToSessionConfiguration((NSURLSessionConfiguration *)legacy);
                if (![legacy.connectionProxyDictionary isEqual:@{ @"HTTPEnable": @1 }]) {
                    NSLog(@"FAIL: legacy proxy settings changed");
                    return 1;
                }

                auto modern = [ModernConfiguration new];
                modern.proxyConfigurations = @[ @"previous proxy" ];
                session.applyProxyConfigurationToSessionConfiguration((NSURLSessionConfiguration *)modern);
                if (![modern.proxyConfigurations isEqual:(hasProxy ? @[ token ] : @[ ])]) {
                    NSLog(@"FAIL: supported setter did not apply or clear proxies");
                    return 1;
                }
            }
            NSLog(@"PASS: missing selector is skipped; existing proxies preserved; supported setter applies and clears proxies");
        } @catch (NSException *exception) {
            NSLog(@"FAIL: %@", exception);
            return 1;
        }
    }
    return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix='webkit-proxy-availability-') as directory:
            executable = str(Path(directory) / 'test')
            compile_result = subprocess.run([
                'xcrun', '--sdk', 'macosx', 'clang++', '-x', 'objective-c++',
                '-std=c++20', '-fobjc-arc', '-DNDEBUG', '-O2', '-mmacosx-version-min=12.0',
                '-I', str(root / 'Source/WTF'), '-framework', 'Foundation',
                '-', '-o', executable
            ], input=source, text=True, capture_output=True, timeout=120)
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
            result = subprocess.run([executable], text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
