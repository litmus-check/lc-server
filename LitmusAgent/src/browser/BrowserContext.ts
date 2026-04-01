import { Browser, BrowserContext as PlaywrightContext, Page } from 'playwright';
import { BrowserConfig } from '../types/browser';
import { logger } from '../utils/logger';
import { DEFAULT_BROWSER_CONFIG, DEVICE_TYPES, USER_AGENTS, BROWSER_TYPES } from '../config/constants';
import * as fs from 'fs';
import * as path from 'path';
import { createLogInstructionFromInstructionObject } from './BrowserAgent';

export class BrowserContext {
    private context: PlaywrightContext | null = null;
    private activePage: Page | null = null;
    private pages: Page[] = [];
    private config: BrowserConfig;
    private browser: Browser;
    private isInitialized: boolean = false;
    private selectorMap: Map<string, any> = new Map();
    private highlights: Set<number> = new Set();

    constructor(browser: Browser, config: BrowserConfig) {
        this.browser = browser;
        this.config = config;
        logger.debug('Created new browser context');
    }

    /**
     * Initialize the browser context
     */
    public async initialize(): Promise<void> {
        try {
            if (this.isInitialized) {
                logger.warn('Browser context already initialized');
                return;
            }

            // Create traces directory if it doesn't exist
            if (this.config.tracePath) {
                const traceDir = path.resolve(this.config.tracePath);
                if (!fs.existsSync(traceDir)) {
                    fs.mkdirSync(traceDir, { recursive: true });
                    logger.info(`Created traces directory at ${traceDir}`);
                }
            }

            // If we're using Browserbase, try to get the existing context
            if (this.config.useBrowserbase) {
                const contexts = this.browser.contexts();
                if (contexts.length > 0) {
                    this.context = contexts[0];
                    logger.info('Using existing Browserbase context');
                } else {
                    // Create new context with custom fingerprinting
                    this.context = await this.createContextWithFingerprint();
                    logger.info('Created new Browserbase context');
                }
            } else {
                // Create new context with custom fingerprinting
                this.context = await this.createContextWithFingerprint();
            }

            // Add anti-detection scripts
            await this.context?.addInitScript(`
                // Webdriver property
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });

                // Languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US']
                });

                // Plugins
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });

                // Chrome runtime
                window.chrome = { runtime: {} };

                // Permissions
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );

                // Shadow DOM
                (function () {
                    const originalAttachShadow = Element.prototype.attachShadow;
                    Element.prototype.attachShadow = function attachShadow(options) {
                        return originalAttachShadow.call(this, { ...options, mode: "open" });
                    };
                })();
            `);

            // Set up page event handlers
            this.setupPageEventHandlers();

            // Get existing pages or create a new one
            if (!this.context) {
                throw new Error('Browser context not initialized');
            }
            
            const pages = this.context.pages();
            if (pages.length > 0) {
                this.activePage = pages[0];
                this.pages = pages;
                logger.info('Using existing page');
            } else {
                // Create initial page
                this.activePage = await this.context.newPage();
                this.pages = [this.activePage];
                logger.info('Created new page');
                
                // Set viewport for new page
                if (this.config.playwright_config?.viewport) {
                    await this.activePage.setViewportSize({
                        width: this.config.playwright_config.viewport.width || DEFAULT_BROWSER_CONFIG.viewport.width,
                        height: this.config.playwright_config.viewport.height || DEFAULT_BROWSER_CONFIG.viewport.height
                    });
                    logger.info('Set viewport for new page:', this.config.playwright_config.viewport);
                } else {
                    logger.warn('No viewport provided in playwright_config');
                }
            }

            // Start tracing if configured
            // if (this.config.tracePath) {
            //     await this.startTracing();
            // }

            this.isInitialized = true;
            logger.info('Browser context initialized successfully');
            
        } catch (error) {
            logger.error('Failed to initialize browser context', error);
            throw error;
        }
    }

    /**
     * Create browser context with custom fingerprinting based on playwright_config
     */
    private async createContextWithFingerprint(): Promise<any> {
        const playwrightConfig = this.config.playwright_config;
        
        if (!playwrightConfig) {
            // Use default context configuration if no config provided
            logger.info('No playwright_config provided, using default context configuration');
            throw new Error('No playwright_config provided');
        }

        // Parse the playwright config structure
        const deviceType = playwrightConfig.device?.type;
        const operatingSystem = playwrightConfig.device?.device_config?.os;
        const browserType = playwrightConfig.browser;
        const viewportWidth = playwrightConfig.viewport?.width;
        const viewportHeight = playwrightConfig.viewport?.height;
        const devicePixelRatio = playwrightConfig.device_pixel_ratio;

        // Determine if mobile
        const isMobile = deviceType === DEVICE_TYPES.MOBILE;
        const hasTouch = isMobile;

        // Create viewport based on playwright_config
        const viewport = {
            width: viewportWidth,
            height: viewportHeight
        };

        // Get the appropriate user agent based on OS and browser
        let userAgent = this.config.userAgent; // Default to config user agent
        if (operatingSystem && browserType) {
            try {
                userAgent = USER_AGENTS[operatingSystem as keyof typeof USER_AGENTS]?.[browserType as keyof typeof USER_AGENTS] || userAgent;
            } catch (error) {
                logger.warn(`Failed to get user agent for OS: ${operatingSystem}, Browser: ${browserType}, using default`);
            }
        }

        // Create context with fingerprint
        const contextOptions: any = {
            viewport: viewport,
            deviceScaleFactor: devicePixelRatio,
            hasTouch: hasTouch,
            javaScriptEnabled: true,
            bypassCSP: this.config.disableSecurity,
            ignoreHTTPSErrors: this.config.disableSecurity,
            locale: this.config.locale,
            userAgent: userAgent
        };

        if (browserType !== BROWSER_TYPES.FIREFOX) {
            contextOptions.isMobile = isMobile;
        }

        // Add user agent metadata if operating system is specified
        if (operatingSystem) {
            contextOptions.userAgentMetadata = {
                platform: operatingSystem
            };
        }

        return await this.browser.newContext(contextOptions);
    }

