import { chromium, firefox, webkit, Browser } from 'playwright';
import { BrowserAgentOptions, BrowserState, InteractableElement, BrowserActionResult } from '../types/browser';
import { Action, ActionResult } from '../types/actions';
import { ActionType } from '../types/actions';
import { AgentState, AgentMemory } from '../types/state';
import { DEFAULT_BROWSER_CONFIG, ACTION_TYPES, TASK_STATUS, DEVICE_TYPES, OPERATING_SYSTEMS, BROWSER_TYPES, DEFAULT_BROWSER_ARGS } from '../config/constants';
import { logger } from '../utils/logger';
import { ActionHandler, buildDescriptiveVerificationSuccessMessage } from './ActionHandler';
import { BrowserContext } from './BrowserContext';
import { LLMInputs } from './LLMInputs';
import { ContainerCommsService } from '../services/ContainerCommsService';
import { InteractableElementsManager } from './InteractableElementsManager';
import { v4 as uuidv4 } from 'uuid';
import * as fs from 'fs';
import * as path from 'path';
import { createGifFromTrace } from '../utils/extractTraceScreenshots';
import { UploadUtils } from '../utils/uploadUtils';
import { substituteVariablesInPlaywrightInstructions } from '../utils/variableUtils';
import assert from 'assert';
import { expect, request } from '@playwright/test';
import { SUPPORTED_AI_ACTIONS } from '../config/constants';
import { buildDescriptiveVerificationErrorMessage } from './ActionHandler';
import { PerformanceMonitoring } from './PerformanceMonitoring';
import { shouldEnablePerformanceMonitoring, extractNavigationUrl } from '../utils/navigationUtils';
import { HtmlCleaner } from './HtmlCleaner';
import { litmusLogger } from '../utils/litmusLogUtils';
import { ScreencastService } from './ScreencastService';


/**
 * Function to create a log instruction from an instruction dictionary.
 */
export function createLogInstructionFromInstructionObject(instructionDict: { [key: string]: any }): string {
    logger.info(`Creating log instruction from instruction object: ${JSON.stringify(instructionDict)}`);
    let instructionStr = instructionDict.action || '';

    // If action type is AI then add prompt to instruction string
    if (SUPPORTED_AI_ACTIONS.includes(instructionDict.action)) {
        instructionStr += ` | ${instructionDict.prompt || ''}`;
    }
    
    for (const arg of instructionDict.args || []) {
        // continue if key is script, file_id, file_url
        if (arg.key === 'script' || arg.key === 'file_id' || arg.key === 'file_url') {
            continue;
        }

        // Special case for handling verification action
        if (arg.key === 'expected_result') {
            arg.value = arg.value ? 'should pass' : 'should fail';
        }

        instructionStr += ` | ${arg.value || ''}`;
    }
    logger.info(`Instruction string: ${instructionStr}`);
    return instructionStr;
}

export class BrowserAgent {
    private browser: Browser | null = null;
    private browserContext: BrowserContext | null = null;
    private state: AgentState;
    private memory: AgentMemory;
    private config: BrowserAgentOptions;
    private actionHandler: ActionHandler | null = null;
    private contextId: string;
    private screenshotDir: string;
    private llmInputs: LLMInputs | null = null;
    private containerCommsService: ContainerCommsService | null = null;
    private elementsManager: InteractableElementsManager;
    private performanceMonitoring: PerformanceMonitoring | null = null;
    private screencastService: ScreencastService | null = null;
    public lastFailureData: { instruction: any; error: string; image: string | null } | null = null;

    constructor(options: Partial<BrowserAgentOptions> = {}) {
        this.config = {
            config: { ...DEFAULT_BROWSER_CONFIG, ...options.config },
            runId: options.runId,
            composeId: options.composeId
        };

        this.state = {
            browserState: {
                urls: { current: '', all: [] },
                activeTab: 0,
                timestamp: Date.now()
            },
            currentInstructionId: '',
            completedInstructions: [],
            errors: [],
            timestamp: Date.now()
        };

        this.memory = {
            instructions: [],
            executionHistory: [],
            playwrightScripts: [],
            errors: []
        };

        this.contextId = uuidv4();
        this.screenshotDir = path.join(__dirname, 'screenshots');
        if (!fs.existsSync(this.screenshotDir)) {
            fs.mkdirSync(this.screenshotDir, { recursive: true });
        }
        
        // Create gifs directory
        const gifsDir = path.join(__dirname, '..', '..', 'gifs');
        if (!fs.existsSync(gifsDir)) {
            fs.mkdirSync(gifsDir, { recursive: true });
        }
        this.containerCommsService = new ContainerCommsService();
        this.elementsManager = InteractableElementsManager.getInstance();
        logger.debug(`Initializing new browser agent with id: ${this.contextId}`);
    }

