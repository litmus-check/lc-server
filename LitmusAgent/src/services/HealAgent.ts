import { AgentConfig, Instruction } from '../types/agent';
import { ContainerCommsService } from './ContainerCommsService';
import { BrowserAgent } from '../browser/BrowserAgent';
import { ActionResult } from '../types/actions';
import { logger } from '../utils/logger';
import { TRIAGE_SUB_CATEGORIES, INSTRUCTION_TYPES, ACTION_TYPES, EDIT_TYPES } from '../config/constants';
import { v4 as uuidv4 } from 'uuid';

export interface HealAgentDependencies {
    config: AgentConfig;
    containerCommsService: ContainerCommsService;
    browserAgent: BrowserAgent;
    executePlaywrightScripts: (scripts: string[], instruction: Instruction) => Promise<ActionResult>;
    handleAIInstruction: (instruction: Instruction) => Promise<void>;
    handleNonAIInstruction: (instruction: Instruction) => Promise<void>;
    handleGoalInstruction: (goalId: string, prompt: string, actionType?: string) => Promise<{
        completionStatus: string;
        generatedInstructions: any[];
        actionsResponses: ActionResult[];
    }>;
}

export class HealAgent {
    private config: AgentConfig;
    private containerCommsService: ContainerCommsService;
    private browserAgent: BrowserAgent;
    private executePlaywrightScripts: (scripts: string[], instruction: Instruction) => Promise<ActionResult>;
    private handleAIInstruction: (instruction: Instruction) => Promise<void>;
    private handleNonAIInstruction: (instruction: Instruction) => Promise<void>;
    private handleGoalInstruction: (goalId: string, prompt: string, actionType?: string) => Promise<{
        completionStatus: string;
        generatedInstructions: any[];
        actionsResponses: ActionResult[];
    }>;

    constructor(dependencies: HealAgentDependencies) {
        this.config = dependencies.config;
        this.containerCommsService = dependencies.containerCommsService;
        this.browserAgent = dependencies.browserAgent;
        this.executePlaywrightScripts = dependencies.executePlaywrightScripts;
        this.handleAIInstruction = dependencies.handleAIInstruction;
        this.handleNonAIInstruction = dependencies.handleNonAIInstruction;
        this.handleGoalInstruction = dependencies.handleGoalInstruction;
    }

    /**
     * Store instruction and playwright_actions in Redis session
     * Used in heal mode to store instructions executed via scripts
     * Stores only in heal_results.suggested_test
     */
    async storeHealInstructionInRedis(instruction: Instruction, playwrightActions: string[], editType: typeof EDIT_TYPES.NEW | typeof EDIT_TYPES.UPDATE | typeof EDIT_TYPES.UNCHANGED | typeof EDIT_TYPES.DELETE = EDIT_TYPES.UNCHANGED): Promise<void> {
        try {
            const session = await this.containerCommsService.get(this.config.runId);
            if (session) {
                // Add selectors only if not present in the instruction
                let selectorsPresent = instruction.selectors && (instruction.selectors as any).length > 0;
                if(!selectorsPresent) {
                    // Check if the selectors are in session 
                    let newSelectors = session.selectors?.[instruction.id] || [];

                    // If not in session, check the instruction object itself. Allow for unchanged edit type.
                    if (newSelectors.length === 0 && instruction.selectors?.selectors && editType===EDIT_TYPES.UNCHANGED) {
                        newSelectors = instruction.selectors.selectors;
                        logger.info(`Found selectors in instruction object for instruction ${instruction.id}`);
                    }

                    logger.info(`New selectors ${JSON.stringify(newSelectors)}`);

                    // Store selectors in heal_results if they exist
                    if (newSelectors.length > 0) {
                        instruction.selectors = newSelectors;
                        logger.info(`Stored ${newSelectors.length} selectors for instruction ${instruction.id} in heal_results.suggested_test`);
                    }
                }
                
                // Create a copy of the instruction to avoid reference issues
                // This ensures we store the instruction with the current prompt value
                const instructionToStore = { ...instruction } as any;
                
                // Add edit_type directly to the instruction object
                instructionToStore.edit_type = editType;
                
                // Log the prompt being stored for debugging
                logger.info(`Storing instruction ${instruction.id} with prompt: ${instructionToStore.prompt || 'No prompt'}`);
                    
                // Push instruction to heal_results.suggested_test.instructions
                session.heal_results.suggested_test.instructions.push(instructionToStore);
                
                // Store playwright_actions in heal_results.suggested_test
                session.heal_results.suggested_test.playwright_actions[instruction.id] = [...playwrightActions];
                
                await this.containerCommsService.set(this.config.runId, session);
                logger.info(`Stored instruction ${instruction.id} with edit_type '${editType}' in heal_results.suggested_test`);
            }
        } catch (error) {
            logger.error(`Failed to store instruction in Redis: ${error instanceof Error ? error.message : String(error)}`);
            throw error;
        }
    }

