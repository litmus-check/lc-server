import { HtmlCleaner } from '../browser/HtmlCleaner';
import { chromium } from 'playwright';

describe('HTML Extraction and Cleaning', () => {
    let browser: any;
    let page: any;
    let htmlCleaner: HtmlCleaner;

    beforeAll(async () => {
        browser = await chromium.launch({ headless: true });
        htmlCleaner = new HtmlCleaner();
    });

    afterAll(async () => {
        if (browser) {
            await browser.close();
        }
    });

    beforeEach(async () => {
        page = await browser.newPage();
    });

    afterEach(async () => {
        if (page) {
            await page.close();
        }
    });

    describe('Real Webpage HTML Extraction', () => {
        it('should extract and clean HTML from a real webpage', async () => {
            // Navigate to a test webpage
            await page.goto('https://example.com');
            await page.waitForLoadState('networkidle');

            // Get the raw HTML
            const rawHtml = await page.content();
            console.log('Raw HTML length:', rawHtml.length);
            console.log('Raw HTML preview:', rawHtml.substring(0, 500));

            // Clean the HTML using our cleaner
            const cleanedHtml = await htmlCleaner.getCleanedPageHtml(page);
            console.log('Cleaned HTML length:', cleanedHtml.length);
            console.log('Cleaned HTML preview:', cleanedHtml.substring(0, 500));

            // Verify cleaning worked
            expect(cleanedHtml.length).toBeLessThan(rawHtml.length);
            expect(cleanedHtml).not.toContain('<head>');
            expect(cleanedHtml).not.toContain('<script>');
            expect(cleanedHtml).not.toContain('style=');
            expect(cleanedHtml).toContain('<body>');
            expect(cleanedHtml).toContain('Example Domain');
        });

        it('should extract HTML from a more complex webpage', async () => {
            // Navigate to a more complex webpage
            await page.goto('https://httpbin.org/html');
            await page.waitForLoadState('networkidle');

            // Get the raw HTML
            const rawHtml = await page.content();
            console.log('Complex page raw HTML length:', rawHtml.length);

            // Clean the HTML
            const cleanedHtml = await htmlCleaner.getCleanedPageHtml(page);
            console.log('Complex page cleaned HTML length:', cleanedHtml.length);

            // Verify cleaning
            expect(cleanedHtml.length).toBeLessThan(rawHtml.length);
            expect(cleanedHtml).not.toContain('<head>');
            expect(cleanedHtml).not.toContain('<script>');
            expect(cleanedHtml).not.toContain('style=');
            expect(cleanedHtml).toContain('<body>');
            expect(cleanedHtml).toContain('<h1>');
        });

        it('should handle pages with inline styles and scripts', async () => {
            // Create a test page with inline styles and scripts
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
                        console.log('This is a test script');
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

            await page.setContent(testHtml);

            // Get raw HTML
            const rawHtml = await page.content();
            console.log('Test page raw HTML:', rawHtml);

            // Clean the HTML
            const cleanedHtml = await htmlCleaner.getCleanedPageHtml(page);
            console.log('Test page cleaned HTML:', cleanedHtml);

            // Verify cleaning worked
            expect(cleanedHtml).not.toContain('<head>');
            expect(cleanedHtml).not.toContain('<title>');
            expect(cleanedHtml).not.toContain('<style>');
            expect(cleanedHtml).not.toContain('<script>');
            expect(cleanedHtml).not.toContain('style=');
            expect(cleanedHtml).not.toContain('onclick=');
            expect(cleanedHtml).toContain('<h1>Test Heading</h1>');
            expect(cleanedHtml).toContain('<p>This is a test paragraph');
            expect(cleanedHtml).toContain('<button>Click me</button>');
        });
    });

    describe('HTML Cleaning Configuration', () => {
        it('should allow custom cleaning configuration', async () => {
            const customCleaner = new HtmlCleaner({
                removeHead: false,
                removeScripts: true,
                removeStyleAttributes: false,
                removeInlineStyles: true,
                removeComments: true,
                removeEmptyElements: true
            });

            const testHtml = `
                <html>
                <head>
                    <title>Keep Head</title>
                </head>
                <body>
                    <div style="color: red;">Keep style attribute</div>
                    <style>body { background: blue; }</style>
                    <script>console.log('remove this');</script>
                    <p>Keep this content</p>
                    <div></div>
                    <!-- Remove this comment -->
                </body>
                </html>
            `;

            await page.setContent(testHtml);
            const cleanedHtml = await customCleaner.getCleanedPageHtml(page);

            // Should keep head section
            expect(cleanedHtml).toContain('<head>');
            expect(cleanedHtml).toContain('<title>Keep Head</title>');
            
            // Should keep style attributes
            expect(cleanedHtml).toContain('style="color: red;"');
            
            // Should remove inline styles
            expect(cleanedHtml).not.toContain('<style>');
            
            // Should remove scripts
            expect(cleanedHtml).not.toContain('<script>');
            
            // Should remove comments
            expect(cleanedHtml).not.toContain('<!--');
            
            // Should remove empty elements
            expect(cleanedHtml).not.toContain('<div></div>');
            
            // Should keep content
            expect(cleanedHtml).toContain('<p>Keep this content</p>');
        });
    });

    describe('HTML Content Analysis', () => {
        it('should provide useful information about cleaned HTML', async () => {
            await page.goto('https://example.com');
            await page.waitForLoadState('networkidle');

            const rawHtml = await page.content();
            const cleanedHtml = await htmlCleaner.getCleanedPageHtml(page);

            // Analyze the cleaning results
            const rawLength = rawHtml.length;
            const cleanedLength = cleanedHtml.length;
            const reductionPercentage = ((rawLength - cleanedLength) / rawLength) * 100;

            console.log('HTML Cleaning Analysis:');
            console.log(`- Raw HTML length: ${rawLength} characters`);
            console.log(`- Cleaned HTML length: ${cleanedLength} characters`);
            console.log(`- Size reduction: ${reductionPercentage.toFixed(2)}%`);
            console.log(`- Characters removed: ${rawLength - cleanedLength}`);

            // Verify significant reduction
            expect(reductionPercentage).toBeGreaterThan(0);
            expect(cleanedLength).toBeLessThan(rawLength);
        });

        it('should preserve essential content structure', async () => {
            await page.goto('https://httpbin.org/html');
            await page.waitForLoadState('networkidle');

            const cleanedHtml = await htmlCleaner.getCleanedPageHtml(page);

            // Check that essential structure is preserved
            expect(cleanedHtml).toContain('<html>');
            expect(cleanedHtml).toContain('<body>');
            expect(cleanedHtml).toContain('</body>');
            expect(cleanedHtml).toContain('</html>');

            // Check that content is preserved
            const bodyMatch = cleanedHtml.match(/<body[^>]*>(.*?)<\/body>/s);
            expect(bodyMatch).toBeTruthy();
            
            if (bodyMatch) {
                const bodyContent = bodyMatch[1];
                expect(bodyContent.length).toBeGreaterThan(0);
                console.log('Body content preserved:', bodyContent.substring(0, 200));
            }
        });
    });

    describe('Error Handling', () => {
        it('should handle malformed HTML gracefully', async () => {
            const malformedHtml = `
                <html>
                <head>
                    <title>Malformed Test</title>
                </head>
                <body>
                    <div>Unclosed div
                    <p>Valid paragraph</p>
                    <script>console.log('unclosed script');</script>
                </body>
                </html>
            `;

            await page.setContent(malformedHtml);
            
            // Should not throw an error
            expect(async () => {
                await htmlCleaner.getCleanedPageHtml(page);
            }).not.toThrow();

            const cleanedHtml = await htmlCleaner.getCleanedPageHtml(page);
            expect(cleanedHtml).toContain('<p>Valid paragraph</p>');
        });

        it('should handle empty pages', async () => {
            await page.setContent('<html><body></body></html>');
            
            const cleanedHtml = await htmlCleaner.getCleanedPageHtml(page);
            expect(cleanedHtml).toContain('<html>');
            expect(cleanedHtml).toContain('<body>');
            expect(cleanedHtml).toContain('</body>');
            expect(cleanedHtml).toContain('</html>');
        });
    });
});
