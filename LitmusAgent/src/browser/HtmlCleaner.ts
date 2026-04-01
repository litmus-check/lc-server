import { Page } from 'playwright';
import { logger } from '../utils/logger';
import { DEFAULT_WORD_COUNT_LIMIT } from '../config/constants';

/**
 * Configuration for HTML cleaning
 */
export interface HtmlCleanerConfig {
    removeHead: boolean;
    removeScripts: boolean;
    removeStyleAttributes: boolean;
    removeInlineStyles: boolean;
    removeComments: boolean;
    removeEmptyElements: boolean;
    removeEventHandlers: boolean;
    preserveTextContent: boolean;
}

/**
 * Default configuration for HTML cleaning
 */
export const DEFAULT_HTML_CLEANER_CONFIG: HtmlCleanerConfig = {
    removeHead: true,
    removeScripts: true,
    removeStyleAttributes: true,
    removeInlineStyles: true,
    removeComments: true,
    removeEmptyElements: false,
    removeEventHandlers: true,
    preserveTextContent: true
};

/**
 * HTML Cleaner utility for cleaning HTML content before AI processing
 */
export class HtmlCleaner {
    private config: HtmlCleanerConfig;

    constructor(config: Partial<HtmlCleanerConfig> = {}) {
        this.config = { ...DEFAULT_HTML_CLEANER_CONFIG, ...config };
    }

    /**
     * Clean HTML content by removing specified elements and attributes
     * @param html The HTML content to clean
     * @returns Cleaned HTML content
     */
    public cleanHtml(html: string): string {
        try {
            let cleanedHtml = html;

            // Remove head section if configured
            if (this.config.removeHead) {
                cleanedHtml = this.removeHeadSection(cleanedHtml);
            }

            // Remove script tags if configured
            if (this.config.removeScripts) {
                cleanedHtml = this.removeScriptTags(cleanedHtml);
            }

            // Remove style attributes if configured
            if (this.config.removeStyleAttributes) {
                cleanedHtml = this.removeStyleAttributes(cleanedHtml);
            }

            // Remove inline styles if configured
            if (this.config.removeInlineStyles) {
                cleanedHtml = this.removeInlineStyles(cleanedHtml);
            }

            // Remove comments if configured
            if (this.config.removeComments) {
                cleanedHtml = this.removeComments(cleanedHtml);
            }

            // Remove empty elements if configured
            if (this.config.removeEmptyElements) {
                cleanedHtml = this.removeEmptyElements(cleanedHtml);
            }

            // Remove event handlers if configured
            if (this.config.removeEventHandlers) {
                cleanedHtml = this.removeEventHandlers(cleanedHtml);
            }

            logger.info('HTML cleaned successfully');
            return cleanedHtml;
        } catch (error) {
            logger.error('Error cleaning HTML:', error);
            throw error;
        }
    }

    /**
     * Remove the entire head section from HTML
     */
    private removeHeadSection(html: string): string {
        return html.replace(/<head[^>]*>[\s\S]*?<\/head>/gi, '');
    }

