# Monterey custom build: Safari code-execution CVE triage

Initially reviewed 2026-10-01 against checkout `898d767627`. This is a source-level
assessment, not an exploitability certification or a complete security audit.
ACE means arbitrary code execution; it does not necessarily imply a sandbox
escape or control of the host operating system.

## Backport update: custom version 619.1.26.31.7

The new custom release backports **CVE-2025-43529** from upstream commit
`b21a503b579a8ab14c839f82cc77176e507352e5`. Its changed production lines match
upstream exactly; the branch retains its existing `HashMap` and Phi APIs.
Global-mode escape handling now follows transitive Phi inputs at the heap-store,
stack-read, and end-of-block stack-escape sites. Fast-mode behavior is unchanged.
This is a fork release number, not a claim of a corresponding Apple release.

Validation before publication:

- All six release/algorithm unit tests passed with Xcode 16.2. The new fixture
  compiles the production escape helper and Phi traversal against a small graph
  model, covers nested/cyclic inputs and fast mode, and rejects the old algorithm
  as a negative control. It is not a full JIT/GC integration test.
- The changed production compilation unit (`UnifiedSource54.cpp`, containing
  `DFGStoreBarrierInsertionPhase.cpp`) compiled successfully for x86_64 with the
  Xcode 16.2 Release/macOS 12 build flags.
- The full local JSC build was interrupted at the 1100-second limit without
  compiler errors; no newly linked local runtime or full build pass is claimed.
- The JS stress harness passed on the pre-existing, unpatched x86_64 runtime in
  both configurations. This only checks harness compatibility, not the fix.
- Deployment-boundary tests (two), proxy-selector regression (one), and the
  WebKit style/whitespace checks passed locally with Xcode 16.2.
- CI now gates packaging on a JS allocation/merge/GC stress test in FTL-enabled
  and DFG-only configurations. It retains both logs in the archive. This test
  exercises related behavior, not a deterministic reproduction of the CVE race.
  Hosted build/runtime results must be checked on the new tag's Actions run.

**CVE-2024-44308 and CVE-2025-24201 are not fixed by this release.** The engine
remains old and experimental, with other security updates outstanding.

The sections below retain the initial assessment of **619.1.26.31.6**, before
this backport. Their source line references and missing-fix findings describe
that original checkout, not the revised CVE-2025-43529 code.

## Build identity

