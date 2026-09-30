# WebKit

WebKit is a cross-platform web browser engine. On iOS and macOS, it powers Safari, Mail, iBooks, and many other applications. For more information about WebKit, see the [WebKit project website](https://webkit.org/).

## Trying the Latest

On macOS, [download Safari Technology Preview](https://webkit.org/downloads/) to test the latest version of WebKit. On Linux, download [Epiphany Technology Preview](https://webkitgtk.org/epiphany-tech-preview). On Windows, you'll have to build it yourself.

## Reporting Bugs

1. [Search WebKit Bugzilla](https://bugs.webkit.org/query.cgi?format=specific&product=WebKit) to see if there is an existing report for the bug you've encountered.
2. [Create a Bugzilla account](https://bugs.webkit.org/createaccount.cgi) to report bugs (and comment on them) if you haven't done so already.
3. File a bug in accordance with [our guidelines](https://webkit.org/bug-report-guidelines/).

Once your bug is filed, you will receive email when it is updated at each stage in the [bug life cycle](https://webkit.org/bug-life-cycle). After the bug is considered fixed, you may be asked to download the [latest nightly](https://webkit.org/nightly) and confirm that the fix works for you.

## Getting the Code

Run the following command to clone WebKit's Git repository:

```
git clone https://github.com/WebKit/WebKit.git WebKit
```

You can enable [git fsmonitor](https://git-scm.com/docs/git-config#Documentation/git-config.txt-corefsmonitor) to make many git commands faster (such as `git status`) with `git config core.fsmonitor true`

## Building WebKit

### Building for Apple platforms

Install Xcode and its command line tools if you haven't done so already:

1. **Install Xcode** Get Xcode from https://developer.apple.com/downloads. To build WebKit for OS X, Xcode 5.1.1 or later is required. To build WebKit for iOS Simulator, Xcode 7 or later is required.
2. **Install the Xcode Command Line Tools** In Terminal, run the command: `xcode-select --install`

Run the following command to build a macOS debug build with debugging symbols and assertions:

```
Tools/Scripts/build-webkit --debug
```

For performance testing, and other purposes, use `--release` instead.

#### macOS 12 back-deployment (webkit-619.1.x)

See the [patch scope and validation record](Documentation/macOS12-back-deployment.md)
for the individual compatibility changes, limitations, and remaining test work.
An experimental [optimized arm64 CI/release workflow](Documentation/macOS12-ci.md)
uses the `macos-26` runner with Xcode 26-specific build preparation; it does not
replace the Xcode 16.2 manual-build validation below.

Build on a newer macOS host with **Xcode 16.2**, using its public SDK and a
**12.0 deployment target**. An old SDK is not required. Xcode 26 encountered
legacy workspace dependency-rule failures in this build. Select Xcode per command
with `DEVELOPER_DIR`; there is no need to replace the system's selected Xcode.

From the repository root, the following builds the engine, helper processes,
and MiniBrowser for **Intel (x86_64)**:

```sh
export DEVELOPER_DIR="$HOME/Applications/Xcode-16.2/Xcode.app/Contents/Developer"
products="$PWD/WebKitBuild/MacOS12/Release"
xcodebuild -workspace WebKit.xcworkspace \
    -scheme 'Everything up to MiniBrowser' -configuration Release \
    -destination 'platform=macOS,arch=x86_64' \
    SYMROOT="$PWD/WebKitBuild/MacOS12" OBJROOT="$PWD/WebKitBuild/MacOS12" \
    SHARED_PRECOMPS_DIR="$PWD/WebKitBuild/MacOS12/PrecompiledHeaders" \
    ARCHS=x86_64 SDKROOT=macosx MACOSX_DEPLOYMENT_TARGET=12.0 \
    CODE_SIGNING_ALLOWED=NO -jobs 8
```

For **Apple Silicon (arm64)**, use a separate output directory and a generic
destination so the build can also be cross-compiled on Intel. Enable ad-hoc
signing to preserve the helper processes' entitlements, including JIT support:

```sh
products="$PWD/WebKitBuild/MacOS12-arm64/Release"
xcodebuild -workspace WebKit.xcworkspace \
    -scheme 'Everything up to MiniBrowser' -configuration Release \
    -destination 'generic/platform=macOS' \
    SYMROOT="$PWD/WebKitBuild/MacOS12-arm64" OBJROOT="$PWD/WebKitBuild/MacOS12-arm64" \
    SHARED_PRECOMPS_DIR="$PWD/WebKitBuild/MacOS12-arm64/PrecompiledHeaders" \
    ARCHS=arm64 ONLY_ACTIVE_ARCH=NO SDKROOT=macosx MACOSX_DEPLOYMENT_TARGET=12.0 \
    CODE_SIGNING_ALLOWED=YES CODE_SIGN_IDENTITY=- -jobs 8
```

These are **development** products (unsigned Intel, ad-hoc-signed arm64), not a
Developer ID-signed or notarized browser distribution. Keep the frameworks,
dylibs, MiniBrowser, and XPC bundles together
in the products directory, preserving their relative symlinks. Do not replace
macOS's system frameworks. To launch with the newly built engine rather than the
system WebKit:

```sh
export DYLD_FRAMEWORK_PATH="$products" DYLD_LIBRARY_PATH="$products"
export __XPC_DYLD_FRAMEWORK_PATH="$products" __XPC_DYLD_LIBRARY_PATH="$products"
"$products/MiniBrowser.app/Contents/MacOS/MiniBrowser" --url about:blank
```

The back-deployment changes keep older media paths, use CPU-only Vision requests
on older systems, and fall back to plain URLs for share-sheet previews. Apple Pay
automatic reload, recurring/multi-merchant payments and order details require a
13.0 deployment target; deferred payments require 13.3. These features are not
enabled in the Monterey build. IOSurface ownership-identity attribution is only
called on systems supporting its public API.

For a self-terminating smoke test, choose the matching build and architecture.
Run from a logged-in graphical session on that architecture:

```sh
arch=x86_64
build="$PWD/WebKitBuild/MacOS12"
# For Apple Silicon instead: arch=arm64; build="$PWD/WebKitBuild/MacOS12-arm64"
products="$build/Release"
xcrun --sdk macosx clang++ -arch "$arch" -std=c++20 -fobjc-arc -mmacosx-version-min=12.0 \
    -F "$products" -framework AppKit -framework WebKit \
    ManualTests/macOS12-back-deployment.mm \
    -o "$build/back-deployment-smoke"
codesign --force --sign - "$build/back-deployment-smoke"
export DYLD_FRAMEWORK_PATH="$products" DYLD_LIBRARY_PATH="$products"
export __XPC_DYLD_FRAMEWORK_PATH="$products" __XPC_DYLD_LIBRARY_PATH="$products"
"$build/back-deployment-smoke" "$products"
```

An Intel build host cannot execute the arm64 smoke test; copy the intact
development package to an Apple Silicon Mac for that test.

The SDK-only availability regression check can run on either build host:

```sh
python3 ManualTests/macOS12-platform-availability.py
```

It verifies that the Objective-C custom-deallocation path is enabled only for
macOS 13+ deployment targets, even when using a newer SDK. Monterey builds must
use the existing fallback rather than import `_class_setCustomDeallocInitiation`.
It also checks the PassKit 13.0/13.3 boundaries while keeping base Apple Pay enabled.

The proxy-selector regression test also runs on the build host with Xcode 16.2:

```sh
python3 ManualTests/macOS12-proxy-availability.py
```

It exercises the production session-configuration method with objects that do
and do not implement `setProxyConfigurations:`. Older CFNetwork versions must
skip that setter even for an empty list, without changing legacy proxy settings.
On supported systems, both applying and clearing custom proxies are checked.

The browser smoke test checks that it loaded the local framework, then exercises
DOM/JavaScript, WebAssembly, conic gradients, canvas readback, PNG export, and a page
snapshot. It does not fetch a remote page.
The Intel build and smoke test have passed on a macOS 15.8.1 host, and the arm64
cross-build has passed on that host. The tester reports that the arm64 revision-3
package runs and renders web pages on macOS 12 without observed errors.
**This is basic browsing validation, not comprehensive or exhaustive testing.**
The loader and Networking crashes in earlier packages were fixed; media playback,
camera capture, DRM, sharing, and broader networking coverage still need testing.
The exact Monterey minor version and the pages exercised were not recorded.
A Mach-O `minos 12.0` setting alone does not prove runtime compatibility.
The full “Everything up to WebKit + Tools” build still encounters availability
errors in `TestWebKitAPI/Tests/WebKitCocoa/Proxy.mm` for macOS 14-only proxy tests;
the MiniBrowser scheme avoids those unrelated test targets.

#### Embedded Builds

To build for an embedded platform like iOS, tvOS, or watchOS, pass a platform
argument to `build-webkit`. 

For example, to build a debug build with debugging symbols and assertions for
embedded simulators:

```
Tools/Scripts/build-webkit --debug --<platform>-simulator
```

or embedded devices:
```
Tools/Scripts/build-webkit --debug --<platform>-device
```

where `platform` is `ios`, `tvos` or `watchos`.

#### Using Xcode

You can open `WebKit.xcworkspace` to build and debug WebKit within Xcode.
Select the "Everything up to WebKit + Tools" scheme to build the entire
project.

If you don't use a custom build location in Xcode preferences, you have to
update the workspace settings to use `WebKitBuild` directory.  In menu bar,
choose File > Workspace Settings, then click the Advanced button, select
"Custom", "Relative to Workspace", and enter `WebKitBuild` for both Products
and Intermediates.

### Building the GTK Port

For production builds:

```
cmake -DPORT=GTK -DCMAKE_BUILD_TYPE=RelWithDebInfo -GNinja
ninja
sudo ninja install
```

For development builds:

```
Tools/gtk/install-dependencies
Tools/Scripts/update-webkitgtk-libs
Tools/Scripts/build-webkit --gtk --debug
```

For more information on building WebKitGTK, see the [wiki page](https://trac.webkit.org/wiki/BuildingGtk).

### Building the WPE Port

For production builds:

```
cmake -DPORT=WPE -DCMAKE_BUILD_TYPE=RelWithDebInfo -GNinja
ninja
sudo ninja install
```

For development builds:

```
Tools/wpe/install-dependencies
Tools/Scripts/update-webkitwpe-libs
Tools/Scripts/build-webkit --wpe --debug
```

### Building Windows Port

For building WebKit on Windows, see the [WebKit on Windows page](https://docs.webkit.org/Ports/WindowsPort.html).

## Running WebKit

### With Safari and Other macOS Applications

Run the following command to launch Safari with your local build of WebKit:

```
Tools/Scripts/run-safari --debug
```

The `run-safari` script sets the `DYLD_FRAMEWORK_PATH` environment variable to point to your build products, and then launches `/Applications/Safari.app`. `DYLD_FRAMEWORK_PATH` tells the system loader to prefer your build products over the frameworks installed in `/System/Library/Frameworks`.

To run other applications with your local build of WebKit, run the following command:

```
Tools/Scripts/run-webkit-app <application-path>
```

### iOS Simulator

Run the following command to launch iOS simulator with your local build of WebKit:

```
run-safari --debug --ios-simulator
```

In both cases, if you have built release builds instead, use `--release` instead of `--debug`.

### Linux Ports

If you have a development build, you can use the `run-minibrowser` script, e.g.:

```
run-minibrowser --debug --wpe
```

Pass one of `--gtk`, `--jsc-only`, or `--wpe` to indicate the port to use.

## Contribute

Congratulations! You’re up and running. Now you can begin coding in WebKit and contribute your fixes and new features to the project. For details on submitting your code to the project, read [Contributing Code](https://webkit.org/contributing-code/).
