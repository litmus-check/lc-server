import { BrowserAgent } from './browser/BrowserAgent';
import { AgentConfig, Instruction, ExecutionData } from './types/agent';
import { logger } from './utils/logger';
import { LLMAgent } from './LLM/LLM';
import { GoalOutput } from './LLM/GoalAgentOutput';
import { Memory } from './services/Memory';
import { State } from './services/State';
import { InstructionFetcher } from './services/InstructionFetcher';
import { ActionResult, Action, ActionType, VerifyEmailAction } from './types/actions';
import * as fs from 'fs';
import * as path from 'path';
import { DEFAULT_BROWSER_CONFIG, INSTRUCTION_TYPES, ACTION_TYPES, TASK_STATUS, SUPPORTED_AI_ACTIONS, FILE_UPLOADS_DIR, VERIFICATION_ELEMENT_PROPERTIES, TRIAGE_MODE, TRIAGE_CATEGORIES, TRIAGE_SUB_CATEGORIES } from './config/constants';
import { ContainerCommsService } from './services/ContainerCommsService';
import { MessageManager } from './LLM/MessageManager';
import { v4 as uuidv4 } from 'uuid';
import { DownloadUtils } from './utils/downloadUtils';
import { substituteVariablesInInstruction, substituteVariablesInArray } from './utils/variableUtils';
import { EmailVerificationService } from './email/EmailVerificationService';
import { VerificationFunctions } from './types/verifications';
import { AI_CREDIT_UNIT, TRIAGE_CREDIT_UNIT } from './config/constants';
import { HealAgent } from './services/HealAgent';


export class LitmusAgent {
    private mode: 'compose' | 'script' | 'triage' | 'heal';
    private browserAgent: BrowserAgent;
    private llmAgent?: LLMAgent;
    private memory: Memory;
    private state: State;
    private instructionFetcher: InstructionFetcher;
    private config: AgentConfig;
    private containerCommsService: ContainerCommsService;
    private lastInstructionTime: number = Date.now();
    private readonly INSTRUCTION_TIMEOUT = 20 * 60 * 1000; // 20 minutes in milliseconds
    private taskIndex: number = 0;
    private completedInstructions: number = 0;
    private addedTasks: Set<number> = new Set();
    private instructionId: string = "";

    constructor(config: AgentConfig) {
        this.config = config;
        this.mode = config.mode;
        
        // Set headless based on browser type and mode
        let headless = (config.mode === 'script' || config.mode === 'triage' || config.mode === 'heal') ? true : DEFAULT_BROWSER_CONFIG.headless;
        if ((config.mode === 'compose' || config.mode === 'heal') && !config.useBrowserbase) {
            // If mode is compose or heal and not using browserbase (i.e., litmus_cloud), set headless to true
            headless = true;
        }
        
        this.browserAgent = new BrowserAgent({
            runId: config.runId,
            composeId: config.mode === 'compose' ? config.runId : undefined,
            config: {
                ...DEFAULT_BROWSER_CONFIG,
                headless: headless,
                useBrowserbase: config.useBrowserbase,
                tracePath: './traces',
                browserbaseSessionId: config.browserbaseSessionId,
                cdpUrl: config.cdpUrl,
                wssUrl: config.wssUrl,
                playwright_config: config.playwright_config
            }
        });


        // Set variables dictionary in BrowserAgent for script substitution
        if (config.variablesDict && Object.keys(config.variablesDict).length > 0) {
            logger.info(`Setting variables dictionary in BrowserAgent: ${JSON.stringify(config.variablesDict)}`);
            this.browserAgent.setVariablesDict(config.variablesDict);
        }

        if (this.mode === 'compose' || this.mode === 'triage' || this.mode === 'heal') {
            this.llmAgent = new LLMAgent();
        }
        this.memory = new Memory();
        this.state = new State(config.runId);
        this.instructionFetcher = new InstructionFetcher(config.runId);
        this.containerCommsService = new ContainerCommsService();
    }

    async init(): Promise<void> {
        try {
            await this.browserAgent.initialize();
            logger.info("Agent initialized");
    
        } catch (error) {
            logger.error(`Failed to initialize agent: ${error instanceof Error ? error.message : String(error)}`);
            throw error;
        }
    }

    private async processNewInstructions(instructions: { [key: string]: any }): Promise<void> {
        if (Object.keys(instructions).length > this.state.getInstructionCount()) {
            // Add new instructions to state
            let start_index = this.state.getInstructionCount();
            for(let i = start_index; i < Object.keys(instructions).length; i++){
                const instruction = instructions[i];
                if (!this.state.hasInstruction(instruction.id)) {
                    logger.info(`LitmusAgent: Adding instruction ${instruction.id} to state`);
                    this.state.addInstruction(instruction);
                }
            }
        }
    }