    /**
     * Generate healing-specific reasoning based on sub_category and status
     */
    generateHealingReasoning(subCategory: string | undefined, status: 'completed' | 'failed', errorMessage?: string): string {
        const isCompleted = status === 'completed';
        let healingReason = isCompleted ? 'Healing completed successfully. ' : 'Healing failed. ';
        
        if (subCategory === TRIAGE_SUB_CATEGORIES.RE_GENERATE_SCRIPT) {
            healingReason += isCompleted 
                ? 'Regenerated and executed the failed instruction with new playwright actions.'
                : 'Failed to regenerate and execute the instruction. ';
        } else if (subCategory === TRIAGE_SUB_CATEGORIES.REPLACE_STEP) {
            healingReason += isCompleted
                ? 'Replaced the failed step with an updated prompt and regenerated playwright actions.'
                : 'Failed to replace the step with updated prompt. ';
        } else if (subCategory === TRIAGE_SUB_CATEGORIES.REMOVE_STEP) {
            healingReason += isCompleted
                ? 'Removed the failed step from the test.'
                : 'Failed to remove the step. ';
        } else if (subCategory === TRIAGE_SUB_CATEGORIES.ADD_NEW_STEP) {
            healingReason += isCompleted
                ? 'Added new steps before the failed instruction and regenerated the failed step.'
                : 'Failed to add new steps or regenerate the failed instruction. ';
        } else {
            healingReason += isCompleted
                ? 'Applied healing strategy and processed all instructions successfully.'
                : 'Failed to apply healing strategy. ';
        }
        
        // Append error message for failed status
        if (!isCompleted && errorMessage) {
            healingReason += errorMessage;
        }
        
        return healingReason;
    }

    /**
     * Helper method to find instruction by ID and get its index
     */
    private findInstructionById(instructionId: string): { instruction: any | null, index: number } {
        const index = this.config.instructions.findIndex((instr: any) => instr.id === instructionId);
        const instruction = index !== -1 ? this.config.instructions[index] : null;
        return { instruction, index };
    }

    /**
     * Helper method to remove playwright actions for a given instruction ID
     */
    private removePlaywrightActionsForInstruction(instructionId: string): void {
        if (this.config.playwrightCode?.[instructionId]) {
            delete this.config.playwrightCode[instructionId];
            logger.info(`Removed playwright actions for instruction ${instructionId} from config`);
        }
    }

    /**
     * Helper method to update instruction in config array
     */
    private updateInstructionInConfig(instruction: any, index: number): void {
        if (index !== -1) {
            this.config.instructions.splice(index, 1, instruction);
            logger.info(`Updated instruction ${instruction.id} at index ${index} in config`);
        }
    }