    /**
     * Remove all script tags and their content
     */
    private removeScriptTags(html: string): string {
        return html.replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '');
    }

    /**
     * Remove style attributes from all elements
     */
    private removeStyleAttributes(html: string): string {
        return html.replace(/\sstyle\s*=\s*["'][^"']*["']/gi, '');
    }

    /**
     * Remove inline style tags and their content
     */
    private removeInlineStyles(html: string): string {
        return html.replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '');
    }

    /**
     * Remove HTML comments
     */
    private removeComments(html: string): string {
        return html.replace(/<!--[\s\S]*?-->/g, '');
    }

    /**
     * Remove empty elements (elements with no content and no attributes)
     */
    private removeEmptyElements(html: string): string {
        // Remove empty divs, spans, p tags, etc.
        return html.replace(/<(div|span|p|section|article|header|footer|nav|aside|main)[^>]*>\s*<\/\1>/gi, '');
    }

    /**
     * Remove event handler attributes (onclick, onload, etc.)
     */
    private removeEventHandlers(html: string): string {
        // Remove common event handler attributes - handle double and single quotes separately
        let cleanedHtml = html;
        // Remove double-quoted event handlers
        cleanedHtml = cleanedHtml.replace(/\s*(onclick|onload|onchange|onsubmit|onmouseover|onmouseout|onfocus|onblur|onkeydown|onkeyup|onkeypress)\s*=\s*"[^"]*"/gi, '');
        // Remove single-quoted event handlers
        cleanedHtml = cleanedHtml.replace(/\s*(onclick|onload|onchange|onsubmit|onmouseover|onmouseout|onfocus|onblur|onkeydown|onkeyup|onkeypress)\s*=\s*'[^']*'/gi, '');
        return cleanedHtml;
    }

    /**
     * Get page HTML and clean it using page.evaluate
     * @param page The Playwright page object
     * @param wordCountLimit Maximum number of words to include in the cleaned HTML (default: 10000)
     * @returns Cleaned HTML content
     */
    public async getCleanedPageHtml(page: Page, wordCountLimit: number = DEFAULT_WORD_COUNT_LIMIT): Promise<string> {
        try {
            const cleanedHtml = await page.evaluate(({ config, wordLimit }) => {
                // Get the full HTML content
                let html = document.documentElement.outerHTML;

                // Remove head section if configured
                if (config.removeHead) {
                    html = html.replace(/<head[^>]*>[\s\S]*?<\/head>/gi, '');
                }

                // Remove script tags if configured
                if (config.removeScripts) {
                    html = html.replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '');
                }

                // Remove style attributes if configured
                if (config.removeStyleAttributes) {
                    html = html.replace(/\sstyle\s*=\s*["'][^"']*["']/gi, '');
                }

                // Remove inline style tags if configured
                if (config.removeInlineStyles) {
                    html = html.replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '');
                }

                // Remove comments if configured
                if (config.removeComments) {
                    html = html.replace(/<!--[\s\S]*?-->/g, '');
                }

                // Remove empty elements if configured
                if (config.removeEmptyElements) {
                    html = html.replace(/<(div|span|p|section|article|header|footer|nav|aside|main)[^>]*>\s*<\/\1>/gi, '');
                }

                // Remove event handlers if configured
                if (config.removeEventHandlers) {
                    // Remove double-quoted event handlers
                    html = html.replace(/\s*(onclick|onload|onchange|onsubmit|onmouseover|onmouseout|onfocus|onblur|onkeydown|onkeyup|onkeypress)\s*=\s*"[^"]*"/gi, '');
                    // Remove single-quoted event handlers
                    html = html.replace(/\s*(onclick|onload|onchange|onsubmit|onmouseover|onmouseout|onfocus|onblur|onkeydown|onkeyup|onkeypress)\s*=\s*'[^']*'/gi, '');
                }

                // Apply word count limit if specified
                if (wordLimit && wordLimit > 0) {
                    // Extract text content and count words
                    const tempDiv = document.createElement('div');
                    tempDiv.innerHTML = html;
                    const textContent = tempDiv.textContent || tempDiv.innerText || '';
                    const words = textContent.trim().split(/\s+/).filter(word => word.length > 0);
                    
                    if (words.length > wordLimit) {
                        // If word count exceeds limit, truncate the HTML
                        // We'll truncate by removing content from the end while preserving structure
                        const truncatedWords = words.slice(0, wordLimit);
                        const truncatedText = truncatedWords.join(' ');
                        
                        // Simple approach: find the position in the original HTML where we need to cut
                        let currentWordCount = 0;
                        let cutPosition = 0;
                        
                        // Walk through the HTML character by character to find the cut point
                        const htmlText = tempDiv.textContent || '';
                        const htmlWords = htmlText.trim().split(/\s+/).filter(word => word.length > 0);
                        
                        if (htmlWords.length > wordLimit) {
                            // Find the position of the last word we want to keep
                            const wordsToKeep = htmlWords.slice(0, wordLimit);
                            const textToKeep = wordsToKeep.join(' ');
                            
                            // Find this text in the original HTML
                            const textIndex = html.indexOf(textToKeep);
                            if (textIndex !== -1) {
                                cutPosition = textIndex + textToKeep.length;
                            } else {
                                // Fallback: estimate position based on word ratio
                                const wordRatio = wordLimit / htmlWords.length;
                                cutPosition = Math.floor(html.length * wordRatio);
                            }
                            
                            // Truncate the HTML at the calculated position
                            html = html.substring(0, cutPosition);
                            
                            // Ensure we don't cut in the middle of a tag
                            const lastOpenTag = html.lastIndexOf('<');
                            const lastCloseTag = html.lastIndexOf('>');
                            
                            if (lastOpenTag > lastCloseTag) {
                                // We cut in the middle of a tag, remove the incomplete tag
                                html = html.substring(0, lastOpenTag);
                            }
                        }
                    }
                }

                return html;
            }, { config: this.config, wordLimit: wordCountLimit });

            logger.info('Page HTML cleaned successfully');
            return cleanedHtml;
        } catch (error) {
            logger.error('Error getting cleaned page HTML:', error);
            throw error;
        }
    }

    /**
     * Update the cleaner configuration
     * @param newConfig Partial configuration to update
     */
    public updateConfig(newConfig: Partial<HtmlCleanerConfig>): void {
        this.config = { ...this.config, ...newConfig };
        logger.info('HTML cleaner configuration updated');
    }

    /**
     * Get the current configuration
     * @returns Current configuration
     */
    public getConfig(): HtmlCleanerConfig {
        return { ...this.config };
    }
}
