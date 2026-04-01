import { HtmlCleaner } from '../browser/HtmlCleaner';
import { AiScriptAction } from '../types/actions';
import { ACTION_TYPES } from '../config/constants';

describe('AI Script Action', () => {
    let htmlCleaner: HtmlCleaner;

    beforeEach(() => {
        htmlCleaner = new HtmlCleaner();
    });

    describe('HtmlCleaner', () => {
        it('should clean HTML by removing head section', () => {
            const html = `
                <html>
                    <head>
                        <title>Test Page</title>
                        <script>console.log('test');</script>
                        <style>body { color: red; }</style>
                    </head>
                    <body>
                        <div>Content</div>
                    </body>
                </html>
            `;

            const cleaned = htmlCleaner.cleanHtml(html);
            
            expect(cleaned).not.toContain('<head>');
            expect(cleaned).not.toContain('</head>');
            expect(cleaned).not.toContain('<title>');
            expect(cleaned).not.toContain('<script>');
            expect(cleaned).not.toContain('<style>');
            expect(cleaned).toContain('<div>Content</div>');
        });

        it('should remove script tags and their content', () => {
            const html = `
                <div>
                    <script>alert('test');</script>
                    <p>Content</p>
                    <script src="test.js"></script>
                </div>
            `;

            const cleaned = htmlCleaner.cleanHtml(html);
            
            expect(cleaned).not.toContain('<script>');
            expect(cleaned).not.toContain('</script>');
            expect(cleaned).not.toContain('alert(');
            expect(cleaned).toContain('<p>Content</p>');
        });

        it('should remove style attributes', () => {
            const html = `
                <div style="color: red; background: blue;">
                    <p style="font-size: 14px;">Content</p>
                </div>
            `;

            const cleaned = htmlCleaner.cleanHtml(html);
            
            expect(cleaned).not.toContain('style=');
            expect(cleaned).toContain('<div>');
            expect(cleaned).toContain('<p>Content</p>');
        });

        it('should remove HTML comments', () => {
            const html = `
                <div>
                    <!-- This is a comment -->
                    <p>Content</p>
                    <!-- Another comment -->
                </div>
            `;

            const cleaned = htmlCleaner.cleanHtml(html);
            
            expect(cleaned).not.toContain('<!--');
            expect(cleaned).not.toContain('-->');
            expect(cleaned).toContain('<p>Content</p>');
        });
    });

    describe('AI Script Action Type', () => {
        it('should have correct action type', () => {
            expect(ACTION_TYPES.SCRIPT).toBe('ai_script');
        });

        it('should be included in supported AI actions', () => {
            const supportedActions = [
                ACTION_TYPES.CLICK,
                ACTION_TYPES.VERIFY,
                ACTION_TYPES.INPUT,
                ACTION_TYPES.SELECT,
                ACTION_TYPES.HOVER,
                ACTION_TYPES.FILE_UPLOAD,
                ACTION_TYPES.GOAL,
                ACTION_TYPES.SCRIPT
            ];

            expect(supportedActions).toContain(ACTION_TYPES.SCRIPT);
        });

        it('should create valid AiScriptAction', () => {
            const action: AiScriptAction = {
                type: 'ai_script',
                prompt: 'Fill in the login form with test credentials',
            };

            expect(action.type).toBe('ai_script');
            expect(action.prompt).toBe('Fill in the login form with test credentials');
        });
    });

    describe('HtmlCleaner Configuration', () => {
        it('should use default configuration', () => {
            const config = htmlCleaner.getConfig();
            
            expect(config.removeHead).toBe(true);
            expect(config.removeScripts).toBe(true);
            expect(config.removeStyleAttributes).toBe(true);
            expect(config.removeInlineStyles).toBe(true);
            expect(config.removeComments).toBe(true);
            expect(config.removeEmptyElements).toBe(false);
            expect(config.preserveTextContent).toBe(true);
        });

        it('should allow configuration updates', () => {
            htmlCleaner.updateConfig({
                removeHead: false,
                removeEmptyElements: true
            });

            const config = htmlCleaner.getConfig();
            
            expect(config.removeHead).toBe(false);
            expect(config.removeEmptyElements).toBe(true);
            expect(config.removeScripts).toBe(true); // Should remain from default
        });
    });
});