    /**
     * Initialize the browser and create a new context
     */
    public async initialize(): Promise<void> {
        try {
            logger.info('Initializing browser agent...');
            
            // If using Browserbase, connect to the session first
            if (this.config.config.useBrowserbase) {
                if (!this.config.config.cdpUrl) {
                    throw new Error('CDP URL is required when using Browserbase');
                }

                // Only connect if we don't already have a browser instance
                if (!this.browser) {
                    // Connect to the CDP session
                    this.browser = await chromium.connectOverCDP(this.config.config.cdpUrl);
                    logger.info('Connected to Browserbase session');
                } else {
                    logger.info('Using existing browser connection');
                }

                // Get the first context or create a new one
                const contexts = this.browser.contexts();
                if (contexts.length > 0) {
                    this.browserContext = new BrowserContext(this.browser, this.config.config);
                    await this.browserContext.initialize();
                } else {
                    // Create new context with anti-detection measures
                    this.browserContext = new BrowserContext(this.browser, this.config.config);
                    await this.browserContext.initialize();
                }

                // Get the active page and wait for it to load
                const page = this.browserContext.getActivePage();
                await page.waitForLoadState('networkidle', { timeout: 30000 });
                logger.info('Page loaded successfully');
            } else {
                // Initialize browser with custom fingerprinting based on playwright_config
                this.browser = await this.createBrowserWithFingerprint();

                // Create new context with anti-detection measures
                this.browserContext = new BrowserContext(this.browser, this.config.config);
                await this.browserContext.initialize();

                // Get the active page and wait for it to load
                const page = this.browserContext.getActivePage();
                await page.waitForLoadState('networkidle', { timeout: 30000 });
                logger.info('Page loaded successfully');
            }

            // Create LLMInputs with the active page
            this.llmInputs = new LLMInputs(this.browserContext.getActivePage());

            // Create action handler with the active page, browser context, LLMInputs, ContainerCommsService, and runId
            this.actionHandler = new ActionHandler(this.browserContext.getActivePage(), 'screenshots', this.browserContext, this.llmInputs, this.containerCommsService || undefined, this.config.runId);

            // Create performance monitoring instance
            this.performanceMonitoring = new PerformanceMonitoring(this.browserContext.getActivePage(), this.containerCommsService || undefined, this.config.runId || undefined);

            // Start tracing if configured
            if (this.config.config.tracePath) {
                await this.browserContext.startTracing();
                logger.info('Started browser tracing');
            }

            // Start screencast service if in compose mode with litmus_cloud (not using browserbase)
            // Uses hardcoded port 8080 for testing if wssUrl is not provided
            if (this.config.composeId && !this.config.config.useBrowserbase) {
                try {
                    const page = this.browserContext.getActivePage();
                    // Use provided wssUrl or undefined (will default to ws://localhost:8080 in ScreencastService)
                    this.screencastService = new ScreencastService(
                        page,
                        this.config.composeId,
                        this.config.config.wssUrl || ''
                    );
                    await this.screencastService.start();
                    logger.info('Screencast service started successfully');
                } catch (error) {
                    logger.error(`Failed to start screencast service: ${error instanceof Error ? error.message : String(error)}`);
                    // Don't throw - screencast is optional
                }
            }

            await this.updateState();
            logger.info('Browser agent initialized successfully');
        } catch (error) {
            logger.error('Failed to initialize browser agent:', error);
            throw error;
        }
    }

