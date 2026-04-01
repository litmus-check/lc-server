import { Instruction } from '../types/agent';
import { logger } from '../utils/logger';
import { ContainerCommsService } from './ContainerCommsService';

export class State {
    private instructions: Instruction[] = [];
    private currentIndex: number = 0;
    private _isStopped: boolean = false;
    private _isPaused: boolean = false;
    private _wasReset: boolean = false;
    private containerCommsService: ContainerCommsService;
    private runId: string;

    constructor(runId: string) {
        this.containerCommsService = new ContainerCommsService();
        this.runId = runId;
    }

    hasNextInstruction(): boolean {
        return this.currentIndex < this.instructions.length;
    }

    nextInstruction(): Instruction {
        if (!this.hasNextInstruction()) {
            throw new Error('No more instructions available');
        }
        const instruction = this.instructions[this.currentIndex];
        this.currentIndex++;
        const message = `Executing instruction: ${instruction.id}`;
        logger.debug(message);
        this.containerCommsService.addLog(this.runId, {
            info: message,
            timestamp: new Date().toISOString(),
            instructionId: instruction.id
        });
        return instruction;
    }

    /**
     * Mark the current instruction as failed and stop execution
     */
    markInstructionFailed(): void {
      //  this._isStopped = true;
        const message = 'Stopping execution due to instruction failure';
        logger.info(message);
        this.containerCommsService.addLog(this.runId, {
            error: message,
            timestamp: new Date().toISOString()
        });
    }

    addInstruction(instruction: Instruction): void {
        if (!this.hasInstruction(instruction.id)) {
            this.instructions.push(instruction);
            const message = `Added instruction ${instruction.id} to the queue`;
            logger.info(message);
            this.containerCommsService.addLog(this.runId, {
                info: message,
                timestamp: new Date().toISOString(),
                instructionId: instruction.id
            });
        }
    }

    addInstructions(newInstructions: Instruction[]): void {
        newInstructions.forEach(instruction => {
            if (!this.hasInstruction(instruction.id)) {
                this.instructions.push(instruction);
                const message = `Added instruction ${instruction.id} to the queue`;
                logger.info(message);
                this.containerCommsService.addLog(this.runId, {
                    info: message,
                    timestamp: new Date().toISOString(),
                    instructionId: instruction.id
                });
            }
        });
    }

    getInstructions(): Instruction[] {
        return [...this.instructions];
    }

    getInstructionCount(): number {
        return this.instructions.length;
    }

    hasInstruction(id: string): boolean {
        return this.instructions.some(inst => inst.id === id);
    }

    getCurrentIndex(): number {
        return this.currentIndex;
    }

    reset(): void {
        this.instructions = [];
        this.currentIndex = 0;
        this._isStopped = false;
        this._isPaused = false;
        this._wasReset = true;
        const message = 'State reset';
        logger.debug(message);
        this.containerCommsService.addLog(this.runId, {
            info: message,
            timestamp: new Date().toISOString()
        });
    }

    get isStopped(): boolean {
        return this._isStopped;
    }

    get isPaused(): boolean {
        return this._isPaused;
    }

    set isStopped(value: boolean) {
        this._isStopped = value;
        const message = `Agent stopped state set to: ${value}`;
        logger.debug(message);
        this.containerCommsService.addLog(this.runId, {
            error: message,
            timestamp: new Date().toISOString()
        });
    }

    set isPaused(value: boolean) {
        this._isPaused = value;
        const message = `Agent paused state set to: ${value}`;
        logger.debug(message);
        this.containerCommsService.addLog(this.runId, {
            error: message,
            timestamp: new Date().toISOString()
        });
    }

    

    
} 