- `Configurations/Version.xcconfig:24-28` specifies **619.1.26.31.6**.
- The matching upstream tag is
  [WebKit-7619.1.26.31.6](https://github.com/WebKit/WebKit/tree/WebKit-7619.1.26.31.6),
  pointing to `a320c6ef715b955ef4643e556a405f3da27a502f`, dated 2024-08-15.
- The version file and all three affected source files discussed below were
  fetched from that tag and compared byte-for-byte: all four match this checkout.
  This establishes those files' provenance, not equivalence of the entire tree.
- Local history is shallow at `09a3a471d6`; missing commits in `git log` alone
  cannot establish missing security fixes. The conclusions below use source
  comparisons with published fixes instead.
- The documented products target macOS 12 on x86_64 and arm64. Recent build and
  compatibility work does not make the underlying engine security-current.
  See [build limitations](macOS12-back-deployment.md).

## Priority findings

### CVE-2024-44308: likely affected; published ACE fix absent

[Apple advisory](https://support.apple.com/en-us/121756): fixed in Safari
18.1.1, November 19, 2024. Malicious web content may cause arbitrary code
execution in JavaScriptCore. Apple reports possible active exploitation on
Intel-based Macs. Bugzilla **283063** links the advisory to
[upstream fix ded4d02c0a93](https://github.com/WebKit/WebKit/commit/ded4d02c0a93af990ed12b26254876bdb072f7e7).

Local evidence: `Source/JavaScriptCore/dfg/DFGSpeculativeJIT.cpp:4225-4242`
still allocates `scratch2` **after** `getIntTypedArrayStoreOperand`. The fix
moves this allocation before the call, preventing incorrect register state
when taking a slow path. The old ordering matches the published defect.

The allocation is guarded by `USE(JSVALUE64)`, not an x86-only condition.
Do not infer arm64 immunity from the reported Intel attacks; actual reachability
and exploitability on each packaged architecture remain untested.

### CVE-2025-43529: likely affected; published ACE fix absent

[Apple advisory](https://support.apple.com/en-us/125892): fixed in Safari
26.2, December 12, 2025. A use-after-free may allow arbitrary code execution
from malicious web content. Apple reports possible exploitation in a highly
targeted attack on iOS versions before iOS 26; that observation is not a
restriction of the Safari advisory to iOS. Bugzilla **302502** maps to
[public main-branch fix b21a503b579a](https://github.com/WebKit/WebKit/commit/b21a503b579a8ab14c839f82cc77176e507352e5).

Local evidence: `Source/JavaScriptCore/dfg/DFGStoreBarrierInsertionPhase.cpp`
marks only the immediate node with `setEpoch(Epoch())` at lines 458, 478-480,
and 544-545. It lacks the fix's transitive marking of incoming Phi values in
global mode. The global phase is called at `dfg/DFGPlan.cpp:441`.
This matches the missing-barrier condition described by the upstream fix.

The source defaults enable DFG JIT, FTL JIT, and concurrent GC
(`runtime/OptionsList.h:92,199,239`). These are source defaults, not measurements
of a running package. Architecture, compiler settings, and runtime overrides
still need verification. The public fix does not apply verbatim to this older
branch; a reviewed backport is required.

### CVE-2025-24201: related sandbox escape, not classified here as ACE

[Apple advisory](https://support.apple.com/en-us/122285): fixed in Safari
18.3.1, March 11, 2025. An out-of-bounds write may allow malicious web content
to escape the Web Content sandbox. Apple calls this a supplementary fix for
an attack blocked in iOS 17.2; do not infer that the original exploit chain
works on this build. Bugzilla **285858** maps to
[fix b48791700366](https://github.com/WebKit/WebKit/commit/b48791700366c773ba002a3ab8e04c9058716873).

Local evidence: `Source/WebCore/platform/graphics/angle/GraphicsContextGLANGLE.cpp`
at lines 1168-1174 and 1202-1208 forwards `disable`/`enable` directly to ANGLE.
The upstream guards preventing changes to `PRIMITIVE_RESTART_FIXED_INDEX`
are absent. This is a concrete missing hardening fix; end-to-end exposure
depends on the graphics backend, process configuration, and other protections.

## Other related findings, not source-verified

- **CVE-2024-44309**: Safari 18.1.1 cookie-management cross-site scripting,
  not an ACE finding. Same [advisory](https://support.apple.com/en-us/121756)
  reports possible exploitation on Intel Macs. Its fix was not compared here.
- **CVE-2025-14174**: Safari 26.2 memory corruption; Apple links it to the
  same targeted-attack report as CVE-2025-43529. The
  [advisory](https://support.apple.com/en-us/125892) does not explicitly label
  it ACE. Its affected code and fix were not compared here.
- Other memory-corruption/crash CVEs must also be investigated. Filtering on
  Apple's explicit ACE wording is useful for a shortlist, not an exhaustive
  list of potentially exploitable vulnerabilities.

## Search coverage and verification

Used the [Apple security releases index](https://support.apple.com/en-us/100100)
and fetched 20 linked Safari advisories: 17.6; 18, 18.1, 18.1.1, 18.2, 18.3,
18.3.1, 18.4, 18.5, 18.6; 26, 26.1, 26.2, 26.3, 26.4, 26.5, 26.5.2, 26.6,
26.6.1; and 27. All fetches returned HTTP 200. These yielded the two explicit
WebKit/JavaScriptCore ACE entries above. Safari 17.6.1 had no linked entry in
the examined index and was not fetched. Earlier releases, companion macOS/iOS
advisories, OS libraries, and all other vulnerability classes were not audited.

Source/patch checks:

- Four upstream-tag file equality checks passed.
- `git apply --check` on actual upstream patches passed for CVE-2024-44308
  and CVE-2025-24201. **No patches were applied.** A successful dry-run proves
  textual applicability, not backport correctness or a passing regression test.
- The CVE-2025-43529 patch dry-run failed at the first hunk. The older source
  uses `HashMap` where the patch expects `UncheckedKeyHashMap`; no automatic
  backport or dependency validation was attempted.
- Initial dry-runs against API-extracted hunk fragments failed because those
  fragments lacked full patch headers. The results above use downloaded GitHub
  commit patches instead. Lookup of the original abbreviated `0cfb4a033f7e`
  commit returned HTTP 422; analysis used the public main-branch fix.
- No exploit, runtime vulnerability regression, build, or packaged-binary
  verification was performed. The identity of the user's running artifact and
  its effective JIT settings are unverified. Engine source was not modified.

## Recommended action

Treat this engine as unsuitable for untrusted browsing pending security work.
Prefer a maintained browser on a supported OS over isolated fixes to this old
branch. If retaining it, prioritize reviewed backports of the two ACE fixes,
then the sandbox-escape fix and a broader audit of intervening security updates.
Test both architectures and confirm that the intended local frameworks and
process settings are actually used. Monterey system components remain outside
the protection offered by updating a custom WebKit alone.
