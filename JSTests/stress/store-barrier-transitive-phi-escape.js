//@ runDefault("--useConcurrentJIT=false", "--thresholdForFTLOptimizeAfterWarmUp=100", "--thresholdForFTLOptimizeSoon=100", "--verifyGC=true")

// Exercise stores through an original allocation after it escapes through
// nested control-flow merges. This is GC/optimization coverage, not a
// deterministic reproduction of the concurrent-GC race in bug 302502.
function escapeThroughPhi(first, second, value)
{
    let holder = { selected: null };
    let original = { payload: null };
    let alternative = { payload: null };
    let selected = first ? original : alternative;
    if (second)
        selected = { payload: null };

    holder.selected = selected;
    original.payload = { value };
    alternative.payload = { value: value + 1 };
    return { holder, original, alternative, first, second, value };
}
noInline(escapeThroughPhi);

function check(result)
{
    if (result.original.payload.value !== result.value
        || result.alternative.payload.value !== result.value + 1)
        throw new Error("Lost a payload after a Phi escape");
    if (result.second) {
        if (result.holder.selected.payload !== null)
            throw new Error("Incorrect second merge");
    } else if (result.holder.selected !== (result.first ? result.original : result.alternative))
        throw new Error("Incorrect first merge");
}
noInline(check);

for (let batch = 0; batch < 100; ++batch) {
    let retained = [];
    for (let i = 0; i < 200; ++i) {
        let result = escapeThroughPhi(!!(i & 1), !!(i & 2), batch * 200 + i);
        check(result);
        retained.push(result);
    }
    edenGC();
    if (!(batch % 10))
        gc();
    for (let result of retained)
        check(result);
}
print("PASS: transitive Phi escape GC stress");
