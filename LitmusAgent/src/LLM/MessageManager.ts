import { BaseMessage, SystemMessage, HumanMessage } from '@langchain/core/messages';
import { readPrompt } from '../utils/promptUtils';
import { logger } from '../utils/logger';

// Define the allowed message content type
type MessageContent =
  | string
  | Array<
      | { type: "text"; text: string }
      | { type: "image_url"; image_url: { url: string } }
    >;

export class MessageManager {
    private messages: BaseMessage[] = [];

    public createInitMessage(actionType: String): void {
        // Read the appropriate prompt based on action type
        logger.info(`Constructing prompt for action type: ${actionType}`);
        const promptPath = `prompts/${actionType.toLowerCase()}_prompt.md`;
        
        const prompt = readPrompt(promptPath);
        this.addSystemMessage(prompt);
    }

    public addUserMessage(message: MessageContent, addFromFront: boolean = false): void {
        if (addFromFront) {
            this.messages.unshift(new HumanMessage({content: message}));
        } else {
            this.messages.push(new HumanMessage({content: message}));
        }
    }

    public addSystemMessage(message: string): void {
        this.messages.push(new SystemMessage(message));
    }

    public getMessages(): BaseMessage[] {
        return this.messages;
    }
} 