    /**
     * Create browser with custom fingerprinting based on playwright_config
     */
    private async createBrowserWithFingerprint(): Promise<Browser> {
        const playwrightConfig = this.config.config.playwright_config;
        if (!playwrightConfig) {
            throw new Error('Playwright config is required');
        }

        // Parse the playwright config structure (new format only)
        const deviceType = playwrightConfig.device?.type;
        const operatingSystem = playwrightConfig.device?.device_config?.os;
        const browserType = playwrightConfig.browser;
        const viewportWidth = playwrightConfig.viewport?.width;
        const viewportHeight = playwrightConfig.viewport?.height;
        const devicePixelRatio = playwrightConfig.device_pixel_ratio;

        // Log the fingerprint configuration
        logger.info('=== Playwright Browser Fingerprint Configuration ===');
        logger.info(`Device: ${deviceType}`);
        logger.info(`OS: ${operatingSystem}`);
        logger.info(`Browser: ${browserType}`);
        logger.info(`Viewport: ${viewportWidth}x${viewportHeight}`);
        logger.info(`DPR: ${devicePixelRatio}`);
        logger.info('==================================================');

        // Determine if mobile
        const isMobile = deviceType === DEVICE_TYPES.MOBILE;

        // Select browser based on playwright_config
        let browser: Browser;
        
        // Create browser-specific launch options
        const baseLaunchOptions = {
            headless: this.config.config.headless
        };
        
        if (browserType === BROWSER_TYPES.FIREFOX) {
            // Firefox-specific launch options
            const firefoxOptions = {
                ...baseLaunchOptions,
                args: [
                    '--no-sandbox',
                    '--disable-setuid-sandbox'
                ]
            };
            browser = await firefox.launch(firefoxOptions);
        } else if (browserType === BROWSER_TYPES.SAFARI) {
            // WebKit-specific launch options (no Chromium args)
            const webkitOptions = {
                ...baseLaunchOptions
                // WebKit doesn't support Chromium-specific arguments
            };
            browser = await webkit.launch(webkitOptions);
        } else if (browserType === BROWSER_TYPES.EDGE) {
            // Edge as Chromium with edge channel
            const edgeOptions = {
                ...baseLaunchOptions,
                channel: 'msedge',
                args: DEFAULT_BROWSER_ARGS
            };
            browser = await chromium.launch(edgeOptions);
        } else {
            // Default to chromium (chrome) with Chromium-specific args
            const chromiumOptions = {
                ...baseLaunchOptions,
                args: DEFAULT_BROWSER_ARGS
            };
            browser = await chromium.launch(chromiumOptions);
        }

        return browser;
    }

    /**
     * Execute an action on the page
     */
    public async executeAction(action: Action): Promise<ActionResult> {
        try {
            if (!this.browserContext || !this.actionHandler || !this.llmInputs) {
                throw new Error('Browser context not initialized');
            }

            logger.info('Executing action:', action);

            // Execute the action
            let result: ActionResult;
            switch (action.type) {
                case ACTION_TYPES.CLICK:
                    result = await this.actionHandler.handleClick(action);
                    break;
                case ACTION_TYPES.INPUT:
                    result = await this.actionHandler.handleInput(action);  
                    break;
                case ACTION_TYPES.SELECT:
                    result = await this.actionHandler.handleSelect(action);
                    break;
                case ACTION_TYPES.VERIFY:
                    result = await this.actionHandler.handleVerify(action);
                    break;
                case ACTION_TYPES.ASSERT:
                    result = await this.actionHandler.handleAiAssert(action);
                    break;
                case ACTION_TYPES.SWITCH_TAB:
                    result = await this.actionHandler.handleSwitchTab(action);
                    break;
                case ACTION_TYPES.HOVER:
                    result = await this.actionHandler.handleHover(action);
                    break;
                case ACTION_TYPES.SCROLL:
                    result = await this.actionHandler.handleScroll(action);
                    break;
                case ACTION_TYPES.FILE_UPLOAD:
                    result = await this.actionHandler.handleUploadFile(action);
                    break;
                case ACTION_TYPES.SCRIPT:
                    result = await this.actionHandler.handleAiScript(action);
                    break;
                case ACTION_TYPES.GO_TO_URL:
                    result = await this.actionHandler.handleGoToUrl(action, this.state.currentInstructionId);
                    break;
                case ACTION_TYPES.GO_BACK:
                    result = await this.actionHandler.handleGoBack(action);
                    break;
                case ACTION_TYPES.WAIT_TIME:
                    result = await this.actionHandler.handleWaitTime(action);
                    break;
                case ACTION_TYPES.OPEN_TAB:
                    result = await this.actionHandler.handleOpenTab(action, this.state.currentInstructionId);
                    break;
                case ACTION_TYPES.RUN_SCRIPT:
                    result = await this.actionHandler.handleRunScript(action);
                    break;
                case ACTION_TYPES.SET_STATE_VARIABLE:
                    // @ts-ignore ensure handler exists
                    result = await this.actionHandler.handleSetStateVariable(action);
                    break;
                case ACTION_TYPES.VERIFICATION:
                    result = await this.actionHandler.handleVerification(action);             // Need to add
                    break;
                case ACTION_TYPES.PAGE_RELOAD:
                    result = await this.actionHandler.handlePageReload(action);
                    break;
                case ACTION_TYPES.KEY_PRESS:
                    result = await this.actionHandler.handleKeyPress(action);
                    break;
                case ACTION_TYPES.API_INTERCEPT:
                    result = await this.actionHandler.handleApiIntercept(action);
                    break;
                case ACTION_TYPES.REMOVE_API_HANDLERS:
                    result = await this.actionHandler.handleRemoveApiHandlers(action);
                    break;
                case ACTION_TYPES.API_MOCK:
                    result = await this.actionHandler.handleApiMock(action);
                    break;
                default:
                    throw new Error(`Unknown action type: ${(action as Action).type}`);
            }

            // Scripts are now generated in ActionHandler before action execution



            // Add the action result to memory
            this.addToMemory(result);

            logger.info('Action result:', result);
            return result;
        } catch (error) {
            logger.error('Failed to execute action', error);
            this.state.errors.push({
                name: error instanceof Error ? error.name : 'Error',
                message: error instanceof Error ? error.message : String(error),
                stack: error instanceof Error ? error.stack : undefined
            });
            const errorResult = {
                action,
                success: false,
                error: error instanceof Error ? error.message : 'Unknown error',
                timestamp: Date.now()
            };
            // Add error result to memory
            this.addToMemory(errorResult);
            return errorResult;
        }
    }