    async run(): Promise<void> {                        
            // Initialize shared state in ActionHandler
            this.browserAgent.initializeSharedState();
            logger.info(`LitmusAgent: Initialized shared state for script mode`);

            // Ensure "Test run queued" log exists in Redis (compose is skipped inside ensureTestRunQueuedLog)
            if (this.mode !== 'compose') {
                await this.containerCommsService.ensureTestRunQueuedLog(this.config.runId, this.mode);
            }

            if(this.mode === 'script'){
                logger.info(`LitmusAgent: Running script: ${JSON.stringify(this.config.playwrightCode)}`);
                
                // Log script execution start
                await this.containerCommsService.addLog(this.config.runId, {
                    info: `Starting script execution`,
                    timestamp: new Date().toISOString()
                });
                
                try {
                    // Process file uploads in script mode
                    for (const instruction of this.config.instructions ) {
                        const script = this.config.playwrightCode[instruction.id];
                        const processedScript = await this.processFileInstruction(instruction as Instruction, script);
                        this.config.playwrightCode[instruction.id] = processedScript;
                    }
                    logger.info(`LitmusAgent: Running script After processing: ${JSON.stringify(this.config.playwrightCode)}`);
                    logger.info(`LitmusAgent: Instructions After processing: ${JSON.stringify(this.config.instructions)}`);

                    // Execute per-instruction: AI for always_ai, scripts otherwise
                    for (const instruction of this.config.instructions as Instruction[]) {
                        const instructionDescription = this.createInstructionDescription(instruction);
                        await this.containerCommsService.addLog(this.config.runId, {
                            info: `Executing instruction ${instructionDescription}`,
                            timestamp: new Date().toISOString(),
                            instructionId: instruction.id
                        });

                        if ((instruction as any).ai_use === 'always_ai' || instruction.action === ACTION_TYPES.ASSERT) {
                            // Ensure LLM agent is initialized in script mode when needed
                            if (!this.llmAgent) {
                                this.llmAgent = new LLMAgent();
                            }
                            // Run this instruction via AI path
                            this.browserAgent.setCurrentInstructionId(instruction.id);

                            // Remove playwright scripts from the instruction
                            if(instruction.playwright_actions){
                                instruction.playwright_actions = [];
                            }
                            await this.handleAIInstruction(instruction);
                            
                            // Check memory for failed actions for this instruction
                            const browserMemory = this.browserAgent.getMemory();
                            const failedAction = browserMemory.executionHistory.find(
                                exec => exec.instructionId === instruction.id && !exec.result.success
                            );
                            
                            if (failedAction) {
                                const errorMessage = failedAction.result.error || `${failedAction.action.type} failed`;
                                throw new Error(errorMessage);
                            }
                        } else {
                            // Run provided Playwright scripts for this instruction
                            const scriptsForInstr = (this.config.playwrightCode as { [key: string]: string[] })[instruction.id] || [];
                            const result = await this.executePlaywrightScripts(scriptsForInstr, instruction);
                            if (!result.success) {
                                throw new Error(result.error || 'Unknown Playwright error');
                            }
                        }
                    }

                    // After all instructions, stop tracing and upload artifacts once
                    try {
                        const { gifUrl, traceUrl } = await this.browserAgent.handleTriagePostExecution(this.config.runId);
                        // Store test result in Redis
                        const session = await this.containerCommsService.get(this.config.runId);
                        if (session) {
                            session.test_result = {
                                status: TASK_STATUS.SUCCESS,
                                gif_url: gifUrl,
                                trace_url: traceUrl,
                                retries: 0,
                                error: undefined
                            };
                            await this.containerCommsService.set(this.config.runId, session);
                        }
                    } catch (postError) {
                        logger.error(`Failed script post-execution tasks: ${postError instanceof Error ? postError.message : String(postError)}`);
                        await this.containerCommsService.addLog(this.config.runId, {
                            error: `Failed script post-execution tasks: ${postError instanceof Error ? postError.message : String(postError)}`,
                            timestamp: new Date().toISOString()
                        });
                    }
                    
                    // Log script execution success
                    await this.containerCommsService.addLog(this.config.runId, {
                        info: 'Script execution completed',
                        timestamp: new Date().toISOString()
                    });

                    // Log final state variables after script execution
                    const finalState = this.browserAgent.getActionHandler()?.getSharedState() || {};
                    if (Object.keys(finalState).length > 0) {
                        await this.containerCommsService.addLog(this.config.runId, {
                            info: `Final state variables: ${JSON.stringify(finalState)}`,
                            timestamp: new Date().toISOString()
                        });
                        logger.info(`Final state variables logged: ${JSON.stringify(finalState)}`);
                    }
                } catch (error) {

                    // After all instructions, stop tracing and upload artifacts once
                    try {
                        const { gifUrl, traceUrl } = await this.browserAgent.handleTriagePostExecution(this.config.runId);
                        // Store test result in Redis
                        const session = await this.containerCommsService.get(this.config.runId);
                        if (session) {
                            session.test_result = {
                                status: TASK_STATUS.FAILED,
                                gif_url: gifUrl,
                                trace_url: traceUrl,
                                retries: 0,
                                error: error instanceof Error ? error.message : String(error),
                                failure_data: this.browserAgent.lastFailureData || null
                            };
                            await this.containerCommsService.set(this.config.runId, session);
                        }
                    } catch (postError) {
                        logger.error(`Failed script post-execution tasks: ${postError instanceof Error ? postError.message : String(postError)}`);
                        await this.containerCommsService.addLog(this.config.runId, {
                            error: `Failed script post-execution tasks: ${postError instanceof Error ? postError.message : String(postError)}`,
                            timestamp: new Date().toISOString()
                        });
                    }
                    // Log script execution error
                    await this.containerCommsService.addLog(this.config.runId, {
                        error: `Script execution failed: ${error instanceof Error ? error.message : String(error)}`,
                        timestamp: new Date().toISOString()
                    });
                    throw error;
                }
                
                // Exit process after script execution in script mode
                process.exit(0);
            }
            else if(this.mode === TRIAGE_MODE){
                logger.info('LitmusAgent: Running in triage mode');
                try {
                    // Get failure data from Redis if available
                    let failureData = null;
                    try {
                        const session = await this.containerCommsService.get(this.config.runId);
                        if (session && session.test_result && session.test_result.failure_data) {
                            failureData = session.test_result.failure_data;
                            logger.info(`Retrieved failure data from Redis: ${JSON.stringify(failureData)}`);
                        }
                    } catch (error) {
                        logger.warn(`Failed to retrieve failure data from Redis: ${error}`);
                    }
                    logger.info(`Failure data received: ${JSON.stringify(failureData)}`);

                    const instructionsArr = this.config.instructions as { [key: string]: any }[];
                    const executedInstructions: any[] = [];
                    const upcomingInstructions: any[] = [];
                    let failedInstruction: any = null;
                    let failureFound = false;

                    // Initialize upcoming instructions with all instruction objects
                    for (const instr of instructionsArr) {
                        upcomingInstructions.push(instr);
                    }

                    for (let i = 0; i < instructionsArr.length; i++) {
                        const instr = instructionsArr[i] as Instruction;
                        const scriptsForInstr = this.config.playwrightCode?.[instr.id] || [];

                        // create instruction description and add to containerCommsService
                        const instructionDescription = this.createInstructionDescription(instr);
                        await this.containerCommsService.addLog(this.config.runId, {
                            info: `Executing instruction ${instructionDescription}`,
                            timestamp: new Date().toISOString(),
                            instructionId: instr.id
                        });

                        try {
                            logger.info(`Running instruction ${instructionDescription}`);
                            
                            // Check if ai_use is always_ai or action is ai_assert, similar to script and compose modes
                            if ((instr as any).ai_use === 'always_ai' || instr.action === ACTION_TYPES.ASSERT) {
                                // Ensure LLM agent is initialized in triage mode when needed
                                if (!this.llmAgent) {
                                    this.llmAgent = new LLMAgent();
                                }
                                // Run this instruction via AI path
                                this.browserAgent.setCurrentInstructionId(instr.id);
                                await this.handleAIInstruction(instr);
                                
                                // Check memory for failed actions for this instruction (same as script mode)
                                const browserMemory = this.browserAgent.getMemory();
                                const failedAction = browserMemory.executionHistory.find(
                                    exec => exec.instructionId === instr.id && !exec.result.success
                                );
                                
                                if (failedAction) {
                                    failureFound = true;
                                    failedInstruction = instr;
                                    const errorMessage = failedAction.result.error || `${failedAction.action.type} failed`;
                                    
                                    // Log the AI verification failure
                                    await this.containerCommsService.addLog(this.config.runId, {
                                        error: `AI verification failed for instruction ${instructionDescription}: ${errorMessage}`,
                                        timestamp: new Date().toISOString(),
                                        instructionId: instr.id
                                    });
                                    
                                    // Use single triage handler method for all scenarios
                                    const triageResult = await this.handleTriageInstruction(
                                        executedInstructions,
                                        upcomingInstructions,
                                        failedInstruction,
                                        errorMessage,
                                        failureData
                                    );
                                    
                                    break;
                                }
                                
                                // If no failure recorded, treat as successful
                                // remove the index 0 from upcoming instructions and add to executed instructions
                                upcomingInstructions.splice(0, 1);
                                executedInstructions.push(instr);
                                continue;
                            } else {
                                // Run the instruction using the existing executePlaywrightScripts method
                                const result = await this.executePlaywrightScripts(scriptsForInstr, instr);
                                logger.info(`Instruction ${instructionDescription} executed with result ${JSON.stringify(result)}`);
                                if (result.success) {
                                    // remove the index 0 from upcoming instructions and add to executed instructions
                                    upcomingInstructions.splice(0, 1);
                                    executedInstructions.push(instr);
                                    continue;
                                } else {
                                    failureFound = true;
                                    failedInstruction = instr;
                                    const playwrightError = result.error || 'Unknown Playwright error';

                                    // Use single triage handler method for all scenarios
                                    const triageResult = await this.handleTriageInstruction(
                                        executedInstructions,
                                        upcomingInstructions,
                                        failedInstruction,
                                        playwrightError,
                                        failureData
                                    );

                                    break;
                                }
                            }
                            
                        } catch (err: any) {
                            logger.error(`Error executing instruction ${instr.id}: ${err}`);
                            await this.containerCommsService.addLog(this.config.runId, {
                                error: `Error executing instruction ${instr.id}: ${err}`,
                                timestamp: new Date().toISOString(),
                                instructionId: instr.id
                            });
                            failureFound = true;
                            failedInstruction = instr;
                            const errorMessage = err instanceof Error ? err.message : String(err);
                            
                            // Use single triage handler method for all scenarios
                            const triageResult = await this.handleTriageInstruction(
                                executedInstructions,
                                upcomingInstructions,
                                failedInstruction,
                                errorMessage,
                                failureData
                            );
                            
                            break;
                        }
                    }

                    if (!failureFound) {
                        logger.info('All instructions executed successfully. Analyzing why it failed in first run but succeeded in triage.');
                        await this.containerCommsService.addLog(this.config.runId, {
                            info: 'All instructions passed; analyzing success in triage vs previous failure',
                            timestamp: new Date().toISOString()
                        });

                        // Call LLM to analyze why it failed first time but succeeded in triage
                        const successAnalysisResult = await this.handleTriageInstruction(
                            executedInstructions,
                            [], // No upcoming instructions for success analysis
                            null, // No failed instruction for success analysis
                            'All instructions executed successfully', // Success message
                            failureData
                        );
                    }
                } catch (error) {
                    logger.error('Triage mode execution error', error);
                    await this.containerCommsService.addLog(this.config.runId, {
                        error: `Triage encountered an error: ${error instanceof Error ? error.message : String(error)}`,
                        timestamp: new Date().toISOString()
                    });

                    const testResult = {
                        status: TASK_STATUS.FAILED,
                        reasoning: `Triage encountered an error: ${error instanceof Error ? error.message : String(error)}`,
                        category: null,
                        sub_category: null
                    }

                    // Add failure result to redis
                    let session = await this.containerCommsService.get(this.config.runId);
                    if(session){
                        session.test_result = testResult;
                        await this.containerCommsService.set(this.config.runId, session);
                    }
                }
                finally{
                    // Handle post-execution tasks for triage mode (GIF and trace URL creation)
                    try {
                        logger.info('Handling triage post-execution tasks (GIF and trace URL creation)');
                        const { gifUrl, traceUrl } = await this.browserAgent.handleTriagePostExecution(this.config.runId);
                        
                        // Update test result with GIF and trace URLs
                        let session = await this.containerCommsService.get(this.config.runId);
                        if (session && session.test_result) {
                            session.test_result.gif_url = gifUrl;
                            session.test_result.trace_url = traceUrl;
                            await this.containerCommsService.set(this.config.runId, session);
                            logger.info(`Updated triage test result with gif_url: ${gifUrl}, trace_url: ${traceUrl}`);
                        }
                    } catch (error) {
                        logger.error(`Failed to handle triage post-execution tasks: ${error instanceof Error ? error.message : String(error)}`);
                        await this.containerCommsService.addLog(this.config.runId, {
                            error: `Failed to handle triage post-execution tasks: ${error instanceof Error ? error.message : String(error)}`,
                            timestamp: new Date().toISOString()
                        });
                    }
                    
                    // Exit process after triage mode execution
                    this.stop();
                }
            }
            else if(this.mode === 'heal'){
                logger.info('LitmusAgent: Running in heal mode');
                
                // Initialize HealAgent with required dependencies
                const healAgent = new HealAgent({
                    config: this.config,
                    containerCommsService: this.containerCommsService,
                    browserAgent: this.browserAgent,
                    executePlaywrightScripts: this.executePlaywrightScripts.bind(this),
                    handleAIInstruction: this.handleAIInstruction.bind(this),
                    handleNonAIInstruction: this.handleNonAIInstruction.bind(this),
                    handleGoalInstruction: this.handleGoalInstruction.bind(this)
                });
                
                try {
                    // Get triage_result from Redis session
                    let session = await this.containerCommsService.get(this.config.runId);
                    const triageResult = session?.triage_result;
                    
                    if (!triageResult) {
                        throw new Error('Triage result not found. Cannot proceed with healing.');
                    }
                    
                    logger.info(`Retrieved triage_result from Redis session: ${JSON.stringify(triageResult)}`);
                    
                    const subCategory = triageResult.sub_category;
                    const category = triageResult.category;
                    const failedInstructionId = triageResult.error_instruction?.id || null;
                    
                    logger.info(`Heal mode: Category: ${category}, Sub category: ${subCategory}, Failed instruction ID: ${failedInstructionId}`);
                    
                    // Initialize heal_results in Redis
                    if (!session) {
                        session = {};
                    }
                    if (!session.heal_results) {
                        session.heal_results = {
                            suggested_test: {
                                instructions: [],
                                playwright_actions: {},
                            },
                            heal_status: 'running',
                            reasoning: ''
                        };
                    }
                    
                    // Store original instructions and playwright_actions as current_test before any modifications
                    session.current_test = {
                        instructions: JSON.parse(JSON.stringify(this.config.instructions)), // Deep copy
                        playwright_actions: JSON.parse(JSON.stringify(this.config.playwrightCode || {})) // Deep copy
                    };
                    
                    await this.containerCommsService.set(this.config.runId, session);
                    
                    // Decrement 5 AI credits when healing agent starts
                    await this.updateAiCreditsInRedis(5.0);
                    logger.info('Decremented 5 AI credits for heal run');

                    // Logs the instructions and playwright actions before removing the playwright actions
                    logger.info(`Instructions before removing playwright: ${JSON.stringify(this.config.instructions)}`);
                    logger.info(`Playwright before removing playwright: ${JSON.stringify(this.config.playwrightCode)}`);
                    
                    // Handle different sub_categories and categories
                    healAgent.handleHealSubCategory(subCategory, triageResult, failedInstructionId);

                    // Logs the instructions to know if the playwright actions are removed
                    logger.info(`Instructions after removing playwright: ${JSON.stringify(this.config.instructions)}`);
                    logger.info(`Playwright after removing playwright: ${JSON.stringify(this.config.playwrightCode)}`);
                    
                    // Sequential healing flow: run scripts until failed instruction, run failed via AI/Non-AI, then scripts again
                    const instructionsArray = this.config.instructions as Instruction[];
                    // Recalculate failedIndex after modifications (remove_step removes it, manual_review inserts wait before it)
                    const failedIndex = failedInstructionId ? instructionsArray.findIndex((i: any) => i.id === failedInstructionId) : -1;
                    
                    // For remove_step, the instruction is already removed, so failedIndex will be -1
                    // In this case, we just run all remaining instructions normally
                    const isRemoveStep = subCategory === TRIAGE_SUB_CATEGORIES.REMOVE_STEP;
                    const isAddNewStep = subCategory === TRIAGE_SUB_CATEGORIES.ADD_NEW_STEP;

                    // Process all instructions in sequence
                    for (let i = 0; i < instructionsArray.length; i++) {
                        const instr = instructionsArray[i] as Instruction;

                        // Before failed step: run with scripts
                        // For remove_step, failedIndex is -1, so we run all instructions normally
                        if (isRemoveStep || failedIndex === -1 || i < failedIndex) {
                            await healAgent.executePreFailedInstruction(instr);
                            continue;
                        }

                        // For add_new_step: run goal agent before the failed instruction
                        if (isAddNewStep && i === failedIndex) {
                            await healAgent.handleAddNewStepInstruction(instr, triageResult);
                            continue;
                        }

                        // Failed instruction: regenerate and run via AI / Non-AI
                        // Skip this for remove_step and add_new_step since they are handled separately
                        if (!isRemoveStep && !isAddNewStep && i === failedIndex) {
                            await healAgent.executeAndStoreFailedInstruction(instr, undefined);
                            continue;
                        }

                        // After failed step: run remaining steps via scripts
                        if (i > failedIndex) {
                            await healAgent.executePostFailedInstruction(instr);
                            continue;
                        }
                    }

                    // All instructions processed, update heal_status to completed and stop
                    await healAgent.finalizeHealMode();
                    
                    // Stop the agent after processing all instructions
                    this.stop();
                } catch (error: any) {
                    logger.error('Heal mode execution error', error);
                    const errorMessage = `Healing encountered an error: ${error instanceof Error ? error.message : String(error)}`;
                    
                    // Update heal_status to failed and set reasoning
                    const session = await this.containerCommsService.get(this.config.runId);
                    if (session?.heal_results) {
                        session.heal_results.heal_status = 'failed';
                        // Generate healing-specific failure reasoning
                        const triageResult = session.triage_result;
                        const subCategory = triageResult?.sub_category;
                        const healingReason = healAgent.generateHealingReasoning(subCategory, 'failed', errorMessage);


                        // Clear suggested_test
                        session.heal_results.suggested_test = {
                            instructions: [],
                            playwright_actions: {}
                        };
                        
                        session.heal_results.reasoning = healingReason;
                        await this.containerCommsService.set(this.config.runId, session);
                        logger.info(`Updated heal_results: status='failed', reasoning='${healingReason}'`);

                        //Add log to container comms service
                        await this.containerCommsService.addLog(this.config.runId, {
                            error: healingReason,
                            timestamp: new Date().toISOString()
                        });
                    }
                } finally {
                    // Handle post-execution tasks
                    try {
                        logger.info('Handling heal post-execution tasks');
                        const { gifUrl, traceUrl } = await this.browserAgent.handleTriagePostExecution(this.config.runId);
                        
                        const session = await this.containerCommsService.get(this.config.runId);
                        if (session?.heal_results) {
                            if (session.heal_results.heal_status === 'running') {
                                session.heal_results.heal_status = 'completed';
                                // Generate healing-specific reasoning if not already set
                                if (!session.heal_results.reasoning) {
                                    const triageResult = session.triage_result;
                                    const subCategory = triageResult?.sub_category;
                                    const healingReason = healAgent.generateHealingReasoning(subCategory, 'completed');
                                    
                                    session.heal_results.reasoning = healingReason;
                                    logger.info(`Created healing reasoning: ${healingReason}`);
                                }
                            }
                            await this.containerCommsService.set(this.config.runId, session);
                            logger.info(`Final heal_results status: '${session.heal_results.heal_status}', reasoning: '${session.heal_results.reasoning}'`);
                        }
                    } catch (error) {
                        logger.error(`Failed to handle heal post-execution tasks: ${error instanceof Error ? error.message : String(error)}`);
                    }
                    
                    this.stop();
                }
            }
            else if(this.mode === 'compose'){

                while (!this.state.isStopped) {
                    // Fetch compose session from Redis
                    const composeSession = await this.containerCommsService.get(this.config.runId);
                    
                    if (!composeSession) {
                       
                        logger.error('No compose session found in Redis, returning from agent');
                        return;
                    }

                    // Check if the goal is added to the compose session
                    const goalData = await this.checkIfGoalAdded(composeSession);
                    if(goalData.goalId !== null && goalData.prompt !== null){
                        logger.info('Goal is added to the compose session, running the goal');
                        await this.updateGoalStatusInContainerCommsService(goalData.goalId, TASK_STATUS.RUNNING);
                        const result = await this.handleGoalInstruction(goalData.goalId, goalData.prompt, ACTION_TYPES.GOAL);
                        logger.info(`Goal completed with status: ${result.completionStatus}, generated ${result.generatedInstructions.length} instructions`);
                        continue;
                    }

                    // Check if run has ended
                    if (composeSession.run_ended === true) {
                        logger.info('Run has ended, waiting for new instructions');
                        this.stop();
                        continue;
                    }

                    if(composeSession.reset === true){
                        logger.info('Reset flag is true, resetting state');
                        await this.handleReset(this.taskIndex);
                       // continue;
                    }

                    // Get instructions from compose session
                    const instructions = composeSession.instructions || {};
                    // logger.info(`instructions from redis: ${JSON.stringify(instructions)}`);
                    // logger.info(`state instruction count: ${this.state.getInstructionCount()}`);
                    // Check if we have new instructions
                    await this.processNewInstructions(instructions);

                    let currentInstruction: Instruction | undefined;
                    try {
                        currentInstruction = this.state.getInstructions()[this.taskIndex];
                        if (!currentInstruction) {
                            // logger.error(`No instruction found for task index ${this.taskIndex}`);
                            continue;
                        }

                        this.instructionId = currentInstruction.id;

                        // Only process if not already added or if we're in a reset state
                        if (!this.addedTasks.has(this.taskIndex)) {
                            this.addedTasks.add(this.taskIndex);     // add task index to added tasks list to avoid infinite loop
                            
                            // Check if the instruction is a stop instruction
                            if(currentInstruction.type === INSTRUCTION_TYPES.STOP){
                                logger.info('Stop instruction found, stopping the agent');
                                await this.containerCommsService.addLog(this.config.runId, {
                                    info: 'Stop instruction found, stopping the agent',
                                    timestamp: new Date().toISOString(),
                                    instructionId: currentInstruction.id
                                });
                                this.stop();
                                continue;
                            }

                            if(currentInstruction.type === INSTRUCTION_TYPES.CLEAR){
                                // if action type is browser_clear, then clear the browser data
                                if(currentInstruction.action === ACTION_TYPES.CLEAR_BROWSER){
                                    logger.info('Browser clear instruction found, clearing the browser data');
                                    await this.containerCommsService.addLog(this.config.runId, {
                                        info: 'Browser clear instruction found, clearing the browser data',
                                        timestamp: new Date().toISOString(),
                                        instructionId: currentInstruction.id
                                    });
                                    await this.clear();
                                }
                                

                                const resetPerformed = await this.updateInstructionStatus(TASK_STATUS.SUCCESS);
                                if (resetPerformed) {
                                    continue;
                                }
                                // increase task index, add task index to added tasks list to avoid infinite loop, and mark instruction as completed
                                this.taskIndex++;
                                continue;
                            }
                            
                            // Update instruction status to Running only if we have a valid instruction
                            const resetPerformedForRunning = await this.updateInstructionStatus(TASK_STATUS.RUNNING);
                            if (resetPerformedForRunning) {
                                continue;
                            }

                            // Log started executing instruction
                            const instructionDescription = this.createInstructionDescription(currentInstruction);
                            await this.containerCommsService.addLog(this.config.runId, {
                                info: `Started Executing Instruction '${instructionDescription}'`,
                                timestamp: new Date().toISOString(),
                                instructionId: currentInstruction.id
                            });

                            // Execute instruction
                            const instructionStatus = await this.executeInstruction(currentInstruction);
                            if (instructionStatus === 'reset') {
                                continue;
                            }
                            
                            // If instruction failed, check if we should stop on error
                            if (instructionStatus === TASK_STATUS.FAILED) {
                                // Check if we should stop on error
                                const shouldStopOnError = composeSession?.stop_on_error === true;
                                const agentType = process.env.AGENT_TYPE;
                                const isSignInSignUpAgent = agentType === 'sign-in' || agentType === 'sign-up';
                                
                                if (shouldStopOnError || isSignInSignUpAgent) {
                                    logger.info(`Instruction failed and stop_on_error is enabled or sign in/sign up agent. Stopping container immediately.`);
                                    await this.containerCommsService.addLog(this.config.runId, {
                                        error: `Instruction failed. Stopping execution due to stop_on_error flag or sign in/sign up agent.`,
                                        timestamp: new Date().toISOString(),
                                        instructionId: currentInstruction.id
                                    });
                                    this.stop(); // This will call process.exit(0)
                                    return;
                                }
                                
                                this.taskIndex++;
                                logger.info(`Instruction failed with status: ${instructionStatus}. Moving to next task. New task index: ${this.taskIndex}`);
                            }
                            
                        }
                    } catch (error) {
                        // Update instruction status to Failed
                        const resetPerformedForError = await this.updateInstructionStatus(TASK_STATUS.FAILED);
                        if (resetPerformedForError) {
                            continue;
                        }
                        
                        if (currentInstruction) {
                            await this.handleInstructionError(currentInstruction, error as Error);
                        }
                        this.state.markInstructionFailed();
                        
                        // Check if we should stop on error
                        const composeSession = await this.containerCommsService.get(this.config.runId);
                        const shouldStopOnError = composeSession?.stop_on_error === true;
                        const agentType = process.env.AGENT_TYPE;
                        const isSignInSignUpAgent = agentType === 'sign-in' || agentType === 'sign-up';
                        
                        if (shouldStopOnError || isSignInSignUpAgent) {
                            logger.info(`Instruction failed with error and stop_on_error is enabled or sign in/sign up agent. Stopping container immediately.`);
                            await this.containerCommsService.addLog(this.config.runId, {
                                error: `Instruction failed with error: ${error}. Stopping execution due to stop_on_error flag or sign in/sign up agent.`,
                                timestamp: new Date().toISOString(),
                                instructionId: currentInstruction?.id
                            });
                            this.stop(); // This will call process.exit(0)
                            return;
                        }
                        
                        // Increment taskIndex to move to next instruction even after failure
                        this.taskIndex++;
                        logger.info(`Instruction failed. Moving to next task. New task index: ${this.taskIndex}`);
                    }
                }    
            }
    
    }

