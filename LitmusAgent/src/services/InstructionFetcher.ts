import { Instruction } from '../types/agent';
import { logger } from '../utils/logger';
import { ContainerCommsService } from './ContainerCommsService';

export class InstructionFetcher {
    private containerCommsService: ContainerCommsService;
    private runId: string;

    constructor(runId: string) {
        this.containerCommsService = new ContainerCommsService();
        this.runId = runId;
    }

    async fetch(): Promise<Instruction[]> {
        try {
            const instructions = await this.containerCommsService.get(this.runId);
            // logger.info(`[InstructionFetcher] Fetching instructions for runId: ${this.runId}`);
            // logger.info(`[InstructionFetcher] Raw Redis data: ${JSON.stringify(instructions, null, 2)}`);
            
            if (instructions && instructions.instructions) {
                const message = `Fetched ${instructions.instructions.length} instructions for execution`;
                // logger.info(`[InstructionFetcher] ${message}`);
                // logger.info(`[InstructionFetcher] Instructions: ${JSON.stringify(instructions.instructions, null, 2)}`);
                await this.containerCommsService.addLog(this.runId, {
                    info: message,
                    timestamp: new Date().toISOString()
                });
                return instructions.instructions;
            }
            // logger.info(`[InstructionFetcher] No instructions found in Redis data`);
            return [];
        } catch (error) {
            const errorMessage = 'Failed to fetch instructions';
            logger.error(`[InstructionFetcher] ${errorMessage}:`, error);
            await this.containerCommsService.addLog(this.runId, {
                error: `${errorMessage}: ${error instanceof Error ? error.message : String(error)}`,
                timestamp: new Date().toISOString()
            });
            throw error;
        }
    }

    async addInstructions(instructions: Instruction[]): Promise<void> {
        try {
            const existingInstructions = await this.fetch();
            const updatedInstructions = [...existingInstructions, ...instructions];
            await this.containerCommsService.set(this.runId, { instructions: updatedInstructions });
            const message = `Added ${instructions.length} new instructions for execution`;
            logger.debug(message);
            await this.containerCommsService.addLog(this.runId, {
                info: message,
                timestamp: new Date().toISOString()
            });
        } catch (error) {
            const errorMessage = 'Failed to add instructions';
            logger.error(errorMessage, error);
            await this.containerCommsService.addLog(this.runId, {
                error: `${errorMessage}: ${error instanceof Error ? error.message : String(error)}`,
                timestamp: new Date().toISOString()
            });
            throw error;
        }
    }
} 