    /**
     * Get the current browser state
     */
    public getState(): AgentState {
        return this.state;
    }

    /**
     * Get the agent memory
     */
    public getMemory(): AgentMemory {
        return this.memory;
    }

    /**
     * Clean up browser resources
     */
    public async cleanup(): Promise<void> {
        try {
            // Stop screencast service if running
            if (this.screencastService) {
                try {
                    await this.screencastService.stop();
                    logger.info('Screencast service stopped');
                } catch (error) {
                    logger.error(`Error stopping screencast service: ${error instanceof Error ? error.message : String(error)}`);
                }
            }

            if (this.browserContext && this.config.config.tracePath) {
                const tracePath = `./traces/browser-${Date.now()}.zip`;
                await this.browserContext.stopTracing(tracePath);
                logger.info(`Saved browser trace to ${tracePath}`);

                // Extract screenshots from the trace
                const screenshotsDir = path.join('./screenshots', `browser-${Date.now()}`);
                await createGifFromTrace(tracePath, screenshotsDir);
                logger.info(`Extracted screenshots to ${screenshotsDir}`);
            }

            if (this.browserContext) {
                await this.browserContext.close();
            }

            if (this.browser) {
                await this.browser.close();
            }

            logger.info('Browser agent cleaned up successfully');
        } catch (error) {
            logger.error('Failed to cleanup browser agent', error);
            this.state.errors.push({
                name: error instanceof Error ? error.name : 'Error',
                message: error instanceof Error ? error.message : String(error),
                stack: error instanceof Error ? error.stack : undefined
            });
            throw error;
        }
    }

    /**
     * Update the current state of the browser
     */
    private async updateState(): Promise<void> {
        if (!this.browserContext || !this.llmInputs) {
            throw new Error('Browser context not initialized');
        }

        const page = this.browserContext.getActivePage();
        this.state.browserState = {
            urls: {
                current: page.url(),
                all: this.browserContext.getPages().map(p => p.url())
            },
            activeTab: this.browserContext.getPages().indexOf(page),
            timestamp: Date.now()
        };

        this.state.timestamp = Date.now();
    }

    public setCurrentInstructionId(instructionId: string): void {
        this.state.currentInstructionId = instructionId;
    }

    private addToMemory(result: ActionResult): void {
        // Get Playwright code for the current action
        let playwrightCode: string[] = [];
        if (this.actionHandler) {
            playwrightCode = this.actionHandler.getCurrentActionCode();
            // Clear the current action code after getting it
            this.actionHandler.clearCurrentActionCode();
        }

        // Add to execution history
        this.memory.executionHistory.push({
            instructionId: this.state.currentInstructionId,
            action: result.action,
            result: {
                ...result,
                playwrightCode: playwrightCode.join('\n') // Join all code with newlines
            },
            timestamp: Date.now()
        });

        // Add to playwright scripts
        playwrightCode.forEach(script => {
            this.memory.playwrightScripts.push({
                instructionId: this.state.currentInstructionId,
                script: script,
                timestamp: Date.now()
            });
        });
    }

    /**
     * Get the current page URL
     */
    public async getCurrentUrl(): Promise<string> {
        if (!this.browserContext) throw new Error('Browser context not initialized');
        return this.browserContext.getActivePage().url();
    }

    /**
     * Initialize shared state in ActionHandler
     */
    public initializeSharedState(): void {
        if (this.actionHandler) {
            this.actionHandler.setSharedState({});
        }
    }

    /**
     * Get the ActionHandler instance
     */
    public getActionHandler(): ActionHandler | null {
        return this.actionHandler;
    }