    private createInstructionDescription(instruction: Instruction): string {
        let description = instruction.action || '';
        
        // Add prompt if present
        if (instruction.prompt && instruction.prompt.trim()) {
            description += ` ${instruction.prompt}`;
        }
        
        // Add args if present
        if (instruction.args && instruction.args.length > 0) {
            const argsStr = instruction.args.map(arg => `${arg.key} ${arg.value}`).join(' ');
            description += ` ${argsStr}`;
        }
        
        return description;
    }

    private async handleNonAIInstruction(instruction: Instruction): Promise<void> {
        // Apply variable substitution to instruction if variablesDict is provided
        let processedInstruction = instruction;
        if (this.config.variablesDict) {
            const dataDrivenVariables = this.config.variablesDict.data_driven_variables || {};
            const environmentVariables = this.config.variablesDict.environment_variables || {};
            
            if (Object.keys(dataDrivenVariables).length > 0 || Object.keys(environmentVariables).length > 0) {
                logger.info(`Applying variable substitution to Non-AI instruction with data-driven variables: ${JSON.stringify(dataDrivenVariables)}`);
                logger.info(`Applying variable substitution to Non-AI instruction with environment variables: ${JSON.stringify(environmentVariables)}`);
                processedInstruction = substituteVariablesInInstruction(instruction, dataDrivenVariables, environmentVariables);
                logger.info(`Non-AI instruction after variable substitution: ${JSON.stringify(processedInstruction)}`);
            }
        }
        
        // Set the original instruction (with variables) in the ActionHandler for playwright code generation
        if (this.browserAgent.getActionHandler()) {
            logger.info(`Setting original instruction for Non-AI: ${JSON.stringify(instruction)}`);
            this.browserAgent.getActionHandler()!.setOriginalInstruction(instruction);
        }

        let response: ActionResult = {
            action: {
                type: processedInstruction.action as ActionType
            },
            success: false,
            error: undefined,
            warning: undefined,
            timestamp: Date.now()
        } as ActionResult;
        
        try {
            
            if (!processedInstruction.action) {
                throw new Error('No action specified for Non-AI instruction');
            }

            // Check if the Non AI action has file_upload_action
            // For test_segment instructions, we will get action as run_script action
            if(processedInstruction.action==ACTION_TYPES.RUN_SCRIPT) {
                // Get the script from the instruction args
                const scriptArg = processedInstruction.args?.find((arg: any) => arg.key === "script");
                const scriptVal = scriptArg?.value as string | undefined;

                // If ai_use is always_ai, reroute to AI mode for this instruction
                if (processedInstruction.ai_use === 'always_ai') {
                    // Treat as AI script instruction and execute via AI
                    const aiInstruction = { ...processedInstruction, type: INSTRUCTION_TYPES.AI, action: ACTION_TYPES.SCRIPT } as Instruction;
                    this.browserAgent.setCurrentInstructionId(aiInstruction.id);
                    await this.handleAIInstruction(aiInstruction);
                    return; // Do not proceed with Non-AI path
                }

                // Replace the file_path with the actual file path if script exists
                if (scriptVal && String(scriptVal).length > 0) {
                    let new_script = await this.processFileInstruction(processedInstruction, [scriptVal as string]);
                    // Replace the script in the instruction
                    for(let eachArg of processedInstruction.args || []){
                        if(eachArg.key === "script"){  // Replace the script in the instruction
                            eachArg.value = new_script[0];
                            break;
                        }
                    }
                }
            }

            // Boolean to check if playwright script is already executed
            let playwrightExectued = false;

            // Check if the playwright instructions are already present in the instruction. Only for verification action
            if (processedInstruction.action === ACTION_TYPES.VERIFICATION && processedInstruction.playwright_actions && processedInstruction.playwright_actions.length > 0) {
                let session = await this.containerCommsService.get(this.config.runId);
                let playwrightActions = processedInstruction.playwright_actions;

                if(session){
                    // Initialize playwright_actions if it doesn't exist
                    if (!session.playwright_actions) {
                        session.playwright_actions = {};
                    }
                    // Use instruction.id as the key - store with variables, not substituted values
                    if (processedInstruction.ai_use !== 'always_ai') {
                        session.playwright_actions[processedInstruction.id] = [...playwrightActions];
                        logger.info(`Stored playwright actions with variables for instruction ${instruction.id}: ${JSON.stringify(playwrightActions)}`);
                        await this.containerCommsService.set(this.config.runId, session);
                    }
                }

                // Log playwright instructions present
                await this.containerCommsService.addLog(this.config.runId, {
                    info: 'Playwright script present, running the instruction using playwright script',
                    timestamp: new Date().toISOString(),
                    instructionId: processedInstruction.id
                });
                
                try{
                    // Store playwright actions with variables (not substituted) in Redis
                    session = await this.containerCommsService.get(this.config.runId);
                    
                    // Apply variable substitution to playwright actions for execution only
                    let processedPlaywrightActions = playwrightActions;
                    
                    const actionResponses: ActionResult[] = [];
                    response = await this.executePlaywrightScripts(processedPlaywrightActions, processedInstruction);


                    actionResponses.push(response);

                    this.memory.addExecution({
                        instructionId: processedInstruction.id,
                        browserData: {
                            screenshot: '',
                            urls: []
                        },
                        actionsData: actionResponses
                    });

                    // Add selectors to session. Take it from instruction itself 
                    if (session) {
                        session = await this.containerCommsService.get(this.config.runId);

                        // Initialize selectors if it doesn't exist
                        if (!session.selectors) {
                            session.selectors = {};
                        }
                        // Initialize scripts if it doesn't exist
                        if (!session.scripts) {
                            session.scripts = {};
                        }

                        // If selectors are not rpesent in session
                        if(!session.selectors[instruction.id]){
                            session.selectors[instruction.id] = instruction.selectors;
                        }

                        // Generate script for each selector
                        let scripts: string[] = [];
                        for(let eachSelector of session.selectors[instruction.id]){
                            scripts.push(eachSelector.script);
                        }

                        // Add the result to the session (skip storing if ai_use is always_ai)
                        if (instruction.ai_use !== 'always_ai') {
                            session.scripts[instruction.id] = [...scripts];
                        }

                        await this.containerCommsService.set(this.config.runId, session);
                    }
                }
                catch(error){
                    logger.error(`LitmusAgent: Error executing playwright scripts: ${error}`);
                    await this.containerCommsService.addLog(this.config.runId, {
                        error: `Playwright actions failed to execute`,
                        timestamp: new Date().toISOString(),
                        instructionId: instruction.id
                    });
                }

                playwrightExectued = true;
            }

            // Special Case for verification action. If the locator_type is ai, resolve elementId via LLM
            if (processedInstruction.action === ACTION_TYPES.VERIFICATION && !playwrightExectued) {
                
                const locatorType = processedInstruction.args?.find((arg: any) => arg.key === "locator_type")?.value;
                const target = processedInstruction.args?.find((arg: any) => arg.key === "target")?.value;
                if (locatorType === "ai" && target !== "page") {                 // If target is page we do not need to make any LLM call
                    logger.info('Resolving elementId for verification via LLM');
                    const elementId = await this.getElementIdForVerification(processedInstruction);
                    if (elementId === null) {
                        // Element not found - create a failed response and return early
                        logger.info('Element not found for verification - creating failed response');
                        response.success = false;
                        response.error = 'Element not found for verification';
                        response.warning = 'The specified element could not be located on the page';
                        
                        // Add to memory
                        this.memory.addExecution({
                            instructionId: processedInstruction.id,
                            browserData: { 
                                screenshot: '',
                                urls: []
                            },
                            actionsData: [response]
                        });
                        
                        
                        
                        
                        return; // Exit early without executing further actions
                    }
                    // Attach elementId to the action props so ActionHandler can use it
                    processedInstruction.args = processedInstruction.args || [];
                    processedInstruction.args.push({ key: 'elementId', value: elementId });
                }
            }

            if(!playwrightExectued){
                // Convert instruction args to action properties
                const actionProps = processedInstruction.args?.reduce((acc, arg) => ({
                    ...acc,
                    [arg.key]: arg.value
                }), {}) || {};

                const action = {
                    type: processedInstruction.action as ActionType,
                    ...actionProps,
                    instruction: processedInstruction
                } as Action;

                // Log executing action
                const actionParams = Object.entries(actionProps).map(([key, value]) => `${key}: ${value}`).join(', ');
                await this.containerCommsService.addLog(this.config.runId, {
                    info: `Executing Action : ${processedInstruction.action} with params: {${actionParams}}`,
                    timestamp: new Date().toISOString(),
                    instructionId: processedInstruction.id
                });

                response = await this.browserAgent.executeAction(action);

                // Check if the response has selectors, scripts
                if(response.selectors || response.scripts){
                    logger.info(`LitmusAgent: Verification Response has selectors or scripts: ${JSON.stringify(response)}`);
                    // Store selectors and scripts in Redis
                    const session = await this.containerCommsService.get(this.config.runId);
                    if(session){
                        // Initialize selectors if it doesn't exist
                        if (!session.selectors) {
                            session.selectors = {};
                        }
                        // Initialize scripts if it doesn't exist
                        if (!session.scripts) {
                            session.scripts = {};
                        }
                        session.selectors[processedInstruction.id] = response.selectors?.selectors || [];
                        if (processedInstruction.ai_use !== 'always_ai') {
                            session.scripts[processedInstruction.id] = response.scripts || [];
                        }
                        await this.containerCommsService.set(this.config.runId, session);
                    }
                }

                const currentUrl = await this.browserAgent.getCurrentUrl();
                this.memory.addExecution({
                    instructionId: processedInstruction.id,
                    browserData: { 
                        screenshot: response.screenshot?.toString() || '',
                        urls: [currentUrl]
                    },
                    actionsData: [response]
                });
            }
            
            // Log action executed successfully
            const successMessage = response.success ? 'executed successfully' : 'failed';
            const errorMessage = response.error ? `. Error: ${response.error}` : '';
            
            if(response.success){
                logger.info(`Action ${processedInstruction.action} ${successMessage}${errorMessage}`);
                await this.containerCommsService.addLog(this.config.runId, {
                    info: `Action ${processedInstruction.action} ${successMessage}${errorMessage}`,
                    timestamp: new Date().toISOString(),
                    instructionId: processedInstruction.id
                });
            }
            else{
                logger.error(`Action ${processedInstruction.action} ${errorMessage}`);
                await this.containerCommsService.addLog(this.config.runId, {
                    error: `Action ${processedInstruction.action} ${successMessage}${errorMessage}`,
                    timestamp: new Date().toISOString(),
                    instructionId: processedInstruction.id
                });
            }

            const currentUrl = await this.browserAgent.getCurrentUrl();
            this.memory.addExecution({
                instructionId: processedInstruction.id,
                browserData: { 
                    screenshot: response.screenshot?.toString() || '',
                    urls: [currentUrl]
                },
                actionsData: [response]
            });

            // Add warning to logs if present
            if (response.warning) {
                await this.containerCommsService.addLog(this.config.runId, {
                    warning: response.warning,
                    timestamp: new Date().toISOString(),
                    instructionId: processedInstruction.id
                });
            }

            // Update playwright actions in Redis
            const successSession = await this.containerCommsService.get(this.config.runId);
            if (successSession) {
                // Initialize playwright_actions if it doesn't exist
                if (!successSession.playwright_actions) {
                    successSession.playwright_actions = {};
                }
                if (!successSession.playwright_actions[processedInstruction.id]) {
                    if (processedInstruction.ai_use !== 'always_ai') {
                        const newActions = this.browserAgent.getPlaywrightActionsForInstruction(processedInstruction.id);
                        successSession.playwright_actions[processedInstruction.id] = [...newActions];
                        await this.containerCommsService.set(this.config.runId, successSession);
                    }
                }
            }
        } catch (error) {
            logger.error(`Error executing Non-AI instruction ${processedInstruction.id}:`, error);
            throw error;
        }
    }

