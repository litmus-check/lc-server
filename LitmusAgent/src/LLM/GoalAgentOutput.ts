import { z } from "zod";
import { BaseAction, BaseActionSchema } from "../types/actions";

export enum GoalOutput {
    SUCCESS = "SUCCESS",
    FAILED = "FAILED",
    UNKNOWN = "UNKNOWN"
}

// Individual action tool schemas
export const AiClickSchema = z.object({
    elementId: z.number().describe("The unique identifier of the element to click. Must be a valid element ID from the current page."),
    prompt: z.string().describe("Provide a concise, descriptive identifier for the target element (e.g., 'Login button', 'Submit button', 'Navigation menu', 'Search icon'). Use clear, specific terms that uniquely identify the element. For elements without unique identifiers, use visually visible labels, text. Avoid verbose instructions like 'click on the login button' or 'press the submit button' - just provide the element identifier."),
    reasoning: z.string().describe("Explanation of why this click action is necessary to achieve the goal. Include the logical reasoning behind this step."),
    warning: z.string().optional().describe("Any potential issues or warnings about this action. Leave empty if no warnings.")
});

export const AiInputSchema = z.object({
    elementId: z.number().describe("The unique identifier of the input field to type into. Must be a valid element ID from the current page."),
    prompt: z.string().describe("Provide a concise, descriptive identifier (e.g., 'Username', 'Password', 'Email', 'Search box', 'Comment textarea'). Use clear, specific terms that uniquely identify the input element. For fields without unique identifiers, use visually visible labels, placeholder text. Avoid verbose instructions like 'type in the username field' or 'enter text in the password field' or 'enter username' - just provide the element identifier."),
    value: z.string().describe("The exact text to enter into the input field. Should be the complete value needed."),
    reasoning: z.string().describe("Explanation of why this input action is necessary to achieve the goal. Include the logical reasoning behind this step."),
    warning: z.string().optional().describe("Any potential issues or warnings about this action. Leave empty if no warnings.")
});

export const AiSelectSchema = z.object({
    elementId: z.number().describe("The unique identifier of the dropdown/select element. Must be a valid element ID from the current page."),
    prompt: z.string().describe("Provide a concise, descriptive identifier for the dropdown/select element (e.g., 'Country dropdown', 'Category menu', 'Language selector', 'Size picker', 'Department list'). Use clear, specific terms that uniquely identify the dropdown element. For dropdowns without unique identifiers, use visually visible labels, text. Avoid verbose instructions like 'select the country dropdown' or 'choose from the category menu' or 'select country - just provide the element identifier."),
    value: z.string().describe("The exact option value or text to select from the dropdown. Should match one of the available options."),
    reasoning: z.string().describe("Explanation of why this selection action is necessary to achieve the goal. Include the logical reasoning behind this step."),
    warning: z.string().optional().describe("Any potential issues or warnings about this action. Leave empty if no warnings.")
});

export const AiScriptSchema = z.object({
    prompt: z.string().describe("A clear description of the task to accomplish using the cleaned HTML content. Should specify what actions need to be performed on the page."),
    reasoning: z.string().describe("Explanation of why generating a script is necessary to achieve the goal. Include the logical reasoning behind this approach."),
    warning: z.string().optional().describe("Any potential issues or warnings about this action. Leave empty if no warnings.")
});

// export const AiVerifySchema = z.object({
//     elementId: z.number().describe("The unique identifier of the element to verify. Must be a valid element ID from the current page."),
//     prompt: z.string().describe("A clear description of what to verify on the page. Should specify the expected condition or content."),
//     value: z.string().describe("The expected value or condition to verify. Should be the specific text, attribute, or state to check."),
//     code: z.string().describe("Playwright code snippet to perform the verification. Should be valid JavaScript code that can be executed in the browser."),
//     validation: z.boolean().describe("Whether the verification should pass (true) or fail (false) for the goal to be considered successful."),
//     reasoning: z.string().describe("Explanation of why this verification is necessary to achieve the goal. Include the logical reasoning behind this step."),
//     warning: z.string().optional().describe("Any potential issues or warnings about this action. Leave empty if no warnings.")
// });

// export const AiHoverSchema = z.object({
//     elementId: z.number().describe("The unique identifier of the element to hover over. Must be a valid element ID from the current page."),
//     prompt: z.string().describe("A clear description of what element to hover over and why. Should be specific enough to identify the target element."),
//     reasoning: z.string().describe("Explanation of why this hover action is necessary to achieve the goal. Include the logical reasoning behind this step."),
//     warning: z.string().optional().describe("Any potential issues or warnings about this action. Leave empty if no warnings.")
// });