    /**
     * Execute a single command with proper error handling
     * @param command The command to execute
     * @param key The command key for logging
     * @param instruction The instruction object for logging
     * @param page The Playwright page object
     * @returns Promise that resolves when command is executed successfully
     */
    private async executeCommand(
        command: string, 
        key: string, 
        instruction: { [key: string]: any } | undefined, 
        page: any
    ): Promise<void> {
        let modifiedCommand = command;
        
        // Check if selector is XPath and convert if needed
        const xpathMatch = command.match(/page\.locator\(['"]([^'"]*)['"]\)/);
        if (xpathMatch) {
            const selector = xpathMatch[1];
            if (selector.startsWith('/html') || selector.startsWith('//')) {
                modifiedCommand = command.replace(
                    /page\.locator\(['"]([^'"]*)['"]\)/g,
                    'page.locator("xpath=$1")'
                );
            }
        }
       
        logger.info(`Executing command ${key}: ${command}`);

        // Add log to Redis
        if (this.config.runId && this.containerCommsService) {
            await this.containerCommsService.addLog(this.config.runId, {
                info: `Executing command ${key}: ${command}`,
                timestamp: new Date().toISOString(),
                instructionId: String(instruction?.id)
            });
        }

        // Check if performance monitoring should be enabled for this command
        if (shouldEnablePerformanceMonitoring(modifiedCommand)) {
            // Set up performance monitoring before navigation
            if (this.performanceMonitoring) {
                await this.performanceMonitoring.setupPerformanceMonitoring();
            }
        }

        // Create litmus_log function for logging to Redis in script mode
        // Get the current instruction ID so logs appear under the correct instruction
        const currentInstructionId = instruction?.id ? String(instruction.id) : undefined;
        
        // Track pending log promises to ensure they complete
        const pendingLogs: Promise<void>[] = [];
        
        const litmusLog = litmusLogger(
            this.containerCommsService,
            this.config.runId,
            currentInstructionId,
            pendingLogs
        );

        // Execute the command using Function constructor to support expect statements and litmus_log
        // eslint-disable-next-line no-eval
        const fn = new Function('page', 'browser', 'context', 'assert', 'expect', 'request', 'state', 'litmus_log', `'use strict'; return (async () => { ${modifiedCommand} })();`);
        await fn(page, page.context(), page.context(), assert, expect, request, this.actionHandler?.getSharedState() || {}, litmusLog);
        
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

        // Check if the instruction is tab-related and update BrowserContext accordingly
        if (instruction && (instruction.action === ACTION_TYPES.OPEN_TAB || instruction.action === ACTION_TYPES.SWITCH_TAB)) {
            await this.updateBrowserContextAfterTabAction(instruction, page);
        }
        
        // Collect and log performance metrics if this was a navigation command
        // Do this AFTER tab management to ensure we're monitoring the correct page
        if (shouldEnablePerformanceMonitoring(modifiedCommand) && this.performanceMonitoring) {
            // Extract URL using utility function
            const url = extractNavigationUrl(modifiedCommand);
            
            if (url) {
                try {
                    // Wait for page to be fully loaded with timeout
                    await this.performanceMonitoring.waitForPageLoadWithTimeout(page, 15000);
                    
                    // Collect performance metrics with timeout protection
                    const metrics = await this.performanceMonitoring.collectPerformanceMetricsWithTimeout(15000);
                    
                    // Log performance metrics
                    await this.performanceMonitoring.logPerformanceMetrics(metrics, url, key);
                } catch (error) {
                    logger.error('Failed to collect performance metrics:', error);
                }
            }
        }
        
        // Log successful execution
        logger.info(`Executed command ${key}: ${modifiedCommand}`);
        
        // Add log to Redis if testRunId is available
        if (this.config.runId && this.containerCommsService) {
            await this.containerCommsService.addLog(this.config.runId, {
                info: `Execution complete`,
                timestamp: new Date().toISOString(),
                instructionId: String(instruction?.id)
            });
        }
        
        // Wait between commands if configured
        if (this.config.config.waitBetweenActions > 0) {
            await new Promise(resolve => setTimeout(resolve, this.config.config.waitBetweenActions));
        }
    }

