import { logger } from './logger';
import { VARIABLE_REGEX_PATTERN, ENV_VARIABLE_REGEX_PATTERN } from '../config/constants';
import { escapeJsStringValue } from './stateVariableUtils';

/**
 * Replaces variables in a string with their actual values from the variables dictionary
 * @param text - The text containing variables in ${variableName} or {{env.variableName}} format
 * @param dataDrivenVariables - Dictionary of data-driven variable names and their values (for ${} format)
 * @param environmentVariables - Dictionary of environment variable names and their values (for {{env.}} format)
 * @returns The text with variables replaced
 */
export function substituteVariables(
    text: string, 
    dataDrivenVariables: { [key: string]: string } = {}, 
    environmentVariables: { [key: string]: string } = {}
): string {
    if (!text) {
        return text;
    }

    try {
        let result = text;

        // Replace all occurrences of ${variableName} with data-driven variables
        result = result.replace(VARIABLE_REGEX_PATTERN, (match, variableName) => {
            const value = dataDrivenVariables[variableName];
            if (value !== undefined) {
                logger.info(`Substituting data-driven variable ${variableName} with value: ${value}`);
                // Escape the substituted value
                return escapeJsStringValue(String(value));
            } else {
                logger.warn(`Data-driven variable ${variableName} not found in variables dictionary`);
                return match; // Keep the original ${variableName} if not found
            }
        });

        // Replace all occurrences of {{env.variableName}} with environment variables
        result = result.replace(ENV_VARIABLE_REGEX_PATTERN, (match, variableName) => {
            const value = environmentVariables[variableName];
            if (value !== undefined) {
                logger.info(`Substituting environment variable ${variableName} with value: ${value}`);
                // Escape the substituted value
                return escapeJsStringValue(String(value));
            } else {
                logger.warn(`Environment variable ${variableName} not found in variables dictionary`);
                return match; // Keep the original {{env.variableName}} if not found
            }
        });

        return result;
    } catch (error) {
        logger.error(`Error substituting variables: ${error}`);
        return text;
    }
}

/**
 * Replaces variables in an array of strings
 * @param texts - Array of strings containing variables
 * @param dataDrivenVariables - Dictionary of data-driven variable names and their values (for ${} format)
 * @param environmentVariables - Dictionary of environment variable names and their values (for {{env.}} format)
 * @returns Array of strings with variables replaced
 */
export function substituteVariablesInArray(
    texts: string[], 
    dataDrivenVariables: { [key: string]: string } = {}, 
    environmentVariables: { [key: string]: string } = {}
): string[] {
    if (!texts) {
        return texts;
    }

    return texts.map(text => substituteVariables(text, dataDrivenVariables, environmentVariables));
}

/**
 * Replaces variables in a playwright instructions object
 * @param playwrightInstructions - Object with instruction IDs as keys and arrays of strings as values
 * @param dataDrivenVariables - Dictionary of data-driven variable names and their values (for ${} format)
 * @param environmentVariables - Dictionary of environment variable names and their values (for {{env.}} format)
 * @returns Object with variables replaced in all strings
 */
export function substituteVariablesInPlaywrightInstructions(
    playwrightInstructions: { [key: string]: string[] }, 
    dataDrivenVariables: { [key: string]: string } = {}, 
    environmentVariables: { [key: string]: string } = {}
): { [key: string]: string[] } {
    if (!playwrightInstructions) {
        return playwrightInstructions;
    }

    const result: { [key: string]: string[] } = {};
    
    for (const [instructionId, instructions] of Object.entries(playwrightInstructions)) {
        result[instructionId] = substituteVariablesInArray(instructions, dataDrivenVariables, environmentVariables);
    }

    return result;
}

/**
 * Replaces variables in instruction arguments
 * @param instruction - Instruction object that may contain variables in args
 * @param dataDrivenVariables - Dictionary of data-driven variable names and their values (for ${} format)
 * @param environmentVariables - Dictionary of environment variable names and their values (for {{env.}} format)
 * @returns Instruction with variables replaced in args
 */
export function substituteVariablesInInstruction(
    instruction: any, 
    dataDrivenVariables: { [key: string]: string } = {}, 
    environmentVariables: { [key: string]: string } = {}
): any {
    if (!instruction) {
        return instruction;
    }

    const result = { ...instruction };

    // Replace variables in args if they exist
    if (result.args && Array.isArray(result.args)) {
        result.args = result.args.map((arg: any) => ({
            ...arg,
            value: typeof arg.value === 'string' ? substituteVariables(arg.value, dataDrivenVariables, environmentVariables) : arg.value
        }));
    }

    // Replace variables in prompt if it exists
    if (result.prompt && typeof result.prompt === 'string') {
        result.prompt = substituteVariables(result.prompt, dataDrivenVariables, environmentVariables);
    }

    // Replace variables in script if it exists
    if (result.script && typeof result.script === 'string') {
        result.script = substituteVariables(result.script, dataDrivenVariables, environmentVariables);
    }

    return result;
}

/**
 * Replaces variables in an array of instructions
 * @param instructions - Array of instruction objects
 * @param dataDrivenVariables - Dictionary of data-driven variable names and their values (for ${} format)
 * @param environmentVariables - Dictionary of environment variable names and their values (for {{env.}} format)
 * @returns Array of instructions with variables replaced
 */
export function substituteVariablesInInstructions(
    instructions: any[], 
    dataDrivenVariables: { [key: string]: string } = {}, 
    environmentVariables: { [key: string]: string } = {}
): any[] {
    if (!instructions) {
        return instructions;
    }

    return instructions.map(instruction => substituteVariablesInInstruction(instruction, dataDrivenVariables, environmentVariables));
}
