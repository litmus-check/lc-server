import { Page } from 'playwright';
import { 
    Action, 
    ActionResult, 
    GoToUrlAction, 
    GoBackAction, 
    WaitTimeAction, 
    OpenTabAction, 
    RunScriptAction,
    InputAction,
    SelectAction,
    VerifyAction,
    AssertAction,
    SwitchTabAction,
    ScrollAction,
    FileUploadAction,
    AiScriptAction,
    VerificationAction,
    SetStateVariableAction,
    PageReload,
    KeyPressAction,
    ApiInterceptAction,
    RemoveApiHandlersAction,
    ApiMockAction
} from '../types/actions';
import { InteractableElement } from '../types/browser';
import { logger } from '../utils/logger';
import * as fs from 'fs';
import * as path from 'path';
import { InteractableElementsManager } from './InteractableElementsManager';
import assert from 'assert';
import { expect, request } from '@playwright/test';
import { DownloadUtils } from '../utils/downloadUtils';
import { ENV_VARIABLE_REGEX_PATTERN, FILE_UPLOADS_DIR, VARIABLE_REGEX_PATTERN, STATE_TEMPLATE_REGEX, API_INTERCEPT_ACTIONS } from '../config/constants';
import { substituteVariables } from '../utils/variableUtils';
import { VerificationFunctions } from '../types/verifications';
import { getURLPattern } from '../utils/URLPatternClone';
import { ContainerCommsService } from '../services/ContainerCommsService';
import { PerformanceMonitoring } from './PerformanceMonitoring';
import { HtmlCleaner } from './HtmlCleaner';
import { StateTemplateDetector, escapeJsStringValue } from '../utils/stateVariableUtils';

import { litmusLogger } from '../utils/litmusLogUtils';
import { escapeRegexStringForJSLiteral } from '../utils/stringEscapeUtils';

export class ActionHandler {
    private executedCode: string[] = [];
    private screenshotDir: string;
    private elementsManager: InteractableElementsManager;
    private originalInstruction: any = null; // Store original instruction with variables
    private variablesDict: { 
        data_driven_variables?: { [key: string]: string },
        environment_variables?: { [key: string]: string }
    } = {}; // Store variables dictionary for script substitution
    private browserContext: any = null; // Store reference to BrowserContext
    private llmInputs: any = null; // Store reference to LLMInputs
    private containerCommsService: ContainerCommsService | null = null; // Store reference to ContainerCommsService
    private runId: string | null = null; // Store runId for Redis logging
    private performanceMonitoring: PerformanceMonitoring; // Store reference to PerformanceMonitoring
    private sharedState: Record<string, any> = {}; // Shared per-run state reference from LitmusAgent

    constructor(private page: Page, screenshotDir: string = 'screenshots', browserContext?: any, llmInputs?: any, containerCommsService?: ContainerCommsService, runId?: string) {
        this.screenshotDir = screenshotDir;
        this.browserContext = browserContext;
        this.llmInputs = llmInputs;
        this.containerCommsService = containerCommsService || null;
        this.runId = runId || null;
        this.elementsManager = InteractableElementsManager.getInstance();
        this.performanceMonitoring = new PerformanceMonitoring(page, containerCommsService || undefined, runId || undefined);
        // Ensure screenshot directory exists
        if (!fs.existsSync(this.screenshotDir)) {
            fs.mkdirSync(this.screenshotDir, { recursive: true });
        }
    }

    /**
     * Set the interactable elements array
     */
    public setInteractableElements(elements: InteractableElement[]) {
        this.elementsManager.setElements(elements);
    }

    /**
     * Set the original instruction (with variables) for playwright code generation
     */
    public setOriginalInstruction(instruction: any) {
        logger.info(`ActionHandler: Setting original instruction: ${JSON.stringify(instruction)}`);
        this.originalInstruction = instruction;
        logger.info(`ActionHandler: Original instruction set successfully`);
    }

    /**
     * Get the original instruction (for debugging)
     */
    public getOriginalInstruction(): any {
        return this.originalInstruction;
    }

    /**
     * Set the variables dictionary for script substitution
     */
    public setVariablesDict(variablesDict: { 
        data_driven_variables?: { [key: string]: string },
        environment_variables?: { [key: string]: string }
    }) {
        this.variablesDict = variablesDict;
        logger.info(`ActionHandler: Set variables dictionary: ${JSON.stringify(variablesDict)}`);
    }

    /**
     * Set the shared state reference from LitmusAgent
     */
    public setSharedState(sharedState: Record<string, any>): void {
        this.sharedState = sharedState;
        logger.info(`ActionHandler: Set shared state reference`);
    }

    /**
     * Get the shared state reference
     */
    public getSharedState(): Record<string, any> {
        return this.sharedState;
    }

    /**
     * Get all executed Playwright code
     */
    public getExecutedCode(): string[] {
        return this.executedCode;
    }

    /**
     * Get code for the current action
     */
    public getCurrentActionCode(): string[] {
        // Return the last entry from executedCode
        return this.executedCode.length > 0 ? [this.executedCode[this.executedCode.length - 1]] : [];
    }

    /**
     * Clear current action code
     */
    public clearCurrentActionCode(): void {
        // Remove the last entry from executedCode
        if (this.executedCode.length > 0) {
            this.executedCode.pop();
        }
    }

    /**
     * Update the page reference and BrowserContext active page
     */
    private async updatePageReference(newPage: Page): Promise<void> {
        this.page = newPage;
        if (this.browserContext) {
            await this.browserContext.setActivePage(newPage);
            logger.info(`Updated page reference and BrowserContext active page to: ${newPage.url()}`);
        } else {
            logger.info(`Updated page reference to: ${newPage.url()}`);
        }
        
        // Also update LLMInputs if available
        if (this.llmInputs) {
            this.llmInputs.updatePageReference(newPage);
            logger.info(`Updated LLMInputs page reference to: ${newPage.url()}`);
        }

        // Update PerformanceMonitoring with new page reference
        this.performanceMonitoring = new PerformanceMonitoring(newPage, this.containerCommsService || undefined, this.runId || undefined);
        logger.info(`Updated PerformanceMonitoring page reference to: ${newPage.url()}`);
    }

    /**
     * Clear all executed Playwright code
     */
    public clearExecutedCode(): void {
        this.executedCode = [];
    }

    /**
     * Store executed Playwright code
     */
    private storeExecutedCode(code: string) {
        this.executedCode.push(code);
    }