export const GoToUrlSchema = z.object({
    url: z.string().describe("The complete URL to navigate to. Must be a valid URL including protocol (http:// or https://)."),
    reasoning: z.string().describe("Explanation of why navigating to this URL is necessary to achieve the goal. Include the logical reasoning behind this step."),
    warning: z.string().optional().describe("Any potential issues or warnings about this action. Leave empty if no warnings.")
});

export const GoBackSchema = z.object({
    reasoning: z.string().describe("Explanation of why going back to the previous page is necessary to achieve the goal. Include the logical reasoning behind this step."),
    warning: z.string().optional().describe("Any potential issues or warnings about this action. Leave empty if no warnings.")
});

export const WaitTimeSchema = z.object({
    delay_seconds: z.number().describe("The number of seconds to wait. Should be a positive number, typically between 1-30 seconds."),
    reasoning: z.string().describe("Explanation of why this wait is necessary to achieve the goal. Include the logical reasoning behind this step."),
    warning: z.string().optional().describe("Any potential issues or warnings about this action. Leave empty if no warnings.")
});

export const ScrollSchema = z.object({
    direction: z.enum(['up', 'down', 'left', 'right']).describe("The direction to scroll. Use 'up' to scroll up, 'down' to scroll down, 'left' to scroll left, 'right' to scroll right."),
    value: z.number().describe("The number of pixels to scroll. Should be a positive number, typically between 100-1000 pixels."),
    reasoning: z.string().describe("Explanation of why this scroll action is necessary to achieve the goal. Include the logical reasoning behind this step."),
    warning: z.string().optional().describe("Any potential issues or warnings about this action. Leave empty if no warnings.")
});

// export const OpenTabSchema = z.object({
//     url: z.string().describe("The complete URL to open in a new tab. Must be a valid URL including protocol (http:// or https://)."),
//     reasoning: z.string().describe("Explanation of why opening a new tab with this URL is necessary to achieve the goal. Include the logical reasoning behind this step."),
//     warning: z.string().optional().describe("Any potential issues or warnings about this action. Leave empty if no warnings.")
// });

// export const RunScriptSchema = z.object({
//     description: z.string().describe("A clear description of what the script will do. Should explain the purpose and expected outcome of the script execution."),
//     script: z.string().describe("Valid JavaScript code to execute in the browser. Should be complete and executable code that performs the described action."),
//     reasoning: z.string().describe("Explanation of why running this script is necessary to achieve the goal. Include the logical reasoning behind this step."),
//     warning: z.string().optional().describe("Any potential issues or warnings about this action. Leave empty if no warnings.")
// });

// Done tool schema for goal completion
export const DoneSchema = z.object({
    output: z.enum([GoalOutput.SUCCESS, GoalOutput.FAILED]).describe("The final status of the goal. Use SUCCESS if the goal was achieved, FAILED if it could not be completed."),
    reasoning: z.string().describe("Detailed explanation of why the goal was marked as SUCCESS or FAILED. Include the final reasoning and any key factors that led to this conclusion."),
    goalDescription: z.string().describe("A summary description of what the goal was trying to achieve. Should be a concise overview of the original objective.")
});

// Main schema without Status field
export const GoalAgentOutputSchema = z.object({
    Actions: z.array(z.object({
        type: z.string(),
        elementId: z.number().nullable().optional(),
        prompt: z.string().optional(),
        value: z.union([z.number(), z.string()]).optional(),
        url: z.string().optional(),
        delay_seconds: z.number().optional(),
        direction: z.string().optional(),
        description: z.string().optional(),
        script: z.string().optional(),
        toEmail: z.string().optional()
    })),
    Reasoning: z.string(),
    Warning: z.string(),
    GoalDescription: z.string()
});

export type GoalAgentOutputData = z.infer<typeof GoalAgentOutputSchema>;

export class GoalAgentOutput {
    Actions: BaseAction[];
    Reasoning: string;
    Warning: string;
    GoalDescription: string;

    constructor(data?: Partial<GoalAgentOutputData>) {
        // Validate and transform Actions - preserve all properties
        this.Actions = (data?.Actions || []).map(action => {
            // Validate the basic structure but preserve all properties
            const validated = GoalAgentOutputSchema.shape.Actions.element.parse(action);
            return validated as BaseAction;
        });

        // Set other properties with defaults
        this.Reasoning = data?.Reasoning || '';
        this.Warning = data?.Warning || '';
        this.GoalDescription = data?.GoalDescription || '';
    }
} 

export const VerificationExtractorSchema = z.object({
    prompt: z.string().describe("The name of the web application to fetch verification information for."),
    reasoning: z.string().describe("Explanation of why this verification extraction is necessary to achieve the goal. Include the logical reasoning behind this step."),
    warning: z.string().optional().describe("Any potential issues or warnings about this action. Leave empty if no warnings."),
    toEmail: z.string().optional().describe("Optional email address to filter emails by recipient. Only verification codes/links from emails sent to this address will be extracted.")
});