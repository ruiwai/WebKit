#!/bin/bash
# Copyright (C) 2026 WebKit contributors. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

set -euo pipefail

# No -ffast-math/-Ofast or -mcpu=native: preserve JS semantics and ARM64 portability.
# WK_LTO_MODE respects the branch's deployment-specific LTO safety gates (notably JSC).
output="$PWD/WebKitBuild/CI-arm64"
logs="$PWD/WebKitBuild/CI-logs"
mkdir -p "$logs"
jobs="${BUILD_JOBS:-2}"
case "$jobs" in 1|2|3) ;; *) echo 'BUILD_JOBS must be 1, 2 or 3' >&2; exit 1 ;; esac

build() {
    local mode="$1"
    local scheme
    : > "$logs/build-$mode.log"
    # Supply script prerequisites explicitly; individual schemes such as WTF and
    # WebCore disable implicit dependency resolution. Include the weakly linked
    # graphics libraries before WebCore and WebCore before WebKitPlatform.
    for scheme in bmalloc WTF libwebrtc JavaScriptCore WebGPU 'ANGLE (dynamic)' WebCore 'Everything up to MiniBrowser'; do
        printf '\n### Scheme: %s\n' "$scheme" >> "$logs/build-$mode.log"
        if ! xcodebuild -workspace WebKit.xcworkspace -scheme "$scheme" \
        -configuration Release -destination 'generic/platform=macOS' \
        "SYMROOT=$output" "OBJROOT=$output" "SHARED_PRECOMPS_DIR=$output/PrecompiledHeaders" \
        ARCHS=arm64 ONLY_ACTIVE_ARCH=NO SDKROOT=macosx MACOSX_DEPLOYMENT_TARGET=12.0 \
        CODE_SIGNING_ALLOWED=YES CODE_SIGN_IDENTITY=- \
        GCC_OPTIMIZATION_LEVEL=3 "WK_LTO_MODE=$mode" \
        'WARNING_CFLAGS=$(inherited) -Wno-error=unused-but-set-variable -Wno-error=thread-safety-reference-return' \
        SWIFT_OPTIMIZATION_LEVEL=-O SWIFT_COMPILATION_MODE=wholemodule \
        GCC_GENERATE_DEBUGGING_SYMBOLS=NO DEBUG_INFORMATION_FORMAT=dwarf \
        -jobs "$jobs" >> "$logs/build-$mode.log" 2>&1; then
            return 1
        fi
    done
}

mode=thin
if ! build "$mode"; then
    tail -60 "$logs/build-$mode.log"
    # Semantic/header errors are independent of LTO. Avoid rebuilding every
    # prerequisite only to reproduce the same source diagnostic a second time.
    if grep -Eq '^.+:[0-9]+:[0-9]+: (fatal )?error:' "$logs/build-$mode.log"; then
        echo '::error::Source diagnostics cannot be fixed by disabling LTO; see build-thin.log.'
        exit 1
    fi
    echo '::warning::Optimized ThinLTO attempt failed; retrying -O3 without LTO. See both logs.'
    mode=none
    # Use the same build root: Xcode tracks the changed settings and recompiles
    # affected targets. No stale package is accepted: both build status and checks gate release.
    if ! build "$mode"; then
        tail -80 "$logs/build-$mode.log"
        exit 1
    fi
fi
printf '%s\n' "$mode" > "$logs/lto-mode.txt"
tail -8 "$logs/build-$mode.log"

xcrun --sdk macosx clang++ -arch arm64 -O3 -std=c++20 -fobjc-arc -mmacosx-version-min=12.0 \
    -F "$output/Release" -framework AppKit -framework WebKit \
    ManualTests/macOS12-back-deployment.mm -o "$output/back-deployment-smoke"
codesign --force --sign - --identifier org.webkit.BackDeploymentSmoke "$output/back-deployment-smoke"