    // Dedicated flow to resolve elementId for verification when locator_type === 'ai'
    private async getElementIdForVerification(instruction: Instruction): Promise<number | null> {
        // For verification actions, include non-interactable elements with text
        const addNonInteractable = instruction.action === ACTION_TYPES.VERIFICATION && instruction.args?.find((arg: any) => arg.key === 'property')?.value === VERIFICATION_ELEMENT_PROPERTIES.VERIFY_TEXT;
        logger.info(`Add non interactable in LitmusAgent: ${addNonInteractable}`);

        // Acquire LLM inputs (elements, url, screenshot)
        const llmInputs = await this.browserAgent['llmInputs']?.getInputs(instruction.action as ActionType, addNonInteractable);
        if (!llmInputs) {
            throw new Error('Failed to get LLM inputs');
        }

        if (!this.llmAgent) {
            throw new Error('LLM Agent not initialized');
        }

        logger.info(`Verify Action LLM inputs: ${JSON.stringify(llmInputs)}`);

        // Create message manager and init message for verification
        const messageManager = new MessageManager();
        messageManager.createInitMessage(ACTION_TYPES.VERIFICATION as string);

        // Use the same instruction JSON message format
        const instructionMessage = LLMAgent.generateInstructionMessage(instruction);
        messageManager.addUserMessage(instructionMessage, true);

        // Add vision message
        const visionMessage = LLMAgent.generateVisionMessage(llmInputs);
        if (llmInputs.screenshot === '') {
            // warn but proceed without image
            await this.containerCommsService.addLog(this.config.runId, {
                info: 'Failed to capture screenshot. Agent response may not be accurate',
                timestamp: new Date().toISOString(),
                instructionId: instruction.id
            });
            visionMessage.pop();
        }
        messageManager.addUserMessage(visionMessage);

        // Print llm messages
        //logger.info(`Verify Action LLM messages: ${JSON.stringify(messageManager.getMessages())}`);

        // Call LLM to select element for verification. We expect a regular AgentOutput-like response
        const llmResponse = await this.llmAgent.invokeWithTools(messageManager.getMessages(), {
            runId: this.config.runId,
            instructionId: instruction.id,
            containerCommsService: this.containerCommsService
        });

        // Print llm response
        logger.info(`Verify Action LLM response: ${JSON.stringify(llmResponse)}`);


        // Check if LLM response indicates element not found
        if (!llmResponse.Actions || llmResponse.Actions.length === 0) {
                
            // Add error log about script generation
            await this.containerCommsService.addLog(this.config.runId, {
                error: 'Agent is unable to find the element. If the element is not expected to be in the viewport, use manual locator for verification, or Run Script instruction for execution.',
                timestamp: new Date().toISOString(),
                instructionId: instruction.id
            });
            
            // Return null to fail the test (cannot generate script)
            return null;
        }

        // Check if the LLM response has an error. If the error is not captured in the above check
        if (llmResponse.hasError()) {
            const errorMessage = llmResponse.getErrorMessage() || 'Unknown AI Agent error';
            await this.containerCommsService.addLog(this.config.runId, {
                error: errorMessage,
                timestamp: new Date().toISOString(),
                instructionId: instruction.id
            });
            throw new Error(errorMessage);
        }
        
        // Update AI credits in Redis if LLM call was successful
        // Only increment if: no ParsingError, no error, Actions length > 0
        const isLLMCallSuccessful = !llmResponse.ParsingError && 
                                   !llmResponse.hasError() && 
                                   llmResponse.Actions && 
                                   llmResponse.Actions.length > 0;
        
        if (isLLMCallSuccessful) {
            await this.updateAiCreditsInRedis(AI_CREDIT_UNIT);
        }

        // Log agent response
        const agentResponseText = this.formatAgentResponse(llmResponse);
        logger.info(`${agentResponseText}`);
        if(llmResponse.hasError() || (!llmResponse.Actions || llmResponse.Actions.length === 0)){
            await this.containerCommsService.addLog(this.config.runId, {
                error: `${agentResponseText}`,
                timestamp: new Date().toISOString(),
                instructionId: instruction.id
            });
        } else {
            await this.containerCommsService.addLog(this.config.runId, {
                info: `${agentResponseText}`,
                timestamp: new Date().toISOString(),
                instructionId: instruction.id
            });
        }

        // Log actions generated by LLM
        if (llmResponse.Actions && llmResponse.Actions.length > 0) {
            const actionsList = llmResponse.Actions.map((action: any, index: number) => 
                `${index + 1}. ${action.type}${action.text ? `: ${action.text}` : ''}${action.selector ? ` (selector: ${action.selector})` : ''}`
            ).join(', ');
            logger.info(`LitmusAgent: Actions generated: ${actionsList}`);
            await this.containerCommsService.addLog(this.config.runId, {
                info: `Actions generated: ${actionsList}`,
                timestamp: new Date().toISOString(),
                instructionId: instruction.id
            });
        }

        // Expect one action with elementId
        const actionWithElement = llmResponse.Actions?.find((a: any) => typeof a.elementId !== 'undefined' || typeof a.element_id !== 'undefined');
        if (!actionWithElement) {
            logger.info('No action with elementId found');

            // Log error
            await this.containerCommsService.addLog(this.config.runId, {
                error: 'No action with elementId found',
                timestamp: new Date().toISOString(),
                instructionId: instruction.id
            });
            throw new Error('No action with elementId found');
        }

        const elementId = actionWithElement.elementId || null;
        return elementId;
    }