    /**
     * Generate script for a selector object, handling getByRole specially
     */
    public generateScriptForSelector(selectorObj: any, action: string, value?: string): string {
        logger.info(`generateScriptForSelector called with value: "${value}"`);
        
        // Test for state variables once and store the result (robust)
        const hasStateVariables = StateTemplateDetector(value);
        logger.info(`STATE_TEMPLATE_REGEX test result: ${hasStateVariables}`);
        
        if (selectorObj.method === 'page.getByRole') {
            // Parse getByRole selector to extract role, name, and optional exact flag
            // Check for exact: true version first
            const exactMatch = selectorObj.selector.match(/^'([^']+)',\s*\{\s*name:\s*'([^']+)',\s*exact:\s*true\s*\}$/);
            if (exactMatch) {
                const role = exactMatch[1];
                const name = exactMatch[2];
                const selector = `${selectorObj.method}('${role}', {name: '${name}', exact: true})`;
                if (value) {
                    // If value contains state variables, wrap with backticks
                    if (hasStateVariables) {
                        const unwrapped = String(value).trim();
                        logger.info(`Value contains state variables: ${unwrapped}`);
                        logger.info(` Generated script: await ${selector}.${action}(\`${unwrapped}\`);`);
                        return `await ${selector}.${action}(\`${unwrapped}\`);`;
                    } else {
                        logger.info(` Value does not contain state variables: ${value}`);
                        // Escape the value to ensure valid JavaScript syntax
                        const escapedValue = escapeJsStringValue(String(value));
                        logger.info(` Generated script: await ${selector}.${action}('${escapedValue}');`);
                        return `await ${selector}.${action}('${escapedValue}');`;
                    }
                }
                return `await ${selector}.${action}();`;
            }
            
            // Regular getByRole without exact
            const roleMatch = selectorObj.selector.match(/^'([^']+)',\s*\{\s*name:\s*'([^']+)'\s*\}$/)!;
            const role = roleMatch[1];
            const name = roleMatch[2];
            const selector = `${selectorObj.method}('${role}', {name: '${name}'})`;
            if (value) {
                // If value contains state variables, wrap with backticks
                if (hasStateVariables) {
                    const unwrapped = String(value).trim();
                    logger.info(`Value contains state variables: ${unwrapped}`);
                    logger.info(` Generated script: await ${selector}.${action}(\`${unwrapped}\`);`);
                    return `await ${selector}.${action}(\`${unwrapped}\`);`;
                } else {
                    logger.info(` Value does not contain state variables: ${value}`);
                    // Escape the value to ensure valid JavaScript syntax
                    const escapedValue = escapeJsStringValue(String(value));
                    logger.info(` Generated script: await ${selector}.${action}('${escapedValue}');`);
                    return `await ${selector}.${action}('${escapedValue}');`;
                }
            }
            return `await ${selector}.${action}();`;
        } else {
            // Always quote the selector value for other methods
            const selectorValue = `'${selectorObj.selector}'`;
            const selector = `${selectorObj.method}(${selectorValue})`;
            if (value) {
                // If value contains state variables, wrap with backticks
                if (hasStateVariables) {
                    const unwrapped = String(value).trim();
                    logger.info(`Value contains state variables: ${unwrapped}`);
                    logger.info(` Generated script: await ${selector}.${action}(\`${unwrapped}\`);`);
                    return `await ${selector}.${action}(\`${unwrapped}\`);`;
                } else {
                    logger.info(` Value does not contain state variables: ${value}`);
                    // Escape the value to ensure valid JavaScript syntax
                    const escapedValue = escapeJsStringValue(String(value));
                    logger.info(` Generated script: await ${selector}.${action}('${escapedValue}');`);
                    return `await ${selector}.${action}('${escapedValue}');`;
                }
            }
            return `await ${selector}.${action}();`;
        }
    }

    /**
     * Take a screenshot of the current page
     * @param fullPage Whether to take a full page screenshot
     * @returns The path to the saved screenshot
     */
    public async takeScreenshot(fullPage: boolean = false): Promise<string> {
        try {
            await this.page.bringToFront();
            await this.page.waitForLoadState();

            const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
            const filename = `screenshot-${timestamp}.png`;
            const filepath = path.join(this.screenshotDir, filename);

            await this.page.screenshot({ 
                path: filepath,
                fullPage,
                animations: 'disabled'
            });

            const code = `await page.screenshot({ path: '${filepath}', fullPage: ${fullPage}, animations: 'disabled' });`;
            this.storeExecutedCode(code);

            return filepath;
        } catch (error) {
            logger.error('Screenshot failed', error);
            throw error;
        }
    }

    /**
     * Get element by element ID from interactableElements array
     * Returns an object with 'element' for compose mode execution and 'script' for script mode storage
     */
    private async getElement(elementId: number): Promise<{ element: any, script: string } | null> {
        const element = this.elementsManager.getElementById(elementId);
        if (!element) {
            throw new Error(`Element with ID ${elementId} not found`);
        }
        
        // Get the selectors array
        const selectors = (element as any).selectors;
        //logger.info('selectors: ' + JSON.stringify(selectors, null, 2));
        if (selectors && selectors.length > 0) {
            // Check for getByLabel and getByRole selectors and remove duplicates
            const filteredSelectors: Array<{method?: string, selector: string, display: string}> = [];
            for (const selectorObj of selectors) {
                if (selectorObj.method === 'page.getByText') {
                    const elements = await this.page.getByText(selectorObj.selector).all();
                    if (elements.length === 1) {
                        filteredSelectors.push(selectorObj);
                    }
                }
                else if (selectorObj.method === 'page.getByLabel') {
                    const elements = await this.page.getByLabel(selectorObj.selector).all();
                    if (elements.length === 1) {
                        filteredSelectors.push(selectorObj);
                    }
                } else if (selectorObj.method === 'page.getByRole') {
                    // Check for exact: true version independently
                    const exactMatch = selectorObj.selector.match(/^'([^']+)',\s*\{\s*name:\s*'([^']+)',\s*exact:\s*true\s*\}$/);
                    if (exactMatch) {
                        const role = exactMatch[1];
                        const name = exactMatch[2];
                        const elements = await this.page.getByRole(role as any, { name, exact: true }).all();
                        if (elements.length === 1) {
                            filteredSelectors.push(selectorObj);
                        }
                    }
                    
                    // Check for regular getByRole independently
                    const roleMatch = selectorObj.selector.match(/^'([^']+)',\s*\{\s*name:\s*'([^']+)'\s*\}$/);
                    if (roleMatch) {
                        const role = roleMatch[1];
                        const name = roleMatch[2];
                        const elements = await this.page.getByRole(role as any, { name }).all();
                        if (elements.length === 1) {
                            filteredSelectors.push(selectorObj);
                        }
                    }
                } else {
                    // Keep other selectors as they are
                    filteredSelectors.push(selectorObj);
                }
            }
            
            // Update the element's selectors array
            (element as any).selectors = filteredSelectors;
            
            // Use the first valid selector
            if (filteredSelectors.length > 0) {
                const firstSelector = filteredSelectors[0];
                const method = firstSelector.method;
                const selectorValue = firstSelector.selector;
                
                let playwrightElement: any;
                let scriptSelector: string = '';
                
                // Check for exact role selector independently before switch
                if (method === 'page.getByRole') {
                    const exactMatch = selectorValue.match(/^'([^']+)',\s*\{\s*name:\s*'([^']+)',\s*exact:\s*true\s*\}$/);
                    if (exactMatch) {
                        const role = exactMatch[1];
                        const name = exactMatch[2];
                        playwrightElement = this.page.getByRole(role as any, { name, exact: true });
                        scriptSelector = `page.getByRole('${role}', {name: '${name}', exact: true})`;
                    }
                }
                
                // Use the appropriate method
                if (!playwrightElement) {
                    switch (method) {
                        case 'page.getByLabel':
                            playwrightElement = this.page.getByLabel(selectorValue);
                            scriptSelector = `page.getByLabel('${selectorValue}')`;
                            break;
                        case 'page.getByText':
                            playwrightElement = this.page.getByText(selectorValue);
                            scriptSelector = `page.getByText('${selectorValue}')`;
                            break;
                        case 'page.getByRole':
                            // Regular getByRole without exact - checked independently
                            const roleMatch = selectorValue.match(/^'([^']+)',\s*\{\s*name:\s*'([^']+)'\s*\}$/);
                            if (roleMatch) {
                                const role = roleMatch[1];
                                const name = roleMatch[2];
                                playwrightElement = this.page.getByRole(role as any, { name });
                                scriptSelector = `page.getByRole('${role}', {name: '${name}'})`;
                            }
                            break;
                        case 'page.locator':
                            playwrightElement = this.page.locator(selectorValue);
                            scriptSelector = `page.locator('${selectorValue}')`;
                            break;
                        default:
                            // Fallback to locator
                            playwrightElement = this.page.locator(selectorValue);
                            scriptSelector = `page.locator('${selectorValue}')`;
                            break;
                    }
                }
                
                return {
                    element: playwrightElement,
                    script: scriptSelector
                };
            }
        }
        return null;
    }



    /**
     * Handle click action
     * Note :- Environment variables, Data driven variables are not supported in click action
     */
    public async handleClick(action: Action): Promise<ActionResult> {
        try {
            const { elementId } = action;
            if (!elementId) throw new Error('Element ID is required for click action');

            // Get element info first
            const elementInfo = this.elementsManager.getElementById(elementId);
            
            // Get the element (this will filter the selectors)
            const elementResult = await this.getElement(elementId);
            if (!elementResult) {
                throw new Error(`Element with ID ${elementId} not found`);
            }
            
            // Generate scripts using the filtered selectors
            const scripts: string[] = [];
            if (elementInfo && (elementInfo as any).selectors) {
                for (const selectorObj of (elementInfo as any).selectors) {
                    const script = this.generateScriptForSelector(selectorObj, 'click');
                    logger.info(`Script: ${script}`);
                    scripts.push(script);
                }
            }

            // Execute the click using the element from the result
            await elementResult.element.click();

            // Store the exact script that was executed using elementResult.script
            const executedScript = `await ${elementResult.script}.click();`;
            this.storeExecutedCode(executedScript);

            // Get selectors for the element (now filtered)
            const selectors = elementInfo && (elementInfo as any).selectors ? (elementInfo as any).selectors : [];

            return {
                action,
                success: true,
                timestamp: Date.now(),
                selectors: { selectors },
                scripts
            };
        } catch (error) {
            logger.error('Click action failed', error);
            return {
                action,
                success: false,
                error: error instanceof Error ? error.message : 'Unknown error',
                timestamp: Date.now()
            };
        }
    }

    /**
     * Handle input action
     */
    public async handleInput(action: InputAction): Promise<ActionResult> {
        try {
            const { elementId, value } = action;
            if (!elementId || !value) throw new Error('Element ID and value are required for input action');

            // Get element info first
            const elementInfo = this.elementsManager.getElementById(elementId);
            
            // Use original instruction value (with variables) for playwright code generation if available
            let scriptValue = value;
            if (this.originalInstruction && this.originalInstruction.args) {
                const originalArg = this.originalInstruction.args.find((arg: any) => arg.key === 'value');
                if (originalArg) {
                    scriptValue = originalArg.value;
                }
            }
            
            // Get the element (this will filter the selectors)
            const elementResult = await this.getElement(elementId);
            if (!elementResult) {
                throw new Error(`Element with ID ${elementId} not found`);
            }
            
            // Generate scripts using the filtered selectors
            const scripts: string[] = [];
            if (elementInfo && (elementInfo as any).selectors) {
                for (const selectorObj of (elementInfo as any).selectors) {
                    const script = this.generateScriptForSelector(selectorObj, 'fill', scriptValue);
                    logger.info(`Script with variables: ${script}`);
                    scripts.push(script);
                }
            }
    
            // Check if the value contains state template
            const isStateTemplate = StateTemplateDetector(String(scriptValue));
    
            if (isStateTemplate) {
                // If it contains ${state.*}, use template literal with state context
                // Escape the scriptValue to prevent premature evaluation
                const fn = new Function('element', 'state', `return (async () => { await element.fill(\`${scriptValue}\`); })();`);
                await fn(elementResult.element, this.sharedState);
                
                const executedScript = `await ${elementResult.script}.fill(\`${scriptValue}\`);`;
                logger.info(`Executed script (with state): ${executedScript}`);
                this.storeExecutedCode(executedScript);
    
            } else {
                // Normal Playwright API for static values
                await elementResult.element.fill(value);
                // Escape the value to ensure valid JavaScript syntax
                const escapedValue = escapeJsStringValue(scriptValue);
                const executedScript = `await ${elementResult.script}.fill('${escapedValue}');`;
                logger.info(`Executed script: ${executedScript}`);
                this.storeExecutedCode(executedScript);
            }
    
            const selectors = elementInfo && (elementInfo as any).selectors ? (elementInfo as any).selectors : [];

            return {
                action,
                success: true,
                timestamp: Date.now(),
                selectors: { selectors },
                scripts
            };
        } catch (error) {
            logger.error('Input action failed', error);
            return {
                action,
                success: false,
                error: error instanceof Error ? error.message : 'Unknown error',
                timestamp: Date.now()
            };
        }
    }

    /**
     * Handle select action
     */
    public async handleSelect(action: SelectAction): Promise<ActionResult> {
        try {
            const { elementId, value } = action;
            if (!elementId || !value) throw new Error('Element ID and value are required for select action');

            // Get element info and check if it's a radio button once
            const elementInfo = this.elementsManager.getElementById(elementId);
            const elementResult = await this.getElement(elementId);
            if (!elementResult) {
                throw new Error(`Element with ID ${elementId} not found`);
            }
            
            const isRadio = await elementResult.element.evaluate(el => el instanceof HTMLInputElement && el.type === 'radio');
            
            // Use original instruction value (with variables) for playwright code generation if available
            let scriptValue = value;
            if (this.originalInstruction && this.originalInstruction.args) {
                const originalArg = this.originalInstruction.args.find((arg: any) => arg.key === 'value');
                if (originalArg) {
                    scriptValue = originalArg.value;
                }
            }
            
            // Generate scripts based on the radio button check
            const scripts: string[] = [];
            if (elementInfo && (elementInfo as any).selectors) {
                for (const selectorObj of (elementInfo as any).selectors) {
                    const action = isRadio ? 'click' : 'selectOption';
                    const script = this.generateScriptForSelector(selectorObj, action, isRadio ? undefined : scriptValue);
                    scripts.push(script);
                }
            }
            
            // Execute the action based on the same radio button check
            if (isRadio) {
                logger.info('Element is a radio button')
                await elementResult.element.click();
                
                // Store the exact script that was executed using elementResult.script
                const executedScript = `await ${elementResult.script}.click();`;
                this.storeExecutedCode(executedScript);
            } else {
                // Check if the value contains state template
                const isStateTemplate = StateTemplateDetector(String(scriptValue));
                
                if (isStateTemplate) {
                    // If it contains ${state.*}, use template literal with state context
                    const fn = new Function('element', 'state', `return (async () => { await element.selectOption(\`${scriptValue}\`); })();`);
                    await fn(elementResult.element, this.sharedState);
                    
                    const executedScript = `await ${elementResult.script}.selectOption(\`${scriptValue}\`);`;
                    logger.info(`Executed script (with state): ${executedScript}`);
                    this.storeExecutedCode(executedScript);
                } else {
                    // Normal Playwright API for static values
                    await elementResult.element.selectOption(String(value));
                    
                    // Escape the value to ensure valid JavaScript syntax
                    const escapedValue = escapeJsStringValue(scriptValue);
                    const executedScript = `await ${elementResult.script}.selectOption('${escapedValue}');`;
                    logger.info(`Executed script: ${executedScript}`);
                    this.storeExecutedCode(executedScript);
                }
            }

            // Get selectors for the element
            const selectors = elementInfo && (elementInfo as any).selectors ? (elementInfo as any).selectors : [];

            return {
                action,
                success: true,
                timestamp: Date.now(),
                selectors: { selectors },
                scripts
            };
        } catch (error) {
            logger.error('Select action failed', error);
            return {
                action,
                success: false,
                error: error instanceof Error ? error.message : 'Unknown error',
                timestamp: Date.now()
            };
        }
    }

    /**
     * Handle verify action
     */
    public async handleVerify(action: VerifyAction): Promise<ActionResult> {
        try {
            const { code, validation } = action;
            if (!code || !validation) throw new Error('Code and validation are required for verify action');
    
            // eslint-disable-next-line no-eval
            const fn = new Function('page', 'assert', 'expect', 'request', `'use strict'; return (async () => { ${code} })();`);
            const result = await fn(this.page, assert, expect, request);
    
            this.storeExecutedCode(code);
    
            logger.info('Verify action executed', JSON.stringify({
                code,
                validation,
                result
            }, null, 2));
    
            return {
                action,
                success: validation,
                timestamp: Date.now()
            }; 
        } catch (error) {
            logger.error('Verify action failed', error);
            return {
                action,
                success: false,
                error: error instanceof Error ? error.message : 'Unknown error',
                timestamp: Date.now()
            };
        }
    }

    /**
     * Handle AI assert action
     * This action only returns the LLM result without generating or executing code
     */
    public async handleAiAssert(action: AssertAction): Promise<ActionResult> {
        try {
            // Import verification types and functions
            const { getArgValue } = await import('../types/verifications');
            
            // Prefer flat action properties; fallback to instruction args
            const getProp = (key: string) => (action as any)[key] ?? ((action as any).instruction ? getArgValue((action as any).instruction, key) : null);
            
            const validation = getProp('validation') ?? action.validation;
            const reasoning = getProp('reasoning') ?? action.reasoning;
            const expectedResult = getProp('expected_result');
            const failTest = (() => {
                const ft = getProp('fail_test');
                return ft === true || ft === 'true';
            })();
            
            if (validation === undefined) {
                throw new Error('Validation result is required for AI assert action');
            }
    
            logger.info('AI assert action result', JSON.stringify({
                validation,
                reasoning,
                expectedResult,
                failTest
            }, null, 2));
    
            // If validation fails, handle based on fail_test flag
            if (!validation) {
                const errorMessage = reasoning || 'AI assert validation failed';
                
                // Log assertion failed
                if (this.containerCommsService && this.runId) {
                    await this.containerCommsService.addLog(this.runId, {
                        warning: 'Assertion failed',
                        timestamp: new Date().toISOString()
                    });
                }
                
                if (failTest) {
                    // If fail_test is true, throw error to fail the test
                    throw new Error(errorMessage);
                } else {
                    // If fail_test is false/undefined, log continuing execution and return success with warning
                    if (this.containerCommsService && this.runId) {
                        await this.containerCommsService.addLog(this.runId, {
                            info: 'Continuing execution',
                            timestamp: new Date().toISOString()
                        });
                    }
                    return {
                        action,
                        success: true,
                        timestamp: Date.now(),
                        warning: errorMessage
                    };
                }
            }
    
            // Validation passed
            if (this.containerCommsService && this.runId) {
                await this.containerCommsService.addLog(this.runId, {
                    info: 'Assertion passed',
                    timestamp: new Date().toISOString()
                });
            }
            
            return {
                action,
                success: true,
                timestamp: Date.now(),
                ...(reasoning && { warning: reasoning })
            }; 
        } catch (error) {
            logger.error('AI assert action failed', error);
            return {
                action,
                success: false,
                error: error instanceof Error ? error.message : 'Unknown error',
                timestamp: Date.now()
            };
        }
    }

    /**
     * Handle switch tab action
     */
    public async handleSwitchTab(action: SwitchTabAction): Promise<ActionResult> {
        try {
            const { url } = action;
            if (!url) throw new Error('URL is required for switch tab action');

            // Check if the URL contains state template
            const isStateTemplate = StateTemplateDetector(String(url));
            let finalUrl = url;

            if (isStateTemplate) {
                // If it contains ${state.*}, resolve the template literal
                const fn = new Function('state', `return \`${url}\`;`);
                finalUrl = fn(this.sharedState);
                logger.info(`Resolved URL with state variables: ${finalUrl}`);
            }

            const pages = this.page.context().pages();
            
            // Use URL Pattern API (native or our clone) to match URLs
            const urlPattern = getURLPattern(finalUrl);
            const targetPage = pages.find(p => urlPattern.test(p.url()));
            const regexString = urlPattern.getRegexString;

            // Log all pages urls
            logger.info(`All pages urls: ${pages.map(p => p.url())}`);

            // Log target page url
            logger.info(`Target page url: ${targetPage?.url()}`);

            // Log regex string
            logger.info(`Regex string: ${regexString}`);
            
            if (!targetPage) {
                throw new Error(`Tab with URL pattern ${url} not found`);
            }

            await targetPage.bringToFront();
            // Update page reference and BrowserContext active page
            await this.updatePageReference(targetPage);

            logger.info(`Switch tab to ${targetPage.url()}`);

            // Generate code using regex (no value argument here)
            // Escape regex string for use in JavaScript string literal
            const escapedRegexString = escapeRegexStringForJSLiteral(regexString);
            const code = (() => {
                const originalUrlArg = this.originalInstruction?.args?.find((arg: any) => arg.key === 'url');
                if (originalUrlArg && STATE_TEMPLATE_REGEX.test(String(originalUrlArg.value))) {
                    return `const pages = await context.pages();\nconst regex = new RegExp(${escapedRegexString});\nconst targetPage = pages.find(p => regex.test(p.url()));\nawait targetPage.bringToFront();`;
                }
                return `const pages = await context.pages();\nconst regex = new RegExp('${escapedRegexString}');\nconst targetPage = pages.find(p => regex.test(p.url()));\nawait targetPage.bringToFront();`;
            })();
            this.storeExecutedCode(code);

            return {
                action,
                success: true,
                timestamp: Date.now()
            };
        } catch (error) {
            logger.error('Switch tab action failed', error);
            return {
                action,
                success: false,
                error: error instanceof Error ? error.message : 'Unknown error',
                timestamp: Date.now()
            };
        }
    }

    /**
     * Handle hover action
     * Note :- Environment variables, Data driven variables are not supported in hover action
     */
    public async handleHover(action: Action): Promise<ActionResult> {
        try {
            const { elementId } = action;
            if (!elementId) throw new Error('Element ID is required for hover action');

            // Get element info first
            const elementInfo = this.elementsManager.getElementById(elementId);
            
            // Get the element (this will filter the selectors)
            const elementResult = await this.getElement(elementId);
            if (!elementResult) {
                throw new Error(`Element with ID ${elementId} not found`);
            }
            
            // Generate scripts using the filtered selectors
            const scripts: string[] = [];
            if (elementInfo && (elementInfo as any).selectors) {
                for (const selectorObj of (elementInfo as any).selectors) {
                    const script = this.generateScriptForSelector(selectorObj, 'hover');
                    scripts.push(script);
                }
            }

            // Execute the hover using the element from the result
            await elementResult.element.hover();

            // Store the exact script that was executed using elementResult.script
            const executedScript = `await ${elementResult.script}.hover();`;
            this.storeExecutedCode(executedScript);

            // Get selectors for the element (now filtered)
            const selectors = elementInfo && (elementInfo as any).selectors ? (elementInfo as any).selectors : [];

            return {
                action,
                success: true,
                timestamp: Date.now(),
                selectors: { selectors },
                scripts
            };
        } catch (error) {
            logger.error('Hover action failed', error);
            return {
                action,
                success: false,
                error: error instanceof Error ? error.message : 'Unknown error',
                timestamp: Date.now()
            };
        }
    }

    /**
     * Handle scroll action
     */
    public async handleScroll(action: ScrollAction): Promise<ActionResult> {
        try {
            let { direction, value = 0 } = action;
            logger.info("Scroll action", action);
            if (!direction) throw new Error('Direction is required for scroll action');
            
            // Convert value to number if it's a string
            const numericValue = typeof value === 'string' ? parseInt(value, 10) : value;
            if (numericValue < 0) throw new Error('Value must be greater than 0 for scroll action');

            // Use original instruction delay (with variables) for playwright code generation if available
            let scrollValue = value;
            if (this.originalInstruction && this.originalInstruction.args) {
                const originalArg = this.originalInstruction.args.find((arg: any) => arg.key === 'value');
                if (originalArg) {
                    scrollValue = originalArg.value;
                }
            }

            // Check if the value contains state template and resolve it
            let finalValue = numericValue;
            if (scrollValue && StateTemplateDetector(String(scrollValue))) {
                const fn = new Function('state', `return \`${value}\`;`);
                const resolvedValue = fn(this.sharedState);
                // Convert resolved value to number if it's a string
                finalValue = typeof resolvedValue === 'string' ? parseInt(resolvedValue, 10) : resolvedValue;
                logger.info(`Resolved scroll value with state variables: ${finalValue}`);
            }

            switch (direction) {
                case 'up':
                    await this.page.mouse.wheel(0, -finalValue);
                    const upCode = StateTemplateDetector(String(scrollValue)) ? `await page.mouse.wheel(0, -\`${scrollValue}\`);` : `await page.mouse.wheel(0, -${scrollValue});`;
                    this.storeExecutedCode(upCode);
                    break;
                case 'down':
                    await this.page.mouse.wheel(0, finalValue);
                    const downCode = StateTemplateDetector(String(scrollValue)) ? `await page.mouse.wheel(0, \`${scrollValue}\`);` : `await page.mouse.wheel(0, ${scrollValue});`;
                    this.storeExecutedCode(downCode);
                    break;
                case 'left':
                    await this.page.mouse.wheel(-finalValue, 0);
                    const leftCode = StateTemplateDetector(String(scrollValue)) ? `await page.mouse.wheel(-\`${scrollValue}\`, 0);` : `await page.mouse.wheel(-${scrollValue}, 0);`;
                    this.storeExecutedCode(leftCode);
                    break;
                case 'right':
                    await this.page.mouse.wheel(finalValue, 0);
                    const rightCode = StateTemplateDetector(String(scrollValue)) ? `await page.mouse.wheel(\`${scrollValue}\`, 0);` : `await page.mouse.wheel(${scrollValue}, 0);`;
                    this.storeExecutedCode(rightCode);
                    break;
            }

            // Get selectors for the element if it's a scroll to action
            let selectors: Array<{selector: string, display: string}> = [];
            let scripts: string[] = [];
   

            return {
                action,
                success: true,
                timestamp: Date.now(),
                selectors: { selectors },
                scripts
            };
        } catch (error) {
            logger.error('Scroll action failed', error);
            return {
                action,
                success: false,
                error: error instanceof Error ? error.message : 'Unknown error',
                timestamp: Date.now()
            };
        }
    }

    /**
     * Handle wait action
     */
    public async handleWait(action: WaitTimeAction): Promise<ActionResult> {
        try {
            let { delay_seconds } = action;
            if (!delay_seconds) throw new Error('Delay seconds is required for wait action');

            // Use original instruction delay (with variables) for playwright code generation if available
            let scriptDelay = delay_seconds;
            if (this.originalInstruction && this.originalInstruction.args) {
                const originalArg = this.originalInstruction.args.find((arg: any) => arg.key === 'delay_seconds');
                if (originalArg) {
                    scriptDelay = originalArg.value;
                }
            }

            // Check if the delay contains state template and resolve it
            if (scriptDelay && StateTemplateDetector(String(scriptDelay))) {
                const fn = new Function('state', `return \`${scriptDelay}\`;`);
                delay_seconds = fn(this.sharedState);
                logger.info(`Resolved wait time with state variables: ${delay_seconds}`);
            }

            await this.page.waitForTimeout(delay_seconds * 1000);

            // Use original delay (with variables) for playwright code generation
            const code = StateTemplateDetector(String(scriptDelay)) ? `await page.waitForTimeout(\`${scriptDelay}\` * 1000);` : `await page.waitForTimeout(${scriptDelay} * 1000);`;
            this.storeExecutedCode(code);

            return {
                action,
                success: true,
                timestamp: Date.now()
            };
        } catch (error) {
            logger.error('Wait action failed', error);
            return {
                action,
                success: false,
                error: error instanceof Error ? error.message : 'Unknown error',
                timestamp: Date.now()
            };
        }
    }

    /**
     * Handle wait time action
     */
    public async handleWaitTime(action: WaitTimeAction): Promise<ActionResult> {
        try {
            let { delay_seconds } = action;
            if (!delay_seconds) throw new Error('Delay seconds is required for waitTime action');

            // Use original instruction delay (with variables) for playwright code generation if available
            let scriptDelay = delay_seconds;
            if (this.originalInstruction && this.originalInstruction.args) {
                const originalArg = this.originalInstruction.args.find((arg: any) => arg.key === 'delay_seconds');
                if (originalArg) {
                    scriptDelay = originalArg.value;
                }
            }

            // Check if the delay contains state template and resolve it
            if (scriptDelay && StateTemplateDetector(String(scriptDelay))) {
                const fn = new Function('state', `return \`${scriptDelay}\`;`);
                delay_seconds = fn(this.sharedState);
                logger.info(`Resolved wait time with state variables: ${scriptDelay}`);
            }

            await this.page.waitForTimeout(delay_seconds * 1000);

            // Use original delay (with variables) for playwright code generation
            const code = STATE_TEMPLATE_REGEX.test(String(scriptDelay)) ? `await page.waitForTimeout(\`${scriptDelay}\` * 1000);` : `await page.waitForTimeout(${scriptDelay} * 1000);`;
            this.storeExecutedCode(code);

            return {
                action,
                success: true,
                timestamp: Date.now()
            };
        } catch (error) {
            logger.error('WaitTime action failed', error);
            return {
                action,
                success: false,
                error: error instanceof Error ? error.message : 'Unknown error',
                timestamp: Date.now()
            };
        }
    }

    /**
     * Handle open tab action
     */
    public async handleOpenTab(action: OpenTabAction, instructionId?: string): Promise<ActionResult> {
        try {
            const { url } = action;
            if (!url) throw new Error('URL is required for openTab action');

            // Check if the URL contains state template
            const isStateTemplate = StateTemplateDetector(String(url));
            let finalUrl = url;

            if (isStateTemplate) {
                // If it contains ${state.*}, resol
                // ve the template literal
                const fn = new Function('state', `return \`${url}\`;`);
                finalUrl = fn(this.sharedState);
                logger.info(`Resolved URL with state variables: ${finalUrl}`);
            }

            // Validate and normalize the URL for execution
            const { normalizedUrl, protocol } = this.validateAndNormalizeUrl(finalUrl);

            // Use original instruction URL (with variables) for playwright code generation if available
            let scriptUrl = normalizedUrl;
            if (this.originalInstruction && this.originalInstruction.args) {
                const originalArg = this.originalInstruction.args.find((arg: any) => arg.key === 'url');
                if (originalArg && (VARIABLE_REGEX_PATTERN.test(originalArg.value) || ENV_VARIABLE_REGEX_PATTERN.test(originalArg.value) || StateTemplateDetector(originalArg.value))) {
                    scriptUrl = protocol + originalArg.value;   // Add protocol if it was added to normalized URL
                }
            }

            const newPage = await this.page.context().newPage();
            
            // Set up performance monitoring before navigation
            await this.performanceMonitoring.setupPerformanceMonitoring();

            await newPage.goto(normalizedUrl);

            // Wait for page to be fully loaded with timeout
            await this.performanceMonitoring.waitForPageLoadWithTimeout(newPage, 15000);

            // Collect performance metrics with timeout protection
            const metrics = await this.performanceMonitoring.collectPerformanceMetricsWithTimeout(15000);

            // Log performance metrics to console and Redis
            await this.performanceMonitoring.logPerformanceMetrics(metrics, url, instructionId);

            // Update page reference and BrowserContext active page
            await this.updatePageReference(newPage);

            logger.info(`New URL now ${this.page.url()}`)

            // Use original URL (with variables) for playwright code generation (preserve ${state.*} templates)
            const code = STATE_TEMPLATE_REGEX.test(String(scriptUrl)) ? `const newPage = await context.newPage();\nawait newPage.goto(\`${scriptUrl}\`);\npage = newPage;` 
                        : `const newPage = await context.newPage();\nawait newPage.goto('${scriptUrl}');\npage = newPage;`;
            this.storeExecutedCode(code);

            return {
                action,
                success: true,
                timestamp: Date.now()
            };
        } catch (error) {
            logger.error('OpenTab action failed', error);
            return {
                action,
                success: false,
                error: error instanceof Error ? error.message : 'Unknown error',
                timestamp: Date.now()
            };
        }
    }

    /**
     * Handle run script action
     */
    public async handleRunScript(action: RunScriptAction): Promise<ActionResult> {
        try {
            const { script } = action;
            // If script is empty but ai_use is always_ai on original instruction, do not throw; AI path will handle execution
            if (!script) {
                if (this.originalInstruction && (this.originalInstruction as any).ai_use === 'always_ai') {
                    return {
                        action,
                        success: true,
                        warning: 'Skipped run_script due to ai_use=always_ai; executed via AI mode',
                        timestamp: Date.now()
                    } as any;
                }
                throw new Error('Script is required for runScript action');
            }

            // Use original instruction script (with variables) for playwright code generation if available
            let scriptValue = script;
            if (this.originalInstruction && this.originalInstruction.args) {
                const originalArg = this.originalInstruction.args.find((arg: any) => arg.key === 'script');
                if (originalArg) {
                    scriptValue = originalArg.value;
                }
            }

            // Clean the script by removing leading/trailing whitespace
            let cleanedScript = script.trim();

            // Apply variable substitution to the script content before execution
            // Variables are substituted before execution:
            // - Data driven variables: ${variable_name}
            // - Environment variables: {{env.variable_name}}
            // - State variables: ${state.variable_name} (handled via state object in script context)
            if (this.variablesDict) {
                const dataDrivenVariables = this.variablesDict.data_driven_variables || {};
                const environmentVariables = this.variablesDict.environment_variables || {};
                
                if (Object.keys(dataDrivenVariables).length > 0 || Object.keys(environmentVariables).length > 0) {
                    logger.info(`Applying variable substitution to script with data-driven variables: ${JSON.stringify(dataDrivenVariables)}`);
                    logger.info(`Applying variable substitution to script with environment variables: ${JSON.stringify(environmentVariables)}`);
                    const originalScript = cleanedScript;
                    cleanedScript = substituteVariables(cleanedScript, dataDrivenVariables, environmentVariables);
                    logger.info(`Script before variable substitution: ${originalScript}`);
                    logger.info(`Script after variable substitution: ${cleanedScript}`);
                }
            }

            // Create litmus_log function for logging to Redis
            // Get the current instruction ID so logs appear under the correct instruction
            const currentInstructionId = this.originalInstruction?.id ? String(this.originalInstruction.id) : undefined;
            
            // Track pending log promises to ensure they complete
            const pendingLogs: Promise<void>[] = [];
            
            const litmusLog = litmusLogger(
                this.containerCommsService,
                this.runId || undefined,
                currentInstructionId,
                pendingLogs
            );

            // Execute the script directly in Node.js context where we have access to page object
            // Use shared state for script execution, and provide litmus_log function
            // Variables can be logged using:
            // - litmus_log('${variable_name}') for data driven variables (substituted before execution)
            // - litmus_log('{{env.variable_name}}') for environment variables (substituted before execution)
            // - litmus_log(`${state.variable_name}`) for state variables
            const fn = new Function('page', 'browser', 'context', 'assert', 'expect', 'request', 'state', 'litmus_log', `'use strict'; return (async () => { ${cleanedScript} })();`);
            await fn(this.page, this.page.context(), this.page.context(), assert, expect, request, this.sharedState, litmusLog);
            
            // Wait for all pending logs to complete before marking execution as complete
            if (pendingLogs.length > 0) {
                try {
                    await Promise.all(pendingLogs);
                    logger.debug(`[litmus_log] All ${pendingLogs.length} log(s) completed successfully`);
                } catch (error) {
                    logger.error(`[litmus_log] Some logs failed to complete: ${error instanceof Error ? error.message : String(error)}`);
                    // Continue execution even if some logs fail
                }
            }

            // Use original script (with variables) for playwright code generation
            this.storeExecutedCode(scriptValue);

            return {
                action,
                success: true,
                timestamp: Date.now()
            };
        } catch (error) {
            logger.error('RunScript action failed', error);
            return {
                action,
                success: false,
                error: error instanceof Error ? error.message : 'Unknown error',
                timestamp: Date.now()
            };
        }
    }

    /**
     * Handle set_state_variable action
     */
    public async handleSetStateVariable(action: SetStateVariableAction): Promise<ActionResult> {
        try {
            // Get the variable from flattened action properties
            logger.info(`SetStateVariable action: ${JSON.stringify(action)}`);
            
            // Extract args from instruction
            const args = action.instruction?.args || [];
            
            logger.info(`State variable to be set: ${JSON.stringify(args)}`);
            
            // Find variable_name and variable_value from args
            let variableName: string | undefined;
            let variableValue: any;
            
            for (const arg of args) {
                if (arg && typeof arg === 'object' && arg.key === 'variable_name') {
                    variableName = arg.value;
                } else if (arg && typeof arg === 'object' && arg.key === 'variable_value') {
                    variableValue = arg.value;
                }
            }
            
            if (!variableName) {
                throw new Error('variable_name is required for set_state_variable action');
            }
            
            if (variableValue === undefined) {
                throw new Error('variable_value is required for set_state_variable action');
            }

            // Use original instruction value (with variables) for playwright code generation if available
            let scriptValue = variableValue;
            if (this.originalInstruction && this.originalInstruction.args) {
                const originalArg = this.originalInstruction.args.find((arg: any) => arg.key === 'variable_value');
                if (originalArg) {
                    scriptValue = originalArg.value;
                }
            }

            // Check if the variable name is a dangerous key
            const dangerousKeys = new Set(['__proto__', 'prototype', 'constructor']);
            if (dangerousKeys.has(variableName)) {
                throw new Error(`Invalid state variable name: ${variableName}`);
            }

            // Set the state variable
            this.sharedState[variableName] = variableValue;
            
            // Log the state update
            if (this.containerCommsService && this.runId) {
                await this.containerCommsService.addLog(this.runId, {
                    info: `state updated: ${variableName} = ${JSON.stringify(variableValue)}`,
                    timestamp: new Date().toISOString()
                });
            }
            
            logger.info(`State variable added: ${variableName} = ${JSON.stringify(variableValue)}`);

            // Store the executed code
            // Escape the value if it's a string to ensure valid JavaScript syntax
            let escapedValue: string;
            if (typeof scriptValue === 'string') {
                escapedValue = `'${escapeJsStringValue(scriptValue)}'`;
            } else {
                // For non-string values, use JSON.stringify which handles numbers, booleans, objects, etc.
                escapedValue = JSON.stringify(scriptValue);
            }
            const executedCode = `state.${variableName} = ${escapedValue};`;
            this.storeExecutedCode(executedCode);
            
            return {
                action: action as any,
                success: true,
                timestamp: Date.now()
            };
        } catch (error) {
            logger.error('SetStateVariable action failed', error);
            return {
                action: action as any,
                success: false,
                error: error instanceof Error ? error.message : 'Unknown error',
                timestamp: Date.now()
            };
        }
    }

    /**
     * Handle API intercept action
     */
    public async handleApiIntercept(action: ApiInterceptAction): Promise<ActionResult> {
        try {
            logger.info(`ApiIntercept action: ${JSON.stringify(action)}`);
            
            const { url, method, action: interceptAction, js_code: jsCode, variable_name: variableName } = action;
            if (!url || !method || !interceptAction) {
                throw new Error('url, method, and action are required for api_intercept action');
            }
            
            // Check if the URL contains state template and resolve it
            const isStateTemplate = StateTemplateDetector(String(url));
            let finalUrl = url;
            if (isStateTemplate) {
                // If it contains ${state.*}, resolve the template literal
                const fn = new Function('state', `return \`${url}\`;`);
                finalUrl = fn(this.sharedState);
                logger.info(`Resolved URL with state variables: ${finalUrl}`);
            }
            
            // Use original instruction URL (with variables) for playwright code generation if available
            let scriptUrl = finalUrl;
            if (this.originalInstruction && this.originalInstruction.args) {
                const originalArg = this.originalInstruction.args.find((arg: any) => arg.key === 'url');
                if (originalArg && (VARIABLE_REGEX_PATTERN.test(originalArg.value) || ENV_VARIABLE_REGEX_PATTERN.test(originalArg.value) || StateTemplateDetector(originalArg.value))) {
                    scriptUrl = originalArg.value;
                }
            }
            
            // variable_name is required for all actions except abort_request
            if (interceptAction !== API_INTERCEPT_ACTIONS.ABORT_REQUEST && !variableName) {
                throw new Error('variable_name is required for api_intercept action when action is not abort_request');
            }
            
            // Get the Playwright browser context - route interception at context level
            // applies to ALL pages in this context, including new pages created later
            if (!this.browserContext) {
                throw new Error('Browser context not available');
            }
            const context = this.browserContext.getContext();
            const normalizedMethod = method.toUpperCase();
            if (variableName && !this.sharedState[variableName]) {
                this.sharedState[variableName] = {};
            }
            
            // Helper functions
            const parseRequestBody = (postData: string | null): any => {
                if (!postData) return null;
                try {
                    return JSON.parse(postData);
                } catch {
                    return postData;
                }
            };
            
            const applyVariableSubstitution = (code: string): string => {
                if (!this.variablesDict) return code;
                const dataDrivenVariables = this.variablesDict.data_driven_variables || {};
                const environmentVariables = this.variablesDict.environment_variables || {};
                if (Object.keys(dataDrivenVariables).length > 0 || Object.keys(environmentVariables).length > 0) {
                    return substituteVariables(code, dataDrivenVariables, environmentVariables);
                }
                return code;
            };
            
            // Set up route interception at context level based on action type
            if (interceptAction === API_INTERCEPT_ACTIONS.ABORT_REQUEST) {
                await context.route(finalUrl, async (route) => {
                    const req = route.request();

                    // Check if method matches, if not continue with original request
                    if (req.method().toUpperCase() !== normalizedMethod) {
                        await route.continue();
                        return;
                    }    
                    
                    await route.abort();
                    logger.info(`Aborted request: ${req.method()} ${req.url()}`);

                    // Add log to Redis
                    if (this.containerCommsService && this.runId) {
                        await this.containerCommsService.addLog(this.runId, {
                            info: `Aborted request: ${req.method()} ${req.url()}`,
                            timestamp: new Date().toISOString()
                        });
                    }
                });
                const abortCode = STATE_TEMPLATE_REGEX.test(String(scriptUrl)) 
                    ? `await context.route(\`${scriptUrl}\`, async (route) => {\n  const req = route.request();\n  if (req.method().toUpperCase() !== '${normalizedMethod}') {\n    await route.continue();\n    return;\n  }\n  await route.abort();\n});`
                    : `await context.route('${scriptUrl}', async (route) => {\n  const req = route.request();\n  if (req.method().toUpperCase() !== '${normalizedMethod}') {\n    await route.continue();\n    return;\n  }\n  await route.abort();\n});`;
                this.storeExecutedCode(abortCode);
            } 
            else if (interceptAction === API_INTERCEPT_ACTIONS.MODIFY_REQUEST) {
                await context.route(finalUrl, async (route) => {
                    const req = route.request();
            
                    // Skip non-matching methods
                    if (req.method().toUpperCase() !== normalizedMethod) {
                        await route.continue();
                        return;
                    }
            
                    const requestObj: any = {
                        url: req.url(),
                        method: req.method(),
                        headers: { ...req.headers() },
                        body: parseRequestBody(req.postData() ?? null)
                    };
            
                    // Run user-provided JS to modify the requestObj
                    if (jsCode) {
                        const cleanedCode = applyVariableSubstitution(jsCode);
                        const fn = new Function("request", "state", `'use strict'; ${cleanedCode}`);
                        fn(requestObj, this.sharedState);
                    }
            
                    // Store request in state if variable_name is provided
                    if (variableName) {
                        this.sharedState[variableName].request = {
                            url: requestObj.url,
                            method: requestObj.method,
                            headers: requestObj.headers,
                            body: requestObj.body
                        };
                    }
            
                    try {
                        // Build fetch options for modified request
                        // route.fetch() accepts url, method, headers, and postData in options
                        const fetchOptions: any = {
                            url: requestObj.url,
                            method: requestObj.method,
                            headers: requestObj.headers
                        };
                
                        if (requestObj.body !== undefined && requestObj.body !== null) {
                            fetchOptions.postData =
                                typeof requestObj.body === "object"
                                    ? JSON.stringify(requestObj.body)
                                    : requestObj.body;
                        }
                
                        logger.info(`Fetching with options: ${JSON.stringify({ url: fetchOptions.url, method: fetchOptions.method, hasHeaders: !!fetchOptions.headers, hasPostData: !!fetchOptions.postData })}`);
                
                        // Fetch actual response from server using modified request
                        const startTime = Date.now();
                        const response = await route.fetch(fetchOptions);
                        const responseTime = Date.now() - startTime;
                        
                        logger.info(`Fetch successful, status: ${response.status()}`);
                
                        // Extract response body
                        const rawResponseBody = await response.body();
                        const bodyText = new TextDecoder().decode(rawResponseBody);
                
                        // Return actual server response back to the browser
                        await route.fulfill({
                            status: response.status(),
                            headers: response.headers(),
                            body: rawResponseBody
                        });
                
                        // Store response in state if variable_name is provided
                        if (variableName) {
                            this.sharedState[variableName].response = {
                                statusCode: response.status(),
                                headers: response.headers(),
                                body: bodyText,
                                time: responseTime
                            };
                        }

                        if (variableName) {
                            logger.info(`Updated Response object: ${JSON.stringify(this.sharedState[variableName])}`);
                        }
                    } catch (error) {
                        logger.error(`Error in modify_request route handler: ${error instanceof Error ? error.message : String(error)}`);
                        logger.error(`Error stack: ${error instanceof Error ? error.stack : 'No stack trace'}`);
                        // Fallback: continue with original request
                        await route.continue();
                        return;
                    }
            
                    // Add log
                    if (this.containerCommsService && this.runId) {
                        await this.containerCommsService.addLog(this.runId, {
                            info: `Modified request: ${req.method()} ${req.url()}`,
                            timestamp: new Date().toISOString()
                        });
                    }
                });
            
                // Store executed code for script mode
                const jsCodeIndented = jsCode ? jsCode.split('\n').map((line: string) => `      ${line}`).join('\n') : '';
                const routeUrl = STATE_TEMPLATE_REGEX.test(String(scriptUrl)) ? `\`${scriptUrl}\`` : `'${scriptUrl}'`;
                const stateInit = variableName ? `  if (!state.${variableName}) {\n    state.${variableName} = {};\n  }\n` : '';
                const modifyRequestCode = `await context.route(${routeUrl}, async (route) => {\n${stateInit}  const req = route.request();\n  if (req.method().toUpperCase() !== '${normalizedMethod}') {\n    await route.continue();\n    return;\n  }\n  const postData = req.postData();\n  let parsedBody = null;\n  if (postData) {\n    try {\n      parsedBody = JSON.parse(postData);\n    } catch {\n      parsedBody = postData;\n    }\n  }\n  const requestObj = {\n    url: req.url(),\n    method: req.method(),\n    headers: { ...req.headers() },\n    body: parsedBody\n  };\n  (function(request, state) {\n    'use strict';\n${jsCodeIndented}\n  })(requestObj, state);\n${variableName ? `  if (state.${variableName}) {\n    state.${variableName}.request = {\n      url: requestObj.url,\n      method: requestObj.method,\n      headers: requestObj.headers,\n      body: requestObj.body\n    };\n  }\n` : ''}  try {\n    const fetchOptions = {\n      url: requestObj.url,\n      method: requestObj.method,\n      headers: requestObj.headers\n    };\n    if (requestObj.body !== undefined && requestObj.body !== null) {\n      fetchOptions.postData = typeof requestObj.body === 'object' ? JSON.stringify(requestObj.body) : requestObj.body;\n    }\n    const startTime = Date.now();\n    const response = await route.fetch(fetchOptions);\n    const responseTime = Date.now() - startTime;\n    const rawResponseBody = await response.body();\n    const bodyText = new TextDecoder().decode(rawResponseBody);\n    await route.fulfill({\n      status: response.status(),\n      headers: response.headers(),\n      body: rawResponseBody\n    });\n${variableName ? `    if (state.${variableName}) {\n      state.${variableName}.response = {\n        statusCode: response.status(),\n        headers: response.headers(),\n        body: bodyText,\n        time: responseTime\n      };\n    }` : ''}\n  } catch (error) {\n    await route.continue();\n    throw error;\n  }\n});`;
                this.storeExecutedCode(modifyRequestCode);
            }             
            else if (interceptAction === API_INTERCEPT_ACTIONS.MODIFY_RESPONSE) {
                await context.route(finalUrl, async (route) => {
                    const req = route.request();
                    if (req.method().toUpperCase() !== normalizedMethod) {
                        await route.continue();
                        return;
                    }
                    if (variableName) {
                        this.sharedState[variableName].request = {
                            url: req.url(),
                            method: req.method(),
                            headers: req.headers(),
                            body: parseRequestBody(req.postData())
                        };
                    }

                    const startTime = Date.now();
                    const response = await route.fetch();
                    const responseTime = Date.now() - startTime;
                    const responseBody = await response.text();
                    
                    // Create response object - user's js_code will modify this directly
                    const responseObj: any = {
                        statusCode: response.status(),
                        headers: { ...response.headers() },
                        body: responseBody,
                        time: responseTime
                    };
                    
                    // Try to parse as JSON initially, but js_code can override this
                    try {
                        responseObj.body = JSON.parse(responseBody);
                    } catch {
                        // Keep as string if not JSON - user can still modify it in js_code
                    }
                    
                    // Execute js_code to modify response object
                    if (jsCode) {
                        const cleanedCode = applyVariableSubstitution(jsCode);
                        const fn = new Function('response', 'state', `'use strict'; ${cleanedCode}`);
                        fn(responseObj, this.sharedState);
                    }
                    
                    // Store in state if variable_name is provided
                    if (variableName) {
                        this.sharedState[variableName].response = {
                            statusCode: responseObj.statusCode,
                            headers: responseObj.headers,
                            body: responseObj.body,
                            time: responseObj.time
                        };
                    }
                    
                    // Convert body to string for fulfill - use modified value from js_code
                    let bodyForFulfill: string;
                    if (responseObj.body === null || responseObj.body === undefined) {
                        bodyForFulfill = '';
                    } else if (typeof responseObj.body === 'object') {
                        bodyForFulfill = JSON.stringify(responseObj.body);
                    } else {
                        bodyForFulfill = String(responseObj.body);
                    }
                    
                    await route.fulfill({
                        status: responseObj.statusCode || response.status(),
                        headers: responseObj.headers || response.headers(),
                        body: bodyForFulfill
                    });
                });
                const jsCodeIndentedResponse = jsCode ? jsCode.split('\n').map((line: string) => `      ${line}`).join('\n') : '';
                const routeUrlResponse = STATE_TEMPLATE_REGEX.test(String(scriptUrl)) ? `\`${scriptUrl}\`` : `'${scriptUrl}'`;
                const stateInitResponse = variableName ? `  if (!state.${variableName}) {\n    state.${variableName} = {};\n  }\n` : '';
                const modifyResponseCode = `await context.route(${routeUrlResponse}, async (route) => {\n${stateInitResponse}  const req = route.request();\n  if (req.method().toUpperCase() !== '${normalizedMethod}') {\n    await route.continue();\n    return;\n  }\n  if (state.${variableName}) {\n    const postData = req.postData();\n    let parsedBody = null;\n    if (postData) {\n      try {\n        parsedBody = JSON.parse(postData);\n      } catch {\n        parsedBody = postData;\n      }\n    }\n    state.${variableName}.request = {\n      url: req.url(),\n      method: req.method(),\n      headers: req.headers(),\n      body: parsedBody\n    };\n  }\n  const startTime = Date.now();\n  const response = await route.fetch();\n  const responseTime = Date.now() - startTime;\n  const responseBody = await response.text();\n  const responseObj = {\n    statusCode: response.status(),\n    headers: { ...response.headers() },\n    body: responseBody,\n    time: responseTime\n  };\n  try {\n    responseObj.body = JSON.parse(responseBody);\n  } catch {\n    // Keep as string if not JSON\n  }\n  (function(response, state) {\n    'use strict';\n${jsCodeIndentedResponse}\n  })(responseObj, state);\n  if (state.${variableName}) {\n    state.${variableName}.response = {\n      statusCode: responseObj.statusCode,\n      headers: responseObj.headers,\n      body: responseObj.body,\n      time: responseObj.time\n    };\n  }\n  let bodyForFulfill = '';\n  if (responseObj.body === null || responseObj.body === undefined) {\n    bodyForFulfill = '';\n  } else if (typeof responseObj.body === 'object') {\n    bodyForFulfill = JSON.stringify(responseObj.body);\n  } else {\n    bodyForFulfill = String(responseObj.body);\n  }\n  await route.fulfill({\n    status: responseObj.statusCode || response.status(),\n    headers: responseObj.headers || response.headers(),\n    body: bodyForFulfill\n  });\n});`;
                this.storeExecutedCode(modifyResponseCode);
            } 
            else if (interceptAction === API_INTERCEPT_ACTIONS.RECORD_ONLY) {
                await context.route(finalUrl, async (route) => {
                    const req = route.request();
                    if (req.method().toUpperCase() !== normalizedMethod) {
                        await route.continue();
                        return;
                    }
                    if (variableName) {
                        this.sharedState[variableName].request = {
                            url: req.url(),
                            method: req.method(),
                            headers: req.headers(),
                            body: parseRequestBody(req.postData())
                        };
                    }

                    const startTime = Date.now();
                    const response = await route.fetch();
                    const responseTime = Date.now() - startTime;
                    let responseBody = await response.text();

                    
                    let responseObj: any = {
                        statusCode: response.status(),
                        headers: response.headers(),
                        body: responseBody,
                        time: responseTime
                    };
                    
                    try {
                        responseObj.body = JSON.parse(responseBody);
                    } catch {}
                    
                    if (variableName) {
                        this.sharedState[variableName].response = {
                            statusCode: responseObj.statusCode,
                            headers: responseObj.headers,
                            body: responseObj.body,
                            time: responseObj.time
                        };
                    }
                    
                    await route.fulfill({ response });
                });
                const routeUrlRecord = STATE_TEMPLATE_REGEX.test(String(scriptUrl)) ? `\`${scriptUrl}\`` : `'${scriptUrl}'`;
                const stateInitRecord = variableName ? `  if (!state.${variableName}) {\n    state.${variableName} = {};\n  }\n` : '';
                const recordOnlyCode = `await context.route(${routeUrlRecord}, async (route) => {\n${stateInitRecord}  const req = route.request();\n  if (req.method().toUpperCase() !== '${normalizedMethod}') {\n    await route.continue();\n    return;\n  }\n  if (state.${variableName}) {\n    const postData = req.postData();\n    let parsedBody = null;\n    if (postData) {\n      try {\n        parsedBody = JSON.parse(postData);\n      } catch {\n        parsedBody = postData;\n      }\n    }\n    state.${variableName}.request = {\n      url: req.url(),\n      method: req.method(),\n      headers: req.headers(),\n      body: parsedBody\n    };\n  }\n  const startTime = Date.now();\n  const response = await route.fetch();\n  const responseTime = Date.now() - startTime;\n  let responseBody = await response.text();\n  let responseObj = {\n    statusCode: response.status(),\n    headers: response.headers(),\n    body: responseBody,\n    time: responseTime\n  };\n  try {\n    responseObj.body = JSON.parse(responseBody);\n  } catch {}\n  if (state.${variableName}) {\n    state.${variableName}.response = {\n      statusCode: responseObj.statusCode,\n      headers: responseObj.headers,\n      body: responseObj.body,\n      time: responseObj.time\n    };\n  }\n  await route.fulfill({ response });\n});`;
                this.storeExecutedCode(recordOnlyCode);
            }
            
            logger.info(`API interception set up: ${normalizedMethod} ${url} (action: ${interceptAction}, variable: ${variableName})`);
            
            return {
                action: action as any,
                success: true,
                timestamp: Date.now()
            };
        } catch (error) {
            logger.error('ApiIntercept action failed', error);
            return {
                action: action as any,
                success: false,
                error: error instanceof Error ? error.message : 'Unknown error',
                timestamp: Date.now()
            };
        }
    }

    /**
     * Handle remove API handlers action
     */
    public async handleRemoveApiHandlers(action: RemoveApiHandlersAction): Promise<ActionResult> {
        try {
            logger.info(`RemoveApiHandlers action: ${JSON.stringify(action)}`);

            const { url } = action;
            if (!url) {
                throw new Error('URL is required for remove_api_handlers action');
            }

            // Check if the URL contains state template and resolve it
            const isStateTemplate = StateTemplateDetector(String(url));
            let finalUrl = url;
            if (isStateTemplate) {
                // If it contains ${state.*}, resolve the template literal
                const fn = new Function('state', `return \`${url}\`;`);
                finalUrl = fn(this.sharedState);
                logger.info(`Resolved URL with state variables: ${finalUrl}`);
            }

            // Use original instruction URL (with variables) for playwright code generation if available
            let scriptUrl = finalUrl;
            if (this.originalInstruction && this.originalInstruction.args) {
                const originalArg = this.originalInstruction.args.find((arg: any) => arg.key === 'url');
                if (originalArg && (VARIABLE_REGEX_PATTERN.test(originalArg.value) || ENV_VARIABLE_REGEX_PATTERN.test(originalArg.value) || StateTemplateDetector(originalArg.value))) {
                    scriptUrl = originalArg.value;
                }
            }

            // Get the Playwright browser context
            if (!this.browserContext) {
                throw new Error('Browser context not available');
            }
            const context = this.browserContext.getContext();

            // Remove route handlers matching the URL pattern
            // Playwright's unroute() supports string (exact URL) or glob pattern
            await context.unroute(finalUrl);
            
            logger.info(`API handlers removed for: ${finalUrl}`);

            // Store executed code for script mode
            const unrouteCode = STATE_TEMPLATE_REGEX.test(String(scriptUrl)) 
                ? `await context.unroute(\`${scriptUrl}\`);`
                : `await context.unroute('${scriptUrl}');`;
            this.storeExecutedCode(unrouteCode);

            // Add log to container comms service
            if (this.containerCommsService && this.runId) {
                await this.containerCommsService.addLog(this.runId, {
                    info: `API handlers removed for: ${finalUrl}`,
                    timestamp: new Date().toISOString()
                });
            }

            return {
                action: action as any,
                success: true,
                timestamp: Date.now()
            };
        } catch (error) {
            logger.error('RemoveApiHandlers action failed', error);
            return {
                action: action as any,
                success: false,
                error: error instanceof Error ? error.message : 'Unknown error',
                timestamp: Date.now()
            };
        }
    }

    /**
     * Handle API mock action
     */
    public async handleApiMock(action: ApiMockAction): Promise<ActionResult> {
        try {
            logger.info(`ApiMock action: ${JSON.stringify(action)}`);
            
            const { url, method, status_code, response_header, response_body } = action;
            if (!url || !method || !status_code || !response_header || !response_body) {
                throw new Error('url, method, status_code, response_header, and response_body are required for api_mock action');
            }
            
            // Check if the URL contains state template and resolve it
            const isStateTemplateUrl = StateTemplateDetector(String(url));
            let finalUrl = url;
            if (isStateTemplateUrl) {
                const fn = new Function('state', `return \`${url}\`;`);
                finalUrl = fn(this.sharedState);
                logger.info(`Resolved URL with state variables: ${finalUrl}`);
            }
            
            // Use original instruction URL (with state variables) for playwright code generation if available
            let scriptUrl = finalUrl;
            if (this.originalInstruction && this.originalInstruction.args) {
                const originalArg = this.originalInstruction.args.find((arg: any) => arg.key === 'url');
                if (originalArg) {
                    scriptUrl = originalArg.value;
                }
            }
            
            // Check if response_header contains state template and resolve it
            const isStateTemplateHeader = StateTemplateDetector(String(response_header));
            let finalResponseHeader = response_header;
            if (isStateTemplateHeader) {
                const fn = new Function('state', `return \`${response_header}\`;`);
                finalResponseHeader = fn(this.sharedState);
                logger.info(`Resolved response_header with state variables: ${finalResponseHeader}`);
            }
            
            // Use original instruction response_header (with state variables) for playwright code generation if available
            let scriptResponseHeader = response_header;
            if (this.originalInstruction && this.originalInstruction.args) {
                const originalArg = this.originalInstruction.args.find((arg: any) => arg.key === 'response_header');
                if (originalArg) {
                    scriptResponseHeader = originalArg.value;
                }
            }
            
            // Check if response_body contains state template and resolve it
            const isStateTemplateBody = StateTemplateDetector(String(response_body));
            let finalResponseBody = response_body;
            if (isStateTemplateBody) {
                const fn = new Function('state', `return \`${response_body}\`;`);
                finalResponseBody = fn(this.sharedState);
                logger.info(`Resolved response_body with state variables: ${finalResponseBody}`);
            }
            
            // Use original instruction response_body (with state variables) for playwright code generation if available
            let scriptResponseBody = response_body;
            if (this.originalInstruction && this.originalInstruction.args) {
                const originalArg = this.originalInstruction.args.find((arg: any) => arg.key === 'response_body');
                if (originalArg) {
                    scriptResponseBody = originalArg.value;
                }
            }
            
            // Parse response_header (should be JSON string)
            let parsedHeaders: any = {};
            try {
                parsedHeaders = JSON.parse(finalResponseHeader);
            } catch (error) {
                logger.warn(`Failed to parse response_header as JSON, using empty object: ${error}`);
                parsedHeaders = {};
            }
            
            // Parse response_body (try JSON first, fallback to string)
            let parsedBody: any = finalResponseBody;
            try {
                parsedBody = JSON.parse(finalResponseBody);
            } catch {
                // Keep as string if not JSON
                parsedBody = finalResponseBody;
            }
            
            // Convert body to string for fulfill
            let bodyForFulfill: string;
            if (parsedBody === null || parsedBody === undefined) {
                bodyForFulfill = '';
            } else if (typeof parsedBody === 'object') {
                bodyForFulfill = JSON.stringify(parsedBody);
            } else {
                bodyForFulfill = String(parsedBody);
            }
            
            // Get the Playwright browser context - route interception at context level
            if (!this.browserContext) {
                throw new Error('Browser context not available');
            }
            const context = this.browserContext.getContext();
            const normalizedMethod = method.toUpperCase();
            const statusCode = parseInt(status_code, 10);
            
            // Set up route interception at context level
            await context.route(finalUrl, async (route) => {
                const req = route.request();
                
                if (req.method().toUpperCase() !== normalizedMethod) {
                    await route.continue();
                    return;
                }
                
                // Fulfill with mock response
                await route.fulfill({
                    status: statusCode,
                    headers: parsedHeaders,
                    body: bodyForFulfill
                });
                
                logger.info(`Mocked request: ${req.method()} ${req.url()} with status ${statusCode}`);
                
                // Add log
                if (this.containerCommsService && this.runId) {
                    await this.containerCommsService.addLog(this.runId, {
                        info: `Mocked request: ${req.method()} ${req.url()} with status ${statusCode}`,
                        timestamp: new Date().toISOString()
                    });
                }
            });
            
            // Store executed code for script mode - must match actual execution
            const routeUrlMock = STATE_TEMPLATE_REGEX.test(String(scriptUrl)) ? `\`${scriptUrl}\`` : `'${scriptUrl}'`;
            const headerHasState = STATE_TEMPLATE_REGEX.test(String(scriptResponseHeader));
            const bodyHasState = STATE_TEMPLATE_REGEX.test(String(scriptResponseBody));
            
            // Resolve state variables first (matching execution)
            const headerResolve = headerHasState 
                ? `const finalResponseHeader = \`${scriptResponseHeader}\`;`
                : `const finalResponseHeader = ${JSON.stringify(scriptResponseHeader)};`;
            const bodyResolve = bodyHasState
                ? `const finalResponseBody = \`${scriptResponseBody}\`;`
                : `const finalResponseBody = ${JSON.stringify(scriptResponseBody)};`;
            
            const mockCode = `await context.route(${routeUrlMock}, async (route) => {\n  const req = route.request();\n  if (req.method().toUpperCase() !== '${normalizedMethod}') {\n    await route.continue();\n    return;\n  }\n  ${headerResolve}\n  let parsedHeaders = {};\n  try {\n    parsedHeaders = JSON.parse(finalResponseHeader);\n  } catch (error) {\n    parsedHeaders = {};\n  }\n  ${bodyResolve}\n  let parsedBody = finalResponseBody;\n  try {\n    parsedBody = JSON.parse(finalResponseBody);\n  } catch {\n    // Keep as string if not JSON\n    parsedBody = finalResponseBody;\n  }\n  let bodyForFulfill = '';\n  if (parsedBody === null || parsedBody === undefined) {\n    bodyForFulfill = '';\n  } else if (typeof parsedBody === 'object') {\n    bodyForFulfill = JSON.stringify(parsedBody);\n  } else {\n    bodyForFulfill = String(parsedBody);\n  }\n  await route.fulfill({\n    status: ${statusCode},\n    headers: parsedHeaders,\n    body: bodyForFulfill\n  });\n});`;
            this.storeExecutedCode(mockCode);
            
            logger.info(`API mock set up: ${normalizedMethod} ${finalUrl} with status ${statusCode}`);
            
            return {
                action: action as any,
                success: true,
                timestamp: Date.now()
            };
        } catch (error) {
            logger.error('ApiMock action failed', error);
            return {
                action: action as any,
                success: false,
                error: error instanceof Error ? error.message : 'Unknown error',
                timestamp: Date.now()
            };
        }
    }

    /**
     * Upload file using file chooser approach (for button/link triggers or fallback)
     * @param element The playwright element to click
     * @param localFilePath The local file path to upload
     * @param scriptSelector The selector string for script generation
     * @returns The executed script string
     */
    private async uploadFileViaFileChooser(element: any, localFilePath: string, scriptSelector: string): Promise<string> {
        // Create file chooser promise before clicking
        const fileChooserPromise = this.page.waitForEvent('filechooser');
        
        // Click the element to trigger file chooser
        await element.click();
        
        // Wait for 2 seconds
        await this.page.waitForTimeout(2000);
        
        // Get the file chooser from the promise
        const fileChooser = await fileChooserPromise;
        
        // Upload file using setFiles
        await fileChooser.setFiles(localFilePath);
        
        // Generate and store the executed script
        const executedScript = `const fileChooserPromise = page.waitForEvent('filechooser');\nawait ${scriptSelector}.click();\nawait page.waitForTimeout(2000);\nconst fileChooser = await fileChooserPromise;\nawait fileChooser.setFiles('{{file_path}}');`;
        this.storeExecutedCode(executedScript);
        
        return executedScript;
    }

    /**
     * Handle file upload action
     * Note :- Environment variables, Data driven variables are not supported in file upload action
     */
    public async handleUploadFile(action: FileUploadAction): Promise<ActionResult> {
        try {
            const { elementId, file_url } = action;
            if (!elementId) throw new Error('Element ID is required for uploadFile action');
            if (!file_url) throw new Error('File URL is required for uploadFile action');

            // Get element info first
            const elementInfo = this.elementsManager.getElementById(elementId);

            // Download the file from the URL(Azure Blob Storage)
            const localFolderPath = FILE_UPLOADS_DIR;
            const localFilePath = await DownloadUtils.getInstance().downloadFile(file_url as string, localFolderPath);

            // Check if file exists
            if (!fs.existsSync(localFilePath)) {
                throw new Error(`File not found: ${localFilePath}`);
            }
            
            // Get the element (this will filter the selectors)
            const elementResult = await this.getElement(elementId);
            if (!elementResult) {
                throw new Error(`Element with ID ${elementId} not found`);
            }
            
            // Check if element is a direct file input by evaluating it
            const isFileInput = await elementResult.element.evaluate((el) => {
                return el instanceof HTMLInputElement && el.type === 'file';
            });
            
            // Generate scripts using the filtered selectors based on element type
            const scripts: string[] = [];
            if (elementInfo && (elementInfo as any).selectors) {
                for (const selectorObj of (elementInfo as any).selectors) {
                    if (isFileInput) {
                        // Generate script for direct file input using setInputFiles
                        const script = this.generateScriptForSelector(selectorObj, 'setInputFiles', '{{file_path}}');
                        logger.info(`Script (file input): ${script}`);
                        scripts.push(script);
                    } else {
                        // Generate script for file chooser approach (button/link trigger)
                        const clickScript = this.generateScriptForSelector(selectorObj, 'click');
                        const fileChooserScript = `const fileChooserPromise = page.waitForEvent('filechooser');\n${clickScript}\nawait page.waitForTimeout(2000);\nconst fileChooser = await fileChooserPromise;\nawait fileChooser.setFiles('{{file_path}}');`;
                        logger.info(`Script (file chooser): ${fileChooserScript}`);
                        scripts.push(fileChooserScript);
                    }
                }
            }

            // Execute upload based on element type
            let executedScript: string;
            const selectors = elementInfo && (elementInfo as any).selectors ? (elementInfo as any).selectors : [];

            if (isFileInput) {
                // Try direct upload first for file input elements
                try {
                    await elementResult.element.setInputFiles(localFilePath);
                    
                    // Store the exact script that was executed using elementResult.script
                    executedScript = `await ${elementResult.script}.setInputFiles('{{file_path}}');`;
                    this.storeExecutedCode(executedScript);
                    
                    logger.info('File uploaded successfully using direct setInputFiles method');
                } catch (directUploadError) {
                    // If direct upload fails, fall back to file chooser approach
                    logger.info('Direct setInputFiles failed for file input, trying file chooser approach', directUploadError);
                    
                    executedScript = await this.uploadFileViaFileChooser(
                        elementResult.element,
                        localFilePath,
                        elementResult.script
                    );
                    
                    logger.info('File uploaded successfully using file chooser approach (fallback)');
                }
            } else {
                // For button/link triggers, use file chooser approach directly
                logger.info('Using file chooser approach for button/link trigger element');
                
                executedScript = await this.uploadFileViaFileChooser(
                    elementResult.element,
                    localFilePath,
                    elementResult.script
                );
                
                logger.info('File uploaded successfully using file chooser approach');
            }

            return {
                action,
                success: true,
                timestamp: Date.now(),
                selectors: { selectors },
                scripts
            };
        } catch (error) {
            logger.error('UploadFile action failed', error);
            return {
                action,
                success: false,
                error: error instanceof Error ? error.message : 'Unknown error',
                timestamp: Date.now()
            };
        }
    }

    /**
     * Handle AI script action - generate and execute a Node.js script
     */
    public async handleAiScript(action: AiScriptAction): Promise<ActionResult> {
        try {
            const { script } = action;
            if (!script) throw new Error('Script is required for AI script action');

            logger.info(`Executing AI script: ${script}`);

            // Execute the script directly in Node.js context where we have access to page object
            // eslint-disable-next-line no-eval
            const fn = new Function('page', 'browser', 'context', 'assert', 'expect', 'request', 'state', `'use strict'; return (async () => { ${script} })();`);
            await fn(this.page, this.page.context(), this.page.context(), assert, expect, request, this.sharedState);

            // Store the generated script
            this.storeExecutedCode(script);

            logger.info('AI script generated and stored successfully');

            return {
                action,
                success: true,
                timestamp: Date.now()
            };
        } catch (error) {
            logger.info('AI script action failed', error);

            return {
                action,
                success: false,
                error: 'Unable to generate valid playwright code: ' + (error instanceof Error ? error.message : 'Unknown error'),
                timestamp: Date.now()
            };
        }
    }

    /**
     * Generate a Node.js script from cleaned HTML content using LLM
     */
    private async generateScriptFromHtml(cleanedHtml: string, taskDescription: string, currentUrl: string): Promise<string> {
        try {
            // This would typically call an LLM service to generate the script
            // For now, we'll create a basic template
            const scriptTemplate = `
                Generated script for: ${taskDescription}

                Current URL: '${currentUrl}',
            `;

            logger.info('Script generated from HTML content');
            return scriptTemplate;
        } catch (error) {
            logger.error('Error generating script from HTML:', error);
            throw error;
        }
    }

    /**
     * Run a sequence of Playwright commands
     * @param commands Array of Playwright commands to execute
     */
    public async runPlaywrightCommands(commands: string[]): Promise<void> {
        for (const [index, command] of commands.entries()) {
            logger.info(`Executing command ${index + 1}: ${command}`);
            
            // Execute the command
            await this.page.evaluate(command);
            
            // Log the result
            logger.info(`Command ${index + 1} executed successfully`);
            
            // Store the executed code
            this.storeExecutedCode(command);
        }
    }

    /**
     * Validate and normalize URL
     * @param url The URL to validate and normalize
     * @returns Object containing normalized URL and protocol that was added
     * @throws Error if URL is invalid
     */
    // Note: If anything is changed here, please update the validate_url function in utils_instruction_validations.py
    private validateAndNormalizeUrl(url: string): { normalizedUrl: string; protocol: string } {
        if (!url || typeof url !== 'string') {
            throw new Error('URL must be a non-empty string');
        }

        // Trim whitespace
        const trimmedUrl = url.trim();
        
        if (!trimmedUrl) {
            throw new Error('URL cannot be empty or whitespace only');
        }

        // Check if URL already has a protocol
        if (trimmedUrl.startsWith('http://') || trimmedUrl.startsWith('https://')) {
            // Validate the URL format using new URL() but return the original string
            try {
                new URL(trimmedUrl); // Only for validation
                return { normalizedUrl: trimmedUrl, protocol: '' }; // No protocol was added
            } catch (error) {
                throw new Error(`Invalid URL format: ${trimmedUrl}`);
            }
        }

        // If no protocol, add https:// as default
        const normalizedUrl = `https://${trimmedUrl}`;
        
        // Validate the normalized URL using new URL() but return the string
        try {
            new URL(normalizedUrl); // Only for validation
            return { normalizedUrl, protocol: 'https://' }; // Protocol was added
        } catch (error) {
            throw new Error(`Invalid URL format: ${trimmedUrl}`);
        }
    }


    /**
     * Handle go to URL action
     */
    public async handleGoToUrl(action: GoToUrlAction, instructionId?: string): Promise<ActionResult> {
        try {
            const { url } = action;
            if (!url) throw new Error('URL is required for goToUrl action');

            // Check if the URL contains state template
            const isStateTemplate = StateTemplateDetector(String(url));
            let finalUrl = url;

            if (isStateTemplate) {
                // If it contains ${state.*}, resolve the template literal
                const fn = new Function('state', `return \`${url}\`;`);
                finalUrl = fn(this.sharedState);
                logger.info(`Resolved URL with state variables: ${finalUrl}`);
            }

            // Validate and normalize the URL for execution
            const { normalizedUrl, protocol } = this.validateAndNormalizeUrl(finalUrl);

            // Use original instruction URL (with variables) for playwright code generation if available
            let scriptUrl = normalizedUrl;
            if (this.originalInstruction && this.originalInstruction.args) {
                const originalArg = this.originalInstruction.args.find((arg: any) => arg.key === 'url');
                if (originalArg && (VARIABLE_REGEX_PATTERN.test(originalArg.value) || ENV_VARIABLE_REGEX_PATTERN.test(originalArg.value) || StateTemplateDetector(originalArg.value))) {
                    scriptUrl = protocol + originalArg.value;   // Add protocol if it was added to normalized URL
                }
            }

            // Set up performance monitoring before navigation
            await this.performanceMonitoring.setupPerformanceMonitoring();

            await this.page.goto(normalizedUrl);

            // Wait for page to be fully loaded with timeout
            await this.performanceMonitoring.waitForPageLoadWithTimeout(this.page, 15000);

            // Collect performance metrics with timeout protection
            const metrics = await this.performanceMonitoring.collectPerformanceMetricsWithTimeout(15000);

            // Log performance metrics to console and Redis
            await this.performanceMonitoring.logPerformanceMetrics(metrics, url, instructionId);

            // Use original URL (with variables) for playwright code generation (preserve ${state.*} templates)
            const code = STATE_TEMPLATE_REGEX.test(String(scriptUrl)) ? `await page.goto(\`${scriptUrl}\`);` : `await page.goto('${scriptUrl}');`;
            this.storeExecutedCode(code);

            return {
                action,
                success: true,
                timestamp: Date.now()
            };
        } catch (error) {
            logger.error('GoToUrl action failed', error);
            return {
                action,
                success: false,
                error: error instanceof Error ? error.message : 'Unknown error',
                timestamp: Date.now()
            };
        }
    }

    /**
     * Handle go back action
     */
    public async handleGoBack(action: GoBackAction): Promise<ActionResult> {
        try {
            await this.page.goBack();

            const code = `await page.goBack();`;
            this.storeExecutedCode(code);

            return {
                action,
                success: true,
                timestamp: Date.now()
            };
        } catch (error) {
            logger.error('GoBack action failed', error);
            return {
                action,
                success: false,
                error: error instanceof Error ? error.message : 'Unknown error',
                timestamp: Date.now()
            };
        }
    }

    public async handlePageReload(action: PageReload): Promise<ActionResult> {
        try {
            await this.page.reload();

            const code = `await page.reload();`;
            this.storeExecutedCode(code);

            return {
                action,
                success: true,
                timestamp: Date.now()
            };
        }
        catch (error) {
            logger.error('PageReload action failed', error);
            return {
                action,
                success: false,
                error: error instanceof Error ? error.message : 'Unknown error',
                timestamp: Date.now()
            };
        }
    }

    /**
     * Handle key press action
     */
    public async handleKeyPress(action: KeyPressAction): Promise<ActionResult> {
        try {
            const { key_type, value } = action;
            
            if (!key_type || !value) throw new Error('Key and value are required for key press action');

            // Use original instruction value (with variables) for playwright code generation if available
            let scriptValue = value;
            if (this.originalInstruction && this.originalInstruction.args) {
                const originalArg = this.originalInstruction.args.find((arg: any) => arg.key === 'value');
                if (originalArg) {
                    scriptValue = originalArg.value;
                }
            }

            // Check if the value contains state template and resolve it
            let resolvedValue = value;
            if (StateTemplateDetector(String(scriptValue))) {
                const fn = new Function('state', `return \`${scriptValue}\`;`);
                resolvedValue = fn(this.sharedState);
                logger.info(`Resolved key press value with state variables: ${resolvedValue}`);
            }

            let code = '';

            // Handle different key press types
            switch (key_type) {
                case 'press':
                    await this.page.keyboard.press(resolvedValue);
                    code = `await page.keyboard.press('${resolvedValue}');`;
                    break;

                case 'down':
                    await this.page.keyboard.down(resolvedValue);
                    code = `await page.keyboard.down('${resolvedValue}');`;
                    break;

                case 'up':
                    await this.page.keyboard.up(resolvedValue);
                    code = `await page.keyboard.up('${resolvedValue}');`;
                    break;

                default:
                    throw new Error(`Invalid key press type: ${key_type}`);
            }

            // Store the executed code
            this.storeExecutedCode(code);

            return {
                action,
                success: true,
                timestamp: Date.now()
            };
        } catch (error) {
            logger.error('KeyPress action failed', error);
            return {
                action,
                success: false,
                error: error instanceof Error ? error.message : 'Unknown error',
                timestamp: Date.now()
            };
        }
    }

    /**
     * Handle verification action
     * This function executes verifications and handles fail_test logic based on the instruction structure
     */
    public async handleVerification(action: VerificationAction): Promise<ActionResult> {
        try {
            // Import verification types and functions
            const { getArgValue } = await import('../types/verifications');
            
            // Prefer flat action properties; fallback to instruction args
            const getProp = (key: string) => (action as any)[key] ?? (action.instruction ? getArgValue(action.instruction, key) : null);
            const target = getProp('target');
            const property = getProp('property');
            const check = getProp('check');
            const locatorType = getProp('locator_type');
            let locator = getProp('locator');
            const subProperty = getProp('sub_property');
            let value = getProp('value');
            const expectedResult = getProp('expected_result');

            // Keep original value for code generation, resolve for execution
            const originalValue = value;
            let resolvedValue = value;
            if (value && StateTemplateDetector(String(value))) {
                const fn = new Function('state', `return \`${value}\`;`);
                resolvedValue = fn(this.sharedState);
                logger.info(`Resolved verification value with state variables: ${resolvedValue}`);
            }
            const failTest = (() => {
                const ft = getProp('fail_test');
                return ft === true || ft === 'true';
            })();

            let verificationCode = '';
            let selectors: Array<{selector: string, display: string, method: string}> = [];
            let scripts: string[] = [];

            // Build a minimal instruction object for generator (so generator API stays consistent)
            const instructionForGen = {
                action: 'verify' as const,
                id: action.instruction?.id || 'verification',
                playwright_actions: action.instruction?.playwright_actions || [],
                type: locatorType === 'ai' ? 'AI' as const : 'Non-AI' as const,
                args: [
                    { key: 'target', value: target ?? null },
                    { key: 'property', value: property ?? null },
                    { key: 'check', value: check ?? null },
                    { key: 'sub_property', value: subProperty ?? null },
                    { key: 'value', value: originalValue ?? null },
                    { key: 'locator_type', value: locatorType ?? null },
                    { key: 'fail_test', value: failTest },
                    { key: 'expected_result', value: expectedResult ?? null }
                ]
            };

            // For element verifications, we need to get the selector
            if (target === 'element') {
                if (locatorType === 'ai') {
                    // Get the element from elementId
                    const elementId = action.elementId;
                    if(!elementId) {
                        throw new Error('Element ID is required for verification action');
                    }
                    const elementInfo = this.elementsManager.getElementById(elementId);
                    if (!elementInfo) {
                        throw new Error(`Element with ID ${elementId} not found`);
                    }
                    
                    // Get the element (this will filter the selectors)
                    const elementResult = await this.getElement(elementId);
                    if (!elementResult) {
                        throw new Error(`Element with ID ${elementId} not found`);
                    }


                    // Generate scripts using the filtered selectors
                    if (elementInfo && (elementInfo as any).selectors) {
                        for (const selectorObj of (elementInfo as any).selectors) {
                            // For verifications, we need to generate the appropriate verification code
                            // Use the existing VerificationFunctions.generateVerificationCode with selector object
                            const verificationScript = VerificationFunctions.generateVerificationCode(instructionForGen as any, selectorObj, this);
                            logger.info(`Verification Script: ${verificationScript}`);
                            scripts.push(verificationScript);
                        }
                    }

                    // Get selectors for the element (now filtered)
                    selectors = elementInfo && (elementInfo as any).selectors ? (elementInfo as any).selectors : [];

                    // Use the first selector to generate the verification code
                    verificationCode = VerificationFunctions.generateScriptFromSelector(elementResult, instructionForGen)
                }
                else{
                    // If the locator is xpath, we need to add xpath= prefix to the locator
                    if (locator?.startsWith('/')) {
                        // Update instructionForGen with xpath= prefix
                        instructionForGen.args.push({ key: 'locator', value: `xpath=${locator}` });
                        logger.info(`Updated instructionForGen with xpath= prefix: ${JSON.stringify(instructionForGen)}`);
                    }
                    else{
                        // If it is css escape it using browser context
                        locator = await this.page.evaluate((selector) => CSS.escape(selector), locator);
                        // Update instructionForGen with css= prefix
                        instructionForGen.args.push({ key: 'locator', value: locator });
                    }

                    verificationCode = VerificationFunctions.generateVerificationCode(instructionForGen as any, undefined, this);
                }
            }
            else {
                verificationCode = VerificationFunctions.generateVerificationCode(instructionForGen as any, undefined, this);
            }

            logger.info(`Verification code generated: ${verificationCode}`);

            // Store the verification code
            this.storeExecutedCode(verificationCode);

            // Execute the verification
            try {
                // Create execution function with state context
                const fn = new Function('page', 'expect', 'state', `'use strict'; return (async () => { ${verificationCode} })();`);
                await fn(this.page, expect, this.sharedState);
                
                // Verification passed
                const successMessage = buildDescriptiveVerificationSuccessMessage({
                    instruction: action.instruction,
                });
                logger.info(successMessage);

                logger.info(`Selectors: ${selectors}`);
                logger.info(`Scripts: ${scripts}`);
                 
                return {
                    action: { ...action } as any,
                    success: true,
                    timestamp: Date.now(),
                    playwrightCode: verificationCode,
                    selectors: { selectors },
                    scripts
                };
            } catch (error) {
                if (!(error as any)?.matcherResult) {     // If the error is not an assertion error, throw it
                    throw error;
                }
                // Verification failed
                const errorMessage = buildDescriptiveVerificationErrorMessage({
                    instruction: action.instruction,
                });
                logger.error(errorMessage);
                
                if (failTest) {
                    // If fail_test is true, throw error to fail the test
                    throw new Error(errorMessage);
                } else {
                    logger.info(errorMessage);
                     
                    return {
                        action: { ...action } as any,
                        success: true,
                        error: undefined,
                        warning: errorMessage,
                        timestamp: Date.now(),
                        playwrightCode: verificationCode,
                        selectors: { selectors },
                        scripts
                    };
                }
            }
        } catch (error) {
            logger.error('Verification handler failed', error);
            return {
                action: { ...action } as any,
                success: false,
                error: error instanceof Error ? error.message : 'Unknown error',
                timestamp: Date.now()
            };
        }
    }

}

