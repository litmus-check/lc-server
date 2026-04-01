import { ExecutionData } from '../types/agent';
import { logger } from '../utils/logger';

export class Memory {
    private executions: ExecutionData[] = [];
    private errors: { instructionId: string; message: string }[] = [];

    addExecution(execution: ExecutionData): void {
        try {
            this.executions.push(execution);
            logger.debug(`Added execution for instruction ${execution.instructionId}`);
        } catch (error) {
            logger.error('Failed to add execution to memory', error);
            throw error;
        }
    }

    addError(error: { instructionId: string; message: string }): void {
        try {
            this.errors.push(error);
            logger.debug(`Added error for instruction ${error.instructionId}`);
        } catch (error) {
            logger.error('Failed to add error to memory', error);
            throw error;
        }
    }

    getExecutions(): ExecutionData[] {
        return this.executions;
    }

    getErrors(): { instructionId: string; message: string }[] {
        return this.errors;
    }

    clear(): void {
        this.executions = [];
        this.errors = [];
        logger.debug('Memory cleared');
    }
} 