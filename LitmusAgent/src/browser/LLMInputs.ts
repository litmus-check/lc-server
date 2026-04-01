import { Page } from 'playwright';
import { InteractableElement } from '../types/browser';
import { logger } from '../utils/logger';
import { ActionType } from '../types/actions';
import { InteractableElementsManager } from './InteractableElementsManager';
import { ContainerCommsService } from '../services/ContainerCommsService';


// Add new interfaces and types
interface SafeAttributes {
    data: string[];
    standard: string[];
    accessibility: string[];
    form: string[];
    media: string[];
    custom: string[];
}

// Add utility functions for selector creation
const SAFE_ATTRIBUTES: SafeAttributes = {
    data: ['data-testid', 'data-qa', 'data-cy', 'data-id'],
    standard: ['id', 'name', 'type', 'placeholder'],
    accessibility: ['aria-label', 'aria-labelledby', 'aria-describedby', 'role'],
    form: ['for', 'autocomplete', 'required', 'readonly'],
    media: ['alt', 'title', 'src'],
    custom: ['href', 'target']
};


// Add type definition for the evaluate function result
interface ElementData {
    id: string;
    selector: string;
    selectors: Array<{ method?: string, selector: string, display: string }>; // Array of all generated selectors with display
    tagName: string;
    boundingBox: {
        x: number;
        y: number;
        width: number;
        height: number;
    };
    isVisible: boolean;
    isEnabled: boolean;
    text?: string;
    value?: string;
    name?: string;
    placeholder?: string;
    isInPopup: boolean;
    attributes?: Record<string, string>; // All element attributes except class and style
}

// Add type for the evaluate function parameters
interface EvaluateParams {
    actionType: ActionType;
    safeAttributes: SafeAttributes;
    isDOMChangeCheck: boolean;
    addNonInteractable: boolean;
}


export class LLMInputs {
    private elementsManager: InteractableElementsManager;
    private lastDOMSnapshot: string = '';

    constructor(private page: Page) {
        this.elementsManager = InteractableElementsManager.getInstance();

    }

    /**
     * Update the page reference
     */
    public updatePageReference(newPage: Page): void {
        this.page = newPage;
        logger.info(`LLMInputs: Updated page reference to: ${newPage.url()}`);
    }




    /**
     * Get all relevant inputs for LLM processing
     * @param actionType Type of action being performed
     * @returns Object containing screenshot, elements, and current URL
     */
    public async getInputs(actionType: ActionType, addNonInteractable: boolean = false): Promise<{
        screenshot: string;
        elements: InteractableElement[];
        currentUrl: string;
    }> {
        try {
            // Create viewport and elements array with screenshot
            await this.createViewport();

            // First call: Get initial elements and screenshot
            const initialResult = await this.createElementsArrayAndTakeScreenshot(actionType, false, 0, addNonInteractable);
            logger.info('Created initial elements array and took screenshot');

            // Second call: Check for DOM changes and refresh if needed
            const domChangeResult = await this.createElementsArrayAndTakeScreenshot(actionType, true, 0, addNonInteractable);
            logger.info('Checked for DOM changes and refreshed elements if needed');

            if (domChangeResult?.hasDOMChanged) {
                logger.info('DOM changes detected before sending inputs to LLM, using fresh element data');
            }

            // Use the result from DOM change check (which has the most up-to-date data)
            const finalResult = domChangeResult?.hasDOMChanged ? domChangeResult : initialResult;
            const screenshot = finalResult?.screenshot;


            // Get current URL
            const currentUrl = this.page.url();

            if (screenshot == '') {
                return {
                    elements: this.elementsManager.getElements(),
                    currentUrl,
                    screenshot: ''
                }
            }

            return {
                screenshot: `data:image/png;base64,${screenshot}`,
                elements: this.elementsManager.getElements(),
                currentUrl
            };
        } catch (error) {
            logger.error('Failed to get LLM inputs', error);
            throw error;
        }
    }

    /**
     * Create viewport for the page
     */
    private async createViewport(): Promise<void> {
        try {
            // Wait for the page to be ready using a more reliable approach
            await Promise.race([
                this.page.waitForLoadState('domcontentloaded'),
                this.page.waitForLoadState('load'),
                new Promise(resolve => setTimeout(resolve, 5000)) // Fallback timeout
            ]);
        } catch (error) {
            logger.error('Failed to create viewport', error);
            throw error;
        }
    }