/**
 * Build a descriptive and user-friendly verification error message
 */
export function buildDescriptiveVerificationErrorMessage(params: {
    instruction: any | null;
}): string {
    let {
        instruction
    } = params;

    // If instruction is provided, use it to get the target, property, check, subProperty, value, expectedResult
    const  target = instruction?.args?.find((arg: any) => arg.key === "target")?.value;
    const property = instruction?.args?.find((arg: any) => arg.key === "property")?.value;
    const check = instruction?.args?.find((arg: any) => arg.key === "check")?.value;
    const subProperty = instruction?.args?.find((arg: any) => arg.key === "subProperty")?.value;
    const value = instruction?.args?.find((arg: any) => arg.key === "value")?.value;
    const expectedResult = instruction?.args?.find((arg: any) => arg.key === "expected_result")?.value;
    const failTest = instruction?.args?.find((arg: any) => arg.key === "fail_test")?.value;
    const locatorType = instruction?.args?.find((arg: any) => arg.key === "locator_type")?.value;
    const locator = instruction?.args?.find((arg: any) => arg.key === "locator")?.value;

    // Determine if this is a negated verification
    const isNegated = expectedResult === 'false';
    
    let message = '';
    
    // Build simple, clear verification description based on property type
    if (target === 'element') {
        switch (property) {
            case 'verify_text':
                if (check === 'is') {
                    message = isNegated 
                        ? `Verification failed: expected text NOT to be "${value}", found "${value}".`
                        : `Verification failed: expected text "${value}", found different text.`;
                } else if (check === 'contains') {
                    message = isNegated
                        ? `Verification failed: expected text NOT to contain "${value}", found "${value}".`
                        : `Verification failed: expected text to contain "${value}", found different text.`;
                }
                break;
                
            case 'verify_class':
                if (check === 'is') {
                    message = isNegated
                        ? `Verification failed: expected class NOT to be "${value}", found "${value}".`
                        : `Verification failed: expected class "${value}", found different class.`;
                } else if (check === 'contains') {
                    message = isNegated
                        ? `Verification failed: expected class NOT to contain "${value}", found "${value}".`
                        : `Verification failed: expected class to contain "${value}", found different class.`;
                }
                break;
                
            case 'verify_attribute':
                if (subProperty) {
                    if (check === 'is') {
                        message = isNegated
                            ? `Verification failed: expected ${subProperty} attribute NOT to be "${value}", found "${value}".`
                            : `Verification failed: expected ${subProperty} attribute "${value}", found different value.`;
                    } else if (check === 'contains') {
                        message = isNegated
                            ? `Verification failed: expected ${subProperty} attribute NOT to contain "${value}", found "${value}".`
                            : `Verification failed: expected ${subProperty} attribute to contain "${value}", found different value.`;
                    }
                }
                break;
                
            case 'verify_count':
                if (check === 'is') {
                    message = isNegated
                        ? `Verification failed: expected count NOT to be ${value}, found ${value}.`
                        : `Verification failed: expected count ${value}, found different count.`;
                } else if (check === 'greater_than') {
                    message = `Verification failed: expected count greater than ${value}, found ${value} or less.`;
                } else if (check === 'less_than') {
                    message = `Verification failed: expected count less than ${value}, found ${value} or more.`;
                }
                break;
                
            case 'verify_value':
                if (check === 'is') {
                    message = isNegated
                        ? `Verification failed: expected value NOT to be "${value}", found "${value}".`
                        : `Verification failed: expected value "${value}", found different value.`;
                } else if (check === 'contains') {
                    message = isNegated
                        ? `Verification failed: expected value NOT to contain "${value}", found "${value}".`
                        : `Verification failed: expected value to contain "${value}", found different value.`;
                }
                break;
                
            case 'verify_css':
                if (subProperty) {
                    if (check === 'is') {
                        message = isNegated
                            ? `Verification failed: expected CSS ${subProperty} NOT to be "${value}", found "${value}".`
                            : `Verification failed: expected CSS ${subProperty} "${value}", found different value.`;
                    } else if (check === 'contains') {
                        message = isNegated
                            ? `Verification failed: expected CSS ${subProperty} NOT to contain "${value}", found "${value}".`
                            : `Verification failed: expected CSS ${subProperty} to contain "${value}", found different value.`;
                    }
                }
                break;
                
            case 'verify_if_visible':
                message = isNegated
                    ? `Verification failed: expected element NOT to be visible, but it was visible.`
                    : `Verification failed: expected element to be visible, but it was not visible.`;
                break;
                
            case 'verify_if_checked':
                message = isNegated
                    ? `Verification failed: expected element NOT to be checked, but it was checked.`
                    : `Verification failed: expected element to be checked, but it was not checked.`;
                break;
                
            case 'verify_if_empty':
                message = isNegated
                    ? `Verification failed: expected element NOT to be empty, but it was empty.`
                    : `Verification failed: expected element to be empty, but it was not empty.`;
                break;
                
            case 'verify_if_in_viewport':
                message = isNegated
                    ? `Verification failed: expected element NOT to be in viewport, but it was in viewport.`
                    : `Verification failed: expected element to be in viewport, but it was not in viewport.`;
                break;
                
            default:
                message = `Verification failed: ${property} ${check} ${value || ''}`;
        }
    } else if (target === 'page') {
        switch (property) {
            case 'title':
                if (check === 'is') {
                    message = isNegated
                        ? `Verification failed: expected page title NOT to be "${value}", found "${value}".`
                        : `Verification failed: expected page title "${value}", found different title.`;
                } else if (check === 'contains') {
                    message = isNegated
                        ? `Verification failed: expected page title NOT to contain "${value}", found "${value}".`
                        : `Verification failed: expected page title to contain "${value}", found different title.`;
                }
                break;
                
            case 'url':
                if (check === 'is') {
                    message = isNegated
                        ? `Verification failed: expected page URL NOT to be "${value}", found "${value}".`
                        : `Verification failed: expected page URL "${value}", found different URL.`;
                } else if (check === 'contains') {
                    message = isNegated
                        ? `Verification failed: expected page URL NOT to contain "${value}", found "${value}".`
                        : `Verification failed: expected page URL to contain "${value}", found different URL.`;
                }
                break;
                
            default:
                message = `Verification failed: page ${property} ${check} ${value || ''}`;
        }
    } else {
        message = `Verification failed: ${target} ${property} ${check} ${value || ''}`;
    }

    // Add simple behavior information
    if (failTest) {
        message += ' Verification failed.';
    } else {
        message += ' Continuing the test';
    }

    return message;
}

