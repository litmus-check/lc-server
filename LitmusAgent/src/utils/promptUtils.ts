import * as fs from 'fs';
import * as path from 'path';

export function readPrompt(promptPath: string): string {
    try {
        const fullPath = path.join(__dirname, '..', 'LLM', promptPath);
        return fs.readFileSync(fullPath, 'utf-8');
    } catch (error) {
        console.error(`Error reading prompt file: ${promptPath}`, error);
        throw new Error(`Failed to read prompt file: ${promptPath}`);
    }
} 