import { BaseChatModel } from "@langchain/core/language_models/chat_models";
import { ChatOpenAI } from "@langchain/openai";
import { AzureChatOpenAI } from "@langchain/openai";
import { BaseMessage } from '@langchain/core/messages';
import { AgentOutput, AgentOutputSchema, AiScriptOutputSchema } from "./AgentOutput";
import { GoalAgentOutput, GoalOutput, AiClickSchema, AiInputSchema, AiSelectSchema, AiScriptSchema, GoToUrlSchema, WaitTimeSchema, DoneSchema, VerificationExtractorSchema, ScrollSchema, GoBackSchema } from "./GoalAgentOutput";
import { TriageAnalysisSchema, TriageAgentOutput } from "./TriageAgentOutput";
import { logger } from "../utils/logger";
import { StructuredTool } from "@langchain/core/tools";
import { z } from "zod";
import dotenv from "dotenv";
import { Instruction } from "../types/agent";
import { ACTION_TYPES, FRAMEWORKS, ERROR_STATUS, TRIAGE_CATEGORIES, TRIAGE_MODE } from "../config/constants";
import { awaitAllCallbacks } from "@langchain/core/callbacks/promises";

dotenv.config();

export enum LLMErrorType {
    TOKEN_LIMIT = "TOKEN_LIMIT",
    RATE_LIMIT = "RATE_LIMIT",
    POLICY_VIOLATION = "POLICY_VIOLATION",
    UNKNOWN = "UNKNOWN"
}

export interface LLMConfig {
    modelName: string;
    temperature?: number;
    maxTokens?: number;
    apiKey?: string;
}

export interface LLMLogContext {
    runId: string;
    instructionId?: string;
    containerCommsService?: any;
    agent?: string | undefined;      // action type
}

export interface LLMInputs {
    elements: any[];
    currentUrl: string;
    screenshot: string;
}

export abstract class BaseLLM {
    public model!: BaseChatModel;
  
    constructor() {
      this.initializeModel();
    }

    // public abstract invoke(messages: BaseMessage[], logContext?: LLMLogContext): Promise<AgentOutput>;

    public abstract invokeWithTools(
        messages: BaseMessage[],
        logContext?: LLMLogContext
    ): Promise<AgentOutput>;
  
    protected abstract initializeModel(): void;

    /**
     * Generate structured instruction message for message manager
     * @param instruction The instruction to format
     * @param pageContent Optional page content for ai_verify and ai_assert actions
     * @returns JSON string representation of the instruction
     */
    public static generateInstructionMessage(instruction: Instruction, pageContent?: string): string {

        // If instruction type is goal, then we need to send it is string not JSON
        if(instruction.action === ACTION_TYPES.GOAL){
            return "Goal: " + (instruction.prompt as string);
        }

        const messageData: any = {
            action: instruction.action,
            prompt: instruction.prompt
        };

        // If instruction type is verification, then take prompt from args
        if(instruction.action === ACTION_TYPES.VERIFICATION){
            messageData.prompt = instruction.args?.find((arg: any) => arg.key === 'prompt')?.value;
            messageData.check = instruction.args?.find((arg: any) => arg.key === 'check')?.value;
        }


        // Add framework and extracted content for ai_verify action
        if (instruction.action === ACTION_TYPES.VERIFY) {
            messageData.framework = FRAMEWORKS.PLAYWRIGHT;
            if (pageContent) {
                messageData.extracted_content = pageContent;
            }
        }

        if (instruction.action === ACTION_TYPES.SCRIPT) {
            const taskPrompt = instruction.args?.find((arg: any) => arg.key === 'prompt')?.value;
            messageData.task_prompt = taskPrompt;
        }

        return JSON.stringify(messageData);
    }

    public static generateContentMessage(instruction: Instruction, pageContent?: string): string {
        const messageData: any = {};
        if (pageContent) {
            messageData.content = pageContent;
        }
        return JSON.stringify(messageData);
    }

