import { config } from 'dotenv';
import { resolve } from 'path';

// Load environment variables from .env file
config({ path: resolve(__dirname, '../../../.env') });

import { BrowserAgent } from '../BrowserAgent';
import { ACTION_TYPES } from '../../config/constants';
import { Action } from '../../types/actions';
import { logger } from '../../utils/logger';
import * as fs from 'fs';
import * as path from 'path';
import { BrowserConfig } from '../../types/browser';

// Add custom serializer for Jest
expect.addSnapshotSerializer({
    test: (val) => {
        return val && typeof val === 'object' && 'req' in val && 'res' in val;
    },
    print: () => '[Circular Object]'
});

// Helper function to sanitize objects for logging
// function sanitizeForLogging(obj: any): any {
//     if (obj === null || typeof obj !== 'object') {
//         return obj;
//     }

//     if (Array.isArray(obj)) {
//         return obj.map(sanitizeForLogging);
//     }

//     const sanitized: any = {};
//     for (const [key, value] of Object.entries(obj)) {
//         if (key === 'req' || key === 'res' || key === 'socket') {
//             sanitized[key] = '[Circular]';
//         } else if (typeof value === 'object' && value !== null) {
//             try {
//                 JSON.stringify(value);
//                 sanitized[key] = sanitizeForLogging(value);
//             } catch (e) {
//                 sanitized[key] = '[Object]';
//             }
//         } else {
//             sanitized[key] = value;
//         }
//     }
//     return sanitized;
// }

