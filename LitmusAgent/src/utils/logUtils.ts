import { Action, ActionType } from '../types/actions';
import { ACTION_TYPES } from '../config/constants';

// Types for instruction structure
interface InstructionArg {
    key: string;
    value: string | number;
}

interface Instruction {
    id: string;
    type: 'ai' | 'non-ai';
    action: string;
    target?: string;
    value?: string | number;
    index?: number;
    timeout?: number;
    success?: boolean;
    message?: string;
    args?: InstructionArg[];
}

// Get all AI action types
const SUPPORTED_AI_ACTIONS = Object.values(ACTION_TYPES).filter((action: string) => 
    action.startsWith('ai_')
);

/**
 * Creates a log instruction string from an instruction object
 * @param instruction The instruction object to convert to a log string
 * @returns A formatted log instruction string
 */
export function createLogInstructionFromInstruction(instruction: Instruction): string {
    let instructionStr = instruction.action;

    // If action type is AI then add prompt/target to instruction string
    if (instruction.type === 'ai' && instruction.target) {
        instructionStr += ` | ${instruction.target}`;
    }

    // If action type is Run Script then don't add script arg to instruction string
    if (instruction.action === ACTION_TYPES.RUN_SCRIPT) {
        return instructionStr;
    }

    // Add value if present
    if (instruction.value !== undefined) {
        instructionStr += ` | ${instruction.value}`;
    }

    // Add all argument values to the instruction string
    if (instruction.args) {
        for (const arg of instruction.args) {
            instructionStr += ` | ${arg.value}`;
        }
    }

    return instructionStr;
}

/**
 * Creates a log entry for an action execution
 * @param action The action that was executed
 * @param result The result of the action execution
 * @returns A formatted log entry
 */
export function createActionLogEntry(action: Action, result: any): string {
    let logEntry = `Action: ${action.type}`;

    // Add elementId if present
    if (action.elementId) {
        logEntry += ` | Element: ${action.elementId}`;
    }

    // Add specific action properties
    if ('prompt' in action) {
        logEntry += ` | Prompt: ${action.prompt}`;
    }
    if ('value' in action) {
        logEntry += ` | Value: ${action.value}`;
    }
    if ('url' in action) {
        logEntry += ` | URL: ${action.url}`;
    }
    if ('file' in action) {
        logEntry += ` | File: ${action.file}`;
    }
    if ('direction' in action) {
        logEntry += ` | Direction: ${action.direction}`;
    }

    // Add result information
    if (result.success !== undefined) {
        logEntry += ` | Success: ${result.success}`;
    }
    if (result.message) {
        logEntry += ` | Message: ${result.message}`;
    }

    return logEntry;
}

// Example usage:
/*
const instruction: Instruction = {
    id: '1',
    type: 'ai',
    action: 'ai_click',
    target: 'Click the submit button',
    args: [
        { key: 'timeout', value: 5000 }
    ]
};

const logString = createLogInstructionFromInstruction(instruction);
// Result: "ai_click | Click the submit button | 5000"

const action: Action = {
    type: 'ai_click',
    elementId: 'submit-button',
    prompt: 'Click the submit button'
};

const result = {
    success: true,
    message: 'Successfully clicked the submit button'
};

const actionLog = createActionLogEntry(action, result);
// Result: "Action: ai_click | Element: submit-button | Prompt: Click the submit button | Success: true | Message: Successfully clicked the submit button"
*/ 