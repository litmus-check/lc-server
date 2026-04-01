import { BrowserState, InteractableElement } from './browser';
import { Action, ActionResult, SelectorResult } from './actions';
import { DEVICE_TYPES, OPERATING_SYSTEMS, BROWSER_TYPES } from '../config/constants';

export type AgentMode = 'compose' | 'script' | 'triage' | 'heal';

export interface AgentConfig {
    mode: AgentMode;
    runId: string;
    useVision?: boolean;
    maxSteps?: number;
    maxFailures?: number;
    retryDelay?: number;
    useBrowserbase: boolean;
    playwrightCode: { [key: string]: string[] };
    instructions:  { [key: string]: any }[];
    browserbaseSessionId?: string;
    cdpUrl?: string;
    wssUrl?: string;
    variablesDict?: { 
        data_driven_variables?: { [key: string]: string },
        environment_variables?: { [key: string]: string }
    };
    playwright_config?: {
        browser: typeof BROWSER_TYPES[keyof typeof BROWSER_TYPES];
        device_pixel_ratio: number;
        device: {
            type: typeof DEVICE_TYPES[keyof typeof DEVICE_TYPES];
            device_config: {
                os: typeof OPERATING_SYSTEMS[keyof typeof OPERATING_SYSTEMS];
            };
        };
        viewport: {
            width: number;
            height: number;
        };
    };
}

export interface Instruction {
    id: string;
    type: string;
    action?: string;
    script?: string;
    ai_use?: string;
    promptType?: string;
    prompt?: string;
    args?: Array<{
        key: string;
        value: string | number;
    }>;
    playwright_actions?: string[];
    selectors?: SelectorResult;
}

export interface BrowserData {
    screenshot: string;
    urls?: string[];
}

export interface LLMData {
    actions: Action[];
    reasoning?: string;
    memory?: string;
}

export interface ExecutionData {
    instructionId: string;
    browserData: BrowserData;
    llmData?: LLMData;
    actionsData?: ActionResult[];
    messages?: string[];
}

export interface AgentState {
    url: string;
    title: string;
    interactableElements: InteractableElement[];
    timestamp: number;
} 