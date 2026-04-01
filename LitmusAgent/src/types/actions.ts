import { z } from "zod";
import { VerificationInstruction } from "./verifications";
import { API_INTERCEPT_ACTIONS } from '../config/constants';

export interface SelectorResult {
    selectors: Array<{
        selector: string;      // Full selector string like "div[data-testid='submit-button']"
        display: string;       // Clean display text for frontend
    }>;
}

export type ActionType = 
    // AI Actions
    | 'ai_click'
    | 'ai_verify'
    | 'ai_assert'
    | 'ai_input'
    | 'ai_select'
    | 'ai_hover'
    | 'ai_file_upload'
    | 'ai_goal'
    | 'ai_script'
    | 'verify'
    // Non-AI Actions
    | 'go_to_url'
    | 'go_back'
    | 'wait_time'
    | 'open_tab'
    | 'run_script'
    | 'scroll'
    | 'verify_email'
    | 'switch_tab'
    | 'page_reload'
    | 'key_press'
    // Special Actions
    | 'all'
    | 'set_state_variable'
    | 'api_intercept'
    | 'remove_api_handlers'
    | 'api_mock';

export const actionTypeValues: ActionType[] = [
    'ai_click',
    'ai_verify',
    'ai_assert',
    'ai_input',
    'ai_select',
    'ai_hover',
    'ai_file_upload',
    'ai_script',
    'scroll',
    'go_to_url',
    'go_back',
    'wait_time',
    'open_tab',
    'run_script',
    'verify_email',
    'switch_tab',
    'page_reload',
    'key_press',
    'verify',
    'all',
    'set_state_variable',
    'api_intercept',
    'remove_api_handlers',
    'api_mock'
];

export interface BaseAction {
    type: ActionType;
    elementId?: number | null;  // Required for action handlers but optional for frontend compatibility
    script?: string; // Required for ai_script action
}

export const AiScriptActionSchema = z.object({
    type: z.enum(actionTypeValues as [ActionType, ...ActionType[]]),
    script: z.string(),
});

// BaseAction schema for validation
export const BaseActionSchema = z.object({
    type: z.enum(actionTypeValues as [ActionType, ...ActionType[]]),
    elementId: z.number().nullable().optional(),
    script: z.string().optional(),
});

export interface ClickAction extends BaseAction {
    type: 'ai_click';
    prompt: string;
}

export interface VerifyAction extends BaseAction {
    type: 'ai_verify';
    prompt: string;
    value?: string;
    code?: string;
    validation?: boolean;
}

export interface AssertAction extends BaseAction {
    type: 'ai_assert';
    prompt: string;
    validation?: boolean;
    reasoning?: string;
}

export interface InputAction extends BaseAction {
    type: 'ai_input';
    prompt: string;
    value: string;
}

export interface SelectAction extends BaseAction {
    type: 'ai_select';
    prompt: string;
    value: string;
}

export interface SwitchTabAction extends BaseAction {
    type: 'switch_tab';
    url: string;
}

export interface HoverAction extends BaseAction {
    type: 'ai_hover';
    prompt: string;
}

export interface FileUploadAction extends BaseAction {
    type: 'ai_file_upload';
    prompt: string;
    file_url: string;
}

export interface AiScriptAction extends BaseAction {
    type: 'ai_script';
    prompt: string;
    script?: string;
}

export interface ScrollAction extends BaseAction {
    type: 'scroll';
    direction: 'up' | 'down' | 'left' | 'right';
    value?: number;
}

export interface GoToUrlAction extends BaseAction {
    type: 'go_to_url';
    url: string;
}

export interface GoBackAction extends BaseAction {
    type: 'go_back';
}

export interface PageReload extends BaseAction {
    type: 'page_reload';
}

export interface KeyPressAction extends BaseAction {
    type: 'key_press';
    key_type: 'up' | 'down' | 'press';
    value: string;
}

export interface WaitTimeAction extends BaseAction {
    type: 'wait_time';
    delay_seconds: number;
}

export interface OpenTabAction extends BaseAction {
    type: 'open_tab';
    url: string;
}

export interface RunScriptAction extends BaseAction {
    type: 'run_script';
    description: string;
    script: string;
}

export interface VerifyEmailAction extends BaseAction {
    type: 'verify_email';
    prompt: string;
    toEmail?: string;
}

export interface VerificationAction extends BaseAction {
    type: 'verify';
    // Keep the structured instruction for codegen/execution
    instruction?: VerificationInstruction;
    // Flattened verification properties (come directly from instruction args)
    target?: 'page' | 'element' | string;
    locator_type?: 'ai' | 'manual' | string;
    locator_prompt?: string | null;
    locator?: string | null;
    property?: 'verify_text' | 'verify_title' | 'verify_url' | 'verify_class' | 'verify_attribute' | 'verify_count' | 'verify_value' | 'verify_css' | 'verify_if_visible' | 'verify_if_checked' | 'verify_if_empty' | 'verify_if_in_viewport' | null | string;
    check?: 'contains' | 'is' | 'greater_than' | 'less_than' | 'greater_than_or_equal' | 'less_than_or_equal' | 'is_visible' | 'is_checked' | 'is_empty' | 'is_in_viewport' | string;
    sub_property?: string | null;
    value?: string | number | null;
    fail_test?: boolean | string;
    expected_result?: boolean | null;
}

export type Action = 
    | ClickAction 
    | VerifyAction 
    | AssertAction
    | InputAction 
    | SelectAction 
    | SwitchTabAction 
    | HoverAction 
    | FileUploadAction
    | AiScriptAction
    | ScrollAction
    | GoToUrlAction
    | GoBackAction
    | WaitTimeAction
    | OpenTabAction
    | RunScriptAction
    | VerifyEmailAction
    | VerificationAction
    | SetStateVariableAction
    | PageReload
    | KeyPressAction
    | ApiInterceptAction
    | RemoveApiHandlersAction
    | ApiMockAction;


export interface SetStateVariableAction extends BaseAction {
    type: 'set_state_variable';
    // Accept any key-value pairs as flattened properties
    [key: string]: any;
}

export interface ApiInterceptAction extends BaseAction {
    type: 'api_intercept';
    url: string; // regex URL pattern
    method: string; // HTTP method (GET, POST, etc.)
    action: typeof API_INTERCEPT_ACTIONS[keyof typeof API_INTERCEPT_ACTIONS];
    js_code?: string; // Optional JavaScript code for modifying request/response
    variable_name?: string; // Variable name for storing request/response in state
}

export interface RemoveApiHandlersAction extends BaseAction {
    type: 'remove_api_handlers';
    url: string; // regex URL pattern or exact URL string
}

export interface ApiMockAction extends BaseAction {
    type: 'api_mock';
    url: string; // full URL or glob pattern
    method: string; // HTTP method (GET, POST, etc.)
    status_code: string; // HTTP status code
    response_header: string; // stringified JSON object
    response_body: string; // stringified JSON or plain string
}

export interface ActionResult {
    action: Action;
    success: boolean;
    error?: string;
    warning?: string;
    timestamp: number;
    screenshot?: Buffer;
    playwrightCode?: string; // All Playwright code executed for this action, joined with newlines
    isDone?: boolean; // Whether this action marks the completion of a task
    selectors?: SelectorResult; // Add selectors for API output
    scripts?: string[]; // Add scripts for each selector
}