    private async handleAIInstruction(instruction: Instruction): Promise<void> {
        logger.info('Handling AI instruction');
        
        // Apply variable substitution to instruction if variablesDict is provided
        let processedInstruction = instruction;
        if (this.config.variablesDict) {
            const dataDrivenVariables = this.config.variablesDict.data_driven_variables || {};
            const environmentVariables = this.config.variablesDict.environment_variables || {};
            
            if (Object.keys(dataDrivenVariables).length > 0 || Object.keys(environmentVariables).length > 0) {
                logger.info(`Applying variable substitution to instruction with data-driven variables: ${JSON.stringify(dataDrivenVariables)}`);
                logger.info(`Applying variable substitution to instruction with environment variables: ${JSON.stringify(environmentVariables)}`);
                processedInstruction = substituteVariablesInInstruction(instruction, dataDrivenVariables, environmentVariables);
                logger.info(`Instruction after variable substitution: ${JSON.stringify(processedInstruction)}`);
            }
        }
        
        let session = await this.containerCommsService.get(this.config.runId);
        // const playwrightActions = session?.instructions[instruction.id].playwright_actions;
        const playwrightActions = processedInstruction.playwright_actions? processedInstruction.playwright_actions : [];
        // logger.info(`Session: ${JSON.stringify(session)}`);
        logger.info(`Playwright actions: ${JSON.stringify(playwrightActions)}`);
        if (playwrightActions && playwrightActions.length > 0) {
            // Log playwright instructions present
            await this.containerCommsService.addLog(this.config.runId, {
                info: 'Playwright script present, running the instruction using playwright scripts',
                timestamp: new Date().toISOString(),
                instructionId: instruction.id
            });
            
            try{
                // Store playwright actions with variables (not substituted) in Redis
                session = await this.containerCommsService.get(this.config.runId);
                if (session) {
                    // Initialize playwright_actions if it doesn't exist
                    if (!session.playwright_actions) {
                        session.playwright_actions = {};
                    }
                    // Use instruction.id as the key - store with variables, not substituted values
                    session.playwright_actions[instruction.id] = [...playwrightActions];
                    logger.info(`Stored playwright actions with variables for instruction ${instruction.id}: ${JSON.stringify(playwrightActions)}`);
                    await this.containerCommsService.set(this.config.runId, session);
                }
                
                // Apply variable substitution to playwright actions for execution only
                let processedPlaywrightActions = playwrightActions;
                if (this.config.variablesDict) {
                    const dataDrivenVariables = this.config.variablesDict.data_driven_variables || {};
                    const environmentVariables = this.config.variablesDict.environment_variables || {};
                    
                    if (Object.keys(dataDrivenVariables).length > 0 || Object.keys(environmentVariables).length > 0) {
                        logger.info(`Applying variable substitution to playwright actions for execution with data-driven variables: ${JSON.stringify(dataDrivenVariables)}`);
                        logger.info(`Applying variable substitution to playwright actions for execution with environment variables: ${JSON.stringify(environmentVariables)}`);
                        processedPlaywrightActions = substituteVariablesInArray(playwrightActions, dataDrivenVariables, environmentVariables);
                        logger.info(`Playwright actions after variable substitution for execution: ${JSON.stringify(processedPlaywrightActions)}`);
                    }
                }
                
                const actionResponses: ActionResult[] = [];
                const result = await this.executePlaywrightScripts(processedPlaywrightActions, processedInstruction);
                actionResponses.push(result);

                this.memory.addExecution({
                    instructionId: instruction.id,
                    browserData: {
                        screenshot: '',
                        urls: []
                    },
                    actionsData: actionResponses
                });

                // Add selectors to session. Take it from instruction itself 
                session = await this.containerCommsService.get(this.config.runId);
                if (session) {
                    // If selectors are not rpesent in session
                    if(!session.selectors[instruction.id]){
                        session.selectors[instruction.id] = instruction.selectors;
                    }

                    // Generate script for each selector
                    let scripts: string[] = [];
                    for(let eachSelector of session.selectors[instruction.id]){
                        scripts.push(eachSelector.script);
                    }

                    // Add the result to the session (skip storing if ai_use is always_ai or action is ai_assert)
                    if (instruction.ai_use !== 'always_ai' && instruction.action !== ACTION_TYPES.ASSERT) {
                        session.scripts[instruction.id] = [...scripts];
                    }

                    await this.containerCommsService.set(this.config.runId, session);
                }
            }
            catch(error){
                logger.error(`LitmusAgent: Error executing playwright scripts: ${error}`);
                await this.containerCommsService.addLog(this.config.runId, {
                    error: `Playwright actions failed to execute`,
                    timestamp: new Date().toISOString(),
                    instructionId: instruction.id
                });
            }

        } else {
            const llmInputs = await this.browserAgent.getLLMInputs()?.getInputs(instruction.action as ActionType);
            if (!llmInputs) {
                throw new Error('Failed to get LLM inputs');
            }

        if (!this.llmAgent) {
            throw new Error('LLM Agent not initialized');
        }

        // Create message manager
        const messageManager = new MessageManager();
        // Add init message
        messageManager.createInitMessage(instruction.action as string);

        // Get page content if action is ai_verify
        let pageContent = '';
        if (instruction.action === ACTION_TYPES.VERIFY) {
            try {
                pageContent = await this.browserAgent.getPageContent();
                logger.info('Successfully scraped page content for ai_verify action');
            } catch (error) {
                logger.error('Failed to scrape page content:', error);
                throw new Error('Failed to scrape page content for verification');
            }
        }

        if (instruction.action === ACTION_TYPES.SCRIPT) {
            try {
                pageContent = await this.browserAgent.getCleanedPageContent();
                logger.info('Successfully scraped and cleaned page content for ai_script action');
                logger.info(`Cleaned HTML length: ${pageContent.length} characters`);
            } catch (error) {
                logger.error('Failed to scrape and clean page content:', error);
                throw new Error('Failed to scrape and clean page content for script');
            }
        }

            // Add user message as first message
        const instructionMessage = LLMAgent.generateInstructionMessage(processedInstruction, pageContent);
        messageManager.addUserMessage(instructionMessage, true);

        if (instruction.action === ACTION_TYPES.SCRIPT){
            const contentMessage = LLMAgent.generateContentMessage(processedInstruction, pageContent);
            messageManager.addUserMessage(contentMessage);
        }

        // Format message for vision model
        const visionMessage = LLMAgent.generateVisionMessage(llmInputs);

        // Remove the screenshot from the llmInputs if screenshot is empty string
        if(llmInputs.screenshot==''){
            // Add log to Redis
            await this.containerCommsService.addLog(this.config.runId, {
                info: 'Failed to capture screenshot. Agent response may not be accurate',  // TODO: Update this to warning
                timestamp: new Date().toISOString(),
                instructionId: instruction.id
            });

            // Remove the screenshot from the vision message
            visionMessage.pop();
        }

        messageManager.addUserMessage(visionMessage);

        // Log instruction being sent to LLM
        const instructionDescription = this.createInstructionDescription(processedInstruction);
        await this.containerCommsService.addLog(this.config.runId, {
            info: `Initiating element identification for action: '${instructionDescription}'`,
            timestamp: new Date().toISOString(),
            instructionId: instruction.id
        });

    //    logger.info('LLM Inputs:' + JSON.stringify(messageManager.getMessages(), null, 2));

        // Use invokeWithTools to ensure proper JSON response format
        const llmResponse = await this.llmAgent.invokeWithTools(messageManager.getMessages(), {
            runId: this.config.runId,
            instructionId: instruction.id,
            containerCommsService: this.containerCommsService,
            agent: instruction.action
        });
        
        // Log LLM response received
        await this.containerCommsService.addLog(this.config.runId, {
            info: `Element identification completed for instruction: '${instructionDescription}'`,
            timestamp: new Date().toISOString(),
            instructionId: instruction.id
        });
        
        // Check for various types of errors in LLM response and log them to Redis
        if (llmResponse.ParsingError) {
            const errorMessage = `AI Agent Error: ${llmResponse.Reasoning || 'Failed to parse AI Agent response'}`;
            // await this.containerCommsService.addLog(this.config.runId, {
            //     error: errorMessage,
            //     timestamp: new Date().toISOString(),
            //     instructionId: instruction.id
            // });
            throw new Error(errorMessage);
        }

        if (llmResponse.Warning && llmResponse.Warning.trim() !== '') {
            await this.containerCommsService.addLog(this.config.runId, {
                warning: `Agent Message: ${llmResponse.Warning}`,
                timestamp: new Date().toISOString(),
                instructionId: instruction.id
            });
        }
        
        // Update AI credits in Redis if LLM call was successful
        // Only increment if: no ParsingError, no error, Actions length > 0, and playwright actions not already executed
        const isLLMCallSuccessful = !llmResponse.ParsingError && 
                                   !llmResponse.hasError() && 
                                   llmResponse.Actions && 
                                   llmResponse.Actions.length > 0;
        
        if (isLLMCallSuccessful) {
            await this.updateAiCreditsInRedis(AI_CREDIT_UNIT);
        }

        // Check if no actions were generated
        if (!llmResponse.Actions || llmResponse.Actions.length === 0) {
            const errorMessage = `No actions generated`;
            await this.containerCommsService.addLog(this.config.runId, {
                error: errorMessage,
                timestamp: new Date().toISOString(),
                instructionId: instruction.id
            });

            throw new Error(errorMessage);
        }
        
        // Log agent response
        const agentResponseText = this.formatAgentResponse(llmResponse);
        logger.info(`${agentResponseText}`);
        if(llmResponse.hasError() || (!llmResponse.Actions || llmResponse.Actions.length === 0)){
            await this.containerCommsService.addLog(this.config.runId, {
                error: `${agentResponseText}`,
                timestamp: new Date().toISOString(),
                instructionId: instruction.id
            });
        } else {
            await this.containerCommsService.addLog(this.config.runId, {
                info: `${agentResponseText}`,
                timestamp: new Date().toISOString(),
                instructionId: instruction.id
            });
        }
        
        // Log actions generated by LLM
        if (llmResponse.Actions && llmResponse.Actions.length > 0) {
            const actionsList = llmResponse.Actions.map((action: any, index: number) => 
                `${index + 1}. ${action.type}${action.text ? `: ${action.text}` : ''}${action.selector ? ` (selector: ${action.selector})` : ''}`
            ).join(', ');
            logger.info(`LitmusAgent: Actions generated: ${actionsList}`);
            await this.containerCommsService.addLog(this.config.runId, {
                info: `Actions generated: ${actionsList}`,
                timestamp: new Date().toISOString(),
                instructionId: instruction.id
            });
        }
        
        // Log LLM response
        // logger.info('LLM Response:', {
        //     reasoning: llmResponse.Reasoning,
        //     actions: llmResponse.Actions,
        //     warning: llmResponse.Warning
        // });

        // Check for any error in LLM response
        if (llmResponse.hasError()) {
            const errorMessage = llmResponse.getErrorMessage() || 'Unknown AI Agent error';
            // Add error to logs
            logger.error(`LitmusAgent: Error in LLM response: ${errorMessage}`);
            await this.containerCommsService.addLog(this.config.runId, {
                error: errorMessage,
                timestamp: new Date().toISOString(),
                instructionId: instruction.id
            });
            throw new Error(errorMessage);
        }

            // Set the original instruction (with variables) in the ActionHandler for playwright code generation
            if (this.browserAgent.getActionHandler()) {
                logger.info(`Setting original instruction: ${JSON.stringify(instruction)}`);
                this.browserAgent.getActionHandler()!.setOriginalInstruction(instruction);
            }

            const actionsResponses: ActionResult[] = [];
            for (const action of llmResponse.Actions) {
                // Log the action being executed
                const actionParams = Object.entries(action).filter(([key]) => key !== 'type').map(([key, value]) => `${key}: ${value}`).join(', ');
                logger.info(`LitmusAgent: Executing Action : ${action.type} with params: {${actionParams}}`);
                await this.containerCommsService.addLog(this.config.runId, {
                    info: `Executing Action : ${action.type} with params: {${actionParams}}`,
                    timestamp: new Date().toISOString(),
                    instructionId: instruction.id
                });

                // Convert instruction args to action properties (for execution - with substituted values)
                const actionProps = processedInstruction.args?.reduce((acc, arg) => ({
                    ...acc,
                    [arg.key]: arg.value
                }), {}) || {};

            // For ai_verify action, add validation and code from LLM response
            // For ai_assert action, only add validation and reasoning (no code generation)
            const fullAction = {
                ...action,
                ...actionProps,
                ...(action.type === ACTION_TYPES.VERIFY && llmResponse.Assert && 'code' in llmResponse.Assert ? {
                    validation: llmResponse.Assert.validation,
                    code: llmResponse.Assert.code,
                    ...(llmResponse.Assert.reasoning && { reasoning: llmResponse.Assert.reasoning })
                } : {}),
                ...(action.type === ACTION_TYPES.ASSERT && llmResponse.Assert ? {
                    validation: llmResponse.Assert.validation,
                    ...(llmResponse.Assert.reasoning && { reasoning: llmResponse.Assert.reasoning })
                } : {})
            } as Action;

                // Execute the action with substituted values
                logger.info(`LitmusAgent: Executing action: ${JSON.stringify(fullAction)}`);
                const response = await this.browserAgent.executeAction(fullAction);
                
                // Log action executed successfully
                const successMessage = response.success ? 'executed successfully' : 'failed';
                const errorMessage = response.error ? `. Error: ${response.error}` : '';
                if(response.success){
                    logger.info(`LitmusAgent: Action ${action.type} ${successMessage}`);
                    await this.containerCommsService.addLog(this.config.runId, {
                        info: `Action ${action.type} ${successMessage}${errorMessage}`,
                        timestamp: new Date().toISOString(),
                        instructionId: instruction.id
                    });
                }
                else{
                    logger.error(`LitmusAgent: Action ${action.type} ${errorMessage}`);
                    await this.containerCommsService.addLog(this.config.runId, {
                        error: `Action ${action.type} ${successMessage}${errorMessage}`,
                        timestamp: new Date().toISOString(),
                        instructionId: instruction.id
                    });
                }
                
                actionsResponses.push(response);
            }

            const currentUrl = await this.browserAgent.getCurrentUrl();
            this.memory.addExecution({
                instructionId: instruction.id,
                browserData: { 
                    screenshot: actionsResponses[actionsResponses.length - 1]?.screenshot?.toString() || '',
                    urls: [currentUrl]
                },
                llmData: {
                    actions: llmResponse.Actions as Action[],
                    reasoning: llmResponse.Reasoning
                },
                actionsData: actionsResponses
            });

            // Store playwright actions and selectors in Redis after execution
            session = await this.containerCommsService.get(this.config.runId);
            if (session) {
                await this.addInstructionDetailsToSession(instruction, actionsResponses, session);
                await this.containerCommsService.set(this.config.runId, session);
            }
        }
        logger.info('AI instruction handled');
        
        session = await this.containerCommsService.get(this.config.runId);
        if (session.reset === true) {
            await this.handleReset(this.taskIndex);
            return;
        }
    }

    private async addGoalInstructionsToSession(goalId: string, instructions: Instruction[], actionsResponses: ActionResult[], session: any): Promise<void> {
        // check if session has a goal instructions key
        if(!session.goal_details){
            session.goal_details = {};

        }
        // check if the goal id is present in the goal details
        if(!session.goal_details[goalId]){
            session.goal_details[goalId] = {
                instructions: [],
                actionsResponses: []
            };
        }
        // add the instruction to the goal instructions key
        session.goal_details[goalId].instructions = instructions;
        // add the actions responses to the goal instructions key
        session.goal_details[goalId].actionsResponses = actionsResponses;
        
    }

    private async addInstructionDetailsToSession(instruction: Instruction, actionsResponses: ActionResult[], session: any): Promise<void> {
        
        // const session = await this.containerCommsService.get(this.config.runId);
        const newActions = this.browserAgent.getPlaywrightActionsForInstruction(instruction.id);
        // Use instruction.id as the key - store with variables, not substituted values

        if(!session.playwright_actions) {
            session.playwright_actions = {};
        }
        // Skip storing playwright actions for always_ai or ai_assert actions
        if (instruction.ai_use !== 'always_ai' && instruction.action !== ACTION_TYPES.ASSERT) {
            session.playwright_actions[instruction.id] = [...newActions];
        }
        
        // Store selectors for this instruction
        if (!session.selectors) {
            session.selectors = {};
        }
        
        // Collect selectors from all action responses for this instruction
        const instructionSelectors: Array<{selector: string, display: string}> = [];
        actionsResponses.forEach(response => {
            if (response.selectors && response.selectors.selectors) {
                instructionSelectors.push(...response.selectors.selectors);
            }
        });
        
        if (instructionSelectors.length > 0) {
            session.selectors[instruction.id] = instructionSelectors;
            logger.info(`Stored ${instructionSelectors.length} selectors for instruction ${instruction.id}`);
        }

        // Store scripts for this instruction
        if (!session.scripts) {
            session.scripts = {};
        }
        
        // Collect scripts from all action responses for this instruction
        const instructionScripts: string[] = [];
        actionsResponses.forEach(response => {
            if ((response as any).scripts && Array.isArray((response as any).scripts)) {
                instructionScripts.push(...(response as any).scripts);
            }
        });
        
        // Skip storing scripts for always_ai or ai_assert actions
        if (instructionScripts.length > 0 && instruction.ai_use !== 'always_ai' && instruction.action !== ACTION_TYPES.ASSERT) {
            session.scripts[instruction.id] = instructionScripts;
            logger.info(`Stored ${instructionScripts.length} scripts for instruction ${instruction.id}`);
        }
    }