describe('BrowserAgent', () => {
    let agent: BrowserAgent;


    beforeAll(() => {
        // Ensure environment variables are set
        if (!process.env.BROWSERBASE_API_KEY || !process.env.BROWSERBASE_PROJECT_ID) {
            throw new Error('BROWSERBASE_API_KEY and BROWSERBASE_PROJECT_ID must be set');
        }
    });

    // beforeAll(async () => {
    //     // Create screenshots directory if it doesn't exist
    //     const screenshotDir = path.join(__dirname, 'screenshots');
    //     if (!fs.existsSync(screenshotDir)) {
    //         fs.mkdirSync(screenshotDir, { recursive: true });
    //     }

    //     logger.info('Starting browser initialization...');
    //     // logger.info('Browserbase API Key:', process.env.BROWSERBASE_API_KEY ? 'Set' : 'Not set');
    //     // logger.info('Browserbase Project ID:', process.env.BROWSERBASE_PROJECT_ID ? 'Set' : 'Not set');

    //     const config: BrowserConfig = {
    //         headless: false,
    //         viewport: {
    //             width: 1280,
    //             height: 720
    //         },
    //         timeout: 30000, // Increased timeout
    //         retryAttempts: 3,
    //         waitBetweenActions: 1000,
    //         screenshotBeforeAction: true,
    //         screenshotAfterAction: true,
    //         useBrowserbase: true
    //     };

    //     try {
    //         agent = new BrowserAgent({
    //             config,
    //             testRunId: 'test-' + Date.now()
    //         });
    //         logger.info('BrowserAgent created, initializing...');
    //         await agent.initialize();
    //         logger.info('BrowserAgent initialized successfully');
    //     } catch (error) {
    //         logger.error('Failed to initialize browser:', error);
    //         throw error;
    //     }
    // }, 120000); 
    
    // Increased timeout to 2 minutes

    // afterAll(async () => {
    //     await agent?.cleanup();
    // });

    // it('should initialize browser agent', async () => {
    //     expect(agent.getState()).toBeDefined();
    // });

    // it('should execute click action', async () => {
    //     const result = await agent.executeAction({
    //         type: ACTION_TYPES.CLICK,
    //         target: 'button.submit'
    //     });
    //     expect(result.success).toBeDefined();
    // });

    // it('should execute input action', async () => {
    //     const result = await agent.executeAction({
    //         type: ACTION_TYPES.INPUT,
    //         target: 'input.search',
    //         value: 'test query'
    //     });
    //     expect(result.success).toBeDefined();
    // });


    // it('should create trace files when tracing is enabled', async () => {
    //     // Initialize agent with tracing enabled
    //     agent = new BrowserAgent({
    //         config: {
    //             headless: false,
    //             viewport: { width: 1280, height: 720 },
    //             timeout: 30000,
    //             retryAttempts: 3,
    //             waitBetweenActions: 1000,
    //             screenshotBeforeAction: true,
    //             screenshotAfterAction: true,
    //             tracePath: './traces'
    //         },
    //         testRunId: 'test-' + Date.now()
    //     });
    //     await agent.initialize();

    //     // Start tracing
    //     const instructionId = 'test-instruction';
    //     await agent.startTrace(instructionId);

    //     // Execute some actions
    //     await agent.executeAction({
    //         type: ACTION_TYPES.GO_TO_URL,
    //         url: 'https://example.com'
    //     });

    //     // End tracing
    //     await agent.endTrace();

    //     // Verify trace file exists
    //     const traceFile = path.resolve('./traces', `${instructionId}.zip`);
    //     expect(fs.existsSync(traceFile)).toBe(true);

    //     // Clean up
    //     await agent.cleanup();
    // }, 60000);

    // it('should go to Google, search Automation Exercise, and navigate to the site', async () => {
    //     // 1. Go to Google
    //     await agent.executeAction({
    //         type: ACTION_TYPES.GO_TO_URL,
    //         url: 'https://www.google.com'
    //     });
    //     await agent.executeAction({
    //         type: ACTION_TYPES.WAIT,
    //         timeout: 2000
    //     });

    //     // 2. Type 'Automation Exercise' in the search box
    //     await agent.executeAction({
    //         type: ACTION_TYPES.INPUT,
    //         target: 'textarea[name="q"]', // Google now uses textarea instead of input
    //         value: 'Automation Exercise'
    //     });

    //     // 3. Press Enter to search
    //     await agent.executeAction({
    //         type: ACTION_TYPES.WAIT,
    //         timeout: 1000
    //     });
    //     await agent.executeAction({
    //         type: ACTION_TYPES.INPUT,
    //         target: 'textarea[name="q"]',
    //         value: 'Automation Exercise\n'
    //     });

    //     // 4. Wait for search results
    //     await agent.executeAction({
    //         type: ACTION_TYPES.WAIT,
    //         timeout: 3000
    //     });

    //     // 5. Click the Automation Exercise link
    //     await agent.executeAction({
    //         type: ACTION_TYPES.CLICK,
    //         target: 'a[href*="automationexercise.com"]'
    //     });

    //     // 6. Wait for navigation
    //     await agent.executeAction({
    //         type: ACTION_TYPES.WAIT,
    //         timeout: 5000
    //     });

    //     // 7. Verify navigation
    //     const url = await agent.getCurrentUrl();
    //     expect(url).toContain('automationexercise.com');
    // });

    // it('should execute AI action and show bounding boxes', async () => {
    //     // Navigate to test page
    //     await agent.executeAction({
    //         type: ACTION_TYPES.GO_TO_URL,
    //         url: testUrl
    //     });
    //     logger.info('Navigated to test page');

    //     // Create a click action
    //     const action: Action = {
    //         type: 'click',
    //         target: 'a[href="https://www.iana.org/domains/example"]',
    //         index: 0
    //     };

    //     // Execute the action
    //     const result = await agent.executeAction(action);
    //     logger.info('Action result:', sanitizeForLogging(result));

    //     // Verify the action was successful
    //     expect(result.success).toBe(true);

    //     // Get the current state
    //     const state = agent.getState();
    //     logger.info('Current state:', sanitizeForLogging(state));

    //     // Verify we have interactable elements
    //     expect(state.interactableElements.length).toBeGreaterThan(0);
    //     logger.info(`Found ${state.interactableElements.length} interactable elements`);

    //     // Log details of each element
    //     state.interactableElements.forEach((element, index) => {
    //         logger.info(`Element ${index + 1}:`, sanitizeForLogging({
    //             id: element.id,
    //             selector: element.selector,
    //             tagName: element.tagName,
    //             isVisible: element.isVisible,
    //             boundingBox: element.boundingBox
    //         }));
    //     });

    //     // Wait a moment to see the bounding boxes in the UI
    //     await new Promise(resolve => setTimeout(resolve, 2000));
    // }, 60000);

    // it('should create a Browserbase session and navigate to a website', async () => {
    //     // Get the streaming URL
    //     const streamingUrl = agent.getStreamingUrl();
    //     expect(streamingUrl).toBeTruthy();
    //     logger.info(`Streaming URL: ${streamingUrl}`);

    //     // Navigate to a website
    //     const result = await agent.executeAction({
    //         type: 'goToUrl',
    //         url: 'https://www.google.com'
    //     });

    //     expect(result.success).toBe(true);

    //     // Wait for a few seconds to see the page in Browserbase
    //     await new Promise(resolve => setTimeout(resolve, 5000));

    //     // Perform some actions
    //     const clickResult = await agent.executeAction({
    //         type: 'click',
    //         target: 'a'
    //     });

    //     expect(clickResult.success).toBe(true);

    //     // Wait again to see the result
    //     await new Promise(resolve => setTimeout(resolve, 5000));
    // }, 30000);

    // it('should create a local browser session and navigate to a website', async () => {
    //     const timestamp = Date.now();
    //     const localConfig: BrowserConfig = {
    //         headless: false,
    //         viewport: {
    //             width: 1280,
    //             height: 720
    //         },
    //         timeout: 30000,
    //         retryAttempts: 3,
    //         waitBetweenActions: 1000,
    //         screenshotBeforeAction: true,
    //         screenshotAfterAction: true,
    //         useBrowserbase: false,
    //         tracePath: './traces'  // Enable tracing
    //     };

    //     const localAgent = new BrowserAgent({
    //         config: localConfig,
    //         testRunId: 'test-' + timestamp
    //     });

    //     try {
    //         await localAgent.initialize();
            
    //         // Start tracing with the same timestamp
    //         await localAgent.startTrace(`init-${timestamp}`);
            
    //         // Navigate to a website
    //         const result = await localAgent.executeAction({
    //             type: 'go_to_url',
    //             url: 'https://www.google.com'
    //         });

    //         expect(result.success).toBe(true);

    //         // Wait for a few seconds
    //         await new Promise(resolve => setTimeout(resolve, 2000));

            // Perform some actions
            // const clickResult = await localAgent.executeAction({
            //     type: 'ai_click',
            //     elementId: '1'  // Using the first element's ID
            // });

    //         expect(clickResult.success).toBe(true);

    //         // Wait again to see the result
    //         await new Promise(resolve => setTimeout(resolve, 2000));

    //         // End tracing
    //         await localAgent.endTrace();

    //         // Verify trace file exists - using the same timestamp as initialization
    //         const traceFile = path.resolve('./traces', `init-${timestamp}.zip`);
    //         expect(fs.existsSync(traceFile)).toBe(true);
    //     } finally {
    //         await localAgent.cleanup();
    //     }
    // }, 30000);


    // it('should execute a custom Playwright script', async () => {
    //     const localConfig: BrowserConfig = {
    //         headless: false,
    //         viewport: {
    //             width: 1280,
    //             height: 720
    //         },
    //         timeout: 30000,
    //         retryAttempts: 3,
    //         waitBetweenActions: 1000,
    //         screenshotBeforeAction: true,
    //         screenshotAfterAction: true,
    //         useBrowserbase: false,
    //         tracePath: './traces'
    //     };

    //     const localAgent = new BrowserAgent({
    //         config: localConfig,
    //         testRunId: 'test-' + Date.now()
    //     });

    //     try {
    //         await localAgent.initialize();
            
    //         // First navigate to a page
    //         await localAgent.executeAction({
    //             type: 'go_to_url',
    //             url: 'https://example.com'
    //         });

    //         // Execute a custom script that clicks a link
    //         const result = await localAgent.executeAction({
    //             type: 'run_script',
    //             script: `
    //                 // Find and click the first link
    //                 const link = document.querySelector('a');
    //                 if (link) {
    //                     link.click();
    //                     return 'Link clicked successfully';
    //                 }
    //                 return 'No link found';
    //             `
    //         });

    //         expect(result.success).toBe(true);
            
    //         // Wait a moment to see the result
    //         await new Promise(resolve => setTimeout(resolve, 2000));

    //         // End tracing
    //         await localAgent.endTrace();

    //         // Verify trace file exists
    //         const traceFile = path.resolve('./traces', `init-${Date.now()}.zip`);
    //         expect(fs.existsSync(traceFile)).toBe(true);
    //     } finally {
    //         await localAgent.cleanup();
    //     }
    // }, 30000);

    // it('should execute a sequence of Playwright commands', async () => {
    //     const localConfig: BrowserConfig = {
    //         headless: false,
    //         viewport: {
    //             width: 1280,
    //             height: 720
    //         },
    //         timeout: 30000,
    //         retryAttempts: 3,
    //         waitBetweenActions: 1000,
    //         screenshotBeforeAction: true,
    //         screenshotAfterAction: true,
    //         useBrowserbase: false,
    //         tracePath: './traces'
    //     };

    //     const localAgent = new BrowserAgent({
    //         config: localConfig,
    //         testRunId: 'test-' + Date.now()
    //     });

    //     try {
    //         await localAgent.initialize();
            
    //         // First navigate to a page
    //         await localAgent.executeAction({
    //             type: 'go_to_url',
    //             url: 'https://example.com'
    //         });

    //         // Execute a sequence of Playwright commands
    //         const commands = [
    //             // Get all links on the page
    //             `return Array.from(document.querySelectorAll('a')).map(a => ({ text: a.textContent, href: a.href }));`,
    //             // Click the first link
    //             `document.querySelector('a').click();`,
    //             // Wait for navigation
    //             `return new Promise(resolve => setTimeout(resolve, 2000));`
    //         ];

    //         const actionHandler = localAgent.getActionHandler();
    //         expect(actionHandler).not.toBeNull();
    //         await actionHandler?.runPlaywrightCommands(commands);
            
    //         // Wait a moment to see the result
    //         await new Promise(resolve => setTimeout(resolve, 2000));

    //         // End tracing
    //         await localAgent.endTrace();

    //         // Verify trace file exists
    //         const traceFile = path.resolve('./traces', `init-${Date.now()}.zip`);
    //         expect(fs.existsSync(traceFile)).toBe(true);
    //     } finally {
    //         await localAgent.cleanup();
    //     }
    // }, 30000);

    it('should run a script with tracing enabled', async () => {
        const agent = new BrowserAgent({
            config: {
                headless: false,
                viewport: {
                    width: 1280,
                    height: 720
                },
                timeout: 30000,
                retryAttempts: 3,
                waitBetweenActions: 1000,
                screenshotBeforeAction: true,
                screenshotAfterAction: true,
                useBrowserbase: false,
                tracePath: './traces'
            }
        });

        await agent.initialize();

        const script = {
            "0": ["await page.goto('http://automationexercise.com')"],
            "1": ["await page.waitForSelector('.features_items')"],
            "2": ["await page.click('a[href=\\'/login\\']')"],
            "3": ["await page.fill('input[data-qa=\\'login-email\\']', 'test@example.com')"],
            "4": ["await page.fill('input[data-qa=\\'login-password\\']', 'password123')"],
            "5": ["await page.click('button[data-qa=\\'login-button\\']')"],
            "6": ["await page.waitForSelector('p:has-text(\\'Your email or password is incorrect!\\')')"]
        };

        const instructions = [
            {
                "id": "0",
                "type": "go_to_url",
                "url": "http://automationexercise.com"
            },
            {
                "id": "1",
                "type": "wait",
                "timeout": 1000
            },
            
        ];

        await agent.runScript(script, instructions, 0);
        await agent.cleanup();
    }, 100000);
}); 