    /**
     * Set up page event handlers
     */
    private setupPageEventHandlers(): void {
        if (!this.context) return;

        this.context.on('page', async (page: Page) => {
            await page.waitForLoadState();
            this.pages.push(page);
            logger.debug(`New page opened: ${page.url()}`);
        });

        this.context.on('close', () => {
            logger.debug('Browser context closed');
            this.isInitialized = false;
        });
    }

    /**
     * Start tracing
     */
    public async startTracing(): Promise<void> {
        if (!this.context) throw new Error('Browser context not initialized');
        
        try {
            await this.context.tracing.start({
                screenshots: true,
                snapshots: true,
                sources: false
            });
            logger.info('Started tracing');
        } catch (error) {
            // If tracing is already started, that's fine
            if (error instanceof Error && error.message.includes('Tracing has been already started')) {
                logger.info('Tracing already started');
                return;
            }
            throw error;
        }
    }

    /**
     * Stop tracing and save to file
     */
    public async stopTracing(tracePath: string): Promise<void> {
        if (!this.context) throw new Error('Browser context not initialized');

        logger.info(`Stopping tracing and saving to ${tracePath}`);
        
        await this.context.tracing.stop({ path: tracePath });
        logger.info(`Tracing stopped and saved to ${tracePath}`);
        
    }

    /**
     * Get the active page
     */
    public getActivePage(): Page {
        if (!this.activePage) throw new Error('No active page');
        return this.activePage;
    }

    /**
     * Get the Playwright browser context
     */
    public getContext(): PlaywrightContext {
        if (!this.context) throw new Error('Browser context not initialized');
        return this.context;
    }

    /**
     * Get all pages
     */
    public getPages(): Page[] {
        return this.pages;
    }

    /**
     * Switch to a different page
     */
    public async switchPage(index: number): Promise<void> {
        if (index < 0 || index >= this.pages.length) {
            throw new Error(`Invalid page index: ${index}`);
        }
        this.activePage = this.pages[index];
        await this.activePage.bringToFront();
        logger.debug(`Switched to page ${index}`);
    }

    /**
     * Set the active page directly
     */
    public async setActivePage(page: Page): Promise<void> {
        if (!this.pages.includes(page)) {
            // Add the page to the pages array if it's not already there
            this.pages.push(page);
            logger.debug(`Added new page to pages array: ${page.url()}`);
        }
        this.activePage = page;
        await this.activePage.bringToFront();
        logger.debug(`Set active page to: ${page.url()}`);
    }

    /**
     * Add highlight to an element
     */
    public async addHighlight(index: number): Promise<void> {
        if (!this.activePage) throw new Error('No active page');
        
        await this.activePage.evaluate((idx) => {
            const elements = document.querySelectorAll('*');
            if (idx < elements.length) {
                const element = elements[idx] as HTMLElement;
                element.style.outline = '2px solid red';
                element.style.outlineOffset = '2px';
            }
        }, index);
        
        this.highlights.add(index);
        logger.debug(`Added highlight to element ${index}`);
    }

    /**
     * Remove highlight from an element
     */
    public async removeHighlight(index: number): Promise<void> {
        if (!this.activePage) throw new Error('No active page');
        
        await this.activePage.evaluate((idx) => {
            const elements = document.querySelectorAll('*');
            if (idx < elements.length) {
                const element = elements[idx] as HTMLElement;
                element.style.outline = '';
                element.style.outlineOffset = '';
            }
        }, index);
        
        this.highlights.delete(index);
        logger.debug(`Removed highlight from element ${index}`);
    }

    /**
     * Remove all highlights
     */
    public async removeAllHighlights(): Promise<void> {
        if (!this.activePage) throw new Error('No active page');
        
        await this.activePage.evaluate(() => {
            document.querySelectorAll('*').forEach(element => {
                (element as HTMLElement).style.outline = '';
                (element as HTMLElement).style.outlineOffset = '';
            });
        });
        
        this.highlights.clear();
        logger.debug('Removed all highlights');
    }