    /**
     * Execute a script with test-level retry logic
     * @param script Object containing Playwright commands to execute, with instruction IDs as keys
     * @param instructions Optional array of instruction objects for logging
     * @param maxRetries Maximum number of retries for the entire script (default: 3)
     * @returns Promise that resolves with execution result
     */
    private async executeScriptWithRetries(
        script: { [key: string]: string[] }, 
        instructions?: { [key: string]: any }[],
        maxRetries: number = 0
    ): Promise<{ success: boolean; retries: number; error?: string }> {
        let retries = 0;
        let lastError: string | undefined;
        let currentInstructionForFailure: any = undefined;

        while (retries <= maxRetries) {
            try {
                // Iterate through instructions array
                for (const instruction of instructions || []) {
                    currentInstructionForFailure = instruction;
                    const instructionId = instruction.id;
                    const commands = script[instructionId];
                    
                    if (!commands) {
                        logger.warn(`No commands found for instruction ID: ${instructionId}`);
                        continue;
                    }

                    // Start a new trace group for each instruction
                    await this.browserContext!.startInstructionTrace(instruction);

                    logger.info(`instruction: ${JSON.stringify(instruction)}`);
                    logger.info(`instructionId: ${instructionId}`);

                    // Add log to Redis
                    if (this.config.runId && this.containerCommsService) {
                        await this.containerCommsService.addLog(this.config.runId, {
                            info: '',
                            timestamp: new Date().toISOString(),
                            instruction: instruction,
                            instructionId: String(instructionId)
                        });
                    }

                    try {
                        for (const command of commands) {
                            try {
                                // Get the current active page for each command to ensure we're always using the latest page
                            const currentPage = this.browserContext!.getActivePage();
                            logger.info(`Executing command on page: ${currentPage.url()}`);
                            await this.executeCommand(command, instructionId, instruction, currentPage);
                            } catch (error) {
                                // Check if this is an verification error and if fail_test is false
                                if (instruction.action && instruction.action === ACTION_TYPES.VERIFICATION && (error as any)?.matcherResult) {

                                    const warningMessage = buildDescriptiveVerificationErrorMessage({instruction});
                                    // If fail_test = false, add woraning message to container service
                                    if(!instruction.args?.find((arg: any) => arg.key === "fail_test")?.value){
                                    
                                        // Log verification failed but continuing execution
                                        logger.warn(`Verification failed for instruction ${instructionId}, but continuing execution due to fail_test=false`);
                                        
                                        // Add warning log to Redis
                                        if (this.config.runId && this.containerCommsService) {
                                            // build warning message
                                            logger.warn(warningMessage);
                                            await this.containerCommsService.addLog(this.config.runId, {
                                                warning: warningMessage,
                                                timestamp: new Date().toISOString(),
                                                instructionId: instructionId
                                            });
                                        }
                                        
                                        // Continue with next command instead of failing
                                        continue;
                                    }

                                    else {
                                        // Add Error to container service
                                        if (this.config.runId && this.containerCommsService) {
                                            await this.containerCommsService.addLog(this.config.runId, {
                                                error: warningMessage,
                                                timestamp: new Date().toISOString(),
                                                instructionId: instructionId
                                            });
                                        }

                                        throw new Error(warningMessage);
                                    }
                                }

                                // For non-verification errors or when fail_test is true, re-throw the error
                                throw error;
                            }
                        }
                    } finally {
                        // End the trace group for this instruction
                        await this.browserContext!.endInstructionTrace();
                        logger.info(`Ended trace group for instruction ${instructionId}`);
                    }
                }

                // If we reach here, all commands executed successfully
                return { success: true, retries };

            } catch (error) {
                lastError = error instanceof Error ? error.message : String(error);
                retries++;

                if (retries <= maxRetries) {
                    logger.warn(`Script execution failed (attempt ${retries}/${maxRetries + 1}): ${lastError}`);
                    logger.info(`Retrying entire script from beginning...`);
                    
                    // Add retry log to Redis
                    if (this.config.runId && this.containerCommsService) {
                        await this.containerCommsService.addLog(this.config.runId, {
                            info: `Retrying entire script from beginning (attempt ${retries}/${maxRetries + 1})`,
                            timestamp: new Date().toISOString()
                        });

                        continue;
                    }

                } else {
                    logger.error(`Script execution failed after ${maxRetries + 1} attempts: ${lastError}`);
                    
                    // Capture failure data (screenshot, error, instruction) for triage context
                    try {
                        let screenshotBase64: string | null = null;
                        const page = this.browserContext?.getActivePage();
                        if (page) {
                            const screenshotBuffer = await page.screenshot({ type: 'png', fullPage: false });
                            screenshotBase64 = screenshotBuffer.toString('base64');
                        }
                        this.lastFailureData = {
                            instruction: currentInstructionForFailure,
                            error: lastError || 'Unknown error',
                            image: screenshotBase64
                        };
                    } catch (capErr) {
                        logger.error('Failed to capture failure screenshot for triage context:', capErr);
                        this.lastFailureData = {
                            instruction: currentInstructionForFailure,
                            error: lastError || 'Unknown error',
                            image: null
                        };
                    }

                    // Add final failure log to Redis
                    if (this.config.runId && this.containerCommsService) {
                        await this.containerCommsService.addLog(this.config.runId, {
                            error: `Script execution failed after ${maxRetries + 1} attempts: ${lastError}`,
                            timestamp: new Date().toISOString()
                        });
                    }
                }

                return { success: false, retries, error: lastError };
            }
        }

        return { success: false, retries, error: lastError };
    }