    private async handleGoalInstruction(goalId: string, prompt: string, actionType?: string | undefined): Promise<{completionStatus: string, generatedInstructions: any[], actionsResponses: ActionResult[]}> {
        try {
            if (!this.llmAgent) {
                throw new Error('LLM Agent not initialized');
            }

            await this.containerCommsService.addLog(this.config.runId, {
                info: `Starting goal execution: '${prompt}'`,
                timestamp: new Date().toISOString(),
                instructionId: goalId
            });

            let goalCompleted = false;
            let stepCount = 0;
            const maxSteps = 25; // Prevent infinite loops
            
            // Create history message list to track all previous actions and results
            const historyMessages: string[] = [];
            
            // Array to store generated instructions for Redis
            const generatedInstructions: any[] = [];

            // Array to store action responses for Redis
            const actionsResponses: ActionResult[] = [];

            // Set goalId to the current instructionId
            this.browserAgent.setCurrentInstructionId(goalId);

            // Create goal instruction
            const goalInstruction = {
                action: ACTION_TYPES.GOAL,
                prompt: prompt
            } as Instruction;

            while (!goalCompleted && stepCount < maxSteps) {
                stepCount++;
                
                // Get current page context - only for AI actions
                let llmInputs;
                try {
                    llmInputs = await this.browserAgent.getLLMInputs()?.getInputs(ACTION_TYPES.GOAL as ActionType);
                }
                catch(error){
                    logger.error('Failed to get LLM inputs:', error);
                    // For non-AI actions, create minimal inputs
                    llmInputs = {
                        elements: [],
                        currentUrl: await this.browserAgent.getCurrentUrl(),
                        screenshot: ''
                    };
                }

                // Create message manager and init message for goal instruction
                const messageManager = new MessageManager();
                messageManager.createInitMessage(ACTION_TYPES.GOAL as string);

                // Add user message with the goal instruction
                // TODO: Instrcution should added like a string not as a json.
                const instructionMessage = LLMAgent.generateInstructionMessage(goalInstruction);
                messageManager.addUserMessage(instructionMessage, true);

                                    
                messageManager.addUserMessage("=== CURRENT PAGE CONTEXT ===");

                // Add vision message with current page context - only for AI actions
                if(llmInputs.screenshot !=='' && llmInputs.elements.length>0){
                    const visionMessage = LLMAgent.generateVisionMessage(llmInputs);
                    messageManager.addUserMessage(visionMessage);
                }

                // Add history messages to provide context of previous actions
                if (historyMessages.length > 0) {
                    // Add history separator
                    messageManager.addUserMessage("=== PREVIOUS ACTION HISTORY ===");
                    
                    // Add all history messages
                    historyMessages.forEach(historyMsg => {
                        messageManager.addUserMessage(historyMsg);
                    });
                }

                // Log goal step
                await this.containerCommsService.addLog(this.config.runId, {
                    info: `Goal step ${stepCount}: Generating next action for '${prompt}'`,
                    timestamp: new Date().toISOString(),
                    instructionId: goalId
                });

                // Log LLM inputs
                logger.info('Goal LLM Inputs: ' + JSON.stringify(messageManager.getMessages(), null, 2));

                // Use Goal LLM to generate next action
                const goalResponse = await this.llmAgent.invokeGoalWithTools(messageManager.getMessages(), {
                    runId: this.config.runId,
                    instructionId: goalId,
                    containerCommsService: this.containerCommsService,
                    agent: actionType
                }, actionType);

                logger.info('Goal LLM Response: ' + JSON.stringify(goalResponse, null, 2));
                
                // Update AI credits in Redis if LLM call was successful
                // Every LLM call in Goal Agent is considered for credits increment
                const isLLMCallSuccessful = true;
                
                if (isLLMCallSuccessful) {
                    await this.updateAiCreditsInRedis(AI_CREDIT_UNIT);
                }

                // Check if goal is completed via done tool call
                if ((goalResponse as any).completionStatus) {
                    const completionStatus = (goalResponse as any).completionStatus;
                    goalCompleted = true;
                    
                    // Update goal status in Redis
                    await this.updateGoalStatusInContainerCommsService(goalId, 'completed', completionStatus, goalResponse.Reasoning);
                    
                    if (completionStatus === GoalOutput.SUCCESS) {
                        // Goal completed successfully
                        await this.containerCommsService.addLog(this.config.runId, {
                            info: `Goal completed successfully: '${prompt}'`,
                            timestamp: new Date().toISOString(),
                            instructionId: goalId
                        });
                    } else if (completionStatus === GoalOutput.FAILED) {
                        // Goal failed
                        await this.containerCommsService.addLog(this.config.runId, {
                            error: `Goal failed: '${prompt}'. Reason: ${goalResponse.Reasoning}`,
                            timestamp: new Date().toISOString(),
                            instructionId: goalId
                        });
                    }
                    const currentUrl = await this.browserAgent.getCurrentUrl();
                    const actionsData = actionsResponses.length > 0 ? [actionsResponses[actionsResponses.length - 1]] as ActionResult[] : [];
                    this.memory.addExecution({
                        instructionId: goalId,
                        browserData: { 
                            screenshot: '',
                            urls: [currentUrl]
                        },
                        actionsData: actionsData
                    });
                    return { completionStatus, generatedInstructions, actionsResponses };
                }

                // Log goal response
                await this.containerCommsService.addLog(this.config.runId, {
                    info: `Goal step ${stepCount} response: ${goalResponse.Actions.length > 0 ? 'Action generated' : 'No action generated, Trying again'}`,
                    timestamp: new Date().toISOString(),
                    instructionId: goalId
                });

                // Execute the generated action if there is one, otherwise add response to history and try again
                if (goalResponse.Actions && goalResponse.Actions.length > 0) {
                    const action = goalResponse.Actions[0];
                    
                    // Log the action being executed
                    const actionParams = Object.entries(action).filter(([key]) => key !== 'type').map(([key, value]) => `${key}: ${value}`).join(', ');
                    logger.info(`Goal step ${stepCount}: Executing action ${action.type} with params: {${actionParams}}`);
                    await this.containerCommsService.addLog(this.config.runId, {
                        info: `Goal step ${stepCount}: Executing action ${action.type}`,
                        timestamp: new Date().toISOString(),
                        instructionId: goalId
                    });

                    // Execute the action
                    const fullAction = {
                        ...action,
                    } as Action;

                    logger.info('Executing Goal Action: ' + JSON.stringify(fullAction, null, 2));


                    if (action.type === ACTION_TYPES.VERIFY_EMAIL) {
                        const verifyEmailAction = action as VerifyEmailAction;
                        const emailVerificationService = new EmailVerificationService(
                            this.containerCommsService,
                            this.config.runId,
                            goalId,
                            stepCount
                        );

                        const result = await emailVerificationService.executeVerifyEmailAction(
                            verifyEmailAction.prompt, 
                            5, // retries
                            verifyEmailAction.toEmail, // optional toEmail parameter,
                            {
                                runId: this.config.runId,
                                instructionId: goalId,
                                agent: action.type
                            }
                        );

                        if (result.success && result.verificationType && result.verificationValue) {
                            // Add verification to history messages
                            const verificationHistoryEntry = emailVerificationService.getVerificationHistoryMessage(
                                result.verificationType,
                                result.verificationValue
                            );
                            historyMessages.push(verificationHistoryEntry);

                            // Continue to next iteration to let the goal agent process the verification
                            continue;
                        } else {
                            historyMessages.push(`Step ${stepCount}: ${action.type} - No verification info found or error occurred`);
                            // Continue to next iteration if no verification found or error occurred
                            continue;
                        }
                    }

                    // Handle AI Script action - invoke AI Script Agent to generate and execute script
                    if (action.type === ACTION_TYPES.SCRIPT) {
                        try {
                            // Cast action to get prompt property
                            const scriptAction = action as any;
                            
                            // Create ai_script instruction to pass to handleAIInstruction
                            const aiScriptInstruction: Instruction = {
                                id: goalId,
                                action: ACTION_TYPES.SCRIPT,
                                args: [
                                    { key: 'prompt', value: scriptAction.prompt || 'Generate script' }
                                ],
                                prompt: scriptAction.prompt || 'Generate script',
                                type: 'AI'
                            };

                            // Call handleAIInstruction to invoke AI Script Agent
                            await this.handleAIInstruction(aiScriptInstruction);

                            // Get the generated script from BrowserAgent's memory
                            // The AI Script Agent stores the script in BrowserAgent.memory.playwrightScripts
                            const playwrightScripts = this.browserAgent.getPlaywrightActionsForInstruction(goalId);

                            logger.info(`Looking for goal ID: ${goalId}`);
                            logger.info(`All playwright scripts: ${JSON.stringify(this.browserAgent.getPlaywrightActions())}`);
                            logger.info(`Playwright scripts for goal: ${JSON.stringify(playwrightScripts)}`);
                            
                            // Check if scripts were generated
                            if (!playwrightScripts || playwrightScripts.length === 0) {
                                historyMessages.push(`Step ${stepCount}: ${action.type} - Script generation failed: No script was generated`);
                                historyMessages.push(`Result: FAILED - Unable to generate script`);
                                
                                await this.containerCommsService.addLog(this.config.runId, {
                                    error: `Goal step ${stepCount}: AI Script generation failed - No script generated`,
                                    timestamp: new Date().toISOString(),
                                    instructionId: goalId
                                });
                                
                                continue;
                            }
                            
                            // Get the generated script (use the first one)
                            const generatedScript: string = playwrightScripts[0];

                            if (generatedScript && generatedScript.length > 0) {
                                // Create ai_script instruction with the generated script
                                const scriptInstructionId = uuidv4();
                                const scriptInstruction = {
                                    id: scriptInstructionId,
                                    action: ACTION_TYPES.SCRIPT,
                                    args: [
                                        { key: 'script', value: generatedScript }
                                    ],
                                    prompt: scriptAction.prompt || 'Generated script',
                                    type: 'AI',
                                    playwright_actions: [generatedScript],
                                    status: TASK_STATUS.SUCCESS
                                } as Instruction;

                                // Store the ai_script instruction in generatedInstructions
                                generatedInstructions.push(scriptInstruction);
                                
                                // Store instruction in Redis (matching other instructions)
                                await this.storeGoalInstructionInContainerCommsService(goalId, scriptInstruction);
                                
                                // Add to history - Note: handleAIInstruction already generated AND executed the script
                                // Include the script prompt so LLM knows what the script was supposed to accomplish
                                const scriptPrompt = scriptAction.prompt || 'Generated script';
                                historyMessages.push(`Step ${stepCount}: ${action.type} - Script generated and executed successfully`);
                                historyMessages.push(`Script purpose: ${scriptPrompt}`);
                                historyMessages.push(`Result: SUCCESS - ${action.type} completed. The script was generated and executed.`);

                                // Log the script generation
                                await this.containerCommsService.addLog(this.config.runId, {
                                    info: `Goal step ${stepCount}: AI Script instruction generated successfully`,
                                    timestamp: new Date().toISOString(),
                                    instructionId: goalId
                                });

                                // Clear the goal instruction
                                this.browserAgent.clearPlaywrightScriptsForInstruction(goalId);

                                logger.info(`After deletion of playwright scripts for goal ID: ${goalId}, playwright scripts: ${JSON.stringify(this.browserAgent.getPlaywrightActions())}`);

                                // Continue to next iteration
                                continue;
                            } else {
                                // Script generation failed
                                historyMessages.push(`Step ${stepCount}: ${action.type} - Script generation failed`);
                                historyMessages.push(`Result: FAILED - Unable to generate script`);
                                
                                await this.containerCommsService.addLog(this.config.runId, {
                                    error: `Goal step ${stepCount}: AI Script generation failed`,
                                    timestamp: new Date().toISOString(),
                                    instructionId: goalId
                                });
                                
                                continue;
                            }
                        } catch (error) {
                            logger.error('AI Script Agent failed:', error);
                            historyMessages.push(`Step ${stepCount}: ${action.type} - AI Script Agent error: ${error}`);
                            historyMessages.push(`Result: FAILED - AI Script Agent error`);
                            
                            await this.containerCommsService.addLog(this.config.runId, {
                                error: `Goal step ${stepCount}: AI Script Agent error: ${error}`,
                                timestamp: new Date().toISOString(),
                                instructionId: goalId
                            });
                            
                            continue;
                        }
                    }

                    const response = await this.browserAgent.executeAction(fullAction);

                    // Log action result
                    const successMessage = response.success ? 'executed successfully' : 'failed';
                    const errorMessage = response.error ? `. Error: ${response.error}` : '';
                    
                    // Add action and result to history
                    const actionHistoryEntry = `Step ${stepCount}: ${action.type} - ${actionParams}`;
                    const resultHistoryEntry = response.success 
                        ? `Result: SUCCESS - ${action.type} completed`
                        : `Result: FAILED - ${response.error}`;
                                        
                    historyMessages.push(actionHistoryEntry);
                    historyMessages.push(resultHistoryEntry);
                    
                    if (response.success) {
                        logger.info(`Goal step ${stepCount}: Action ${action.type} ${successMessage}`);
                        await this.containerCommsService.addLog(this.config.runId, {
                            info: `Goal step ${stepCount}: Action ${action.type} ${successMessage}`,
                            timestamp: new Date().toISOString(),
                            instructionId: goalId
                        });
                    } else {
                        logger.error(`Goal step ${stepCount}: Action ${action.type} ${errorMessage}`);
                        await this.containerCommsService.addLog(this.config.runId, {
                            error: `Goal step ${stepCount}: Action ${action.type} ${errorMessage}\nAction failed, but continuing to let AI Agent decide next step`,
                            timestamp: new Date().toISOString(),
                            instructionId: goalId
                        });
                        
                        // If action fails, don't throw error - let LLM decide what to do next
                        // The LLM will see the failure in history and can retry or choose a different approach
                        logger.warn(`Action failed, but continuing to let LLM decide next step: ${response.error}`);
                        continue;
                    }

                    // Create instruction object for Redis storage
                    const instructionId = uuidv4();  // generate uuid
                    const instruction = {
                        id: instructionId,
                        action: action.type,
                        args: this.convertActionToArgs(action),
                        prompt: this.generatePromptFromAction(action),
                        type: this.isAIAction(action.type) ? 'AI' : 'Non-AI',
                        status: response.success ? TASK_STATUS.SUCCESS : TASK_STATUS.FAILED,
                        playwright_actions: this.browserAgent.getPlaywrightActionsForInstruction(goalId)
                    };
                    
                    generatedInstructions.push(instruction);
                    actionsResponses.push(response);
                    
                    // Store instruction in Redis
                    await this.storeGoalInstructionInContainerCommsService(goalId, instruction);

                    // Store selectors for this instruction (matching compose mode behavior)
                    let session = await this.containerCommsService.get(this.config.runId);
                    if (session) {
                        // Store selectors for this instruction
                        if (!session.selectors) {
                            session.selectors = {};
                        }
                        
                        // Collect selectors from the action response
                        const instructionSelectors: Array<{selector: string, display: string}> = [];
                        if (response.selectors && response.selectors.selectors) {
                            instructionSelectors.push(...response.selectors.selectors);
                        }
                        
                        if (instructionSelectors.length > 0) {
                            session.selectors[instructionId] = instructionSelectors;
                            logger.info(`Stored ${instructionSelectors.length} selectors for goal instruction ${instructionId}`);
                        }

                        // Store scripts for this instruction
                        if (!session.scripts) {
                            session.scripts = {};
                        }
                        
                        // Collect scripts from the action response
                        const instructionScripts: string[] = [];
                        if ((response as any).scripts && Array.isArray((response as any).scripts)) {
                            instructionScripts.push(...(response as any).scripts);
                        }
                        
                        if (instructionScripts.length > 0) {
                            session.scripts[instructionId] = instructionScripts;
                            logger.info(`Stored ${instructionScripts.length} scripts for goal instruction ${instructionId}`);
                        }
                        
                        await this.containerCommsService.set(this.config.runId, session);
                    }

                    // Clear the playwright actions for the goalID
                    this.browserAgent.clearPlaywrightScriptsForInstruction(goalId);

                    // Wait a bit for page to settle
                    // await new Promise(resolve => setTimeout(resolve, 1000));
                } else {
                    // No action generated - add response to history and try again
                    const responseHistoryEntry = `Step ${stepCount}: AI Agent Response - No action generated, Reasoning: ${goalResponse.Reasoning}`;
                    historyMessages.push(responseHistoryEntry);
                    
                    logger.warn(`Goal step ${stepCount}: No action generated by LLM.`);
                    await this.containerCommsService.addLog(this.config.runId, {
                        info: `Goal step ${stepCount}: No action generated by Goal Agent.`,
                        timestamp: new Date().toISOString(),
                        instructionId: goalId
                    });
                }
            }

            if (!goalCompleted) {
                // Update goal status to failed if max steps exceeded
                await this.updateGoalStatusInContainerCommsService(goalId, 'failed');
                return { completionStatus: GoalOutput.FAILED, generatedInstructions, actionsResponses: actionsResponses };
            }

            // This should never be reached due to the while loop logic, but required for TypeScript
            return { completionStatus: GoalOutput.FAILED, generatedInstructions: generatedInstructions, actionsResponses: actionsResponses };

        } catch (error) {
            logger.error(`Error in handleGoalInstruction: ${error instanceof Error ? error.message : String(error)}`);
            await this.containerCommsService.addLog(this.config.runId, {
                error: `Goal instruction processing failed: ${error instanceof Error ? error.message : String(error)}`,
                timestamp: new Date().toISOString(),
                instructionId: goalId
            });
            return { completionStatus: GoalOutput.FAILED, generatedInstructions: [], actionsResponses: [] };
        }
    }

