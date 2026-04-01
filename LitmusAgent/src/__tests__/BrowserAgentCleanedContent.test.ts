import { BrowserAgent } from '../browser/BrowserAgent';
import { chromium } from 'playwright';

describe('BrowserAgent Cleaned Content', () => {
    let browserAgent: BrowserAgent;
    let browser: any;

    beforeAll(async () => {
        browser = await chromium.launch({ headless: true });
    });

    afterAll(async () => {
        if (browser) {
            await browser.close();
        }
    });

    beforeEach(async () => {
        browserAgent = new BrowserAgent({
            config: {
                headless: true,
                viewport: { width: 1366, height: 768 },
                disableSecurity: false,
                extraChromiumArgs: [],
                userAgent: 'test-agent',
                locale: 'en-US',
                tracePath: './traces',
                timeout: 30000,
                retryAttempts: 3,
                waitBetweenActions: 100,
                screenshotBeforeAction: false,
                screenshotAfterAction: false
            }
        });
        await browserAgent.initialize();
    });

    afterEach(async () => {
        if (browserAgent) {
            await browserAgent.cleanup();
        }
    });

    describe('getCleanedPageContent method', () => {
        it('should return cleaned HTML content', async () => {
            // Create a test HTML page
            const testHtml = `
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Test Page</title>
                    <style>
                        body { background-color: #f0f0f0; }
                        .test { color: red; }
                    </style>
                    <script>
                        console.log('This should be removed');
                        function testFunction() { return 'test'; }
                    </script>
                </head>
                <body>
                    <div style="color: blue; font-size: 16px;">
                        <h1>Test Heading</h1>
                        <p>This is a test paragraph with <span style="font-weight: bold;">bold text</span>.</p>
                        <button onclick="alert('test')">Click me</button>
                    </div>
                    <script>
                        document.addEventListener('DOMContentLoaded', function() {
                            console.log('Page loaded');
                        });
                    </script>
                </body>
                </html>
            `;

            // Set the test HTML content
            const browserContext = browserAgent.getBrowserContext();
            const page = browserContext!.getActivePage();
            await page.setContent(testHtml);

            // Get raw content
            const rawContent = await browserAgent.getPageContent();
            console.log('Raw content length:', rawContent.length);

            // Get cleaned content
            const cleanedContent = await browserAgent.getCleanedPageContent();
            console.log('Cleaned content length:', cleanedContent.length);
            console.log('Cleaned content preview:', cleanedContent.substring(0, 300));

            // Verify cleaning worked
            expect(cleanedContent.length).toBeLessThan(rawContent.length);
            expect(cleanedContent).not.toContain('<head>');
            expect(cleanedContent).not.toContain('<title>');
            expect(cleanedContent).not.toContain('<style>');
            expect(cleanedContent).not.toContain('<script>');
            expect(cleanedContent).not.toContain('style=');
            expect(cleanedContent).not.toContain('onclick=');
            
            // Verify content is preserved
            expect(cleanedContent).toContain('<h1>Test Heading</h1>');
            expect(cleanedContent).toContain('<p>This is a test paragraph');
            expect(cleanedContent).toContain('<button>Click me</button>');
            expect(cleanedContent).toContain('<body>');
            expect(cleanedContent).toContain('</body>');
        });

        it('should handle simple HTML pages', async () => {
            const simpleHtml = '<html><body><h1>Simple Page</h1><p>Content</p></body></html>';
            
            const browserContext = browserAgent.getBrowserContext();
            const page = browserContext!.getActivePage();
            await page.setContent(simpleHtml);

            const cleanedContent = await browserAgent.getCleanedPageContent();
            
            expect(cleanedContent).toContain('<h1>Simple Page</h1>');
            expect(cleanedContent).toContain('<p>Content</p>');
            expect(cleanedContent).toContain('<body>');
        });

        it('should throw error when browser context not initialized', async () => {
            const uninitializedAgent = new BrowserAgent();
            
            await expect(uninitializedAgent.getCleanedPageContent())
                .rejects
                .toThrow('Browser context not initialized');
        });
    });

    describe('comparison with getPageContent', () => {
        it('should return different content sizes for complex pages', async () => {
            const complexHtml = `
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Complex Page</title>
                    <meta charset="utf-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1">
                    <style>
                        body { margin: 0; padding: 20px; font-family: Arial, sans-serif; }
                        .container { max-width: 800px; margin: 0 auto; }
                        .header { background: #333; color: white; padding: 10px; }
                    </style>
                    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
                    <script>
                        $(document).ready(function() {
                            console.log('Page ready');
                            $('.button').click(function() {
                                alert('Button clicked');
                            });
                        });
                    </script>
                </head>
                <body>
                    <div class="container">
                        <header class="header" style="border-bottom: 2px solid #ccc;">
                            <h1>Welcome to Complex Page</h1>
                        </header>
                        <main style="padding: 20px 0;">
                            <p>This is a complex page with many elements.</p>
                            <button class="button" onclick="handleClick()">Interactive Button</button>
                        </main>
                    </div>
                    <script>
                        function handleClick() {
                            console.log('Handle click function');
                        }
                    </script>
                </body>
                </html>
            `;

            const browserContext = browserAgent.getBrowserContext();
            const page = browserContext!.getActivePage();
            await page.setContent(complexHtml);

            const rawContent = await browserAgent.getPageContent();
            const cleanedContent = await browserAgent.getCleanedPageContent();

            console.log('Complex page analysis:');
            console.log(`- Raw content: ${rawContent.length} characters`);
            console.log(`- Cleaned content: ${cleanedContent.length} characters`);
            console.log(`- Size reduction: ${((rawContent.length - cleanedContent.length) / rawContent.length * 100).toFixed(2)}%`);

            expect(cleanedContent.length).toBeLessThan(rawContent.length);
            expect(rawContent.length - cleanedContent.length).toBeGreaterThan(100); // Significant reduction
        });
    });
});
