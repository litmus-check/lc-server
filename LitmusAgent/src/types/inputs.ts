export interface Instruction {
    id: string;
    type: 'ai' | 'non-ai';
    action: string;
    target?: string;
    value?: string | number;
    index?: number;
    timeout?: number;
    success?: boolean;
    message?: string;
}

export interface InstructionSet {
    instructions: Instruction[];
    testRunId: string;
    composeId?: string;
}

export interface InstructionResult {
    instructionId: string;
    success: boolean;
    error?: string;
    screenshot?: Buffer;
    timestamp: number;
} 