    private async handleTriageInstruction(
        executedInstructions: any[], 
        upcomingInstructions: any[], 
        failedInstruction: any, 
        playwrightError: string,
        failureData?: any
    ): Promise<any> {
        try {
            if (!this.llmAgent) {
                throw new Error('LLM Agent not initialized');
            }

            await this.containerCommsService.addLog(this.config.runId, {
                info: 'Starting triage analysis',
                timestamp: new Date().toISOString(),
                instructionId: failedInstruction?.id
            });

            // Create message manager for triage
            const messageManager = new MessageManager();
            messageManager.createInitMessage(TRIAGE_MODE);

            // Add all available data in the order specified in the prompt
            const triageInput: string[] = [];

            // Add executed instructions (always present)
            triageInput.push('=== EXECUTED INSTRUCTIONS ===');
            triageInput.push(JSON.stringify(executedInstructions));

            // Add upcoming instructions if any
            if (upcomingInstructions.length > 0) {
                triageInput.push('=== UPCOMING INSTRUCTIONS ===');
                triageInput.push(JSON.stringify(upcomingInstructions));
            }

            // Add failed instruction if any
            if (failedInstruction) {
                triageInput.push('=== FAILED INSTRUCTION ===');
                triageInput.push(JSON.stringify(failedInstruction));
            }

            // Add playwright error if any
            if (playwrightError) {
                triageInput.push('=== PLAYWRIGHT ERROR MESSAGE ===');
                triageInput.push(playwrightError);
            }

            // Add all current run data to message manager
            messageManager.addUserMessage(triageInput.join('\n'));

            // Add current run screenshot (always present)
            try {
                const page = this.browserAgent.getBrowserContext()?.getActivePage();
                if (page) {
                    const screenshotBuffer = await page.screenshot({
                        type: 'png',
                        fullPage: false
                    });
                    const base64Screenshot = screenshotBuffer.toString('base64');
                    messageManager.addUserMessage('=== CURRENT RUN SCREENSHOT ===');
                    const visionMessage = LLMAgent.generateVisionMessageOnly(`data:image/png;base64,${base64Screenshot}`);
                    messageManager.addUserMessage(visionMessage);
                    logger.info('Current run screenshot captured for triage analysis');
                } else {
                    await this.containerCommsService.addLog(this.config.runId, {
                        info: 'No active page available for screenshot. Agent may not be able to analyze the failure',
                        timestamp: new Date().toISOString(),
                        instructionId: failedInstruction?.id
                    });
                    logger.info('No active page available for screenshot');
                }
            } catch (screenshotError) {
                await this.containerCommsService.addLog(this.config.runId, {
                    error: `Screenshot capture failed: ${screenshotError}. Agent may not be able to analyze the failure`,
                    timestamp: new Date().toISOString(),
                    instructionId: failedInstruction?.id
                });
                logger.error('Screenshot capture error:', screenshotError);
            }

            // Add previous failure data if available
            if (failureData) {
                const previousFailureData: string[] = [];

                // Add previous failure instruction if available
                if (failureData.instruction) {
                    previousFailureData.push('=== PREVIOUS FAILURE INSTRUCTION ===');
                    previousFailureData.push(JSON.stringify(failureData.instruction));
                }

                // Add previous failure error message if available
                if (failureData.error) {
                    previousFailureData.push('=== PREVIOUS FAILURE PLAYWRIGHT ERROR MESSAGE ===');
                    previousFailureData.push(failureData.error);
                }

                // Add previous failure data to message manager
                if (previousFailureData.length > 0) {
                    messageManager.addUserMessage(previousFailureData.join('\n'));
                }

                // Add previous failure image if available
                if (failureData.image) {
                    try {
                        messageManager.addUserMessage('=== PREVIOUS FAILURE SCREENSHOT ===');
                        const failureImageMessage = LLMAgent.generateVisionMessageOnly(`data:image/png;base64,${failureData.image}`);
                        messageManager.addUserMessage(failureImageMessage);
                        logger.info('Added failure data image from previous run for triage analysis');
                    } catch (error) {
                        logger.error('Failed to add failure data image:', error);
                    }
                }
            }

            logger.info('Triage LLM Inputs: ' + JSON.stringify(messageManager.getMessages(), null, 2));
            logger.info('Triage LLM Inputs prepared');

            const triageResponse = await this.llmAgent.invokeTriageWithTools(messageManager.getMessages(), {
                runId: this.config.runId,
                instructionId: failedInstruction?.id,
                containerCommsService: this.containerCommsService,
                agent: TRIAGE_MODE
            });

            logger.info('Triage Tool Call Output: ' + JSON.stringify(triageResponse));

            // Update AI credits in Redis for successful triage LLM call
            if (triageResponse && !triageResponse.parsing_error) {
                await this.updateAiCreditsInRedis(TRIAGE_CREDIT_UNIT);
            }

            // Create test result
            const testResult = {
                status: TASK_STATUS.COMPLETED,
                reasoning: triageResponse.reasoning,
                category: triageResponse.category,
                sub_category: triageResponse.sub_category,
                error_instruction: failedInstruction,
                prompt: triageResponse.prompt
            };

            // Note:- Always set category to success on retry on triage run was successful, regardless of what is returned from LLM
            if (!failedInstruction) {
                testResult.category = TRIAGE_CATEGORIES.SUCCESSFUL_ON_RETRY;
                testResult.sub_category = undefined;
            }

            // Add test result to redis
            let session = await this.containerCommsService.get(this.config.runId);
            if(session){
                session.test_result = testResult;
                await this.containerCommsService.set(this.config.runId, session);
            }

            return testResult;

        } catch (error: any) {
            logger.error(`Error in handleTriageInstruction: ${error instanceof Error ? error.message : String(error)}`);
            await this.containerCommsService.addLog(this.config.runId, {
                error: `Triage instruction processing failed: ${error instanceof Error ? error.message : String(error)}`,
                timestamp: new Date().toISOString(),
                instructionId: failedInstruction?.id
            });
            return null;
        }
    }

    private formatAgentResponse(llmResponse: any): string {
        let response = '';
        
        // Add evaluation
        if (llmResponse.Eval) {
            response += `🤷 Eval: ${llmResponse.Eval}`;
        }
        
        // Add memory
        if (llmResponse.Memory) {
            response += ` 🧠 Memory: ${llmResponse.Memory}`;
        }
        
        // Add action reasoning
        if (llmResponse.Reasoning) {
            response += ` 💡 Agent Reasoning: ${llmResponse.Reasoning}`;
        }
        
        // Add actions
        if (llmResponse.Actions && llmResponse.Actions.length > 0) {
            response += ` 🛠️ `;
            llmResponse.Actions.forEach((action: any, index: number) => {
                response += `Action ${index + 1}/${llmResponse.Actions.length}: ${JSON.stringify(action)}`;
                if (index < llmResponse.Actions.length - 1) {
                    response += ' ';
                }
            });
        }
        
        return response;
    }

    private isValidInstruction(instruction: any): instruction is Instruction {
        return (
            typeof instruction === 'object' &&
            instruction !== null &&
            typeof instruction.id === 'string' &&
            typeof instruction.type === 'string' &&
            typeof instruction.action === 'string' &&
            (!instruction.args || Array.isArray(instruction.args))
        );
    }

    private async handleInstructionError(instruction: Instruction, error: Error): Promise<void> {
        this.memory.addError({ instructionId: instruction.id, message: error.message });
        logger.error(`Error on instruction ${instruction.id}: ${error.message}`);
        
        // Log error to Redis
        await this.containerCommsService.addLog(this.config.runId, {
            error: `Error on instruction ${instruction.id}: ${error.message}`,
            timestamp: new Date().toISOString(),
            instructionId: instruction.id
        });
    }

    /**
     * Handle agent reset with optional task index parameter
     * @param taskIndex Optional task index to determine if reset flag should be cleared
     * 
     * Reset flag logic explanation:
     * The reset flag is only set to false when we're at the first instruction (taskIndex === 0) because:
     * 1. When a reset is triggered during the first instruction, it means we want to start fresh
     * 2. Clearing the reset flag at taskIndex 0 ensures we don't get stuck in an infinite reset loop
     * 3. For subsequent instructions, we keep the reset flag true until we complete the reset process
     * 4. This prevents multiple resets from being triggered while a reset is already in progress
     */
    private async handleReset(taskIndex?: number): Promise<void> {
        try {
            logger.info(`[handleReset] Resetting state for run ${this.config.runId}${taskIndex !== undefined ? ` at task index ${taskIndex}` : ''}`);
            
            // Handle reset flag logic
            if (taskIndex !== undefined) {
                const session = await this.containerCommsService.get(this.config.runId);
                if (session && session.reset === true) {
                    if (taskIndex === 0) {
                        // Only set reset flag to false if we're at the first instruction
                        // This prevents infinite reset loops and ensures clean state transitions
                        session.reset = false;
                        await this.containerCommsService.set(this.config.runId, session);
                        logger.info('[handleReset] Reset flag cleared for first instruction');
                    }
                }
            }
            
            // Log reset start
            await this.containerCommsService.addLog(this.config.runId, {
                info: 'Starting agent reset',
                timestamp: new Date().toISOString()
            });
            
            // Reset state
            this.state.reset();
            
            // Reset memory
            this.memory.clear();
            
            // Reset task tracking variables
            this.taskIndex = 0;
            this.completedInstructions = 0;
            this.addedTasks.clear();
            
            // Reset executed code in browser agent
            const actionHandler = this.browserAgent.getActionHandler();
            if (actionHandler) {
                // Clear both current action code and executed code
                actionHandler.clearCurrentActionCode();
                actionHandler.clearExecutedCode();
            }

            // Clear playwright scripts from browser agent
            this.browserAgent.clearPlaywrightScripts();

            // Clear browser data while keeping the session alive
            await this.browserAgent.clearBrowserData();
           
            // Log reset completion
            await this.containerCommsService.addLog(this.config.runId, {
                info: 'Agent reset completed successfully',
                timestamp: new Date().toISOString()
            });
            
            logger.info(`[handleReset] Reset completed`);
        } catch (error) {
            const errorMessage = `Error handling reset: ${error instanceof Error ? error.message : String(error)}`;
            logger.error(errorMessage);
            
            // Log reset error
            await this.containerCommsService.addLog(this.config.runId, {
                error: errorMessage,
                timestamp: new Date().toISOString()
            });
            
            throw error;
        }
    }

    
    // Control methods
    stop(): void {
        this.state.isStopped = true;
        logger.info("Agent stopped");
        process.exit(0);
    }

    /**
     * Reset the shared state to empty object
     */
    resetSharedState(): void {
        this.browserAgent.initializeSharedState();
        logger.info("Shared state reset");
    }

    async clear(): Promise<void> {
        // clear browser data without clearing the memory or other state
        try {
            await this.browserAgent.clearAllData();
            // Reset shared state when clearing
            this.resetSharedState();
            logger.info("All browser data cleared and pages reloaded successfully");
            await this.containerCommsService.addLog(this.config.runId, {
                info: "All browser data cleared and pages reloaded successfully",
                timestamp: new Date().toISOString()
            });
        } catch (error) {
            logger.error(`Error clearing all browser data: ${error instanceof Error ? error.message : String(error)}`);
            await this.containerCommsService.addLog(this.config.runId, {
                error: `Error clearing all browser data: ${error instanceof Error ? error.message : String(error)}`,
                timestamp: new Date().toISOString()
            });
        }
        logger.info("Agent cleared");
    }

    // async cleanup(): Promise<void> {
    //     try {
    //         await this.browserAgent.cleanup();
    //         logger.info("Agent cleaned up successfully");
    //     } catch (error) {
    //         logger.error(`Error during agent cleanup: ${error instanceof Error ? error.message : String(error)}`);
    //         throw error;
    //     }
    // }


