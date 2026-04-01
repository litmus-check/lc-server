import { BaseLLM, LLMLogContext } from './LLM';
import { AgentOutput } from './AgentOutput';
import { EmailData } from '../email/GmailClient';
import { logger } from '../utils/logger';
import { BaseMessage, HumanMessage } from '@langchain/core/messages';
import { AzureChatOpenAI } from '@langchain/openai';
import { StructuredTool } from '@langchain/core/tools';
import { z } from 'zod';
import fs from 'fs';
import path from 'path';
import { awaitAllCallbacks } from "@langchain/core/callbacks/promises";

export interface VerificationResult {
    type: 'code' | 'link';
    value: string;
}

// Schema for the verification extraction tool
const VerificationExtractionSchema = z.object({
    type: z.enum(['code', 'link']).describe("The type of verification found - either 'code' or 'link'"),
    value: z.string().describe("The extracted verification code or link, or 'none' if no verification found")
});

// Tool for extracting verification codes/links from email content
class EmailVerificationExtractionTool extends StructuredTool<typeof VerificationExtractionSchema> {
    name = "extract_verification";
    description = "Extract verification code or link from email content";
    schema = VerificationExtractionSchema;

    async _call(input: z.infer<typeof VerificationExtractionSchema>): Promise<string> {
        return JSON.stringify({
            type: input.type,
            value: input.value
        });
    }
}

export class VerificationExtractor extends BaseLLM {
    private promptTemplate: string = '';

    constructor() {
        super();
        this.loadPromptTemplate();
    }

    protected initializeModel(): void {
        const endpoint = process.env.AZURE_OPENAI_ENDPOINT;
        const modelName = process.env.AZURE_OPENAI_MODEL_NAME;
        const deployment = process.env.AZURE_OPENAI_DEPLOYMENT_NAME;
        const apiKey = process.env.AZURE_OPENAI_KEY;
        const apiVersion = "2024-04-01-preview";

        this.model = new AzureChatOpenAI({
            modelName: modelName,
            temperature: 0.7,
            maxTokens: 16000,
            openAIApiKey: apiKey,
            openAIBasePath: endpoint,
            deploymentName: deployment,
            openAIApiVersion: apiVersion,
            azureOpenAIApiInstanceName: process.env.AZURE_OPENAI_INSTANCE_NAME,
        });
    }

    public async invokeWithTools(
        messages: BaseMessage[],
        logContext?: LLMLogContext
    ): Promise<AgentOutput> {
        try {
            logger.info('Starting verification extraction with tools');
            
            const response = await (this.model as any).invoke(messages, {
                tools: [new EmailVerificationExtractionTool()],
                metadata: {
                    "run_id": logContext?.runId,
                    "instruction_id": logContext?.instructionId,
                    "agent": logContext?.agent
                }
            }
        );

            logger.info("Verification LLM Response: " + JSON.stringify(response));
            
            try {
                // Parse the tool call response
                const toolCall = response.additional_kwargs.tool_calls?.[0];
                if (!toolCall) {
                    logger.error("No valid tool call arguments found in verification response");
                    return new AgentOutput({
                        Actions: [],
                        Reasoning: "No valid tool call arguments found in verification response",
                        Warning: "Failed to extract verification from LLM response",
                        ParsingError: true,
                        ErrorStatus: "error"
                    });
                }

                const verificationData = JSON.parse(toolCall.function.arguments);
                logger.info('Verification tool call result:', verificationData);
                
                // Return the verification data directly
                return {
                    type: "tool_call",
                    tool: "extract_verification",
                    args: {
                        type: verificationData.type,
                        value: verificationData.value
                    }
                } as any;

            } catch (error: any) {
                logger.error(`Verification LLM Parsing Error: ${error.message}`);
                return {
                    type: "tool_call",
                    tool: "extract_verification",
                    args: {
                        type: "code",
                        value: "none"
                    }
                } as any;
            } finally {
                await awaitAllCallbacks();
            }
        } catch (error: any) {
            logger.error("Error in verification invokeWithTools:", error);
            return {
                type: "tool_call",
                tool: "extract_verification",
                args: {
                    type: "code",
                    value: "none"
                }
            } as any;
        } finally {
            await awaitAllCallbacks();
        }
    }