    /**
     * Run a sequence of Playwright commands with logging and test-level retries
     * @param script Object containing Playwright commands to execute, keyed by instruction id
     * @param instructions Optional array of instruction objects for logging
     * @param maxRetries Maximum number of retries for the entire script (default: 3)
     */
    public async runScript(
        script: { [key: string]: string[] }, 
        instructions?: { [key: string]: any }[], 
        maxRetries: number = 0,
        variablesDict?: { 
            data_driven_variables?: { [key: string]: string },
            environment_variables?: { [key: string]: string }
        }
    ): Promise<{ success: boolean; retries: number; error?: string }> {
        if (!this.browserContext) {
            throw new Error('Browser context not initialized');
        }

        logger.info(`Running script: ${JSON.stringify(script)}`);

        // Apply variable substitution if variablesDict is provided
        let processedScript = script;
        if (variablesDict) {
            const dataDrivenVariables = variablesDict.data_driven_variables || {};
            const environmentVariables = variablesDict.environment_variables || {};
            
            // Only apply substitution if we have variables to substitute
            if (Object.keys(dataDrivenVariables).length > 0 || Object.keys(environmentVariables).length > 0) {
                logger.info(`Applying variable substitution with data-driven variables: ${JSON.stringify(dataDrivenVariables)}`);
                logger.info(`Applying variable substitution with environment variables: ${JSON.stringify(environmentVariables)}`);
                processedScript = substituteVariablesInPlaywrightInstructions(script, dataDrivenVariables, environmentVariables);
                logger.info(`Script after variable substitution: ${JSON.stringify(processedScript)}`);
            }
        }

        // Execute script with retry logic
        const result = await this.executeScriptWithRetries(processedScript, instructions, maxRetries);

        return result;
    }

    public getPlaywrightActions(): { [key: string]: string[] } {
        const actionsByInstruction: { [key: string]: string[] } = {};
        this.memory.playwrightScripts.forEach(script => {
            if (!actionsByInstruction[script.instructionId]) {
                actionsByInstruction[script.instructionId] = [];
            }
            actionsByInstruction[script.instructionId].push(script.script);
        });
        return actionsByInstruction;
    }

    public getPlaywrightActionsForInstruction(instructionId: string): string[] {
        return this.memory.playwrightScripts
            .filter(script => script.instructionId === instructionId)
            .map(script => script.script);
    }

    /**
     * Handle post-execution tasks for triage mode (GIF and trace URL creation)
     * @param runId The run ID for file naming and storage
     * @returns Object containing gifUrl and traceUrl
     */
    public async handleTriagePostExecution(runId: string): Promise<{ gifUrl: string; traceUrl: string | null }> {
        if (!this.browserContext) {
            throw new Error('Browser context not initialized');
        }

        let gifUrl = '';
        let traceUrl: string | null = null;

        try {
            // End tracing here
            const tracePath = `./traces/${runId}.zip`;
            await this.browserContext.stopTracing(tracePath);
            logger.info(`Saved browser trace to ${tracePath}`);

            const uploadUtils = UploadUtils.getInstance();

            // Extract screenshots from the trace and create gif
            try {
                const gifPath = `./gifs/${runId}.gif`;
                await createGifFromTrace(tracePath, gifPath);
                logger.info(`Extracted gif to ${gifPath}`);

                // Upload gif to storage
                const gifResult = await uploadUtils.uploadGif(runId, gifPath);
                gifUrl = gifResult.success ? gifResult.url : '';
                logger.info(`Uploaded browser gif to ${gifUrl}`);
            } catch (gifError) {
                const errorMessage = `Failed to create or upload gif: ${gifError instanceof Error ? gifError.message : String(gifError)}`;
                logger.error(errorMessage);
                
                // Add error to Redis
                if (this.config.runId && this.containerCommsService) {
                    await this.containerCommsService.addLog(this.config.runId, {
                        error: errorMessage,
                        timestamp: new Date().toISOString()
                    });
                }
            }

            // Upload trace to storage
            try {
                const traceResult = await uploadUtils.uploadTrace(runId, tracePath);
                traceUrl = traceResult.success ? traceResult.url : null;
                logger.info(`Uploaded browser trace to ${traceUrl}`);
            } catch (traceError) {
                const errorMessage = `Failed to upload trace: ${traceError instanceof Error ? traceError.message : String(traceError)}`;
                logger.error(errorMessage);
                
                // Add error to Redis
                if (this.config.runId && this.containerCommsService) {
                    await this.containerCommsService.addLog(this.config.runId, {
                        error: errorMessage,
                        timestamp: new Date().toISOString()
                    });
                }
            }

        } catch (error) {
            const errorMessage = `Failed to handle triage post-execution: ${error instanceof Error ? error.message : String(error)}`;
            logger.error(errorMessage);
            
            // Add error to Redis
            if (this.config.runId && this.containerCommsService) {
                await this.containerCommsService.addLog(this.config.runId, {
                    error: errorMessage,
                    timestamp: new Date().toISOString()
                });
            }
        }

        return { gifUrl, traceUrl };
    }