    /**
     * Generate structured vision message for message manager
     * @param llmInputs The LLM inputs containing elements, URL, and screenshot
     * @returns Array of message content for vision model
     */
    public static generateVisionMessage(llmInputs: LLMInputs): Array<{ type: "text"; text: string } | { type: "image_url"; image_url: { url: string } }> {
        // Filter out selectors from elements before sending to LLM
        const elementsWithoutSelectors = llmInputs.elements.map(element => {
            const { selector, selectors, ...elementWithoutSelectors } = element;
            return elementWithoutSelectors;
        });

        return [
            {
                type: 'text' as const,
                text: JSON.stringify({
                    elements: elementsWithoutSelectors,
                    currentUrl: llmInputs.currentUrl,
                })
            },
            {
                type: 'image_url' as const,
                image_url: {
                    url: llmInputs.screenshot
                }
            }
        ];
    }

    public static generateVisionMessageOnly(screenshot: string): Array<{ type: "image_url"; image_url: { url: string } }> {
        return [
            {
                type: 'image_url' as const,
                image_url: {
                    url: screenshot
                }
            }
        ];
    }

    // protected async logToRedis(logContext: LLMLogContext | undefined, logData: { info?: string; error?: string; timestamp: string; instructionId?: string }) {
    //     if (logContext?.containerCommsService && logContext.runId) {
    //         try {
    //             await logContext.containerCommsService.addLog(logContext.runId, {
    //                 ...logData,
    //                 instructionId: logData.instructionId || logContext.instructionId
    //             });
    //         } catch (error) {
    //             logger.error(`Failed to log to Redis: ${error}`);
    //         }
    //     }
    // }

    protected handleLLMError(error: any): { type: LLMErrorType; message: string } {
        const errorMessage = error.message?.toLowerCase() || '';
        
        if (errorMessage.includes('token') || errorMessage.includes('length')) {
            return {
                type: LLMErrorType.TOKEN_LIMIT,
                message: "🚫 Too many tokens. Please try with a shorter input."
            };
        }
        
        if (errorMessage.includes('rate') || errorMessage.includes('limit')) {
            return {
                type: LLMErrorType.RATE_LIMIT,
                message: "⏳ Rate limit exceeded. Please try again in a few moments."
            };
        }
        
        if (errorMessage.includes('policy') || errorMessage.includes('violation')) {
            return {
                type: LLMErrorType.POLICY_VIOLATION,
                message: "🚨 Policy violation detected. Please review your input."
            };
        }
        
        return {
            type: LLMErrorType.UNKNOWN,
            message: "❌ An unexpected error occurred. Please try again."
        };
    }

    protected handleParsingError(error: any): AgentOutput {
        return new AgentOutput({
            Actions: [],
            Reasoning: "Failed to parse agent response",
            Warning: error.message || "Invalid response format",
            ParsingError: true,
            ErrorStatus: ERROR_STATUS.ERROR
        });
    }
}
  
export class LLMAgent extends BaseLLM {
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

    public async invokeTriageWithTools(
        messages: BaseMessage[],
        logContext?: LLMLogContext
    ): Promise<TriageAgentOutput> {
        try {
            const tools: any[] = [
                new TriageAnalysisTool()
            ];

            const response = await (this.model as any).invoke(messages, {
                tool_choice: { type: "function", function: { name: "triage_analysis" } },
                tools: tools,
                metadata: {
                    "run_id": logContext?.runId,
                    "instruction_id": logContext?.instructionId,
                    "agent": TRIAGE_MODE
                }
            });

            logger.info("Triage LLM Raw Response: " + JSON.stringify(response));

            try {
                const toolCalls = response.additional_kwargs?.tool_calls || [];
                const triageCall = toolCalls.find((tc: any) => tc.function?.name === 'triage_analysis');
                if (!triageCall) {
                    throw new Error('No triage_analysis tool call found');
                }
                const argsStr = triageCall.function?.arguments || '{}';
                const argsObj = JSON.parse(argsStr);

                // Log to container
                await logContext?.containerCommsService?.addLog(logContext?.runId, {
                    info: `Triage Agent Response: ${JSON.stringify(argsObj)}`,
                    timestamp: new Date().toISOString(),
                    instructionId: logContext?.instructionId
                });

                const AgentResponse = new TriageAgentOutput({...argsObj, success: true, parsing_error: false});

                logger.info('Triage Agent Response: ' + JSON.stringify(AgentResponse));

                return AgentResponse;
            } catch (error: any) {
                logger.error(`Triage LLM Parsing Error: ${error.message}`);
                await logContext?.containerCommsService?.addLog(logContext?.runId, {
                    error: `Failed to parse triage response: ${error.message}`,
                    timestamp: new Date().toISOString(),
                    instructionId: logContext?.instructionId
                });
                return new TriageAgentOutput({
                    description: "",
                    category: TRIAGE_CATEGORIES.CANNOT_CONCLUDE,
                    sub_category: undefined,
                    reasoning: "Unable to complete triaging",
                    success: false,
                    parsing_error: true
                });
            } finally {
                await awaitAllCallbacks();
            }
        } catch (error: any) {
            const { type, message } = this.handleLLMError(error);
            logger.error(`Triage LLM Error: ${type} - ${message}`);
            await logContext?.containerCommsService?.addLog(logContext?.runId, {
                error: `Error in triage LLM: ${type}`,
                timestamp: new Date().toISOString(),
                instructionId: logContext?.instructionId
            });
            return new TriageAgentOutput({
                description: `Error in triage analysis: ${type}`,
                category: TRIAGE_CATEGORIES.CANNOT_CONCLUDE,
                sub_category: undefined,
                reasoning: message,
                success: false,
                parsing_error: false
            });
        } finally {
            await awaitAllCallbacks();
        }
    }