    /**
     * Handle different heal sub-categories
     */
    handleHealSubCategory(subCategory: string | undefined, triageResult: any, failedInstructionId: string | null): void {
        if (!failedInstructionId) {
            return;
        }

        if (subCategory === TRIAGE_SUB_CATEGORIES.RE_GENERATE_SCRIPT) {
            logger.info('Handling re_generate_script: Removing playwright actions of failed instruction');
            
            this.removePlaywrightActionsForInstruction(failedInstructionId);
            
            const { instruction, index } = this.findInstructionById(failedInstructionId);
            if (instruction) {
                instruction.playwright_actions = [];
                instruction.selectors = [];
                this.updateInstructionInConfig(instruction, index);
            }
        } else if (subCategory === TRIAGE_SUB_CATEGORIES.REPLACE_STEP) {
            logger.info('Handling replace_step: Updating prompt and removing playwright actions of failed instruction');
            
            const updatedPrompt = triageResult.prompt;
            if (!updatedPrompt) {
                logger.error(`No prompt provided in triage result for replace_step. Cannot proceed with healing.`);
                throw new Error('Prompt is required for replace_step subcategory but was not provided by triage agent.');
            }
            
            logger.info(`Using updated prompt from triage: ${updatedPrompt}`);
            
            this.removePlaywrightActionsForInstruction(failedInstructionId);
            
            const { instruction, index } = this.findInstructionById(failedInstructionId);
            if (!instruction) {
                logger.error(`Failed to find instruction ${failedInstructionId} in config.instructions`);
                throw new Error(`Instruction ${failedInstructionId} not found in instructions array`);
            }
            
            instruction.prompt = updatedPrompt;
            instruction.playwright_actions = [];
            instruction.selectors = [];
            
            logger.info(`Updated instruction ${failedInstructionId} with new prompt: ${updatedPrompt}`);
            this.updateInstructionInConfig(instruction, index);
        } else if (subCategory === TRIAGE_SUB_CATEGORIES.REMOVE_STEP) {
            logger.info('Handling remove_step: Removing failed instruction completely');
            
            const { index } = this.findInstructionById(failedInstructionId);
            if (index !== -1) {
                this.config.instructions.splice(index, 1);
                logger.info(`Removed instruction ${failedInstructionId} at index ${index} from instructions array`);
            }
            
            this.removePlaywrightActionsForInstruction(failedInstructionId);
        } else if (subCategory === TRIAGE_SUB_CATEGORIES.ADD_NEW_STEP) {
            logger.info('Handling add_new_step: Will run goal agent to generate new steps before failed instruction');
            
            const goalPrompt = triageResult.prompt;
            if (!goalPrompt) {
                logger.error(`No prompt provided in triage result for add_new_step. Cannot proceed with healing.`);
                throw new Error('Prompt is required for add_new_step subcategory but was not provided by triage agent.');
            }
            
            logger.info(`Using goal prompt from triage: ${goalPrompt}`);
        } else {
            // Manual review: Add 10-second wait before failed instruction
            logger.info('Handling manual_review: Adding 10-second wait before failed instruction');
            
            const { index: failedIndex } = this.findInstructionById(failedInstructionId);
            if (failedIndex !== -1) {
                const waitInstruction: Instruction = {
                    id: `wait_${failedInstructionId}_${Date.now()}`,
                    type: INSTRUCTION_TYPES.NON_AI,
                    action: ACTION_TYPES.WAIT_TIME,
                    args: [
                        {
                            key: 'time',
                            value: '10'
                        }
                    ]
                };
                
                this.config.instructions.splice(failedIndex, 0, waitInstruction);
                
                if (!this.config.playwrightCode) {
                    this.config.playwrightCode = {};
                }
                this.config.playwrightCode[waitInstruction.id] = [
                    "await page.waitForTimeout(10000);"
                ];
                
                logger.info(`Inserted wait instruction ${waitInstruction.id} before failed instruction ${failedInstructionId}`);
            }
        }
    }

    /**
     * Execute instruction before failed step using playwright scripts
     */
    async executePreFailedInstruction(instr: Instruction): Promise<void> {
        const scriptsForInstr = this.config.playwrightCode[instr.id] || [];
        if (!scriptsForInstr || scriptsForInstr.length === 0) {
            logger.warn(`No playwright script found for instruction ${instr.id} before failed step`);
            return;
        }
        
        logger.info(`Running pre-failed instruction ${instr.id} using playwright scripts`);
        const result = await this.executePlaywrightScripts(scriptsForInstr, instr);
        logger.info(`Instruction ${instr.id} executed with result ${JSON.stringify(result)}`);
        
        if (result.success) {
            await this.storeHealInstructionInRedis(instr, scriptsForInstr, EDIT_TYPES.UNCHANGED);
        } else {
            // Pre-failed instruction failed, stop healing
            const errorMessage = `Pre-failed instruction ${instr.id} execution failed`;
            throw new Error(errorMessage);
        }
    }