/**
 * Build a descriptive and user-friendly verification success message
 */
export function buildDescriptiveVerificationSuccessMessage(params: {
    instruction: any | null;
}): string {
    const {
        instruction
    } = params;

    // If instruction is provided, use it to get the target, property, check, subProperty, value, expectedResult
    const target = instruction?.args?.find((arg: any) => arg.key === "target")?.value;
    const property = instruction?.args?.find((arg: any) => arg.key === "property")?.value;
    const check = instruction?.args?.find((arg: any) => arg.key === "check")?.value;
    const subProperty = instruction?.args?.find((arg: any) => arg.key === "subProperty")?.value;
    const value = instruction?.args?.find((arg: any) => arg.key === "value")?.value;
    const expectedResult = instruction?.args?.find((arg: any) => arg.key === "expected_result")?.value;

    // Determine if this is a negated verification
    const isNegated = expectedResult === false;
    
    let message = '';
    
    // Build simple, clear success description based on property type
    if (target === 'element') {
        switch (property) {
            case 'verify_text':
                if (check === 'is') {
                    message = isNegated 
                        ? `Verification passed: text is NOT "${value}" as expected.`
                        : `Verification passed: text is "${value}" as expected.`;
                } else if (check === 'contains') {
                    message = isNegated
                        ? `Verification passed: text does NOT contain "${value}" as expected.`
                        : `Verification passed: text contains "${value}" as expected.`;
                }
                break;
                
            case 'verify_class':
                if (check === 'is') {
                    message = isNegated
                        ? `Verification passed: class is NOT "${value}" as expected.`
                        : `Verification passed: class is "${value}" as expected.`;
                } else if (check === 'contains') {
                    message = isNegated
                        ? `Verification passed: class does NOT contain "${value}" as expected.`
                        : `Verification passed: class contains "${value}" as expected.`;
                }
                break;
                
            case 'verify_attribute':
                if (subProperty) {
                    if (check === 'is') {
                        message = isNegated
                            ? `Verification passed: ${subProperty} attribute is NOT "${value}" as expected.`
                            : `Verification passed: ${subProperty} attribute is "${value}" as expected.`;
                    } else if (check === 'contains') {
                        message = isNegated
                            ? `Verification passed: ${subProperty} attribute does NOT contain "${value}" as expected.`
                            : `Verification passed: ${subProperty} attribute contains "${value}" as expected.`;
                    }
                }
                break;
                
            case 'verify_count':
                if (check === 'is') {
                    message = isNegated
                        ? `Verification passed: count is NOT ${value} as expected.`
                        : `Verification passed: count is ${value} as expected.`;
                } else if (check === 'greater_than') {
                    message = `Verification passed: count is greater than ${value} as expected.`;
                } else if (check === 'less_than') {
                    message = `Verification passed: count is less than ${value} as expected.`;
                }
                break;
                
            case 'verify_value':
                if (check === 'is') {
                    message = isNegated
                        ? `Verification passed: value is NOT "${value}" as expected.`
                        : `Verification passed: value is "${value}" as expected.`;
                } else if (check === 'contains') {
                    message = isNegated
                        ? `Verification passed: value does NOT contain "${value}" as expected.`
                        : `Verification passed: value contains "${value}" as expected.`;
                }
                break;
                
            case 'verify_css':
                if (subProperty) {
                    if (check === 'is') {
                        message = isNegated
                            ? `Verification passed: CSS ${subProperty} is NOT "${value}" as expected.`
                            : `Verification passed: CSS ${subProperty} is "${value}" as expected.`;
                    } else if (check === 'contains') {
                        message = isNegated
                            ? `Verification passed: CSS ${subProperty} does NOT contain "${value}" as expected.`
                            : `Verification passed: CSS ${subProperty} contains "${value}" as expected.`;
                    }
                }
                break;
                
            case 'verify_if_visible':
                message = isNegated
                    ? `Verification passed: element is NOT visible as expected.`
                    : `Verification passed: element is visible as expected.`;
                break;
                
            case 'verify_if_checked':
                message = isNegated
                    ? `Verification passed: element is NOT checked as expected.`
                    : `Verification passed: element is checked as expected.`;
                break;
                
            case 'verify_if_empty':
                message = isNegated
                    ? `Verification passed: element is NOT empty as expected.`
                    : `Verification passed: element is empty as expected.`;
                break;
                
            case 'verify_if_in_viewport':
                message = isNegated
                    ? `Verification passed: element is NOT in viewport as expected.`
                    : `Verification passed: element is in viewport as expected.`;
                break;
                
            default:
                message = `Verification passed: ${property} ${check} ${value || ''}`;
        }
    } else if (target === 'page') {
        switch (property) {
            case 'title':
                if (check === 'is') {
                    message = isNegated
                        ? `Verification passed: page title is NOT "${value}" as expected.`
                        : `Verification passed: page title is "${value}" as expected.`;
                } else if (check === 'contains') {
                    message = isNegated
                        ? `Verification passed: page title does NOT contain "${value}" as expected.`
                        : `Verification passed: page title contains "${value}" as expected.`;
                }
                break;
                
            case 'url':
                if (check === 'is') {
                    message = isNegated
                        ? `Verification passed: page URL is NOT "${value}" as expected.`
                        : `Verification passed: page URL is "${value}" as expected.`;
                } else if (check === 'contains') {
                    message = isNegated
                        ? `Verification passed: page URL does NOT contain "${value}" as expected.`
                        : `Verification passed: page URL contains "${value}" as expected.`;
                }
                break;
                
            default:
                message = `Verification passed: page ${property} ${check} ${value || ''}`;
        }
    } else {
        message = `Verification passed: ${target} ${property} ${check} ${value || ''}`;
    }

    return message;
}