    // public async invoke(messages: BaseMessage[], logContext?: LLMLogContext): Promise<AgentOutput> {
    //     try {
    //         // Log input
    //         logger.info(`LLM Input: ${JSON.stringify(messages)}`);
    //         await this.logToRedis(logContext, {
    //             info: `LLM Input: ${JSON.stringify(messages)}`,
    //             timestamp: new Date().toISOString()
    //         });

    //         const response = await this.model.invoke(messages);
    //         try {
    //             const parsed = JSON.parse(response.content as string);
                
    //             // Log output
    //             logger.info(`LLM Output: ${JSON.stringify(parsed)}`);
    //             await this.logToRedis(logContext, {
    //                 info: `LLM Output: ${JSON.stringify(parsed)}`,
    //                 timestamp: new Date().toISOString()
    //             });

    //             return new AgentOutput({
    //                 ...AgentOutputSchema.parse(parsed),
    //                 ParsingError: false
    //             });
    //         } catch (error: any) {
    //             // Log parsing error
    //             logger.error(`LLM Parsing Error: ${error.message}`);
    //             await this.logToRedis(logContext, {
    //                 error: `LLM Parsing Error: ${error.message}`,
    //                 timestamp: new Date().toISOString()
    //             });
    //             return this.handleParsingError(error);
    //         }
    //     } catch (error: any) {
    //         const { type, message } = this.handleLLMError(error);
            
    //         // Log LLM error
    //         logger.error(`LLM Error: ${type} - ${message}`);
    //         await this.logToRedis(logContext, {
    //             error: `LLM Error: ${type} - ${message}`,
    //             timestamp: new Date().toISOString()
    //         });

    //         return new AgentOutput({
    //             Actions: [],
    //             Reasoning: `Error Type: ${type}`,
    //             Warning: message,
    //             ParsingError: false,
    //             ErrorStatus: ERROR_STATUS.ERROR
    //         });
    //     }
    // }
    