    /**
     * Handle add_new_step: run goal agent before failed instruction
     */
    async handleAddNewStepInstruction(instr: Instruction, triageResult: any): Promise<void> {
        logger.info(`Handling add_new_step: Running goal agent before failed instruction ${instr.id}`);
        
        const goalPrompt = triageResult.prompt;
        if (!goalPrompt) {
            logger.error(`No prompt provided in triage result for add_new_step. Cannot proceed with healing.`);
            throw new Error('Prompt is required for add_new_step subcategory but was not provided by triage agent.');
        }
        
        const goalId = uuidv4();
        logger.info(`Running goal agent with prompt: ${goalPrompt}`);
        
        const goalResult = await this.handleGoalInstruction(goalId, goalPrompt, ACTION_TYPES.GOAL);
        
        logger.info(`Goal agent completed with status: ${goalResult.completionStatus}, generated ${goalResult.generatedInstructions.length} instructions`);
        
        // Store all generated instructions from goal agent in heal_results
        for (let i = 0; i < goalResult.generatedInstructions.length; i++) {
            const generatedInstr = goalResult.generatedInstructions[i];
            const playwrightActions = generatedInstr.playwright_actions || [];
            
            // Get corresponding action response from goalResult
            const actionResponse = goalResult.actionsResponses[i];
            
            if (actionResponse?.selectors?.selectors) {
                const selectors = actionResponse.selectors.selectors;
                const scripts = actionResponse.scripts || [];

                const selectorsWithScript: any[] = [];
                
                if (selectors.length > 0) {
                    for(let j = 0; j < Math.min(selectors.length, scripts.length); j++) {
                        const selector = selectors[j];
                        const script = scripts[j];
                        selectorsWithScript.push({
                            ...selector,
                            script: script
                        });
                    }
                }

                generatedInstr.selectors = selectorsWithScript;
                logger.info(`Retrieved ${selectorsWithScript.length} selectors with scripts for goal-generated instruction ${generatedInstr.id}`);
            }
            
            await this.storeHealInstructionInRedis(generatedInstr, playwrightActions, EDIT_TYPES.NEW);
            logger.info(`Stored goal-generated instruction ${generatedInstr.id} in heal_results with ${playwrightActions.length} playwright actions`);
        }
        
        await this.containerCommsService.addLog(this.config.runId, {
            info: `Goal agent generated ${goalResult.generatedInstructions.length} new instructions for add_new_step`,
            timestamp: new Date().toISOString(),
            instructionId: goalId
        });
        
        // After goal agent completes, continue with the failed instruction
        logger.info(`Continuing with failed instruction ${instr.id} after goal agent completion`);
        await this.executeAndStoreFailedInstruction(instr, EDIT_TYPES.UNCHANGED);
    }

    /**
     * Execute failed instruction via AI/Non-AI and store in Redis
     */
    async executeAndStoreFailedInstruction(instr: Instruction, edit_type: string | undefined): Promise<void> {
        logger.info(`Regenerating and executing failed instruction ${instr.id}`);
        logger.info(`Instruction prompt before execution: ${instr.prompt || 'No prompt'}`);
        
        this.browserAgent.setCurrentInstructionId(instr.id);
        
        if (instr.type === INSTRUCTION_TYPES.AI) {
            await this.handleAIInstruction(instr);
        } else {
            await this.handleNonAIInstruction(instr);
        }
        
        // Get playwright actions from BrowserAgent memory first
        let playwrightActions = this.browserAgent.getPlaywrightActionsForInstruction(instr.id);
        if (!Array.isArray(playwrightActions)) {
            playwrightActions = [];
        }
        
        // If not in memory, try to get from session (stored by handleAIInstruction)
        if (playwrightActions.length === 0) {
            const session = await this.containerCommsService.get(this.config.runId);
            if (session?.playwright_actions?.[instr.id]) {
                playwrightActions = [...session.playwright_actions[instr.id]];
                logger.info(`Retrieved playwright actions from session for instruction ${instr.id}`);
            }
        }
        instr.playwright_actions = [...playwrightActions];
        
        // Log prompt before storing to verify it's the updated one
        logger.info(`Instruction prompt before storing: ${instr.prompt || 'No prompt'}`);
        logger.info(`Playwright actions to store: ${JSON.stringify(playwrightActions)}`);
        
        // If edit type is provided, use it, otherwise use 'update'
        if (edit_type) {
            await this.storeHealInstructionInRedis(instr, playwrightActions, edit_type as typeof EDIT_TYPES.NEW | typeof EDIT_TYPES.UPDATE | typeof EDIT_TYPES.UNCHANGED | typeof EDIT_TYPES.DELETE);
        } else {
            await this.storeHealInstructionInRedis(instr, playwrightActions, EDIT_TYPES.UPDATE);
        }
        
        await this.containerCommsService.addLog(this.config.runId, {
            info: `Regenerated and executed failed instruction`,
            timestamp: new Date().toISOString(),
            instructionId: instr.id
        });
    }

