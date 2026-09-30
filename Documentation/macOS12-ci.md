# Best-effort optimized arm64 CI releases

Workflow: [macos12-arm64.yml](../.github/workflows/macos12-arm64.yml).
This is separate from the existing manual upterm workflow.

## Triggering and publishing

- `workflow_dispatch` builds, tests and uploads downloadable Actions artifacts;
  it does **not** publish a release.
- Pushing `v<MAJOR.MINOR.TINY.MICRO.NANO>-macos12-arm64` runs the same build and,
  only on success, creates an experimental GitHub **prerelease**, not `latest`.
- The tag must exactly match `Configurations/Version.xcconfig`. For this source
  version the tag is `v619.1.26.31.6-macos12-arm64`.
- The workflow does not create/move tags or overwrite an existing release. Build
  fixes should use a new version/tag rather than silently replacing published assets.

For example, after committing the source/workflow changes:

```sh
git tag -a v619.1.26.31.6-macos12-arm64 -m 'Best-effort optimized macOS 12 arm64 build'
git push --atomic origin webkit-619.1.x refs/tags/v619.1.26.31.6-macos12-arm64
```

Build permissions are read-only, checkout credentials are not retained, and the
separate Linux publication job alone receives `contents: write`. No signing
certificate, Apple account, interactive session, or third-party release action
is required. Actions must be enabled and the repository token must be allowed
to create releases. There is no automatic publication of failed builds.

## Runner and build policy

The workflow requests **`macos-26`**, checks for native arm64, and selects the
installed **Xcode 26.3** with its public SDK. Python 3.11 is selected for scripts.
Missing Metal tooling is installed with `xcodebuild -downloadComponent`.
Runner images change: if Xcode 26.3 is removed, the job fails rather than
silently switching compilers. Update and revalidate that pin deliberately.

The validated manual Monterey build used Xcode 16.2. Xcode 26 is a separate,
experimental build path, not a replacement compatibility claim. CI applies a
single project-file adjustment to its checkout: remove the legacy explicit
Frameworks-symlink build-phase invocation because Xcode 26 creates that link.
The phase definition is left intact and normal Xcode 16 checkouts are unchanged.
The exact adjustment is recorded in build metadata and uploaded logs.

Xcode 26 also misses prerequisites previously inferred from legacy targets'
`Product Dependencies` copy phases, including native static libraries. The build
therefore explicitly completes `bmalloc`, `WTF`, `libwebrtc`, `JavaScriptCore`,
and `WebCore` before `Everything up to MiniBrowser`.
They use the same build root/settings, so completed products are reused. This
supplies allocator headers, WTF generator scripts, libwebrtc/JSC generated headers
and WebKitPlatform's WebCore headers before their consumers run. A cold hosted
build is important: previously generated local headers can conceal missing edges.

The source also removes an unnecessary `template` disambiguator from the
non-dependent `CodePtr<CFunctionPtrTag>` call in `LLIntThunks.cpp`. New Clang
rejects that keyword without a following template argument list; ordinary
member-template deduction retains the existing default return type/behavior.

Optimization policy:

- Release, `arm64`, deployment target **12.0**, C/C++ **`-O3`**, Swift **`-O`** and
  whole-module compilation. Debug information is disabled to reduce CI disk use.
- First attempt: `WK_LTO_MODE=thin`. The project's per-target/deployment LTO gates
  are retained; notably JavaScriptCore can disable LTO for a pre-13 target.
- If that attempt fails, retry `-O3` with `WK_LTO_MODE=none`. Both logs are kept
  and metadata identifies the successful mode. If both fail, nothing is released.
- No fast-math/`-Ofast`, CPU-native tuning, PGO profile claims, or blanket disabling
  of availability diagnostics. New Clang's `unused-but-set-variable` diagnostic
  (e.g. release-disabled logging) remains a warning rather than an error in CI;
  other project diagnostics, including availability errors, remain in force.
- Two build jobs limit concurrent compiler memory use on hosted runners. LTO can
  still exhaust memory/disk or the six-hour job limit. No optimal performance,
  full-LTO success, or speedup over the tested manual build is claimed.

## Gates and artifacts

Before building, CI runs the deployment-boundary and proxy-selector regressions,
plus tests for version/tag handling, the narrow graph adjustment and mocked
optimization-fallback control flow. After a successful build it:

1. Compiles the arm64 browser smoke, assembles a relocatable package and embeds
   the helpers/Swift dylib with relative product-root aliases.
2. Removes build-only `.tbd` stubs, retains helper entitlements, adds JIT
   entitlements to both `jsc` copies, and re-signs the assembled frameworks ad hoc.
3. Checks all 23 Mach-O binaries (architecture/minimum OS, signatures, removed
   custom-deallocation imports), JIT entitlements, and contained valid links.
4. Runs native `jsc` JavaScript/Wasm validation and the WKWebView local-HTML smoke
   on **macOS 26**. Failure, including a missing usable graphical session, blocks release.
5. Archives the package, extracts it to a fresh directory and repeats the static
   audit. Uploads the tarball, SHA-256, build metadata and verification summary.

Diagnostics are uploaded even on failure and retained for 14 days. Archives are
uploaded only after the success gates. Metadata records source commit, tag/run,
Xcode, SDK, host OS, optimization settings and the CI project adjustment.
Checksums are verified again in the publication job. Tests do not constitute a
complete imported-symbol or Objective-C selector audit.

These are **ad-hoc-signed, non-notarized development builds** of an old WebKit
branch. The smoke is not remote-network testing, and a successful macOS 26 job
does not prove Monterey compatibility. The tester's successful basic Monterey
browsing report concerns the earlier Xcode 16.2 revision-3 package, not this new
toolchain/optimization combination. See the
[patch/validation record](macOS12-back-deployment.md) for remaining runtime work.