    public async invokeWithTools(
        messages: BaseMessage[],
        logContext?: LLMLogContext
    ): Promise<AgentOutput> {
        try {
            let response: any;

            if(logContext?.agent === ACTION_TYPES.SCRIPT){
                await logContext?.containerCommsService?.addLog(logContext?.runId, {
                    info: `Generating script for action`,
                    timestamp: new Date().toISOString()
                });
                response = await (this.model as any).invoke(messages, {
                    tool_choice: { type: "function", function: { name: "ai_script_output" } },
                    tools: [new AiScriptOutputTool()],
                    metadata: {
                        "run_id": logContext?.runId,
                        "instruction_id": logContext?.instructionId,
                        "agent": logContext?.agent
                    }
                });
            }      
            else {
                // Skip generic log for ai_assert - it will be logged in handleAiAssert
                if (logContext?.agent !== ACTION_TYPES.ASSERT) {
                    await logContext?.containerCommsService?.addLog(logContext?.runId, {
                        info: `Identifying element for action`,
                        timestamp: new Date().toISOString()
                    });
                }
                response = await (this.model as any).invoke(messages, {
                    tool_choice: { type: "function", function: { name: "agent_output" } },
                    tools: [new AgentOutputTool()],
                    metadata: {
                        "run_id": logContext?.runId,
                        "instruction_id": logContext?.instructionId,
                        "agent": logContext?.agent
                    }
                });
            }      

            logger.info("LLM Response: " + JSON.stringify(response));
            // await this.logToRedis(logContext, {
            //     info: `Full LLM Response: ${JSON.stringify(response, null, 2)}`,
            //     timestamp: new Date().toISOString()
            // });
            
            try {
                // Parse the tool call response
                const toolCall = response.additional_kwargs.tool_calls?.[0];
                if (!toolCall) {
                    // Log error
                    const errorMsg = "No valid tool call arguments found in response";
                    logger.error(errorMsg);
                    // await this.logToRedis(logContext, {
                    //     error: errorMsg,
                    //     timestamp: new Date().toISOString()
                    // });
                    await logContext?.containerCommsService?.addLog(logContext?.runId, {
                        error: "Unable to identify element for action",
                        timestamp: new Date().toISOString()
                    });

                    return new AgentOutput({
                        Actions: [],
                        Reasoning: "No valid tool call arguments found in response",
                        Warning: "Failed to extract tool call arguments from LLM response",
                        ParsingError: true,
                        ErrorStatus: ERROR_STATUS.ERROR
                    });
                }

                const action = JSON.parse(toolCall.function.arguments) as AgentOutput;
                const parsedData = AgentOutputSchema.parse(action);

                // Log successful output
                // logger.info(`LLM Output with Tools: ${JSON.stringify(parsedData)}`);
                // await this.logToRedis(logContext, {
                //     info: `LLM Output with Tools: ${JSON.stringify(parsedData)}`,
                //     timestamp: new Date().toISOString()
                // });

                // Handle empty Actions array case
                if (parsedData.Actions && parsedData.Actions.length > 0) {
                    logger.info('type of action: '+parsedData.Actions[0].type)
                    logger.info('Actions: '+JSON.stringify(action))
                    const elementId = parsedData.Actions[0].elementId? parsedData.Actions[0].elementId : "NA";
                    const script = parsedData.Actions[0].script? parsedData.Actions[0].script : "NA";
                    // Skip generic log for ai_assert - it will be logged in handleAiAssert
                    if (parsedData.Actions[0].type !== ACTION_TYPES.ASSERT) {
                        await logContext?.containerCommsService?.addLog(logContext?.runId, {
                            info: `Identified element for action: ${parsedData.Actions[0].type} ${elementId}`,
                            timestamp: new Date().toISOString()
                        });
                    }
                    if(parsedData.Actions[0].type === ACTION_TYPES.SCRIPT){
                        await logContext?.containerCommsService?.addLog(logContext?.runId, {
                            info: `Generated script for action: ${parsedData.Actions[0].type} ${script}`,
                            timestamp: new Date().toISOString()
                        });
                    }
                }
                
                // Return a proper AgentOutput instance instead of the parsed plain object
                return new AgentOutput(parsedData)

            } catch (error: any) {
                // Log parsing error
                logger.error(`LLM Parsing Error with Tools: ${error.message}`);
                // await this.logToRedis(logContext, {
                //     error: `LLM Parsing Error with Tools: ${error.message}`,
                //     timestamp: new Date().toISOString()
                // });
                return this.handleParsingError(error);
            }
            finally {
                await awaitAllCallbacks();
            }
        } catch (error: any) {
            logger.info("Error in invokeWithTools:", error);
            const { type, message } = this.handleLLMError(error);

            // Log LLM error
            logger.error(`LLM Error with Tools: ${type} - ${message}`);
            await logContext?.containerCommsService?.addLog(logContext?.runId, {
                error: `Error in identifying next action: ${type}`,
                timestamp: new Date().toISOString()
            });
            // await this.logToRedis(logContext, {
            //     error: `LLM Error with Tools: ${type} - ${message}`,
            //     timestamp: new Date().toISOString()
            // });

            return new AgentOutput({
                Actions: [],
                Reasoning: `Error Type: ${type}`,
                Warning: message,
                ParsingError: false,
                ErrorStatus: ERROR_STATUS.ERROR
            });
        }
        finally {
            await awaitAllCallbacks();
        }
    }

