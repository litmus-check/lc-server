import { z } from "zod";
import { TRIAGE_CATEGORIES, TRIAGE_SUB_CATEGORIES } from "../config/constants";

// Triage analysis tool schema
export const TriageAnalysisSchema = z.object({
    description: z.string().describe("Issue description in simple language."),
    category: z.enum(Object.values(TRIAGE_CATEGORIES) as [string, ...string[]]).describe(
        `Primary categorization of the issue. MUST be one of: "${TRIAGE_CATEGORIES.RAISE_BUG}", "${TRIAGE_CATEGORIES.UPDATE_SCRIPT}", "${TRIAGE_CATEGORIES.CANNOT_CONCLUDE}", "${TRIAGE_CATEGORIES.RETRY_WITHOUT_CHANGES}", or "${TRIAGE_CATEGORIES.SUCCESSFUL_ON_RETRY}". ` +
        `NEVER use sub-category values (add_new_step, remove_step, replace_step, re_generate_script) as category values.`
    ),
    sub_category: z.enum(Object.values(TRIAGE_SUB_CATEGORIES) as [string, ...string[]]).optional().describe(
        `Optional sub-category ONLY when category is "${TRIAGE_CATEGORIES.UPDATE_SCRIPT}". ` +
        `MUST be one of: "${TRIAGE_SUB_CATEGORIES.ADD_NEW_STEP}", "${TRIAGE_SUB_CATEGORIES.REMOVE_STEP}", "${TRIAGE_SUB_CATEGORIES.REPLACE_STEP}", or "${TRIAGE_SUB_CATEGORIES.RE_GENERATE_SCRIPT}". ` +
        `Do NOT include this field if category is not "${TRIAGE_CATEGORIES.UPDATE_SCRIPT}".`
    ),
    reasoning: z.string().describe("Categorization reasoning."),
    prompt: z.string().optional().describe("Updated prompt for the failed instruction. Required when sub_category is replace_step or add_new_step.")
});

// Main triage output schema
export const TriageAgentOutputSchema = z.object({
    description: z.string(),
    category: z.enum(Object.values(TRIAGE_CATEGORIES) as [string, ...string[]]),
    sub_category: z.enum(Object.values(TRIAGE_SUB_CATEGORIES) as [string, ...string[]]).optional(),
    reasoning: z.string(),
    prompt: z.string().optional(),
    success: z.boolean(),
    parsing_error: z.boolean()
});

export type TriageAnalysisData = z.infer<typeof TriageAnalysisSchema>;
export type TriageAgentOutputData = z.infer<typeof TriageAgentOutputSchema>;

export class TriageAgentOutput {
    description: string;
    category: string;
    sub_category?: string;
    reasoning: string;
    prompt?: string;
    success: boolean;
    parsing_error: boolean;

    constructor(data?: Partial<TriageAgentOutputData>) {
        // Create safe data
        const safeData = {
            description: data?.description || '',
            category: data?.category || '',
            sub_category: data?.sub_category || undefined,
            reasoning: data?.reasoning || '',
            prompt: data?.prompt || undefined,
            success: data?.success || false,
            parsing_error: data?.parsing_error || false,
            ...data
        } as Partial<TriageAgentOutputData>;


        // Validate the data using the schema
        const validatedData = TriageAgentOutputSchema.parse(safeData || {});
        
        // Set properties from validated data
        this.description = validatedData.description || '';
        this.category = validatedData.category || '';
        this.sub_category = validatedData.sub_category || undefined;
        this.reasoning = validatedData.reasoning || '';
        this.prompt = validatedData.prompt || undefined;
        this.success = validatedData.success || false;
        this.parsing_error = validatedData.parsing_error || false;
    }
}
