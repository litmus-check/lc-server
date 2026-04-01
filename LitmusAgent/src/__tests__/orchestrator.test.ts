import { LitmusAgent } from '../LitmusAgent';
import { AgentConfig } from '../types/agent';
import { logger } from '../utils/logger';
import { INSTRUCTION_TYPES } from '../config/constants';
import { v4 as uuidv4 } from 'uuid';

describe('Orchestrator End-to-End Tests', () => {
    let agent: LitmusAgent;
    const runId = 'test-run-' + 'blablablabla';
    const mode = 'compose';
    const browserbaseSessionId = '309c2b4f-3a98-4914-943c-c27b6ccd2feb';
    const cdpUrl = 'wss://connect.usw2.browserbase.com/?signingKey=eyJhbGciOiJBMjU2S1ciLCJlbmMiOiJBMjU2R0NNIn0.kqyQPiSZE2vOAOC2IYM2O2TOwXhqI-UPt1RTs_goDD3m-AWIp6JpOg.zXTV4K9nuYGNhqye.0UMQugrv8dM51XBJLUMQ3bC7vTdbCSDvxMhsL8uW5kS4DfMmeDqUIbbTU0ZMV3sG5ghJsVgINwb_ik4NzXxb1gef2-v6Xf7hKdCxhL1VFqBWaGIjt9vG6vnr0L-_kjFLthPg18UAAwXEBXgpjg-uXJcALYDl59_4QBbiA8pB5n3RvLT9JSw4egNI71oS8Ek2nuuEaf7F7T3-755iSnm4bEkz-NItrM-lqqkKXPlYcghfDrafPlKkHdyd8Q6S0uxvB1kJ0rMi8hJilUuLa7YOOSRzszLYLn5pFZuk7EH-y-j5gUikmjyEusB3XXFqrW5fHNERynog_FAsgjjUNh1WD-D_CbQi.S_Zp9KhiZlzgdv1rQ-lmPA';

    beforeAll(() => {
        if (!browserbaseSessionId || !cdpUrl) {
            throw new Error('BROWSERBASE_SESSION_ID and BROWSERBASE_CDP_URL environment variables must be set');
        }
        logger.info(`Using Browserbase session: ${browserbaseSessionId}`);
    });

    it('should execute actions on parabank website through orchestrator in compose mode', async () => {
        // Initialize agent with updated config
        agent = new LitmusAgent({
            mode: mode as 'script' | 'compose',
            runId: runId,
            useBrowserbase: false,
            playwrightCode: {},
            instructions: [],
            browserbaseSessionId: browserbaseSessionId,
            cdpUrl: cdpUrl
        });
        await agent.init();

        // Create initial empty compose session in Redis
        const composeSession = {
            instruction_status: {},
            instructions: {},
            playwright_actions: {},
            logs: {},
            reset: false,
            run_ended: false
        };
        
        // Set the initial empty compose session in Redis
        await agent['containerCommsService'].set(runId, composeSession);

        // Start the agent first - it will continuously check Redis for instructions
        const runPromise = agent.run();

        // Create instructions for the test
        const instructions = [
            {
                id: '1',
                "action": "go_to_url",
                "args": [
                    {
                        "key": "url",
                        "value": "https://www.automationexercise.com/"
                    }
                ],
                "type": "Non-AI"
            },
            {
                id: '2',
                "action": "ai_click",
                "args": [],
                "prompt": "Click on \"Signup/Login\"",
                "type": "AI"
            },
            {
                id: '3',
                "action": "ai_input",
                "args": [
                    {
                        "key": "value",
                        "value": "Bhavyatesttest"
                    }
                ],
                "prompt": "add value in \"Name\" textbox",
                "type": "AI"
            },
            {
                id: '4',
                "action": "ai_input",
                "args": [
                    {
                        "key": "value",
                        "value": "bhavya@abcdtesttests.com"
                    }
                ],
                "prompt": "add value in \"Email Address\" textbox below \"Bhavya\"",
                "type": "AI"
            },
            {
                id: '5',
                "action": "ai_click",
                "args": [],
                "prompt": "Click on \"Signup\"  button below \"bhavya@abcdtesttests.com\"",
                "type": "AI"
            },
            {
                id: '6',
                "action": "ai_select",
                "args": [
                    {
                        "key": "value",
                        "value": "Mr."
                    }
                ],
                "prompt": "select \"Mr.\" below \"Title\" field",
                "type": "AI"
            },
            {
                id: '7',
                "action": "ai_input",
                "args": [
                    {
                        "key": "value",
                        "value": "Bhavya@2025testtest"
                    }
                ],
                "prompt": "add value in textbox below \"Password*\" field",
                "type": "AI"
            },
            {
                id: '8',
                "action": "ai_input",
                "args": [
                    {
                        "key": "value",
                        "value": "Bhavya"
                    }
                ],
                "prompt": "add value in textbox below \"First name*\" field",
                "type": "AI"
            },
            {
                id: '9',
                "action": "ai_input",
                "args": [
                    {
                        "key": "value",
                        "value": "M"
                    }
                ],
                "prompt": "add value in textbox below \"Last name*\" field",
                "type": "AI"
            },
            {
                id: '10',
                "action": "ai_input",
                "args": [
                    {
                        "key": "value",
                        "value": "xyzz"
                    }
                ],
                "prompt": "add value in textbox below \"Company\" field",
                "type": "AI"
            },
            {
                id: '11',
                "action": "ai_input",
                "args": [
                    {
                        "key": "value",
                        "value": "1st block,2nd street"
                    }
                ],
                "prompt": "add value in textbox below \"Address*\" field",
                "type": "AI"
            },
            {
                id: '12',
                "action": "ai_input",
                "args": [
                    {
                        "key": "value",
                        "value": "hsr layout"
                    }
                ],
                "prompt": "add value in textbox below \"Address 2\" field",
                "type": "AI"
            },
            {
                id: '13',
                "action": "ai_input",
                "args": [
                    {
                        "key": "value",
                        "value": "Karnataka"
                    }
                ],
                "prompt": "add value in textbox below \"State*\" field",
                "type": "AI"
            },
            {
                id: '14',
                "action": "ai_input",
                "args": [
                    {
                        "key": "value",
                        "value": "Bengaluru"
                    }
                ],
                "prompt": "add value in textbox below \"City*\" field",
                "type": "AI"
            },
            {
                id: '15',
                "action": "ai_input",
                "args": [
                    {
                        "key": "value",
                        "value": "123456"
                    }
                ],
                "prompt": "add value in textbox below \"Zipcode*\" field",
                "type": "AI"
            },
            {
                id: '16',
                "action": "ai_input",
                "args": [
                    {
                        "key": "value",
                        "value": "9191229900"
                    }
                ],
                "prompt": "add value in textbox below \"Mobile Number*\" field",
                "type": "AI"
            },
            {
                id: '17',
                "action": "ai_click",
                "args": [],
                "prompt": "click on \"Create Account\" button",
                "type": "AI"
            },
            {
                id: '18',
                "action": "ai_click",
                "args": [],
                "prompt": "click on \"continue\" button",
                "type": "AI"
            }
        ];
        
        // Add instructions to Redis after agent has started
        const updatedSession = await agent['containerCommsService'].get(runId);
        instructions.forEach(inst => {
            updatedSession.instructions[inst.id] = inst;
        });
        await agent['containerCommsService'].set(runId, updatedSession);

        // Wait for the agent to finish processing all instructions
        await runPromise;

        // Verify the final state
        const finalSession = await agent['containerCommsService'].get(runId);
        expect(finalSession).toBeDefined();
        expect(finalSession.instruction_status).toBeDefined();
        
        // Check that all instructions were processed
        instructions.forEach(inst => {
            expect(finalSession.instruction_status[inst.id]).toBeDefined();
            expect(['success', 'failed']).toContain(finalSession.instruction_status[inst.id]);
        });
    });

     // [
        //     {
        //         id: '1',
        //         type: INSTRUCTION_TYPES.NON_AI,
        //         action: 'go_to_url',
        //         args: [
        //             { key: 'url', value: 'https://parabank.parasoft.com/parabank/admin.htm' }
        //         ]
        //     },
        //     {
        //         id: '2',
        //         type: INSTRUCTION_TYPES.AI,
        //         action: 'ai_click',
        //         args: [],
        //         prompt: 'Click on the SOAP radio button',
              
        //     },
        //     {
        //         id: '3',
        //         type: INSTRUCTION_TYPES.AI,
        //         action: 'ai_input',
        //         prompt: 'Enter the amount in the initial balance field',
              
        //         args: [
        //             { key: 'value', value: '732.45' }
        //         ]
        //     },
        //     {
        //         id: '4',
        //         type: INSTRUCTION_TYPES.AI,
        //         action: 'ai_select',
        //         prompt: 'Select the loan provider from the dropdown',
               
        //         args: [
        //             { key: 'value', value: 'JMS' }
        //         ]
        //     },
        //     {
        //         id: '5',
        //         type: INSTRUCTION_TYPES.AI,
        //         action: 'ai_click',
        //         prompt: 'Click the Submit button',
             
        //     },
        //     {
        //         id: '6',
        //         type: INSTRUCTION_TYPES.NON_AI,
        //         action: 'wait_time',
        //         args: [
        //             { key: 'delay_seconds', value: 8 }
        //         ]
        //     }
        // ];

    // it('should execute actions on parabank website through orchestrator in script mode', async () => {
    //     const agent = new LitmusAgent({
    //         runId: runId,
    //         mode: 'script',
    //         playwrightCode: [
    //             `await page.goto('https://parabank.parasoft.com/parabank/admin.htm')`,
    //             `await page.waitForSelector('#accessMode1')`,
    //             `await page.click('#accessMode1')`,
    //             `await page.waitForSelector('#initialBalance')`,
    //             `await page.fill('#initialBalance', '732.45')`,
    //             `await page.waitForSelector('#loanProvider')`,
    //             `await page.selectOption('#loanProvider', 'JMS')`,
    //             `await page.waitForSelector('input[value="Submit"]')`,
    //             `await page.click('input[value="Submit"]')`,
    //             `await page.waitForTimeout(8000)`
    //         ],
    //         useBrowserbase: false
    //     });

    //     await agent.init();
    //     await agent.run();


    // }, 120000);
}); 