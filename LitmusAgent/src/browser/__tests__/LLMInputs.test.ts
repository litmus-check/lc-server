import { BrowserAgent } from '../BrowserAgent';
import { LLMInputs } from '../LLMInputs';
import { logger } from '../../utils/logger';
import * as fs from 'fs';
import * as path from 'path';
import { ACTION_TYPES } from '../../config/constants';
import dotenv from 'dotenv';

dotenv.config();

describe('LLMInputs', () => {
    let agent: BrowserAgent;
    let llmInputs: LLMInputs;
    const testUrl = 'https://automationexercise.com/login';
    const screenshotDir = path.join(__dirname, 'llm-inputs-screenshots');

    beforeAll(async () => {
        // Create screenshots directory if it doesn't exist
        if (!fs.existsSync(screenshotDir)) {
            fs.mkdirSync(screenshotDir, { recursive: true });
        }
    });

    beforeEach(async () => {
        agent = new BrowserAgent({
            config: {
                headless: false, // Set to false to see the browser UI
                viewport: { width: 1280, height: 720 },
                timeout: 30000,
                retryAttempts: 3,
                waitBetweenActions: 1000,
                screenshotBeforeAction: true,
                screenshotAfterAction: true
            }
        });
        await agent.initialize();
        if (!agent['browserContext']) {
            throw new Error('Browser context not initialized');
        }
        llmInputs = new LLMInputs(agent['browserContext'].getActivePage());
    });

    afterEach(async () => {
        await agent.cleanup();
    }, 10000);


    // it('should get inputs from automation exercise website', async () => {
    //     // Navigate to the website
    //     await agent.executeAction({
    //         type: ACTION_TYPES.GO_TO_URL,
    //         url: 'https://parabank.parasoft.com/parabank/admin.htm'
    //     });
    //     logger.info('Navigated to automation exercise website');

    //     // Get inputs using LLMInputs
    //     const inputs = await llmInputs.getInputs();
        
    //     // Log the response
    //     logger.info('LLM Inputs response:', {
    //         currentUrl: inputs.currentUrl,
    //         elementsCount: inputs.elements.length,
    //         elements: inputs.elements
    //     });

    //     // Save the screenshot
    //     const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    //     const filename = `llm-inputs-${timestamp}.png`;
    //     const filepath = path.join(screenshotDir, filename);
    //     await fs.promises.writeFile(filepath, inputs.screenshot);
    //     logger.info(`Screenshot saved to ${filepath}`);

    //     // Verify we got the expected data
    //     // expect(inputs.currentUrl).toBe('https://automationexercise.com/');
    //     // expect(inputs.elements.length).toBeGreaterThan(0);
    //     // expect(inputs.screenshot).toBeDefined();
    // }, 60000);

    it('should execute actions on parabank website', async () => {
        // Navigate to the website
        await agent.executeAction({
            type: ACTION_TYPES.GO_TO_URL,
            url: 'https://parabank.parasoft.com/parabank/admin.htm'
        });
        logger.info('Navigated to automation exercise website');


        await agent.executeAction({
            type: ACTION_TYPES.CLICK,
            elementId: 20,
            prompt: 'Click on the SOAP radio button'
        });

        logger.info('Selected SOAP');

        await agent.executeAction({
            type: ACTION_TYPES.INPUT,
            elementId: 31,
            value: '732.45',
            prompt: 'Enter the amount 732.45 in the initial balance field'
        });

        logger.info('Entered amount');

        await agent.executeAction({
            type: ACTION_TYPES.SELECT,
            elementId: 33,
            value: 'JMS',
            prompt: 'Select JMS from the loan provider dropdown'
        });

        logger.info('Selected JMS');
        
        await agent.executeAction({
            type: ACTION_TYPES.CLICK,
            elementId: 36,
            prompt: 'Click the Submit button'
        });

        logger.info('Clicked on Submit button');

        await agent.executeAction({
            type: ACTION_TYPES.WAIT_TIME,
            delay_seconds: 8
        });

    }, 120000);
}); 