    /**
     * Get the selector map
     */
    public getSelectorMap(): Map<string, any> {
        return this.selectorMap;
    }

    /**
     * Update the selector map
     */
    public async updateSelectorMap(): Promise<void> {
        if (!this.activePage) throw new Error('No active page');
        
        const newMap = await this.activePage.evaluate(() => {
            const elements = document.querySelectorAll('*');
            const map = new Map();
            
            elements.forEach((element, index) => {
                const rect = element.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) {
                    map.set(index.toString(), {
                        tagName: element.tagName,
                        attributes: Object.fromEntries(
                            Array.from(element.attributes).map(attr => [attr.name, attr.value])
                        ),
                        text: element.textContent?.trim(),
                        rect: {
                            x: rect.x,
                            y: rect.y,
                            width: rect.width,
                            height: rect.height
                        }
                    });
                }
            });
            
            return Array.from(map.entries());
        });
        
        this.selectorMap = new Map(newMap);
        logger.debug('Updated selector map');
    }

    /**
     * Close the browser context
     */
    public async close(): Promise<void> {
        if (this.context) {
            await this.context.close();
            this.context = null;
            this.activePage = null;
            this.pages = [];
            this.isInitialized = false;
        }
    }

    /**
     * Get the current trace file path
     */
    public getTracePath(): string | null {
        if (!this.config.tracePath) {
            return null;
        }
        return path.join(this.config.tracePath, `trace-${Date.now()}.zip`);
    }

    /**
     * Clear browser data (cookies, storage, etc.) while keeping the session alive
     */
    public async clearBrowserData(): Promise<void> {
        if (!this.context) throw new Error('Browser context not initialized');
        
        try {
            // Clear cookies
            await this.context.clearCookies();
            
            // Clear storage for all pages
            for (const page of this.pages) {
                await page.evaluate(() => {
                   
                    if ('caches' in window) {
                        caches.keys().then(keys => {
                            keys.forEach(key => caches.delete(key));
                        });
                    }
                });
            }
            
            logger.info('Browser data cleared successfully');
        } catch (error) {
            logger.error('Failed to clear browser data:', error);
            throw error;
        }
    }

    /**
     * Clear all browser data comprehensively (localStorage, sessionStorage, IndexedDB, caches, etc.) and reload pages
     */
    public async clearAllData(): Promise<void> {
        if (!this.context) throw new Error('Browser context not initialized');
        
        try {
            // Clear cookies
            await this.context.clearCookies();
            
            // Clear storage for all pages
            for (const page of this.pages) {
                await page.evaluate(() => {
                    // Clear localStorage
                    if (typeof localStorage !== 'undefined') {
                        localStorage.clear();
                    }
                    
                    // Clear sessionStorage
                    if (typeof sessionStorage !== 'undefined') {
                        sessionStorage.clear();
                    }
                    
                    // Clear IndexedDB
                    if (typeof indexedDB !== 'undefined') {
                        // Get all databases and delete them
                        indexedDB.databases?.().then(databases => {
                            databases.forEach(db => {
                                if (db.name) {
                                    indexedDB.deleteDatabase(db.name);
                                }
                            });
                        });
                    }
                    
                    // Clear caches
                    if ('caches' in window) {
                        caches.keys().then(keys => {
                            keys.forEach(key => caches.delete(key));
                        });
                    }
                    
                    // Clear service worker registrations
                    if ('serviceWorker' in navigator) {
                        navigator.serviceWorker.getRegistrations().then(registrations => {
                            registrations.forEach(registration => {
                                registration.unregister();
                            });
                        });
                    }
                });
            }
            
            // Clear all storage for the context
            await this.context.clearPermissions();
            
            // Reload all pages to ensure clean state
            for (const page of this.pages) {
                try {
                    await page.reload({ waitUntil: 'networkidle' });
                } catch (error) {
                    logger.warn(`Failed to reload page: ${error}`);
                }
            }
            
            logger.info('All browser data cleared and pages reloaded successfully');
        } catch (error) {
            logger.error('Failed to clear all browser data:', error);
            throw error;
        }
    }

    /**
     * Start a new trace group for an instruction
     */
    public async startInstructionTrace(instruction: { [key: string]: any }): Promise<void> {
        if (!this.context) throw new Error('Browser context not initialized');
        
        try {
            // Create group name in format "action_type | prompt"
            const groupName = createLogInstructionFromInstructionObject(instruction);
            await this.context.tracing.group(groupName as string);
            logger.info(`Started trace group: ${groupName}`);
        } catch (error) {
            logger.error('Error starting trace group:', error);
            throw error;
        }
    }

    /**
     * End the current trace group
     */
    public async endInstructionTrace(): Promise<void> {
        if (!this.context) throw new Error('Browser context not initialized');
        
        try {
            await this.context.tracing.groupEnd();
            logger.info('Ended current trace group');
        } catch (error) {
            logger.error('Error ending trace group:', error);
            throw error;
        }
    }

} 