    /**
     * Execute instruction after failed step using playwright scripts
     */
    async executePostFailedInstruction(instr: Instruction): Promise<void> {
        const scriptsForInstr = this.config.playwrightCode[instr.id] || [];
        if (!scriptsForInstr || scriptsForInstr.length === 0) {
            logger.warn(`No playwright script found for instruction ${instr.id} after failed step`);
            return;
        }
        
        logger.info(`Running post-failed instruction ${instr.id} using playwright scripts`);
        const result = await this.executePlaywrightScripts(scriptsForInstr, instr);
        logger.info(`Instruction ${instr.id} executed with result ${JSON.stringify(result)}`);
        
        if (result.success) {
            await this.storeHealInstructionInRedis(instr, scriptsForInstr, EDIT_TYPES.UNCHANGED);
        } else {
            // Post-failed instruction failed, stop healing
            const errorMessage = `Post-failed instruction ${instr.id} execution failed`;
            throw new Error(errorMessage);
        }
    }

    /**
     * Handle healing failure: update status, clear suggested_test, set reasoning
     */
    private async handleHealingFailure(errorMessage: string): Promise<void> {
        logger.error(`Healing failed: ${errorMessage}`);
        
        const session = await this.containerCommsService.get(this.config.runId);
        if (session?.heal_results) {
            // Set heal_status to failed
            session.heal_results.heal_status = 'failed';
            
            // Clear suggested_test (empty updated_test)
            session.heal_results.suggested_test = {
                instructions: [],
                playwright_actions: {}
            };
            
            session.heal_results.reasoning = errorMessage;
            await this.containerCommsService.set(this.config.runId, session);
            logger.info(`Updated heal_results: status='failed', reasoning='${errorMessage}', suggested_test cleared`);
        }
    }

    /**
     * Add removed steps (instructions in suggested_test) with edit_type 'delete'
     */
    private async addRemovedStepsToSuggestedTest(session: any): Promise<void> {
        try {
            // Get current_test and suggested_test from session
            const currentTest = session?.current_test;
            const suggestedTest = session?.heal_results?.suggested_test;
            
            // Edge case: current_test is missing
            if (!currentTest) {
                logger.warn('current_test not found in session, skipping removed steps check');
                return;
            }
            
            // Edge case: current_test.instructions is empty or null
            if (!currentTest.instructions || !Array.isArray(currentTest.instructions) || currentTest.instructions.length === 0) {
                logger.info('current_test.instructions is empty, no removed steps to add');
                return;
            }
            
            // Edge case: suggested_test is missing
            if (!suggestedTest) {
                logger.warn('suggested_test not found in heal_results, skipping removed steps check');
                return;
            }
            
            // Initialize suggested_test.instructions if it doesn't exist
            if (!suggestedTest.instructions) {
                suggestedTest.instructions = [];
            }
            
            // Initialize suggested_test.playwright_actions if it doesn't exist
            if (!suggestedTest.playwright_actions) {
                suggestedTest.playwright_actions = {};
            }
            
            // Create a Set of instruction IDs from suggested_test for O(1) lookup
            const suggestedTestInstructionIds = new Set(
                suggestedTest.instructions.map((instr: any) => instr.id).filter((id: any) => id != null)
            );
            
            // Create a Map of instruction ID to index in suggested_test for position tracking
            const suggestedTestInstructionIndexMap = new Map<string, number>();
            suggestedTest.instructions.forEach((instr: any, index: number) => {
                if (instr.id) {
                    suggestedTestInstructionIndexMap.set(instr.id, index);
                }
            });
            
            let removedStepsCount = 0;
            
            // Iterate through current_test.instructions to maintain original order
            for (let currentIndex = 0; currentIndex < currentTest.instructions.length; currentIndex++) {
                const currentInstruction = currentTest.instructions[currentIndex];
                
                // Edge case: instruction doesn't have an ID
                if (!currentInstruction.id) {
                    logger.warn(`Skipping instruction without ID in current_test: ${JSON.stringify(currentInstruction)}`);
                    continue;
                }
                
                // Check if this instruction exists in suggested_test
                if (!suggestedTestInstructionIds.has(currentInstruction.id)) {
                    // Instruction is in current_test but not in suggested_test - it was removed
                    // Create a copy of the instruction to avoid reference issues
                    const deletedInstruction = JSON.parse(JSON.stringify(currentInstruction)) as any;
                    
                    // Set edit_type to 'delete'
                    deletedInstruction.edit_type = EDIT_TYPES.DELETE;
                    
                    // Find the correct position to insert: after the last instruction from current_test that appears before this one
                    let insertIndex = suggestedTest.instructions.length;
                    
                    // Look for instructions that come before this one in current_test and are already in suggested_test
                    for (let prevIndex = currentIndex - 1; prevIndex >= 0; prevIndex--) {
                        const prevInstructionId = currentTest.instructions[prevIndex]?.id;
                        if (prevInstructionId && suggestedTestInstructionIndexMap.has(prevInstructionId)) {
                            const prevSuggestedTestIndex = suggestedTestInstructionIndexMap.get(prevInstructionId)!;
                            insertIndex = prevSuggestedTestIndex + 1;
                            break;
                        }
                    }
                    
                    // Insert at the calculated position to maintain order
                    suggestedTest.instructions.splice(insertIndex, 0, deletedInstruction);
                    
                    // Update the index map for all instructions after the insertion point
                    for (let i = insertIndex + 1; i < suggestedTest.instructions.length; i++) {
                        const instrId = suggestedTest.instructions[i]?.id;
                        if (instrId) {
                            suggestedTestInstructionIndexMap.set(instrId, i);
                        }
                    }
                    // Add the new instruction to the map
                    suggestedTestInstructionIndexMap.set(currentInstruction.id, insertIndex);
                    
                    // Add playwright_actions if available in current_test, otherwise empty array
                    if (currentTest.playwright_actions && currentTest.playwright_actions[currentInstruction.id]) {
                        suggestedTest.playwright_actions[currentInstruction.id] = [...currentTest.playwright_actions[currentInstruction.id]];
                    } else {
                        suggestedTest.playwright_actions[currentInstruction.id] = [];
                    }
                    
                    removedStepsCount++;
                    logger.info(`Added removed instruction ${currentInstruction.id} to suggested_test at position ${insertIndex} with edit_type='${EDIT_TYPES.DELETE}'`);
                }
            }
            
            if (removedStepsCount > 0) {
                logger.info(`Added ${removedStepsCount} removed step(s) to suggested_test with edit_type='${EDIT_TYPES.DELETE}'`);
            } else {
                logger.info('No removed steps found - all instructions from current_test are present in suggested_test');
            }
        } catch (error) {
            logger.error(`Error adding removed steps to suggested_test: ${error instanceof Error ? error.message : String(error)}`);
            // Don't throw - allow healing to complete even if this step fails
        }
    }