    public async invokeGoalWithTools(
        messages: BaseMessage[],
        logContext?: LLMLogContext,
        actionType?: string | undefined
    ): Promise<GoalAgentOutput> {
        try {

            // Create all available tools
            const tools: any[] = [
                new AiClickTool(),
                new AiInputTool(),
                new AiSelectTool(),
                new AiScriptTool(),
                // new AiVerifyTool(), // Commented out - not in supported actions list
                // new AiHoverTool(), // Commented out - not in supported actions list
                new GoToUrlTool(),
                new GoBackTool(),
                new ScrollTool(),
                new WaitTimeTool(),
                // new OpenTabTool(), // Commented out - not in supported actions list
                // new RunScriptTool(), // Commented out - not in supported actions list
                new DoneTool()
            ];

            if (actionType && actionType === ACTION_TYPES.VERIFY_EMAIL) {
                tools.push(new VerificationExtractorTool());
            }

            const response = await (this.model as any).invoke(messages, {
                tools: tools,
                metadata: {
                    "run_id": logContext?.runId,
                    "instruction_id": logContext?.instructionId,
                    "agent": actionType
                }
            }
        );

            logger.info("Goal LLM Response: " + JSON.stringify(response));
            
            try {
                // Parse the tool call response
                const toolCall = response.additional_kwargs.tool_calls?.[0];
                if (!toolCall) {
                    const errorMsg = "No valid tool call arguments found in goal response";
                    logger.error(errorMsg);
                    await logContext?.containerCommsService?.addLog(logContext?.runId, {
                        error: "Unable to generate goal instruction",
                        timestamp: new Date().toISOString()
                    });

                    return new GoalAgentOutput({
                        Actions: [],
                        Reasoning: "No valid tool call arguments found in goal response",
                        Warning: "Failed to extract tool call arguments from goal LLM response",
                        GoalDescription: "Failed to generate goal instruction"
                    });
                }

                const toolName = toolCall.function.name;
                const toolArgs = JSON.parse(toolCall.function.arguments);

                logger.info('Goal Tool Call: ' + toolName);
                logger.info('Goal Tool Args: ' + JSON.stringify(toolArgs));

                // Handle done tool call
                if (toolName === "done") {
                    const doneData = DoneSchema.parse(toolArgs);
                    await logContext?.containerCommsService?.addLog(logContext?.runId, {
                        info: `Goal completed with status: ${doneData.output}`,
                        timestamp: new Date().toISOString()
                    });

                    // Return a special GoalAgentOutput that indicates completion
                    const result = new GoalAgentOutput({
                        Actions: [],
                        Reasoning: doneData.reasoning,
                        Warning: "",
                        GoalDescription: doneData.goalDescription
                    });

                    // Add completion status to the result
                    (result as any).completionStatus = doneData.output;
                    return result;
                }

                // Handle action tool calls
                const action = {
                    type: toolName,
                    elementId: toolArgs.elementId,
                    prompt: toolArgs.prompt,
                    value: toolArgs.value,
                    url: toolArgs.url,
                    delay_seconds: toolArgs.delay_seconds,
                    direction: toolArgs.direction,
                    description: toolArgs.description,
                    script: toolArgs.script,
                    toEmail: toolArgs.toEmail
                };

                const elementId = action.elementId ? action.elementId : "NA";
                await logContext?.containerCommsService?.addLog(logContext?.runId, {
                    info: `Generated goal instruction: ${action.type} ${elementId}`,
                    timestamp: new Date().toISOString()
                });
                
                // Return a proper GoalAgentOutput instance
                return new GoalAgentOutput({
                    Actions: [action],
                    Reasoning: toolArgs.reasoning || "",
                    Warning: toolArgs.warning || "",
                    GoalDescription: "Goal in progress"
                });

            } catch (error: any) {
                logger.error(`Goal LLM Parsing Error: ${error.message}`);
                return new GoalAgentOutput({
                    Actions: [],
                    Reasoning: "Failed to parse goal LLM response",
                    Warning: error.message || "Invalid goal response format",
                    GoalDescription: "Failed to parse goal response"
                });
            }
            finally {
                await awaitAllCallbacks();
            }
        } catch (error: any) {
            logger.info("Error in invokeGoalWithTools:", error);
            const { type, message } = this.handleLLMError(error);

            logger.error(`Goal LLM Error: ${type} - ${message}`);
            await logContext?.containerCommsService?.addLog(logContext?.runId, {
                error: `Error in generating goal instruction: ${type}`,
                timestamp: new Date().toISOString()
            });

            return new GoalAgentOutput({
                Actions: [],
                Reasoning: `Error Type: ${type}`,
                Warning: message,
                GoalDescription: "Failed due to Agent error"
            });
        }
        finally {
            await awaitAllCallbacks();
        }
    }
}