    /**
     * Create elements array by executing JS on the page and take screenshot with bounding boxes
     */
    public async createElementsArrayAndTakeScreenshot(actionType: ActionType, isDOMChangeCheck: boolean, attempt: number = 0, addNonInteractable: boolean = false): Promise<{ elements: ElementData[], screenshot: string, hasDOMChanged: boolean } | null> {
        try {
            logger.info('Creating elements array and taking screenshot');
            // First create bounding box overlays and get elements
            logger.info(`Current URL in screenshot ${this.page.url()}`)
            const result = await this.page.evaluate(
                ({ actionType, safeAttributes, isDOMChangeCheck, addNonInteractable }: EvaluateParams) => {
                    // Text normalization function for Playwright selectors
                    function normalizeTextForPlaywright(text: string): string {
                        return text
                            .replace(/\s+/g, ' ')  // Collapse all whitespace (space, tab, newline) to a single space
                            .trim();               // Trim leading/trailing whitespace
                    }

                    // Get only direct text content (not from child elements)
                    function getDirectTextContent(element: Element): string {
                        let directText = '';
                        for (const node of element.childNodes) {
                            if (node.nodeType === Node.TEXT_NODE) {
                                directText += node.textContent || '';
                            }
                        }
                        return directText;
                    }

                    // Performance optimization with caching
                    const DOM_CACHE = {
                        boundingRects: new WeakMap(),
                        computedStyles: new WeakMap(),
                        clearCache: () => {
                            DOM_CACHE.boundingRects = new WeakMap();
                            DOM_CACHE.computedStyles = new WeakMap();
                        }
                    };

                    // DOM snapshot function (moved from getDOMSnapshot)
                    function getDOMSnapshot(): string {
                        const walker = document.createTreeWalker(
                            document.body,
                            NodeFilter.SHOW_ELEMENT,
                            {
                                acceptNode: (node) => {
                                    const element = node as Element;
                                    const tagName = element.tagName.toLowerCase();

                                    // Skip non-visible elements
                                    if (['script', 'style', 'meta', 'link', 'title'].includes(tagName)) {
                                        return NodeFilter.FILTER_REJECT;
                                    }

                                    // Skip hidden elements
                                    const style = window.getComputedStyle(element);
                                    if (style.display === 'none' || style.visibility === 'hidden') {
                                        return NodeFilter.FILTER_REJECT;
                                    }

                                    return NodeFilter.FILTER_ACCEPT;
                                }
                            }
                        );

                        const snapshot: string[] = [];
                        let node;
                        while (node = walker.nextNode()) {
                            const element = node as Element;
                            snapshot.push(`${element.tagName.toLowerCase()}:${element.className}:${element.id}`);
                        }

                        return snapshot.join('|');
                    }

                    function getCachedBoundingRect(element: Element): DOMRect | null {
                        if (!element) return null;
                        if (DOM_CACHE.boundingRects.has(element)) {
                            return DOM_CACHE.boundingRects.get(element);
                        }
                        const rect = element.getBoundingClientRect();
                        if (rect) {
                            DOM_CACHE.boundingRects.set(element, rect);
                        }
                        return rect;
                    }

                    function getCachedComputedStyle(element: Element): CSSStyleDeclaration | null {
                        if (!element) return null;
                        if (DOM_CACHE.computedStyles.has(element)) {
                            return DOM_CACHE.computedStyles.get(element);
                        }
                        const style = window.getComputedStyle(element);
                        if (style) {
                            DOM_CACHE.computedStyles.set(element, style);
                        }
                        return style;
                    }

                    // Enhanced XPath generation
                    function getXPathTree(element: Element, stopAtBoundary = true): string {
                        //   if (element.id) return `//*[@id="${element.id}"]`;
                        if (element === document.body) return '/html/body';

                        let ix = 0;
                        const siblings = element.parentNode?.childNodes || [];

                        for (let i = 0; i < siblings?.length; i++) {
                            const sibling = siblings[i];
                            if (sibling === element) {
                                return getXPathTree(element.parentNode as Element) + '/' + element.tagName.toLowerCase() + '[' + (ix + 1) + ']';
                            }
                            if (sibling.nodeType === 1 && (sibling as Element).tagName === element.tagName) {
                                ix++;
                            }
                        }
                        return '';
                    }

                    // Enhanced element acceptance check
                    function isElementAccepted(element: Element, actionType: ActionType): boolean {
                        if (!element || element.nodeType !== Node.ELEMENT_NODE) return false;

                        const tagName = element.tagName.toLowerCase();
                        const excludedTags = ['script', 'style', 'noscript', 'meta', 'link', 'title', 'head', 'body', 'html'];

                        if (excludedTags.includes(tagName)) return false;

                        if (actionType !== 'ai_file_upload') {
                            // Check for hidden elements
                            const style = getCachedComputedStyle(element);
                            if (style && (style.display === 'none' || style.visibility === 'hidden')) return false;
                        }

                        return true;
                    }

                    // Enhanced element visibility check
                    function isElementVisible(element: Element): boolean {
                        if (!element || element.nodeType !== Node.ELEMENT_NODE) return false;

                        const rect = getCachedBoundingRect(element);
                        const style = getCachedComputedStyle(element);

                        if (!rect || !style) return false;

                        return style.display !== 'none' &&
                            style.visibility !== 'hidden' &&
                            style.opacity !== '0' &&
                            rect.width > 0 &&
                            rect.height > 0;
                    }

                    // Enhanced top element detection
                    function isTopElement(element: Element): boolean {
                        const rect = getCachedBoundingRect(element);
                        if (!rect) return false;

                        // Check if element is in viewport
                        const isInViewport = (
                            rect.left < window.innerWidth &&
                            rect.right > 0 &&
                            rect.top < window.innerHeight &&
                            rect.bottom > 0
                        );

                        if (!isInViewport) return false;

                        // Check if element is the topmost at its position
                        const centerX = rect.left + rect.width / 2;
                        const centerY = rect.top + rect.height / 2;

                        const elementAtPoint = document.elementFromPoint(centerX, centerY);
                        return elementAtPoint === element || element.contains(elementAtPoint);
                    }

                    // Enhanced viewport expansion check
                    function isInExpandedViewport(element: Element, viewportExpansion: number): boolean {
                        if (viewportExpansion === -1) return true;

                        const rect = getCachedBoundingRect(element);
                        if (!rect) return false;

                        const style = getCachedComputedStyle(element);
                        const isFixedOrSticky = style && (style.position === 'fixed' || style.position === 'sticky');

                        if (isFixedOrSticky) return true;

                        return rect.bottom >= -viewportExpansion &&
                            rect.top <= window.innerHeight + viewportExpansion &&
                            rect.right >= -viewportExpansion &&
                            rect.left <= window.innerWidth + viewportExpansion;
                    }

                    // Enhanced popup detection
                    function isInPopup(element: Element): boolean {
                        const popupSelectors = [
                            '[role="dialog"]', '[role="alertdialog"]',
                            '.modal', '.popup', '.overlay', '.dialog', '.lightbox', '.tooltip',
                            '.dropdown-menu', '.dropdown-content', '.popover', '.notification', '.toast',
                            '[data-modal]', '[data-popup]', '[data-overlay]',
                            '.ReactModal__Overlay', '.MuiModal-root', '.ant-modal', '.el-dialog',
                            '.v-dialog', '.b-modal', '.popup-container', '.modal-container', '.overlay-container'
                        ];

                        for (const selector of popupSelectors) {
                            if (element.closest(selector)) return true;
                        }

                        const style = getCachedComputedStyle(element);
                        if (style) {
                            const zIndex = parseInt(style.zIndex);
                            if (zIndex > 1000) return true;
                            if ((style.position === 'fixed' || style.position === 'absolute') && zIndex > 100) return true;
                        }

                        return false;
                    }

                    // Enhanced event listener detection
                    function getEventListeners(el: Element): Record<string, any[]> {
                        try {
                            return (window as any).getEventListeners?.(el) || {};
                        } catch (e) {
                            const listeners: Record<string, any[]> = {};
                            const eventTypes = ['click', 'mousedown', 'mouseup', 'touchstart', 'touchend', 'keydown', 'keyup', 'focus', 'blur'];

                            for (const type of eventTypes) {
                                const handler = (el as any)[`on${type}`];
                                if (handler) {
                                    listeners[type] = [{ listener: handler, useCapture: false }];
                                }
                            }
                            return listeners;
                        }
                    }

                    // Enhanced interactive element detection
                    function isInteractiveElement(element: Element): boolean {
                        if (!element || element.nodeType !== Node.ELEMENT_NODE) return false;

                        // Cookie banner handling
                        const isCookieBannerElement = element.closest && (
                            element.closest('[id*="onetrust"]') ||
                            element.closest('[class*="onetrust"]') ||
                            element.closest('[data-nosnippet="true"]') ||
                            element.closest('[aria-label*="cookie"]')
                        );

                        if (isCookieBannerElement) {
                            if (element.tagName.toLowerCase() === 'button' ||
                                element.getAttribute('role') === 'button' ||
                                (element as HTMLElement).onclick ||
                                element.getAttribute('onclick') ||
                                element.classList?.contains('ot-sdk-button') ||
                                element.classList?.contains('accept-button') ||
                                element.classList?.contains('reject-button') ||
                                (element.getAttribute('aria-label')?.toLowerCase() || '').includes('accept') ||
                                (element.getAttribute('aria-label')?.toLowerCase() || '').includes('reject')) {
                                return true;
                            }
                        }

                        // Base interactive elements and roles
                        const interactiveElements = new Set([
                            "a", "button", "details", "embed", "input", "menu", "menuitem",
                            "object", "select", "textarea", "canvas", "summary", "dialog", "banner"
                        ]);

                        const interactiveRoles = new Set([
                            'button-icon', 'dialog', 'button-text-icon-only', 'treeitem', 'alert', 'grid',
                            'progressbar', 'radio', 'checkbox', 'menuitem', 'option', 'switch', 'dropdown',
                            'scrollbar', 'combobox', 'a-button-text', 'button', 'region', 'textbox', 'tabpanel',
                            'tab', 'click', 'button-text', 'spinbutton', 'a-button-inner', 'link', 'menu',
                            'slider', 'listbox', 'a-dropdown-button', 'button-icon-only', 'searchbox',
                            'menuitemradio', 'tooltip', 'tree', 'menuitemcheckbox'
                        ]);
                        const tagName = element.tagName.toLowerCase();
                        const role = element.getAttribute("role");
                        const ariaRole = element.getAttribute("aria-role");
                        const tabIndex = element.getAttribute("tabindex");

                        // Address input class check
                        const hasAddressInputClass = element.classList && (
                            element.classList.contains("address-input__container__input") ||
                            element.classList.contains("nav-btn") ||
                            element.classList.contains("pull-left")
                        );

                        // Dropdown interactive elements
                        if (element.classList && (
                            element.classList.contains('dropdown-toggle') ||
                            element.getAttribute('data-toggle') === 'dropdown' ||
                            element.getAttribute('aria-haspopup') === 'true'
                        )) {
                            return true;
                        }

                        // Basic role/attribute checks
                        const hasInteractiveRole = hasAddressInputClass ||
                            interactiveElements.has(tagName) ||
                            (role && interactiveRoles.has(role)) ||
                            (ariaRole && interactiveRoles.has(ariaRole)) ||
                            (tabIndex !== null && tabIndex !== "-1" && element.parentElement?.tagName.toLowerCase() !== "body") ||
                            element.getAttribute("data-action") === "a-dropdown-select" ||
                            element.getAttribute("data-action") === "a-dropdown-button";

                        if (hasInteractiveRole) return true;

                        // Cookie banner checks
                        // Ensure element.id is converted to string before calling toLowerCase
                        const elementId = element?.id ? String(element?.id) : '';
                        const elementIdLower = elementId?.toLowerCase();
                        const isCookieBanner = elementIdLower?.includes('cookie') ||
                            elementIdLower?.includes('consent') ||
                            elementIdLower?.includes('notice') ||
                            (element.classList && (
                                element.classList.contains('otCenterRounded') ||
                                element.classList.contains('ot-sdk-container')
                            )) ||
                            element.getAttribute('data-nosnippet') === 'true' ||
                            (element.getAttribute('aria-label')?.toLowerCase() || '').includes('cookie') ||
                            (element.getAttribute('aria-label')?.toLowerCase() || '').includes('consent') ||
                            (element.tagName.toLowerCase() === 'div' && (
                                elementId?.includes('onetrust') ||
                                (element.classList && (
                                    element.classList.contains('onetrust') ||
                                    element.classList.contains('cookie') ||
                                    element.classList.contains('consent')
                                ))
                            ));

                        if (isCookieBanner) return true;

                        // Cookie banner button check
                        const isInCookieBanner = element.closest && element.closest(
                            '[id*="cookie"],[id*="consent"],[class*="cookie"],[class*="consent"],[id*="onetrust"]'
                        );

                        if (isInCookieBanner && (
                            element.tagName.toLowerCase() === 'button' ||
                            element.getAttribute('role') === 'button' ||
                            element.classList?.contains('button') ||
                            (element as HTMLElement).onclick ||
                            element.getAttribute('onclick')
                        )) {
                            return true;
                        }

                        // Event listener checks
                        const hasClickHandler = (element as HTMLElement).onclick !== null ||
                            element.getAttribute("onclick") !== null ||
                            element.hasAttribute("ng-click") ||
                            element.hasAttribute("@click") ||
                            element.hasAttribute("v-on:click");

                        const listeners = getEventListeners(element);
                        const hasClickListeners = listeners &&
                            (listeners.click?.length > 0 ||
                                listeners.mousedown?.length > 0 ||
                                listeners.mouseup?.length > 0 ||
                                listeners.touchstart?.length > 0 ||
                                listeners.touchend?.length > 0);

                        // ARIA properties check
                        const hasAriaProps = element.hasAttribute("aria-expanded") ||
                            element.hasAttribute("aria-pressed") ||
                            element.hasAttribute("aria-selected") ||
                            element.hasAttribute("aria-checked");

                        // Content editable check
                        const isContentEditable = element.getAttribute("contenteditable") === "true" ||
                            (element as HTMLElement).isContentEditable ||
                            element.id === "tinymce" ||
                            element.classList.contains("mce-content-body") ||
                            (element.tagName.toLowerCase() === "body" && element.getAttribute("data-id")?.startsWith("mce_"));

                        // Draggable check
                        const isDraggable = (element as HTMLElement).draggable || element.getAttribute("draggable") === "true";

                        return !!(hasAriaProps || hasClickHandler || hasClickListeners || isDraggable || isContentEditable);
                    }

                    // Enhanced element collection with iframe and shadow DOM support
                    function getAllInteractiveElements(selector: string): Element[] {
                        const allElements: Element[] = [];

                        // Regular DOM elements
                        const elements = document.querySelectorAll(selector);
                        allElements.push(...Array.from(elements));

                        // Shadow DOM elements
                        document.querySelectorAll('*').forEach(el => {
                            if (el.shadowRoot) {
                                const shadowEls = el.shadowRoot.querySelectorAll(selector);
                                allElements.push(...Array.from(shadowEls));
                            }
                        });

                        // Iframe elements
                        document.querySelectorAll('iframe').forEach(iframe => {
                            try {
                                const iframeDoc = iframe.contentDocument || iframe.contentWindow?.document;
                                if (iframeDoc) {
                                    const iframeEls = iframeDoc.querySelectorAll(selector);
                                    allElements.push(...Array.from(iframeEls));
                                }
                            } catch (e) {
                                // Cross-origin iframe access denied
                            }
                        });

                        return allElements;
                    }

                    // Get elements based on action type
                    const selector = actionType === 'ai_click' ? `
                       *
                    ` : actionType === 'ai_input' ? `
                        textarea,
                        input, 
                        [contenteditable="true"], 
                        [role="textbox"]
                    ` : actionType === 'ai_select' ? `
                        select, 
                        input[type="checkbox"], 
                        input[type="radio"], 
                        input[type="file"],
                        [role="checkbox"], 
                        [role="radio"], 
                        [role="switch"]
                    ` : actionType === 'ai_file_upload' ? `
                            *
                    ` : actionType === 'ai_hover' ? `
                        a, 
                        button, 
                        img, 
                        div, 
                        span, 
                        li, 
                        tr, 
                        td, 
                        th, 
                        p, 
                        h1, h2, h3, h4, h5, h6,
                        [data-toggle="tooltip"],
                        [aria-haspopup="true"],
                        [data-bs-toggle="tooltip"],
                        [title],
                        [data-tooltip]
                    ` : actionType === 'ai_verify' || actionType === 'verify' || actionType === 'ai_script' || actionType === 'ai_assert' ? `
                        *
                    ` : actionType === 'ai_goal' ? `
                        button, 
                        a, 
                        label, 
                        div,
                        summary, 
                        details, 
                        input,
                        [role="button"], 
                        [role="link"],
                        textarea, 
                        select,
                        [onclick],
                        [data-action],
                        [role="menuitem"],
                        [role="tab"],
                        [role="option"],
                        [role="checkbox"],
                        [role="radio"],
                        [role="switch"],
                        [role="slider"],
                        [role="spinbutton"],
                        [role="combobox"],
                        [role="listbox"],
                        [role="gridcell"],
                        [role="textbox"],
                        [tabindex]:not([tabindex="-1"]),
                        [cursor="pointer"],
                        [contenteditable="true"],
                        .clickable,
                        .interactive,
                        .btn,
                        .button,
                        .nav-link,
                        .dropdown-toggle,
                        .modal-trigger,
                        .tab,
                        .accordion-toggle,
                        .carousel-control,
                        .slider-handle,
                        .toggle,
                        .switch,
                        [ng-click],
                        [data-bind],
                        [data-toggle],
                        [data-target],
                        a, 
                        img, 
                        span, 
                        li, 
                        tr, 
                        td, 
                        th, 
                        p, 
                        h1, h2, h3, h4, h5, h6,
                        [data-toggle="tooltip"],
                        [aria-haspopup="true"],
                        [data-bs-toggle="tooltip"],
                        [title],
                        [data-tooltip]
                    ` : '';

                    // Get all elements including those in popups, iframes, and shadow DOM
                    const allElements = getAllInteractiveElements(selector);

                    // Step 1: Filter accepted elements
                    const acceptedElements = allElements.filter(el => {
                        const result = isElementAccepted(el, actionType);
                        return result;
                    });

                    // Step 2: Filter visible elements
                    let visibleElements = acceptedElements;
                    if (actionType !== 'ai_file_upload') {
                        visibleElements = acceptedElements.filter(el => {
                            const result = isElementVisible(el);
                            return result;
                        });
                    }

                    // Step 3: Filter top elements
                    let topElements = visibleElements;
                    if (actionType !== 'ai_file_upload') {
                        if (addNonInteractable) {
                            // For non-interactable elements, skip top element filtering as they might be covered
                            topElements = visibleElements;
                        } else {
                            // Default behavior: only include top elements
                            topElements = visibleElements.filter(el => {
                                const result = isTopElement(el);
                                return result;
                            });
                        }
                    }

                    // Step 4: Filter interactive elements
                    let interactiveElements = topElements;
                    if (actionType !== 'ai_file_upload') {
                        if (addNonInteractable) {
                            // Include both interactive elements and non-interactive elements with text
                            interactiveElements = topElements.filter(el => {
                                const isInteractive = isInteractiveElement(el);
                                const hasText = el.textContent && el.textContent.trim().length > 0;
                                return isInteractive || hasText;
                            });
                        } else {
                            // Default behavior: only include interactive elements
                            interactiveElements = topElements.filter(el => {
                                const result = isInteractiveElement(el);
                                return result;
                            });
                        }
                    }

                    // Step 5: Filter viewport elements
                    const processedElements = interactiveElements.filter(el => {
                        const result = isInExpandedViewport(el, 0); // No viewport expansion for now
                        return result;
                    });

                    // Remove duplicates
                    const uniqueElements = processedElements.filter((el, index, arr) =>
                        arr.findIndex(e => e === el) === index
                    );

                    const domSnapshot = getDOMSnapshot();
                    if (domSnapshot === this.lastDOMSnapshot && isDOMChangeCheck && this.lastDOMSnapshot !== '') {
                        return
                    }
                    this.lastDOMSnapshot = domSnapshot;

                    return {
                        elements: uniqueElements.map((el, index) => {
                            const rect = getCachedBoundingRect(el);
                            const style = getCachedComputedStyle(el);

                            // Check if element is in a popup
                            const isInPopupElement = isInPopup(el);

                            // Generate enhanced selector
                            const config = {
                                includeDynamicAttributes: true,
                                safeAttributes: safeAttributes
                            };

                            let selector = '';

                            // Helper function to check for duplicates
                            function hasDuplicateElements(selector: string): boolean {
                                try {
                                    const elements = document.querySelectorAll(selector.toString());
                                    // logger.info(`Elements has duplicates: ${elements}`);
                                    return elements?.length > 1;
                                } catch (e) {
                                    //  logger.info(`Error in hasDuplicateElements: ${e}`);
                                    return false; // Invalid selector
                                }
                            }




                            function generateSelectorArray(element: Element): Array<{ method?: string, selector: string, display: string }> {
                                const selectors: Array<{ method?: string, selector: string, display: string }> = [];
                                const tagName = element.tagName.toLowerCase();

                                // Helper function to check if attribute value only contains allowed characters
                                // Allowed: alphanumerics, -, _, /, :, ?, space
                                function isValidAttributeValue(value: string): boolean {
                                    if (!value) return false;
                                    // Regex: only allow alphanumerics, -, _, /, :, ?, and space
                                    return /^[a-zA-Z0-9\-_\/:? ]+$/.test(value);
                                }

                                // Helper function to escape CSS selectors
                                function escapeIdForCss(id: string): string {
                                    return '#' + CSS.escape(id);
                                }

                                // Helper function to add selector if unique
                                function addUniqueSelector(method: string, selector: string, display: string): boolean {
                                    //logger.info(`Adding unique selector (outside): ${selector}`);
                                    if (method === 'page.getByRole' || method === 'page.getByLabel' || method === 'page.getByText') {
                                        // For Playwright selectors, we'll add them and let ActionHandler filter duplicates later
                                        selectors.push({ method, selector, display });
                                        return true;
                                    }
                                    if (selector.startsWith('xpath=')) {
                                        // XPath selectors should always be unique, so always add them
                                        selectors.push({ method, selector, display });
                                        return true;
                                    }
                                    if (!hasDuplicateElements(selector)) {
                                        //  logger.info(`Adding unique selector (inside): ${selector}`);
                                        selectors.push({ method, selector, display });
                                        return true;
                                    }
                                    //logger.info(`Duplicate selector: ${selector}`);
                                    return false;
                                }

                                // Check for data and test attributes dynamically
                                Array.from(element.attributes).forEach(attr => {
                                    const attrName = attr.name.toLowerCase();
                                    const attrValue = attr.value;
                                    
                                    // Check if attribute name contains "data" or "test"
                                    if ((attrName.includes('data') || attrName.includes('test')) && attrValue && isValidAttributeValue(attrValue)) {
                                        addUniqueSelector('page.locator', `${tagName}[${attr.name}="${CSS.escape(attrValue)}"]`, `Get By Test ID`);
                                    }
                                });

                                // 11. Role attribute with accessible name (explicit or implicit)
                                let role = element.getAttribute('role');

                                // If no explicit role, check for implicit roles based on tag name
                                if (!role) {
                                    const implicitRoles: Record<string, string> = {
                                        'button': 'button',
                                        'input': element.tagName.toLowerCase() === 'input' ? getInputRole(element as HTMLInputElement) : 'textbox',
                                        'a': 'link',
                                        'select': 'combobox',
                                        'textarea': 'textbox',
                                        'h1': 'heading',
                                        'h2': 'heading',
                                        'h3': 'heading',
                                        'h4': 'heading',
                                        'h5': 'heading',
                                        'h6': 'heading',
                                        'nav': 'navigation',
                                        'main': 'main',
                                        'header': 'banner',
                                        'footer': 'contentinfo',
                                        'aside': 'complementary',
                                        'section': 'region',
                                        'article': 'article',
                                        'form': 'form',
                                        'table': 'table',
                                        'ul': 'list',
                                        'ol': 'list',
                                        'li': 'listitem',
                                        'tr': 'row',
                                        'td': 'cell',
                                        'th': 'columnheader',
                                        'checkbox': 'checkbox',
                                        'radio': 'radio',
                                        'switch': 'switch',
                                        'slider': 'slider',
                                        'spinbutton': 'spinbutton',
                                        'combobox': 'combobox',
                                        'listbox': 'listbox',
                                        'grid': 'grid',
                                        'gridcell': 'gridcell',
                                        'menuitem': 'menuitem',
                                        'menuitemcheckbox': 'menuitemcheckbox',
                                        'menuitemradio': 'menuitemradio',
                                        'option': 'option',
                                        'tab': 'tab',
                                        'tabpanel': 'tabpanel',
                                        'toolbar': 'toolbar',
                                        'tooltip': 'tooltip',
                                        'tree': 'tree',
                                        'treeitem': 'treeitem',
                                        'alert': 'alert',
                                        'alertdialog': 'alertdialog',
                                        'dialog': 'dialog',
                                        'log': 'log',
                                        'marquee': 'marquee',
                                        'status': 'status',
                                        'timer': 'timer',
                                        'progressbar': 'progressbar',
                                        'scrollbar': 'scrollbar',
                                        'searchbox': 'searchbox',
                                        'textbox': 'textbox'
                                    };

                                    role = implicitRoles[tagName] || implicitRoles[element.getAttribute('type') || ''];
                                }

                                // Get accessible name from various sources (following W3C spec)
                                let accessibleName = '';

                                // 1. aria-labelledby (highest priority)
                                if (element.getAttribute('aria-labelledby')) {
                                    const ariaLabelledBy = element.getAttribute('aria-labelledby');
                                    if (ariaLabelledBy) {
                                        const labelledByElement = document.getElementById(ariaLabelledBy);
                                        if (labelledByElement?.textContent?.trim()) {
                                            accessibleName = normalizeTextForPlaywright(labelledByElement.textContent);
                                        }
                                    }
                                }

                                // 2. aria-label
                                else if (!accessibleName && element.getAttribute('aria-label')) {
                                    const ariaLabel = element.getAttribute('aria-label');
                                    if (ariaLabel) {
                                        accessibleName = normalizeTextForPlaywright(ariaLabel);
                                    }
                                }
                                // 3. text content (fallback)
                                else {
                                    const textContent = element.textContent;
                                    if (textContent) {
                                        accessibleName = normalizeTextForPlaywright(textContent);
                                    }
                                }

                                if (role && accessibleName && isValidAttributeValue(role) && isValidAttributeValue(accessibleName)) {
                                    addUniqueSelector('page.getByRole', `'${role}', {name: '${accessibleName}'}`, `Get By Role`);
                                    addUniqueSelector('page.getByRole', `'${role}', {name: '${accessibleName}', exact: true}`, `Get By Role (exact)`);
                                }

                                // Helper function to get input role based on type
                                function getInputRole(input: HTMLInputElement): string {
                                    const type = input.type?.toLowerCase() || 'text';
                                    const inputRoles: Record<string, string> = {
                                        'button': 'button',
                                        'checkbox': 'checkbox',
                                        'color': 'button',
                                        'date': 'textbox',
                                        'datetime-local': 'textbox',
                                        'email': 'textbox',
                                        'file': 'button',
                                        'hidden': 'textbox',
                                        'image': 'button',
                                        'month': 'textbox',
                                        'number': 'spinbutton',
                                        'password': 'textbox',
                                        'radio': 'radio',
                                        'range': 'slider',
                                        'reset': 'button',
                                        'search': 'searchbox',
                                        'submit': 'button',
                                        'tel': 'textbox',
                                        'text': 'textbox',
                                        'time': 'textbox',
                                        'url': 'textbox',
                                        'week': 'textbox'
                                    };
                                    return inputRoles[type] || 'textbox';
                                }

                                // 12. ARIA-label attribute
                                const ariaLabel = element.getAttribute('aria-label');
                                if (ariaLabel) {
                                    const normalizedLabel = normalizeTextForPlaywright(ariaLabel);
                                    if (isValidAttributeValue(normalizedLabel)) {
                                        addUniqueSelector('page.getByLabel', `${normalizedLabel}`, `Get By Aria Label`);
                                    }
                                }

                                // 13. ARIA-labelledby attribute
                                const ariaLabelledBy = element.getAttribute('aria-labelledby');
                                if (ariaLabelledBy) {
                                    const labelledByElement = document.getElementById(ariaLabelledBy);
                                    if (labelledByElement?.textContent?.trim()) {
                                        const labelText = normalizeTextForPlaywright(labelledByElement.textContent);
                                        if (isValidAttributeValue(labelText)) {
                                            addUniqueSelector('page.getByLabel', `${labelText}`, `Get By Aria Labelled By`);
                                        }
                                    }
                                }

                                // 14. Try label association
                                if (element.id) {
                                    const label = document.querySelector(`label[for=${CSS.escape(element.id)}]`);
                                    if (label?.textContent?.trim()) {
                                        const labelText = normalizeTextForPlaywright(label.textContent);
                                        if (isValidAttributeValue(labelText)) {
                                            addUniqueSelector('page.getByLabel', `${labelText}`, `Get By Label`);
                                        }
                                    }
                                }

                                // 15. Name attribute on form elements
                                const name = element.getAttribute('name');
                                if (name && isValidAttributeValue(name)) {
                                    addUniqueSelector('page.locator', `${tagName}[name="${CSS.escape(name)}"]`, `Get By Name`);
                                }

                                // 16. Placeholder attribute
                                const placeholder = element.getAttribute('placeholder');
                                if (placeholder && isValidAttributeValue(placeholder)) {
                                    addUniqueSelector('page.locator', `${tagName}[placeholder="${CSS.escape(placeholder)}"]`, `Get By Placeholder`);
                                }

                                // 17. Type attribute on inputs
                                const type = element.getAttribute('type');
                                if (type && isValidAttributeValue(type)) {
                                    addUniqueSelector('page.locator', `${tagName}[type="${CSS.escape(type)}"]`, `Get By Type`);
                                }

                                // 18. Title attribute
                                const title = element.getAttribute('title');
                                if (title && isValidAttributeValue(title)) {
                                    addUniqueSelector('page.locator', `${tagName}[title="${CSS.escape(title)}"]`, `Get By Title`);
                                }

                                // 19. Href attribute
                                const href = element.getAttribute('href');
                                if (href && isValidAttributeValue(href)) {
                                    addUniqueSelector('page.locator', `${tagName}[href="${CSS.escape(href)}"]`, `Get By Href`);
                                }

                                // 20. ID selector
                                if (element.id) {
                                    addUniqueSelector('page.locator', `${escapeIdForCss(element.id)}`, `Get By ID`);
                                }

                                // 21. Tag + class selector
                                const classes = Array.from(element.classList).filter(c => c.trim());
                                if (classes.length > 0) {
                                    // Use attribute selector for all class names to avoid CSS parsing issues with special characters
                                    const classAttr = element.getAttribute('class');
                                    if (classAttr && isValidAttributeValue(classAttr)) {
                                        addUniqueSelector('page.locator', `${tagName}[class="${CSS.escape(classAttr)}"]`, `Get By Tag and Class Attribute`);
                                    }
                                }

                                // 22. Visible text content fallback (if under 80 characters)
                                const text = element.textContent?.trim();
                                if (text && text.length < 80) {
                                    const normalizedText = normalizeTextForPlaywright(text);
                                    addUniqueSelector('page.getByText', `${normalizedText}`, `Get By Text`);
                                }

                                // 23. XPath fallback (always add as it should be unique)
                                const xpathSelector = getXPathTree(element);
                                if (xpathSelector) {
                                    addUniqueSelector('page.locator', `xpath=${xpathSelector}`, `Get By XPath`);
                                }

                                return selectors;
                            }

                            const selectorArray = generateSelectorArray(el);
                            // Store the CSS selector (not the full Playwright code) for ActionHandler
                            selector = selectorArray.length > 0 ? selectorArray[0].selector : '';


                            const isVisible = !!(
                                style && style.display !== 'none' &&
                                style.visibility !== 'hidden' &&
                                style.opacity !== '0' &&
                                rect && rect.width > 0 &&
                                rect.height > 0
                            );

                            // Inside the element mapping, restore the overlay creation for visible elements:
                            if (isVisible && rect) {
                                const overlay = document.createElement('div');
                                overlay.setAttribute('data-element-id', `${index + 1}`);
                                overlay.style.position = 'absolute';
                                overlay.style.left = `${rect.x}px`;
                                overlay.style.top = `${rect.y}px`;
                                overlay.style.width = `${rect.width}px`;
                                overlay.style.height = `${rect.height}px`;
                                if (isInPopupElement) {
                                    overlay.style.border = '2px solid #00ff00'; // Green for popup elements
                                    overlay.style.backgroundColor = 'rgba(0, 255, 0, 0.1)';
                                } else {
                                    overlay.style.border = '2px solid #ff0000'; // Red for regular elements
                                    overlay.style.backgroundColor = 'rgba(255, 0, 0, 0.1)';
                                }
                                overlay.style.pointerEvents = 'none';
                                overlay.style.zIndex = '10000';
                                const label = document.createElement('div');
                                label.textContent = `${index + 1}`;
                                label.style.position = 'absolute';
                                label.style.top = '-20px';
                                label.style.right = '0';
                                label.style.backgroundColor = isInPopupElement ? '#00ff00' : '#ff0000';
                                label.style.color = '#ffffff';
                                label.style.padding = '2px 4px';
                                label.style.borderRadius = '2px';
                                label.style.fontSize = '12px';
                                label.style.fontFamily = 'Arial, sans-serif';
                                label.style.zIndex = '10001';
                                overlay.appendChild(label);
                                document.body.appendChild(overlay);
                            }

                            // Collect all attributes except class and style
                            const attributes: Record<string, string> = {};
                            Array.from(el.attributes).forEach(attr => {
                                if (attr.name !== 'class' && attr.name !== 'style') {
                                    attributes[attr.name] = attr.value;
                                }
                            });

                            return {
                                id: `${index + 1}`,
                                selector,
                                selectors: selectorArray,
                                tagName: el.tagName,
                                boundingBox: rect ? {
                                    x: rect.x,
                                    y: rect.y,
                                    width: rect.width,
                                    height: rect.height
                                } : { x: 0, y: 0, width: 0, height: 0 },
                                isVisible,
                                isEnabled: !el.hasAttribute('disabled'),
                                text: (() => {
                                    if (addNonInteractable) {
                                        // For non-interactable elements, use only direct text content
                                        const directText = getDirectTextContent(el);
                                        return directText ? normalizeTextForPlaywright(directText).substring(0, 500) : undefined;
                                    } else {
                                        // For interactive elements, use full text content (including child text)
                                        return el.textContent ? normalizeTextForPlaywright(el.textContent).substring(0, 500) : undefined;
                                    }
                                })(), //max 500 characters
                                value: (el as HTMLInputElement).value || undefined,
                                name: (el as HTMLInputElement).name || undefined,
                                placeholder: (el as HTMLInputElement).placeholder || undefined,
                                isInPopup: isInPopupElement,
                                attributes: Object.keys(attributes).length > 0 ? attributes : undefined
                            };
                        }), domSnapshot
                    };
                },
                { actionType, safeAttributes: SAFE_ATTRIBUTES, isDOMChangeCheck, addNonInteractable }
            );
            if (!result) {
                logger.info('DOM has not changed');
                return {
                    elements: [],
                    screenshot: '',
                    hasDOMChanged: false
                };
            }
            if (actionType !== "ai_verify" && actionType !== "ai_assert" && result?.elements.length === 0 && attempt < 1) {
                logger.info(`No elements found, waiting 2 seconds and retrying...`);
                // Wait for 2 seconds before retrying
                await new Promise(resolve => setTimeout(resolve, 2000));
                const retryResult = await this.createElementsArrayAndTakeScreenshot(actionType, isDOMChangeCheck, attempt + 1, addNonInteractable);
                if (retryResult?.elements) {
                    this.elementsManager.setElements(retryResult.elements);
                    if (retryResult.elements.length === 0) {
                        logger.warn('No interactive elements found on the page. Elements array is empty.');
                    }
                }
                return retryResult;
            } else if (actionType !== "ai_verify" && actionType !== "ai_assert" && result?.elements.length === 0) {
                logger.error('No elements found on page after retry');
                throw new Error('No interactive elements found on the current page. Please check if the page has loaded completely or if there are any interactive elements available.');
            }

            logger.info('Starting to create elements array...');

            // Update the elements manager with new elements (only if not retried)
            if (result?.elements) {
                this.elementsManager.setElements(result.elements);
                if (result.elements.length === 0) {
                    logger.warn('No interactive elements found on the page. Elements array is empty.');
                }
            }

            logger.info(`Created array with ${result?.elements?.length} elements`);

            // Log the elements array without selectors
            const elementsForLogging = result?.elements?.map(element => {
                const { selector, selectors, ...elementWithoutSelectors } = element;
                return elementWithoutSelectors;
            });

            logger.info('Elements array:', {
                length: result?.elements?.length,
                elements: elementsForLogging
            });

            // Take screenshot directly
            logger.info('Taking screenshot...');
            const screenshotBuffer = await this.page.screenshot({
                type: 'png',
                fullPage: false
            });

            const base64Screenshot = screenshotBuffer.toString('base64');
            logger.info('Screenshot taken and converted to base64');

            // Remove overlays from the DOM only (do not clear or modify the elements array)
            await this.page.evaluate(() => {
                document.querySelectorAll('[data-element-id]').forEach(el => el.remove());
            });
            logger.info('Overlays removed');

            return {
                elements: result?.elements ?? [],
                screenshot: base64Screenshot,
                hasDOMChanged: true
            };

        } catch (error) {
            logger.error('Failed to create elements array and take screenshot', error);
            throw error;
        }
    }
} 