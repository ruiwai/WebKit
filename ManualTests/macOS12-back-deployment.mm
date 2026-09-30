// Copyright (C) 2026 WebKit contributors. All rights reserved.
// SPDX-License-Identifier: BSD-2-Clause
//
// Build and run instructions are in ReadMe.md under macOS 12 back-deployment.
// Run on Monterey as well as the build host; targeting 12.0 is not a runtime test.

#import <AppKit/AppKit.h>
#import <WebKit/WKNavigationDelegate.h>
#import <WebKit/WKWebView.h>
#import <WebKit/WKWebViewConfiguration.h>
#import <WebKit/WKWebsiteDataStore.h>
#import <dlfcn.h>

static int result = 1;
static bool finished;

static void finish(int status)
{
    if (finished)
        return;
    finished = true;
    result = status;
    [NSApp stop:nil];
    [NSApp postEvent:[NSEvent otherEventWithType:NSEventTypeApplicationDefined location:NSZeroPoint modifierFlags:0 timestamp:0 windowNumber:0 context:nil subtype:0 data1:0 data2:0] atStart:YES];
}

@interface BackDeploymentDelegate : NSObject <WKNavigationDelegate>
@end

@implementation BackDeploymentDelegate
- (void)webView:(WKWebView *)webView didFailProvisionalNavigation:(WKNavigation *)navigation withError:(NSError *)error
{
    NSLog(@"Navigation failed: %@", error);
    finish(1);
}

- (void)webView:(WKWebView *)webView didFailNavigation:(WKNavigation *)navigation withError:(NSError *)error
{
    NSLog(@"Navigation failed: %@", error);
    finish(1);
}

- (void)webViewWebContentProcessDidTerminate:(WKWebView *)webView
{
    NSLog(@"Web content process terminated");
    finish(1);
}

- (void)webView:(WKWebView *)webView didFinishNavigation:(WKNavigation *)navigation
{
    NSString *script = @"(() => {"
        "if (document.body.textContent !== 'Monterey smoke test') throw Error('DOM');"
        "if (!WebAssembly.validate(new Uint8Array([0,97,115,109,1,0,0,0]))) throw Error('Wasm');"
        "if (!CSS.supports('background-image', 'conic-gradient(red, blue)')) throw Error('CSS');"
        "const canvas = document.createElement('canvas'); canvas.width = canvas.height = 16;"
        "const context = canvas.getContext('2d');"
        "context.fillStyle = 'red'; context.fillRect(0, 0, 16, 16);"
        "if (context.getImageData(2, 2, 1, 1).data[3] !== 255) throw Error('Solid canvas fill');"
        "context.clearRect(0, 0, 16, 16);"
        "const gradient = context.createConicGradient(0, 8, 8);"
        "gradient.addColorStop(0, 'red'); gradient.addColorStop(1, 'blue');"
        "context.fillStyle = gradient; context.fillRect(0, 0, 16, 16);"
        "const pixel = context.getImageData(2, 2, 1, 1).data;"
        // Allow one quantization step when CoreGraphics interpolates the gradient.
        "if (pixel[3] < 254) throw Error('Conic canvas pixel: ' + pixel);"
        "if (!canvas.toDataURL().startsWith('data:image/png;base64,')) throw Error('PNG');"
        "return 'PASS: DOM, JavaScript, WebAssembly, conic gradient, canvas, PNG';"
        "})()";
    [webView evaluateJavaScript:script completionHandler:^(id value, NSError *error) {
        if (error) {
            NSLog(@"JavaScript failed: %@", error);
            finish(1);
            return;
        }
        NSLog(@"%@", value);
        [webView takeSnapshotWithConfiguration:nil completionHandler:^(NSImage *image, NSError *snapshotError) {
            if (snapshotError || !image || image.size.width <= 0) {
                NSLog(@"Snapshot failed: %@", snapshotError);
                finish(1);
                return;
            }
            NSLog(@"PASS: page snapshot");
            finish(0);
        }];
    }];
}
@end

int main(int argc, const char *argv[])
{
    @autoreleasepool {
        if (argc != 2) {
            fprintf(stderr, "Usage: %s /absolute/path/to/build/Release\n", argv[0]);
            return 1;
        }
        Dl_info info;
        if (!dladdr((__bridge const void *)[WKWebView class], &info))
            return 1;
        NSString *frameworkPath = [[NSString stringWithUTF8String:info.dli_fname] stringByResolvingSymlinksInPath];
        NSString *productsPath = [[NSString stringWithUTF8String:argv[1]] stringByResolvingSymlinksInPath];
        if (![frameworkPath hasPrefix:[productsPath stringByAppendingString:@"/"]]) {
            NSLog(@"FAIL: loaded %@ instead of the local WebKit", frameworkPath);
            return 1;
        }
        NSLog(@"Testing %@ on %@", frameworkPath, NSProcessInfo.processInfo.operatingSystemVersionString);
        [NSApplication sharedApplication];
        auto delegate = [BackDeploymentDelegate new];
        auto configuration = [WKWebViewConfiguration new];
        configuration.websiteDataStore = [WKWebsiteDataStore nonPersistentDataStore];
        auto webView = [[WKWebView alloc] initWithFrame:NSMakeRect(0, 0, 320, 240) configuration:configuration];
        webView.navigationDelegate = delegate;
        auto window = [[NSWindow alloc] initWithContentRect:webView.frame styleMask:NSWindowStyleMaskBorderless backing:NSBackingStoreBuffered defer:NO];
        window.contentView = webView;
        [window orderFront:nil];
        [webView loadHTMLString:@"<!doctype html><style>body { background: conic-gradient(red, blue); }</style><body>Monterey smoke test</body>" baseURL:nil];
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 60 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
            NSLog(@"FAIL: timed out");
            finish(1);
        });
        [NSApp run];
        [webView stopLoading];
        [window orderOut:nil];
    }
    return result;
}