export class AgentOutputTool extends StructuredTool<typeof AgentOutputSchema> {
    name = "agent_output";
    description = "Generate a structured agent response including reasoning and warnings";
    schema = AgentOutputSchema;
  
    async _call(input: z.infer<typeof AgentOutputSchema>): Promise<string> {
      // This is where you perform tool logic; you can return a string or structured data
      return JSON.stringify({
        ...input,
        processedBy: "AgentOutputTool"
      });
    }
  }

export class AiScriptOutputTool extends StructuredTool<typeof AiScriptOutputSchema> {
    name = "ai_script_output";
    description = "Generate a structured agent response including reasoning and warnings";
    schema = AiScriptOutputSchema;
  
    async _call(input: z.infer<typeof AiScriptOutputSchema>): Promise<string> {
        return JSON.stringify({
            ...input,
            processedBy: "AiScriptOutputTool"
        });
    }
}

export class AiClickTool extends StructuredTool<typeof AiClickSchema> {
    name = "ai_click";
    description = "Click on interactive elements like buttons, links, etc.";
    schema = AiClickSchema;
  
    async _call(input: z.infer<typeof AiClickSchema>): Promise<string> {
        return JSON.stringify({
            type: "ai_click",
            elementId: input.elementId,
            prompt: input.prompt,
            reasoning: input.reasoning,
            warning: input.warning
        });
    }
}

export class AiInputTool extends StructuredTool<typeof AiInputSchema> {
    name = "ai_input";
    description = "Enter text into input fields";
    schema = AiInputSchema;
  
    async _call(input: z.infer<typeof AiInputSchema>): Promise<string> {
        return JSON.stringify({
            type: "ai_input",
            elementId: input.elementId,
            prompt: input.prompt,
            value: input.value,
            reasoning: input.reasoning,
            warning: input.warning
        });
    }
}

export class AiSelectTool extends StructuredTool<typeof AiSelectSchema> {
    name = "ai_select";
    description = "Select options from dropdown menus";
    schema = AiSelectSchema;
  
    async _call(input: z.infer<typeof AiSelectSchema>): Promise<string> {
        return JSON.stringify({
            type: "ai_select",
            elementId: input.elementId,
            prompt: input.prompt,
            value: input.value,
            reasoning: input.reasoning,
            warning: input.warning
        });
    }
}

export class AiScriptTool extends StructuredTool<typeof AiScriptSchema> {
    name = "ai_script";
    description = "Generate a Node.js script to accomplish a task using cleaned HTML content";
    schema = AiScriptSchema;
  
    async _call(input: z.infer<typeof AiScriptSchema>): Promise<string> {
        return JSON.stringify({
            type: "ai_script",
            prompt: input.prompt,
            reasoning: input.reasoning,
            warning: input.warning
        });
    }
}

// export class AiVerifyTool extends StructuredTool<typeof AiVerifySchema> {
//     name = "ai_verify";
//     description = "Verify specific conditions or content on the page and also return playwright code to verify the condition";
//     schema = AiVerifySchema;
  
//     async _call(input: z.infer<typeof AiVerifySchema>): Promise<string> {
//         return JSON.stringify({
//             type: "ai_verify",
//             elementId: input.elementId,
//             prompt: input.prompt,
//             value: input.value,
//             code: input.code,
//             validation: input.validation,
//             reasoning: input.reasoning,
//             warning: input.warning
//         });
//     }
// }

// export class AiHoverTool extends StructuredTool<typeof AiHoverSchema> {
//     name = "ai_hover";
//     description = "Hover over elements to trigger tooltips or menus";
//     schema = AiHoverSchema;
  
//     async _call(input: z.infer<typeof AiHoverSchema>): Promise<string> {
//         return JSON.stringify({
//             type: "ai_hover",
//             elementId: input.elementId,
//             prompt: input.prompt,
//             reasoning: input.reasoning,
//             warning: input.warning
//         });
//     }
// }

export class GoToUrlTool extends StructuredTool<typeof GoToUrlSchema> {
    name = "go_to_url";
    description = "Navigate to a specific URL";
    schema = GoToUrlSchema;
  