    /**
     * Creates a tool call for verification extraction
     */
    private createVerificationToolCall(result: VerificationResult): any {
        return {
            type: "tool_call",
            tool: "verification_extractor",
            args: {
                type: result.type,
                value: result.value
            }
        };
    }

    private loadPromptTemplate() {
        try {
            const promptPath = path.join(__dirname, 'prompts', 'verification_extraction_prompt.md');
            this.promptTemplate = fs.readFileSync(promptPath, 'utf-8');
        } catch (error) {
            logger.error('Error loading verification extraction prompt:', error);
            throw new Error('Verification extraction prompt file not found');
        }
    }

    /**
     * Extracts verification code or link from email data using invokeWithTools
     * @param emailData The email data to analyze
     * @param url Optional URL context for better extraction
     * @returns Promise<any> Tool call with verification information
     */
    async extractVerification(emailData: EmailData, url?: string, logContext?: LLMLogContext): Promise<any> {
        try {
            logger.info('Starting verification extraction from email data using invokeWithTools');

            // Prepare the prompt with email data
            const prompt = this.promptTemplate
                .replace('{{subject}}', emailData.subject)
                .replace('{{content}}', emailData.content)
                .replace('{{from}}', emailData.from)
                .replace('{{date}}', emailData.date)
                .replace('{{url}}', url || 'No URL provided');

            // Use invokeWithTools instead of direct model invocation
            const toolCallResult = await this.invokeWithTools([
                new HumanMessage(prompt)
            ], logContext);

            logger.info('Tool call result from invokeWithTools:', JSON.stringify(toolCallResult, null, 2));

            // The invokeWithTools method now returns a tool call directly
            if (toolCallResult && (toolCallResult as any).type === 'tool_call' && (toolCallResult as any).tool === 'extract_verification') {
                return toolCallResult;
            }

            // If no verification found, return none
            logger.warn('No verification found in tool call result');
            const result: VerificationResult = {
                type: 'code',
                value: 'none'
            };
            return this.createVerificationToolCall(result);

        } catch (error) {
            logger.error('Error extracting verification from email:', error);
            const result: VerificationResult = {
                type: 'code',
                value: 'none'
            };
            return this.createVerificationToolCall(result);
        }
    }



    /**
     * Extracts verification from multiple emails (useful for getting the latest)
     * @param emails Array of email data
     * @param url Optional URL context
     * @returns Promise<any[]> Array of tool call results
     */
    async extractFromMultipleEmails(emails: EmailData[], url?: string, logContext?: LLMLogContext): Promise<any[]> {
        const results: any[] = [];
        
        for (const email of emails) {
            // log email subject
            logger.info(`Email subject: ${email.subject}`);
            const result = await this.extractVerification(email, url, logContext);
            results.push(result);
            
            // Return as soon as a valid verification is found
            if (result.args && result.args.value !== 'none') {
                logger.info(`Found valid verification in email: ${email.subject}`);
                break;
            }
        }

        return results;
    }

    /**
     * Gets the first non-"none" verification result from multiple emails
     * @param emails Array of email data
     * @param url Optional URL context
     * @returns Promise<any | null> First valid verification tool call or null
     */
    async getFirstValidVerification(emails: EmailData[], url?: string, logContext?: LLMLogContext): Promise<any | null> {
        const results = await this.extractFromMultipleEmails(emails, url, logContext);
        
        for (const result of results) {
            if (result.args && result.args.value !== 'none') {
                return result;
            }
        }

        return null;
    }
}
