# macOS 12 back-deployment patch series

Scope: `webkit-619.1.x`, based on `09a3a471d6`. Build instructions are in
[ReadMe.md](../ReadMe.md#macos-12-back-deployment-webkit-6191x).
The series below groups the changes by compatibility boundary, not by the order
in which compiler and runtime failures were discovered. Apply the series in order.
Shared files are split by the symbols identified in each entry.

## Validation status and limits

The tester reports that **arm64 revision 3 runs MiniBrowser and renders web pages
on macOS 12 without observed errors**. This is a basic browsing check, explicitly
not comprehensive or exhaustive. The precise macOS 12 minor version, URLs,
duration, and feature coverage were not recorded. It is not a claim that every
Monterey release, feature, hardware configuration, or architecture has been tested.

Build environment: Intel macOS 15.8.1, Xcode 16.2, public macOS 15.2 SDK,
Release, `MACOSX_DEPLOYMENT_TARGET=12.0`, `Everything up to MiniBrowser`.
Both x86_64 and arm64 builds succeeded during development. The Intel local-HTML
smoke passed on macOS 15.8.1, not on Monterey. The revised arm64 engine cannot be
executed on that Intel build host. Later review refinements narrow diagnostic
suppressions and improve tests/docs without intentionally changing runtime behavior;
the tester's report applies to the previously delivered revision-3 package.

The original arm64 package failed to load `_class_setCustomDeallocInitiation`.
Revision 2 removed that import but crashed its Networking helper on
`setProxyConfigurations:`. Revision 3 added the missing selector check. Its
extracted archive passed static checks for all 23 Mach-O binaries: arm64,
`minos 12.0`, code signatures, JIT entitlements, and contained, resolving symlinks.
The custom-deallocation hook imports are absent; strong libobjc imports were
compared with macOS 12.3 SDK exports. That comparison is **not** a complete
system-symbol, selector, ABI, or runtime audit, nor evidence for macOS 12.0 itself.

The full `Everything up to WebKit + Tools` scheme remains outside the verified
scope: the earlier Intel attempt failed on macOS 14-only proxy APIs in
`Tools/TestWebKitAPI/Tests/WebKitCocoa/Proxy.mm`. Internal Apple SDK builds,
iOS-family runtime behavior, Developer ID signing/notarization, and distribution
readiness are unverified. This is an old, experimental WebKit branch, not an
up-to-date, security-supported browser.

## Individual patches

Paths below are repository-relative. Tests listed are evidence for the stated
boundary, not proof of every feature in that subsystem.

### P01 — Gate Monterey build features on deployment targets

Files:
- `Source/WTF/wtf/PlatformHave.h`
- `ManualTests/macOS12-platform-availability.py`

Use the macOS deployment target, rather than the SDK version, for Objective-C
custom deallocation (macOS 13+). This selects the existing `WKObject.h` fallback
and removes the missing runtime-hook imports; it does not introduce a replacement
deallocation mechanism or extend newer off-main-thread lifetime guarantees.
Gate PassKit automatic reload, recurring and multi-merchant payments, and order
details at 13.0; deferred payments at 13.3. Base Apple Pay stays enabled.
These build-time feature gates remain disabled in a 12.0-targeted binary even
when that binary runs on a newer OS. Non-macOS gates are unchanged.

Regression: compile-time checks on arm64 and x86_64 for custom deallocation at
12.0/12.7/13.0/14.0 and PassKit at 12.0/12.7/13.0/13.2/13.3/14.0, including base
Apple Pay. No payment transaction or off-main-thread object-lifetime test is claimed.

### P02 — Guard IOSurface ownership attribution

Files:
- `Source/WebCore/platform/graphics/cocoa/IOSurface.mm`
- `Source/WebGPU/WebGPU/PresentationContextIOSurface.mm`

Call `IOSurfaceSetOwnershipIdentity` only at its public availability boundary:
macOS 14.4, iOS/tvOS 17.4, watchOS 10.4. Older systems still create/use surfaces
but skip this explicit graphics-memory ownership attribution. This is a
conservative fallback, not a statement that the SPI never existed on older OSes:
the symbol was found in a macOS 12.3 SDK stub, but 12.0 runtime availability was
not established. Memory accounting and WebGPU behavior require dedicated tests.
Evidence: successful back-deployment builds; no attribution-specific runtime test.

### P03 — Keep a legacy Vision compute path

Files:
- `Source/WebCore/Modules/ShapeDetection/Implementation/Cocoa/VisionUtilities.mm`
- `Source/WebCore/PAL/pal/cocoa/CoreMLSoftLink.h`
- `Source/WebCore/PAL/pal/cocoa/CoreMLSoftLink.mm`

Annotate soft-linked `MLCPUComputeDevice`/`MLGPUComputeDevice` getters and guard
Vision compute-device APIs at macOS 14 / iOS/tvOS 17. Older systems, and builds
using the existing CPU-only property path, set `usesCPUOnly = YES`. Keep the
newer-device selection algorithm unchanged; this is not a compute-policy rewrite.
The fallback may reduce shape-detection performance. Evidence: build checks;
barcode/text/face detection and CPU/GPU performance remain untested on Monterey.

### P04 — Make newer video-renderer declarations and notifications availability-safe

Files:
- `Source/WebCore/PAL/pal/cocoa/AVFoundationSoftLink.h` (`AVSampleBufferVideoRenderer`)
- `Source/WebCore/PAL/pal/cocoa/AVFoundationSoftLink.mm` (same class)
- `Source/WebCore/platform/graphics/avfoundation/WebAVSampleBufferListener.mm`
- `Source/WebCore/platform/graphics/avfoundation/objc/MediaPlayerPrivateMediaSourceAVFObjC.h`
- `Source/WebCore/platform/graphics/cocoa/MediaPlayerPrivateWebM.h`

Annotate the soft-linked macOS 14 / iOS/tvOS 17 renderer getter, guard class
inspection and notification registration/removal, and allow the newer pointer
type only at the two member declarations. Older display-layer paths and their
notifications remain in place; a pointer declaration does not instantiate the
new class. Evidence: build checks. MSE, WebM and WebRTC rendering/flush/error
notification behavior still need playback tests on both old and new OSes.

### P05 — Preserve legacy video-performance metric selectors

Files:
- `Source/WebCore/PAL/pal/cocoa/AVFoundationSoftLink.h` (`AVVideoPerformanceMetrics`)
- `Source/WebCore/PAL/pal/cocoa/AVFoundationSoftLink.mm` (same class)
- `Source/WebCore/PAL/pal/spi/cocoa/AVFoundationSPI.h` (`WebAVVideoPerformanceMetrics`)
- `Source/WebCore/platform/graphics/cocoa/WebSampleBufferVideoRendering.h`
- `Source/WebCore/platform/graphics/avfoundation/objc/LocalSampleBufferDisplayLayer.mm`
- `Source/WebCore/platform/graphics/avfoundation/objc/MediaPlayerPrivateAVFoundationObjC.mm`
- `Source/WebCore/platform/graphics/avfoundation/objc/MediaPlayerPrivateMediaSourceAVFObjC.mm`

Distinguish the public macOS 14.4 metrics class from the older SPI selectors.
Declare a private protocol for the existing counters/delay getters, annotate the
soft-linked public class and protocol return type, and check `videoPerformanceMetrics`
before requesting it. If unavailable, omit metrics/logging rather than sending
an unsupported selector. Narrow diagnostic suppressions to the guarded getter;
do not disable availability warnings for the rest of the metrics path.
The protocol is a compile-time description, not a runtime conformance requirement.
Counter-selector compatibility and correctness remain SPI assumptions requiring
media tests. Evidence: build checks, not measured playback-quality validation.

### P06 — Fall back when request-level FairPlay protection status is unavailable

Files:
- `Source/WebCore/PAL/pal/spi/cocoa/AVFoundationSPI.h` (`AVContentKeyRequest_PendingProtectionStatus`)
- `Source/WebCore/platform/graphics/avfoundation/objc/CDMInstanceFairPlayStreamingAVFObjC.mm`

Keep the request-level SPI declaration distinct from the newer public content-key
API and its annotated enum. Check the request selector before calling it. If it
is absent, continue through the existing per-display obscuration and aggregate
output-restriction checks instead of compiling that fallback out. Qualify the
logging helper as `CDMPrivateFairPlayStreaming::keyIDsForRequest` in the newly
reachable branch. This is not a DRM/HDCP bypass: existing protection-status
checks and their unknown/pending outcomes are retained. Evidence: compilation;
licensed playback, pending responses, HDCP and display transitions are untested.

### P07 — Retain selector-checked resource-loading behavior

File: `Source/WebCore/platform/graphics/avfoundation/objc/WebCoreAVFResourceLoader.mm`.

Suppress availability diagnostics only around the existing
`setEntireLengthAvailableOnDemand:` selector check/call. Preserve the data-URL
exception and existing resource-loader behavior; add no unconditional API call.
Evidence: compilation; byte-range media loads and data-URL playback are untested.

### P08 — Retain selector-checked camera photo dimensions

File: `Source/WebCore/platform/mediastream/mac/AVVideoCaptureSource.mm`.

Add local diagnostic scopes for the existing checks of supported/max photo
dimensions. Keep the preset-size fallback and existing photo-output configuration.
The first scope covers only the newer getter, not the size-selection algorithm
or fallback. Evidence: compilation; device capabilities, permissions, photo
capture, and legacy/new camera behavior still need hardware tests.

### P09 — Preserve pre-public graphics SPI on older systems

Files:
- `Source/WebCore/platform/graphics/cg/GradientRendererCG.cpp`
- `Source/WebCore/platform/network/mac/UTIUtilities.mm`

Apply narrow diagnostic suppressions to `CGContextDrawConicGradient` and
`CGImageSourceSetAllowableTypes`: both were exported as SPI in the macOS 11.3 SDK
before their newer public annotations. Preserve conic rendering and the ImageIO
decoder allowlist rather than disabling them on Monterey. These remain direct
SPI calls under the existing feature gates, not a general soft-link fallback.
The local smoke exercises conic canvas drawing and PNG export; it does not prove
allowlist enforcement or validate all image decoders. SPI/runtime compatibility
outside the tested configurations remains a risk.

### P10 — Guard CFNetwork proxy configuration at runtime

Files:
- `Source/WebCore/PAL/pal/spi/cf/CFNetworkSPI.h` (`NSURLSession._networkContext`)
- `Source/WebKit/NetworkProcess/cocoa/NetworkSessionCocoa.mm` (proxy methods)
- `ManualTests/macOS12-proxy-availability.py`

Expose the private network-context declaration when proxy support needs it;
check the selector and a non-null context before collecting live session contexts.
Check `setProxyConfigurations:` before applying **or clearing** the proxy list,
covering initialization and session recreation. This fixes the repeat Networking
crash even when the custom list is empty. Legacy `connectionProxyDictionary`
configuration is not changed. This does not backport the macOS 14 public proxy
configuration API; custom new-API proxy lists cannot be applied through a missing
setter. Custom/PAC/authenticated proxies require separate testing.

Regression: compile and execute the actual setter method body with old/new
Objective-C configuration test doubles, empty/nonempty lists, and existing legacy
settings. This reproduced the exception before the guard and passed afterward.
It is an isolated fixture (real `RetainPtr`, a lightweight session/container), not
a complete NetworkProcess test. Keep its method-body extraction in sync if the
production method is renamed, moved, or substantially restructured.

### P11 — Allow informational-response forwarding to our own implementation

File: `Source/WebKit/NetworkProcess/cocoa/NetworkSessionCocoa.mm`
(`URLSession:task:_didReceiveInformationalResponse:`).

Suppress availability diagnostics for forwarding to WebKit's own
`didReceiveInformationalResponse:` implementation, which is compiled on older
systems too. Do not assume that the newer system callback exists on Monterey.
Evidence: compilation; 1xx/103 response delivery remains untested.

### P12 — Fall back to plain share-sheet URLs

File: `Source/WebKit/UIProcess/Cocoa/WKShareSheet.mm`.

Use `NSPreviewRepresentingActivityItem` only on macOS 13+. Pass file/ordinary
URLs directly on older macOS; leave iOS item-provider paths unchanged. Monterey
loses the newer rich preview wrapper, not the intended shareable URL. Evidence:
build checks; file/URL sharing, titles and preview behavior still need UI tests.

### P13 — Document the series and add a local browser smoke

Files:
- `ManualTests/macOS12-back-deployment.mm`
- `ReadMe.md`
- `Documentation/macOS12-back-deployment.md`

Provide reproducible architecture-specific build/launch/test commands and a
self-terminating WKWebView smoke. It verifies the local WebKit image path, then
checks DOM/JavaScript, WebAssembly validation, conic gradients, canvas pixels,
PNG export and a page snapshot. It fails on navigation/content-process errors
or a 60-second timeout. It uses local HTML and a nonpersistent data store, not
an HTTP server; it does not cover remote networking or persistent profile state.
The library-path check applies to the UI executable; it is not an independent
audit of every helper's loaded images. Full runtime limitations are listed above.

## Development packaging scope (not source patches)

Generated products, logs and archives stay under ignored `WebKitBuild/` and are
not part of the source commits. Revision-3 artifact:

```
WebKit-619.1.26.31.6-macOS12-arm64-r3.tar.gz
SHA-256 b0621e80a19f01a7640e20d2813886c113e6cd9eecd0495e5edfc23e702718de
```

Packaging retains MiniBrowser, six frameworks, shared dylibs, `jsc`, six XPC
bundles and the smoke executable. Move the XPC bundles and `libWebKitSwift.dylib`
inside WebKit.framework and replace their product-root entries with relative
aliases; otherwise strict framework signing rejects the external targets.
Retain the empty directory targeted by WebCore.framework's `Frameworks` symlink.
Remove generated `.tbd` link stubs and their aliases from the runtime copy: their
signatures used extended attributes that did not survive the portable tar archive.

Ad-hoc sign both `jsc` copies with `com.apple.security.cs.allow-jit`, retain the
WebContent JIT entitlements generated by the public-SDK build, and re-sign the
frameworks after assembly (not with blanket `codesign --deep` signing).
Audit all binaries and bundles again **after archive extraction**, including
signatures, architecture/minimum OS, entitlements and links. The launcher sets
`DYLD_FRAMEWORK_PATH`, `DYLD_LIBRARY_PATH` and their `__XPC_` equivalents to its
own `Release` directory. Launching MiniBrowser directly can select system WebKit.
Never replace system frameworks or merge package revisions into an old directory.

## Remaining validation checklist

- Record exact OS minor version, hardware, package/hash, URLs and repro steps.
- Run the local smoke on Monterey and test HTTP/HTTPS, redirects, downloads,
  cookies, cache/persistent profiles, WebSockets, and proxy configurations.
- Exercise AVFoundation/MSE/WebM/WebRTC playback, quality counters, decode/flush
  errors, camera/photos, Vision detection, and file/URL sharing.
- Test DRM/HDCP with authorized content and relevant display configurations.
- Check GPU/WebGPU, memory accounting, and long-running/multi-tab stability.
- Recheck supported newer macOS paths; back-deployment should not remove them.
- Keep Intel-on-Monterey and non-macOS ports explicitly unverified until tested.