    async _call(input: z.infer<typeof GoToUrlSchema>): Promise<string> {
        return JSON.stringify({
            type: "go_to_url",
            url: input.url,
            reasoning: input.reasoning,
            warning: input.warning
        });
    }
}

// export class GoBackTool extends StructuredTool<typeof GoBackSchema> {
//     name = "go_back";
//     description = "Navigate back to the previous page";
//     schema = GoBackSchema;
  
//     async _call(input: z.infer<typeof GoBackSchema>): Promise<string> {
//         return JSON.stringify({
//             type: "go_back",
//             reasoning: input.reasoning,
//             warning: input.warning
//         });
//     }
// }

export class WaitTimeTool extends StructuredTool<typeof WaitTimeSchema> {
    name = "wait_time";
    description = "Wait for a specified amount of time";
    schema = WaitTimeSchema;
  
    async _call(input: z.infer<typeof WaitTimeSchema>): Promise<string> {
        return JSON.stringify({
            type: "wait_time",
            delay_seconds: input.delay_seconds,
            reasoning: input.reasoning,
            warning: input.warning
        });
    }
}

export class ScrollTool extends StructuredTool<typeof ScrollSchema> {
    name = "scroll";
    description = "Scroll the page in a specific direction by a specified number of pixels";
    schema = ScrollSchema;
  
    async _call(input: z.infer<typeof ScrollSchema>): Promise<string> {
        return JSON.stringify({
            type: "scroll",
            direction: input.direction,
            value: input.value,
            reasoning: input.reasoning,
            warning: input.warning
        });
    }
}

export class GoBackTool extends StructuredTool<typeof GoBackSchema> {
    name = "go_back";
    description = "Navigate back to the previous page in browser history";
    schema = GoBackSchema;
  
    async _call(input: z.infer<typeof GoBackSchema>): Promise<string> {
        return JSON.stringify({
            type: "go_back",
            reasoning: input.reasoning,
            warning: input.warning
        });
    }
}

// export class OpenTabTool extends StructuredTool<typeof OpenTabSchema> {
//     name = "open_tab";
//     description = "Open a new browser tab";
//     schema = OpenTabSchema;
  
//     async _call(input: z.infer<typeof OpenTabSchema>): Promise<string> {
//         return JSON.stringify({
//             type: "open_tab",
//             url: input.url,
//             reasoning: input.reasoning,
//             warning: input.warning
//         });
//     }
// }

// export class RunScriptTool extends StructuredTool<typeof RunScriptSchema> {
//     name = "run_script";
//     description = "Execute custom JavaScript code";
//     schema = RunScriptSchema;
  
//     async _call(input: z.infer<typeof RunScriptSchema>): Promise<string> {
//         return JSON.stringify({
//             type: "run_script",
//             description: input.description,
//             script: input.script,
//             reasoning: input.reasoning,
//             warning: input.warning
//         });
//     }
// }

export class DoneTool extends StructuredTool<typeof DoneSchema> {
    name = "done";
    description = "Mark the goal as completed with success or failure status";
    schema = DoneSchema;
  
    async _call(input: z.infer<typeof DoneSchema>): Promise<string> {
        return JSON.stringify({
            type: "done",
            output: input.output,
            reasoning: input.reasoning,
            goalDescription: input.goalDescription
        });
    }
}

export class VerificationExtractorTool extends StructuredTool<typeof VerificationExtractorSchema> {
    name = "verify_email";
    description = "Fetch verification code or link from the email for the given web application name";
    schema = VerificationExtractorSchema;

    async _call(input: z.infer<typeof VerificationExtractorSchema>): Promise<string> {
        return JSON.stringify({
            type: "verify_email",
            prompt: input.prompt,
            reasoning: input.reasoning,
            warning: input.warning,
            toEmail: input.toEmail
        });
    }
}

// Triage analysis tool implementation
export class TriageAnalysisTool extends StructuredTool<typeof TriageAnalysisSchema> {
    name = "triage_analysis";
    description = "Analyze a failed Playwright test execution and provide a single categorization with reasoning.";
    schema = TriageAnalysisSchema;

    async _call(input: z.infer<typeof TriageAnalysisSchema>): Promise<string> {
        const triageOutput = new TriageAgentOutput({
            description: input.description,
            category: input.category,
            sub_category: input.sub_category,
            reasoning: input.reasoning
        });
        
        return JSON.stringify(triageOutput);
    }
}