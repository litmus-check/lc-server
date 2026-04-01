import { Browser, BrowserContext, Page } from 'playwright';
import { DEVICE_TYPES, OPERATING_SYSTEMS, BROWSER_TYPES } from '../config/constants';

export interface BrowserState {
    urls: {
        current: string;
        all: string[];
    };
    activeTab: number;
    screenshot?: Buffer;
    timestamp: number;
}

export interface BrowserConfig {
    headless: boolean;
    viewport: {
        width: number;
        height: number;
    };
    disableSecurity?: boolean;
    extraChromiumArgs?: string[];
    userAgent?: string;
    locale?: string;
    tracePath?: string;
    timeout: number;
    retryAttempts: number;
    waitBetweenActions: number;
    screenshotBeforeAction: boolean;
    screenshotAfterAction: boolean;
    cdpUrl?: string;
    wssUrl?: string;
    chromeInstancePath?: string;
    useBrowserbase?: boolean;
    browserbaseSessionId?: string;
    playwright_config?: {
        browser: typeof BROWSER_TYPES[keyof typeof BROWSER_TYPES];
        device_pixel_ratio: number;
        device: {
            type: typeof DEVICE_TYPES[keyof typeof DEVICE_TYPES];
            device_config: {
                os?: typeof OPERATING_SYSTEMS[keyof typeof OPERATING_SYSTEMS];
            };
        };
        viewport: {
            width: number;
            height: number;
        };
    };
}

export interface BrowserAgentOptions {
    config: BrowserConfig;
    runId?: string;
    composeId?: string;
}

export interface InteractableElement {
    id: string;
    selector: string;
    selectors: Array<{method?: string, selector: string, display: string}>;
    tagName: string;
    boundingBox: {
        x: number;
        y: number;
        width: number;
        height: number;
    };
    isVisible: boolean;
    name?: string;
    placeholder?: string;
    isEnabled: boolean;
    text?: string;
    value?: string;
    isInPopup: boolean;
}

export interface BrowserActionResult {
    success: boolean;
    error?: string;
    screenshot?: Buffer;
    elements?: InteractableElement[];
    executedAction?: string;
    timestamp: number;
}

export interface BrowserTrace {
    id: string;
    startTime: number;
    endTime?: number;
    actions: string[];
    errors: string[];
}
