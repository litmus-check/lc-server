import { BrowserState, InteractableElement } from './browser';
import { Action, ActionResult } from './actions';

export interface AgentState {
    browserState: BrowserState;
    currentInstructionId: string;
    completedInstructions: string[];
    errors: { name: string; message: string; stack?: string }[];
    lastActionResult?: ActionResult;
    timestamp: number;
}

export interface AgentMemory {
    instructions: {
        id: string;
        description: string;
        type: 'ai' | 'non-ai';
        status: 'pending' | 'running' | 'completed' | 'failed';
        timestamp: number;
    }[];
    executionHistory: {
        instructionId: string;
        action: Action;
        result: ActionResult;
        timestamp: number;
    }[];
    playwrightScripts: {
        instructionId: string;
        script: string;
        timestamp: number;
    }[];
    errors: {
        instructionId: string;
        action: string;
        errorType: 'exception' | 'warning';
        message: string;
        timestamp: number;
    }[];
}

export interface AgentConfig {
    maxRetries: number;
    timeout: number;
    waitBetweenActions: number;
    screenshotBeforeAction: boolean;
    screenshotAfterAction: boolean;
    logLevel: 'debug' | 'info' | 'warn' | 'error';
}