    public clearPlaywrightScripts(): void {
        this.memory = {
            instructions: [],
            executionHistory: [],
            playwrightScripts: [],
            errors: []
        };
    }

    public clearPlaywrightScriptsForInstruction(instructionId: string): void {
        this.memory.playwrightScripts = this.memory.playwrightScripts.filter(script => script.instructionId !== instructionId);
    }


    /**
     * Get the original instruction from the action handler (for debugging)
     */
    public getOriginalInstruction(): any {
        return this.actionHandler?.getOriginalInstruction();
    }

    /**
     * Set the variables dictionary in the action handler for script substitution
     */
    public setVariablesDict(variablesDict: { 
        data_driven_variables?: { [key: string]: string },
        environment_variables?: { [key: string]: string }
    }) {
        this.actionHandler?.setVariablesDict(variablesDict);
    }

    /**
     * Clear browser data while keeping the session alive
     */
    public async clearBrowserData(): Promise<void> {
        if (!this.browserContext) throw new Error('Browser context not initialized');
        await this.browserContext.clearBrowserData();
    }

    /**
     * Clear all browser data comprehensively and reload pages
     */
    public async clearAllData(): Promise<void> {
        if (!this.browserContext) throw new Error('Browser context not initialized');
        await this.browserContext.clearAllData();
    }

    /**
     * Get the current page content
     */
    public async getPageContent(): Promise<string> {
        if (!this.browserContext) {
            throw new Error('Browser context not initialized');
        }

        const page = this.browserContext.getActivePage();
        return await page.content();
    }

    /**
     * Get the current page content cleaned (without head, scripts, styles, etc.)
     */
    public async getCleanedPageContent(): Promise<string> {
        if (!this.browserContext) {
            throw new Error('Browser context not initialized');
        }

        const page = this.browserContext.getActivePage();
        const htmlCleaner = new HtmlCleaner();
        return await htmlCleaner.getCleanedPageHtml(page);
    }

    /**
     * Get the browser context
     */
    public getBrowserContext(): BrowserContext | null {
        return this.browserContext;
    }

    /**
     * Get the LLMInputs instance
     */
    public getLLMInputs(): LLMInputs | null {
        return this.llmInputs;
    }

    /**
     * Update BrowserContext after executing tab-related actions
     * @param instruction The instruction that was executed
     * @param currentPage The page that was used for execution
     */
    private async updateBrowserContextAfterTabAction(instruction: { [key: string]: any }, currentPage: any): Promise<void> {
        if (!this.browserContext) {
            return;
        }

        if (instruction.action === ACTION_TYPES.OPEN_TAB) {
            // For open_tab, find the page with the target URL to avoid race conditions
            const targetUrl = instruction.args?.find((arg: any) => arg.key === 'url')?.value;
            if (targetUrl) {
                const allPages = currentPage.context().pages();
                const targetPage = allPages.find(p => p.url() === targetUrl);
                
                if (targetPage && targetPage !== currentPage) {
                    // Update BrowserContext to use the target page
                    await this.browserContext.setActivePage(targetPage);
                    logger.info(`Updated BrowserContext active page to: ${targetPage.url()}`);
                    
                    // Update PerformanceMonitoring with new page reference
                    if (this.performanceMonitoring) {
                        this.performanceMonitoring = new PerformanceMonitoring(targetPage, this.containerCommsService || undefined, this.config.runId || undefined);
                        logger.info(`Updated PerformanceMonitoring page reference to: ${targetPage.url()}`);
                    }
                }
            }
        }
        else if (instruction.action === ACTION_TYPES.SWITCH_TAB) {
            // For switch_tab, find the page with the target URL
            const targetUrl = instruction.args?.find((arg: any) => arg.key === 'url')?.value;
            if (targetUrl) {
                const allPages = currentPage.context().pages();
                const targetPage = allPages.find(p => p.url() === targetUrl);
                
                if (targetPage && targetPage !== currentPage) {
                    // Update BrowserContext to use the target page
                    await this.browserContext.setActivePage(targetPage);
                    logger.info(`Updated BrowserContext active page to: ${targetPage.url()}`);
                    
                    // Update PerformanceMonitoring with new page reference
                    if (this.performanceMonitoring) {
                        this.performanceMonitoring = new PerformanceMonitoring(targetPage, this.containerCommsService || undefined, this.config.runId || undefined);
                        logger.info(`Updated PerformanceMonitoring page reference to: ${targetPage.url()}`);
                    }
                }
            }
        }
    }


}
