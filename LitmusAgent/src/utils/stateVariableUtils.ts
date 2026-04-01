import { STATE_TEMPLATE_REGEX } from '../config/constants';
import { logger } from './logger';

/**
 * Escape a string value for use in JavaScript string literals (single-quoted strings).
 * Escapes quotes, backslashes, control characters, and Unicode line/paragraph separators.
 */
export function escapeJsStringValue(value: string): string {
    if (value == null) return '';
    
    const valueStr = String(value);
    return valueStr
        .replace(/\\/g, '\\\\')            // backslashes
        .replace(/'/g, "\\'")              // single quotes
        .replace(/\n/g, '\\n')             // newlines
        .replace(/\r/g, '\\r')             // carriage returns
        .replace(/\t/g, '\\t')             // tabs
        .replace(/[\b]/g, '\\b')           // backspace (use [\b] to match actual backspace, not word boundary)
        .replace(/\f/g, '\\f')             // form feed
        .replace(/\u2028/g, '\\u2028')     // line separator
        .replace(/\u2029/g, '\\u2029');    // paragraph separator
}

/**
 * Robust state-template detector: strips wrapping quotes/backticks before testing
 */
export function StateTemplateDetector(value: string | undefined | null): boolean {
    if (!value) return false;
    const trimmed = String(value).trim();
    const unwrapped = (trimmed.startsWith('`') && trimmed.endsWith('`'))
        || (trimmed.startsWith("'") && trimmed.endsWith("'"))
        || (trimmed.startsWith('"') && trimmed.endsWith('"'))
        ? trimmed.slice(1, -1)
        : trimmed;
    return STATE_TEMPLATE_REGEX.test(unwrapped);
}

/**
 * Helper to format value for code storage based on state template presence
 * @param value The value to format
 * @returns Formatted value with proper quotes or backticks
 */
export function formatCodeValue(value: any): string {
    return StateTemplateDetector(String(value)) ? `\`${value}\`` : `'${value}'`;
}

/**
 * Helper to resolve state variable if present
 * @param value The value that might contain state variables
 * @param sharedState The shared state object
 * @returns The resolved value
 */
export function resolveStateValue(value: any, sharedState: Record<string, any>): any {
    if (StateTemplateDetector(String(value))) {
        const fn = new Function('state', `return \`${value}\`;`);
        const resolved = fn(sharedState);
        logger.info(`Resolved value with state variables: ${resolved}`);
        return resolved;
    }
    return value;
}