    /**
     * Directly executes Playwright scripts
     * @param scripts Array of Playwright script strings to execute
     */
    async executePlaywrightScripts(scripts: string[], instruction: Instruction): Promise<ActionResult> {
        try {
            // Log playwright script execution start
            await this.containerCommsService.addLog(this.config.runId, {
                info: `Starting Playwright script execution: ${scripts.length} script lines`,
                timestamp: new Date().toISOString()
            });

            // Log the current URLs present in the browser
            const currentUrls = await this.browserAgent.getBrowserContext()?.getPages().map(p => p.url());
            if (currentUrls) {
                logger.info(`Current URLs present in the browser: ${JSON.stringify(currentUrls)}`);
                await this.containerCommsService.addLog(this.config.runId, {
                    info: `Current URLs present in the browser: ${JSON.stringify(currentUrls)}`,
                    timestamp: new Date().toISOString()
                });
            }

            // Check if the instruction has any ai_file_upload action
            scripts = await this.processFileInstruction(instruction, scripts);
            
            // Convert array of scripts to the format expected by runScript
            const scriptObject = {
                [instruction.id]: scripts
            }

            // Use the browserAgent's runScript method
            const result = await this.browserAgent.runScript(scriptObject, [instruction], 0, this.config.variablesDict);
            logger.info(`Playwright script execution result: ${JSON.stringify(result)}`);
            
            if (result.success) {
                // Log playwright script execution success
                await this.containerCommsService.addLog(this.config.runId, {
                    info: 'Playwright script execution completed successfully',
                    timestamp: new Date().toISOString()
                });
            }

            // Return success as action result
            return {
                action: {
                    type: instruction.action
                },
                success: result.success,
                error: result.error,
                timestamp: Date.now()
            } as ActionResult;


        } catch (error) {
            logger.error(`LitmusAgent: Error executing playwright scripts: ${error}`);
            // Add logs to Redis
            await this.containerCommsService.addLog(this.config.runId, {
                error: `Error executing playwright scripts: ${error}`,
                timestamp: new Date().toISOString()
            });

            // Return error as action result
            return {
                action: {
                    type: instruction.action
                },
                success: false,
                error: error instanceof Error ? error.message : String(error),
                timestamp: Date.now()
            } as ActionResult;
        }
    }

    private async updateInstructionStatus(status: string, instructionId?: string): Promise<boolean> {
        const session = await this.containerCommsService.get(this.config.runId);
        if (!session) {
            return false;
        }

        // Check reset flag before updating status
        if (session.reset === true) {
            await this.handleReset(this.taskIndex);
            return true; // Reset was performed
        }

        // Update instruction status in dedicated status hash key.
        const targetInstructionId = instructionId ?? this.instructionId;
        await this.containerCommsService.setInstructionStatus(this.config.runId, targetInstructionId, status);
        const instructionStatuses = await this.containerCommsService.getInstructionStatuses(this.config.runId);
        logger.info(`Updated Redis status for instruction ${targetInstructionId} to ${status}. Current status:`, instructionStatuses);
        
        
        return false; // No reset performed
    }

    
    private async executeInstruction(instruction: Instruction): Promise<string> {
        // Execute instruction
        let goalStatus = '';
        if (instruction.type === INSTRUCTION_TYPES.AI) {
            this.browserAgent.setCurrentInstructionId(instruction.id);
            await this.handleAIInstruction(instruction);
            
        } else if (instruction.type === INSTRUCTION_TYPES.NON_AI) {
            this.browserAgent.setCurrentInstructionId(instruction.id);
            await this.handleNonAIInstruction(instruction);
        } else if (instruction.type === INSTRUCTION_TYPES.GOAL) {
            this.browserAgent.setCurrentInstructionId(instruction.id);
            console.log("Executing goal as instruction");
            const prompt = instruction.args?.find((arg: any) => arg.key === "prompt")?.value as string;
            const actionType = instruction.action as string;
            const result = await this.handleGoalInstruction(instruction.id, prompt, actionType);
            goalStatus = result.completionStatus;
            const generatedInstructions = result.generatedInstructions;
            const actionsResponses = result.actionsResponses;
            if(goalStatus === GoalOutput.SUCCESS){
                // append instructions to session
                let session = await this.containerCommsService.get(this.config.runId);
                if (session) {
                    await this.addGoalInstructionsToSession(instruction.id, generatedInstructions, actionsResponses, session);
                    await this.containerCommsService.set(this.config.runId, session);
                }
                await this.containerCommsService.addLog(this.config.runId, {
                    info: `Goal completed: ${prompt}`,
                    timestamp: new Date().toISOString(),
                    instructionId: instruction.id
                });
            } else if(goalStatus === GoalOutput.FAILED){
                // add log to redis
                await this.containerCommsService.addLog(this.config.runId, {
                    error: `Goal failed: ${prompt}`,
                    timestamp: new Date().toISOString(),
                    instructionId: instruction.id
                });
            }
        }

        // Check instruction status based on action results and playwright actions
        const redisSession = await this.containerCommsService.get(this.config.runId);
        const playwrightActions = redisSession?.playwright_actions[instruction?.id];
        
        // Get the last action result for this instruction from memory executions
        const lastExecution = this.memory.getExecutions()
            .filter(execution => execution.instructionId === instruction?.id)
            .pop();
        const lastActionResult = lastExecution?.actionsData?.[0]; // Get the first action result
        
        // Determine instruction status based on action success and playwright actions
        let instructionStatus: string = TASK_STATUS.RUNNING;
        const instructionDescription = this.createInstructionDescription(instruction);
        if ((lastActionResult && !lastActionResult.success) || (instruction.type === INSTRUCTION_TYPES.GOAL && goalStatus === GoalOutput.FAILED)) {
            // Action failed
            logger.info(`LitmusAgent: Last instruction status is failed. Instruction ${instruction.id} failed with status: ${TASK_STATUS.FAILED}`);
            instructionStatus = TASK_STATUS.FAILED;
            // Add log to redis
            await this.containerCommsService.addLog(this.config.runId, {
                error: `Failed to execute instruction ${instructionDescription}`,
                timestamp: new Date().toISOString(),
                instructionId: instruction.id
            });
        } else if (
            instruction.type !== INSTRUCTION_TYPES.GOAL &&
            (!playwrightActions || playwrightActions.length === 0)
        ) {
            // If this instruction is flagged always_ai or is ai_assert, do not fail due to missing scripts in redis
            if ((instruction as Instruction).ai_use === 'always_ai' || (instruction as Instruction).action === ACTION_TYPES.ASSERT) {
                logger.info(`LitmusAgent: Missing playwright actions ignored due to ai_use=always_ai or ai_assert action for instruction ${instruction.id}`);
                instructionStatus = TASK_STATUS.SUCCESS;
            } else {
                // No playwright actions generated
                logger.info(`LitmusAgent: No playwright actions generated. Instruction ${instruction.id} failed with status: ${TASK_STATUS.FAILED}`);
                instructionStatus = TASK_STATUS.FAILED;
                // Add log to redis
                await this.containerCommsService.addLog(this.config.runId, {
                    error: `Failed to execute instruction ${instructionDescription}`,
                    timestamp: new Date().toISOString(),
                    instructionId: instruction.id
                });
            }
        } else {
            logger.info(`LitmusAgent: Last instruction status is success. Instruction ${instruction.id} success with status: ${TASK_STATUS.SUCCESS}`);
            instructionStatus = TASK_STATUS.SUCCESS;
        }

        // Update instruction status
        const resetPerformed = await this.updateInstructionStatus(instructionStatus);
        if (resetPerformed) {
            return 'reset'; // Special status to indicate reset was performed
        }
        
        // Handle task progression
        if (instructionStatus === TASK_STATUS.SUCCESS) {
            this.completedInstructions++;
            this.taskIndex++;
            logger.info(`Moving to next task. New task index: ${this.taskIndex}`);
        } else {
            logger.info(`Instruction ${this.taskIndex} failed with status: ${instructionStatus}. Staying on current task.`);
        }

        return instructionStatus;
    }

    private async checkIfGoalAdded(composeSession: any): Promise<{goalId: string | null, prompt: string | null}> {
        const goalData = composeSession.goal_data;
        // Check the status of each goal in goal data.
        for(const goalId in goalData){
            const goalStatus = goalData[goalId].status;
            if(goalStatus === 'pending'){
                return {goalId: goalId, prompt: goalData[goalId].prompt};
            }
        }
        return {goalId: null, prompt: null};
    }

    /**
     * Update goal status in ContainerCommsService
     */
    private async updateGoalStatusInContainerCommsService(goalId: string, status: string, output: string | null = null, reasoning: string | null = null): Promise<void> {
        try {
            const session = await this.containerCommsService.get(this.config.runId);
            if (session && session.goal_data && session.goal_data[goalId]) {
                session.goal_data[goalId].status = status;
                // Update output and reasoning if they are provided
                if(output){
                    session.goal_data[goalId].output = output;
                }
                if(reasoning){
                    session.goal_data[goalId].reasoning = reasoning;
                }
                await this.containerCommsService.set(this.config.runId, session);
                logger.info(`Updated goal ${goalId} status to ${status} in ContainerCommsService`);
            }
        } catch (error) {
            logger.error(`Error updating goal status in ContainerCommsService: ${error instanceof Error ? error.message : String(error)}`);
        }
    }

    /**
     * Store goal instruction in ContainerCommsService
     */
    private async storeGoalInstructionInContainerCommsService(goalId: string, instruction: any): Promise<void> {
        try {
            const session = await this.containerCommsService.get(this.config.runId);
            if (session && session.goal_data && session.goal_data[goalId]) {
                // Initialize instructions array if it doesn't exist
                if (!session.goal_data[goalId].instructions) {
                    session.goal_data[goalId].instructions = [];
                }
                
                // Add the instruction to the array
                session.goal_data[goalId].instructions.push(instruction);
                
                await this.containerCommsService.set(this.config.runId, session);
                logger.info(`Stored instruction ${instruction.id} for goal ${goalId} in ContainerCommsService`);
            }
        } catch (error) {
            logger.error(`Error storing goal instruction in ContainerCommsService: ${error instanceof Error ? error.message : String(error)}`);
        }
    }

    /**
     * Convert action object to args array format
     */
    private convertActionToArgs(action: any): Array<{key: string, value: string | number}> {
        const args: Array<{key: string, value: string | number}> = [];
        
        // Add action properties as args (excluding 'type')
        Object.entries(action).forEach(([key, value]) => {
            if (key !== 'type' && value !== undefined && value !== null && key !== 'elementId' && key !== 'prompt') {
                args.push({
                    key: key,
                    value: typeof value === 'string' || typeof value === 'number' ? value : String(value)
                });
            }
        });
        
        return args;
    }

    /**
     * Return the prompt for the action
     */
    private generatePromptFromAction(action: any): string {
        return action.prompt;
    }

    /**
     * Check if an action is an AI action
     */
    private isAIAction(actionType: string): boolean {
        return SUPPORTED_AI_ACTIONS.includes(actionType as any);
    }

    /**
     * Helper method to update ai_credits in Redis session
     * @param creditAmount The amount to add (positive for increment)
     */
    private async updateAiCreditsInRedis(creditAmount: number): Promise<void> {
        try {
            const session = await this.containerCommsService.get(this.config.runId);
            if (session) {
                // Initialize ai_credits if it doesn't exist
                if (session.ai_credits === undefined) {
                    session.ai_credits = 0.0;
                }
                
                // Update ai_credits
                session.ai_credits += creditAmount;
                
                // Save back to Redis
                await this.containerCommsService.set(this.config.runId, session);
                
                logger.info(`Updated ai_credits in Redis: +${creditAmount} units. Current total: ${session.ai_credits}`);
            }
        } catch (error) {
            logger.error(`Error updating ai_credits in Redis: ${error instanceof Error ? error.message : String(error)}`);
        }
    }

    private async processFileInstruction(instruction: Instruction, script: string[]): Promise<string[]> {
        const processedScript: string[] = [];
        
        // Find all file_url arguments
        const fileUrlArgs = instruction.args?.filter((arg: any) => arg.key === "file_url") || [];
        logger.info(`LitmusAgent: File URL arguments: ${JSON.stringify(fileUrlArgs)}`);
        logger.info(`LitmusAgent: Script: ${JSON.stringify(script)}`);
        
        if (fileUrlArgs.length > 0) {
            const localFolderPath = FILE_UPLOADS_DIR;      // Local path to save the files in container
            const downloadedFiles: string[] = [];
            
            // Download all files
            for (const fileUrlArg of fileUrlArgs) {
                const file_url = fileUrlArg.value;
                if (file_url) {
                    try {
                        const localFilePath = await DownloadUtils.getInstance().downloadFile(file_url as string, localFolderPath);
                        
                        // Check if file exists
                        if (!fs.existsSync(localFilePath)) {
                            throw new Error(`File not found: ${localFilePath}`);
                        }
                        
                        downloadedFiles.push(localFilePath);
                    } catch (error) {
                        logger.error(`Error downloading file from ${file_url}: ${error instanceof Error ? error.message : String(error)}`);
                        throw error;
                    }
                }
            }
            
            let index = 0;
            // Update the script to include all file paths
            for (const line of script) {
                let processedLine = line;

                if (processedLine.includes("{{file_path}}")) {
                    processedLine = processedLine.replace("{{file_path}}", downloadedFiles[index]);
                    index++;
                }

                logger.info(`LitmusAgent: Processed line: ${processedLine}`);
                
                processedScript.push(processedLine);
            }
        } else {
            // Not a file-related action, return original script
            processedScript.push(...script);
        }
        
        return processedScript;
    }
}