    /**
     * Finalize heal mode: update status and log final session
     */
    async finalizeHealMode(): Promise<void> {
        logger.info('All instructions processed in heal mode');
        
        const session = await this.containerCommsService.get(this.config.runId);
        if (session?.heal_results) {
            // Update heal_status to completed
            session.heal_results.heal_status = 'completed';
            
            // Generate healing-specific reasoning based on sub_category
            const triageResult = session.triage_result;
            const subCategory = triageResult?.sub_category;
            const healingReason = this.generateHealingReasoning(subCategory, 'completed');
            
            session.heal_results.reasoning = healingReason;
            
            // Go through all instructions in suggested_test and mark wait instructions without edit_type as NEW
            if (session.heal_results.suggested_test?.instructions) {
                for (const instruction of session.heal_results.suggested_test.instructions) {
                    // Check if it's a wait instruction without edit_type
                    if (instruction.action === ACTION_TYPES.WAIT_TIME && !instruction.edit_type) {
                        (instruction as any).edit_type = EDIT_TYPES.NEW;
                        logger.info(`Marked wait instruction ${instruction.id} as '${EDIT_TYPES.NEW}' (missing edit_type)`);
                    }
                }
            }
            
            // Add removed steps (instructions in suggested_test) with edit_type 'delete'
            await this.addRemovedStepsToSuggestedTest(session);
            
            // Clear current_test after healing is done
            delete session.current_test;
            
            await this.containerCommsService.set(this.config.runId, session);
            logger.info(`Finalized heal mode: status='completed', reasoning='${healingReason}', current_test cleared`);
        }
        
        // Log all instructions and playwright_actions from Redis
        const finalSession = await this.containerCommsService.get(this.config.runId);
        if (finalSession) {
            logger.info(`Final session: ${JSON.stringify(finalSession)}`);
        }
        
        await this.containerCommsService.addLog(this.config.runId, {
            info: 'Healing completed: All instructions processed',
            timestamp: new Date().toISOString()
        });
    }
}

