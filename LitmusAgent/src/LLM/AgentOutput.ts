import { AiScriptActionSchema, BaseAction, BaseActionSchema } from "../types/actions";
import { z } from "zod";
import { ERROR_STATUS } from "../config/constants";

// Assertion for verify action
export interface BaseAssertion {
    validation: boolean;
    reasoning: string;
    code: string; // Playwright code or equivalent
    framework: "playwright" | "cypress" | "puppeteer" | "selenium"; // for future-proofing
}

// Assertion for ai_assert action
export interface AssertionAssert {
    validation: boolean;
    reasoning: string;
}

export const BaseAssertionSchema = z.object({
    validation: z.boolean(),
    reasoning: z.string(),
    code: z.string(),
    framework: z.enum(["playwright", "cypress", "puppeteer", "selenium"])
});

// Schema for ai_assert
export const AssertionAssertSchema = z.object({
    validation: z.boolean(),
    reasoning: z.string()
});

// Base schema that accepts either type of Assert
export const AgentOutputSchema = z.object({
    Actions: z.array(BaseActionSchema).optional().default([]),
    Reasoning: z.string().optional().default(''),
    Warning: z.string().optional().default(''),
    Assert: z.union([BaseAssertionSchema, AssertionAssertSchema]).optional(),
    ParsingError: z.boolean().optional().default(false),
    ErrorStatus: z.enum([
        ERROR_STATUS.SUCCESS,
        ERROR_STATUS.ERROR,
        ERROR_STATUS.WARNING
    ]).optional().default(ERROR_STATUS.SUCCESS)
});

export const AiScriptOutputSchema = z.object({
    Actions: z.array(AiScriptActionSchema).optional().default([]),
    Reasoning: z.string().optional().default(''),
    Warning: z.string().optional().default(''),
    ParsingError: z.boolean().optional().default(false),
    ErrorStatus: z.enum([
        ERROR_STATUS.SUCCESS,
        ERROR_STATUS.ERROR,
        ERROR_STATUS.WARNING
    ]).optional().default(ERROR_STATUS.SUCCESS)
});

export type AgentOutputData = z.infer<typeof AgentOutputSchema>;
export type AiScriptOutputData = z.infer<typeof AiScriptOutputSchema>;

export class AgentOutput {
    Actions: BaseAction[];
    Reasoning: string;
    Warning: string;
    ParsingError: boolean;
    Assert: BaseAssertion | AssertionAssert | null;
    ErrorStatus: typeof ERROR_STATUS[keyof typeof ERROR_STATUS];

    constructor(data?: Partial<AgentOutputData>) {
        // Parse and validate the entire data object using the schema
        const validatedData = AgentOutputSchema.parse(data || {});
        
        // Set properties from validated data
        this.Actions = validatedData.Actions || [];
        this.Reasoning = validatedData.Reasoning || '';
        this.Warning = validatedData.Warning || '';
        this.ParsingError = validatedData.ParsingError || false;
        this.ErrorStatus = validatedData.ErrorStatus || ERROR_STATUS.SUCCESS;
        
        // Validate and transform Assert if present
        // Try to parse as BaseAssertion first (for ai_verify), then as AssertionAssert (for ai_assert)
        if (validatedData.Assert) {
            try {
                // Try full assertion schema first (ai_verify)
                this.Assert = BaseAssertionSchema.parse(validatedData.Assert) as BaseAssertion;
            } catch {
                // If that fails, try assertion assert schema (ai_assert)
                try {
                    this.Assert = AssertionAssertSchema.parse(validatedData.Assert) as AssertionAssert;
                } catch {
                    // If both fail, set to null
                    this.Assert = null;
                }
            }
        } else {
            this.Assert = null;
        }
    }

    /**
     * Check if the response indicates an error
     * @returns true if there's an error, false otherwise
     */
    hasError(): boolean {
        return this.ParsingError || 
               this.ErrorStatus === ERROR_STATUS.ERROR || 
               this.Reasoning.includes("Error Type:") ||
               this.Warning.includes("Error Type:");
    }

    /**
     * Get error message if present
     * @returns error message or null if no error
     */
    getErrorMessage(): string | null {
        if (this.hasError()) {
            if (this.ParsingError) {
                return `AI Agent Response Error: ${this.Warning}`;
            }
            if (this.ErrorStatus === ERROR_STATUS.ERROR) {
                return `AI Agent Error: ${this.Reasoning}`;
            }
            if (this.Reasoning.includes("Error Type:")) {
                return `AI Agent Error: ${this.Reasoning}`;
            }
            if (this.Warning.includes("Error Type:")) {
                return `AI Agent Error: ${this.Warning}`;
            }
        }
        return null;
    }
}