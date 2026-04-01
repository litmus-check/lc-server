import { LitmusAgent } from './LitmusAgent';
import { AgentConfig, Instruction } from './types/agent';
import { logger } from './utils/logger';
import { DownloadUtils } from './utils/downloadUtils';

// Import websocket server
import { startWebSocketServer } from './websocket-server';

// Module-level variable to store WebSocket server instance for graceful shutdown
let wssInstance: any = null;

async function main() {
    let wss: any = null;
    try {
        // Start WebSocket server immediately on port 8080
        // This allows clients to connect and stream screencast data
        const port = parseInt(process.env.WS_PORT || '8080');
        logger.info(`Starting WebSocket server on port ${port} for screencast streaming`);
        wss = startWebSocketServer(port);
        wssInstance = wss; // Store for graceful shutdown
        logger.info(`WebSocket server is now listening on 0.0.0.0:${port}`);

        // Get command line arguments
        const args = process.argv.slice(2);
        if (args.length !== 10) {
            throw new Error('Usage: node index.js <playwright_instructions> <instructions> <mode> <run_id> <browser> <browserbase_session_id> <cdp_url> <playwright_config> <variables_dict> <blob_url> [wss_url]');
        }
        logger.info(`LitmusAgent: Run script args: ${JSON.stringify(args)}`);
        const [playwright_instructions, instructions, mode, run_id, browser, browserbase_session_id, cdp_url, playwright_config, variables_dict, blob_url, wss_url] = args;

        // Validate mode
        if (mode !== 'script' && mode !== 'compose' && mode !== 'triage' && mode !== 'heal') {
            throw new Error('Mode must be either "script", "compose", "triage" or "heal"');
        }

        // If blob_url is provided, fetch the queue_obj and extract instructions
        let parsedPlaywrightInstructions: { [key: string]: string[] };
        let parsedInstructions: { [key: string]: any }[];
        
        if (blob_url && blob_url.trim() !== '') {
            logger.info(`Blob URL provided, fetching queue object from: ${blob_url}`);
            try {
                const downloadUtils = DownloadUtils.getInstance();
                const queue_obj = await downloadUtils.downloadJson(blob_url);
                
                // Extract test_obj from queue_obj
                const test_obj = queue_obj.test_obj;
                if (!test_obj) {
                    throw new Error('test_obj not found in queue_obj from blob');
                }
                
                // Get instructions and playwright_instructions from test_obj
                if (test_obj.instructions) {
                    parsedInstructions = Array.isArray(test_obj.instructions) 
                        ? test_obj.instructions 
                        : JSON.parse(test_obj.instructions);
                } else {
                    parsedInstructions = [{}];
                }
                
                if (test_obj.playwright_instructions) {
                    parsedPlaywrightInstructions = typeof test_obj.playwright_instructions === 'string'
                        ? JSON.parse(test_obj.playwright_instructions)
                        : test_obj.playwright_instructions;
                } else {
                    parsedPlaywrightInstructions = { "0": [] };
                }
                
                logger.info('Successfully extracted instructions and playwright_instructions from blob');
            } catch (error) {
                logger.error(`Failed to fetch or parse blob content: ${error instanceof Error ? error.message : String(error)}`);
                throw error;
            }
        } else {
            // Parse playwright instructions from args
            try {
                parsedPlaywrightInstructions = JSON.parse(playwright_instructions);
            } catch (error) {
                // Fallback: treat as a single command array under key "0"
                parsedPlaywrightInstructions = { "0": [playwright_instructions] };
            }

            // Parse instructions from args
            try {
                parsedInstructions = JSON.parse(instructions);
            } catch (error) {
                // Fallback: treat as a single command array under key "0"
                parsedInstructions = [{}];
            }
        }

        // Parse playwright config
        let parsedPlaywrightConfig: any = null;
        try {
            parsedPlaywrightConfig = JSON.parse(playwright_config);
            logger.info(`Playwright config: ${JSON.stringify(parsedPlaywrightConfig)}`);
        } catch (error) {
            logger.warn('Failed to parse playwright_config, using default configuration');
        }

        // Parse variables dict
        let parsedVariablesDict: { [key: string]: string } = {};
        try {
            parsedVariablesDict = JSON.parse(variables_dict);
            logger.info(`Variables dict: ${JSON.stringify(parsedVariablesDict)}`);
        } catch (error) {
            logger.warn('Failed to parse variables_dict, using empty dictionary');
        }

        // Create agent config
        const config: AgentConfig = {
            runId: run_id,
            mode: mode as 'script' | 'compose' | 'triage' | 'heal',
            useBrowserbase: browser === 'browserbase',
            playwrightCode: parsedPlaywrightInstructions,
            instructions: parsedInstructions,
            browserbaseSessionId: browserbase_session_id,
            cdpUrl: cdp_url,
            wssUrl: wss_url || undefined,
            playwright_config: parsedPlaywrightConfig,
            variablesDict: parsedVariablesDict
        };

        // Initialize and run the agent
        const agent = new LitmusAgent(config);
    
        await agent.init();
        await agent.run();

    } catch (error) {
        logger.error(`Error in main process: ${error instanceof Error ? error.message : String(error)}`);
        process.exit(1);
    }
}

// Setup graceful shutdown for websocket server
if (typeof process !== 'undefined') {
    process.on('SIGINT', () => {
        logger.info('Shutting down...');
        if (wssInstance) {
            wssInstance.close(() => {
                logger.info('WebSocket server closed');
                process.exit(0);
            });
        } else {
            process.exit(0);
        }
    });

    process.on('SIGTERM', () => {
        logger.info('Shutting down...');
        if (wssInstance) {
            wssInstance.close(() => {
                logger.info('WebSocket server closed');
                process.exit(0);
            });
        } else {
            process.exit(0);
        }
    });
}

main();