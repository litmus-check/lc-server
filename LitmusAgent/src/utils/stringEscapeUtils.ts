/**
 * Utility functions for escaping strings for use in JavaScript code generation
 */

/**
 * Escapes a regex string for insertion into a JavaScript string literal (single quotes)
 * 
 * JavaScript string parser recognizes these escape sequences:
 * - \\ (backslash), \' (single quote), \" (double quote)
 * - \n (newline), \r (carriage return), \t (tab)
 * - \b (backspace), \f (form feed), \v (vertical tab)
 * - \0 (null), \xHH (hex), \uHHHH (unicode)
 * 
 * For regex strings, we need to escape:
 * 1. Backslashes: \ becomes \\ (double-escape so JS consumes one, RegExp gets the other)
 * 2. Single quotes: ' becomes \' (since we use single quotes for string literal)
 * 3. Newlines/tabs: Escape to prevent breaking the string literal
 * 
 * @param regexString The regex string to escape
 * @returns The escaped string safe for use in JavaScript string literal with single quotes
 */
export function escapeRegexStringForJSLiteral(regexString: string): string {
    return regexString
        .replace(/\\/g, '\\\\')  // Escape backslashes first (before other escapes)
        .replace(/'/g, "\\'")    // Escape single quotes
        .replace(/\n/g, '\\n')   // Escape newlines
        .replace(/\r/g, '\\r')   // Escape carriage returns
        .replace(/\t/g, '\\t');  // Escape tabs
}

