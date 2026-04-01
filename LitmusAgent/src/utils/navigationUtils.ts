/**
 * Utility functions for detecting and handling navigation commands
 */

// Regex patterns for navigation command detection
export const PAGE_GOTO_PATTERN = /page\.goto\(/;
export const NEW_PAGE_GOTO_PATTERN = /newPage\.goto\(/;
export const NAVIGATION_URL_PATTERN = /(?:page|newPage)\.goto\(['"]([^'"]*)['"]\)/;

export interface NavigationCommandInfo {
    isNavigationCommand: boolean;
    isGotoCommand: boolean;
    isNewPageGotoCommand: boolean;
    url: string;
}

/**
 * Detects if a command is a navigation command and extracts relevant information
 * @param command The command string to analyze
 * @returns NavigationCommandInfo object with detection results
 */
export function detectNavigationCommand(command: string): NavigationCommandInfo {
    // Check if this is a page.goto() command
    const isGotoCommand = PAGE_GOTO_PATTERN.test(command);
    // Check if this is a newPage.goto() command (for open_tab actions)
    const isNewPageGotoCommand = NEW_PAGE_GOTO_PATTERN.test(command);
    
    const isNavigationCommand = isGotoCommand || isNewPageGotoCommand;
    
    // Extract URL using the centralized pattern
    const url = isNavigationCommand ? extractNavigationUrl(command) : '';
    
    return {
        isNavigationCommand,
        isGotoCommand,
        isNewPageGotoCommand,
        url
    };
}

/**
 * Extracts URL from a navigation command
 * @param command The command string to analyze
 * @returns The extracted URL or empty string if not found
 */
export function extractNavigationUrl(command: string): string {
    const urlMatch = command.match(NAVIGATION_URL_PATTERN);
    return urlMatch ? urlMatch[1] : '';
}

/**
 * Determines if performance monitoring should be enabled for a command
 * @param command The command string to analyze
 * @returns true if performance monitoring should be enabled
 */
export function shouldEnablePerformanceMonitoring(command: string): boolean {
    const navInfo = detectNavigationCommand(command);
    return navInfo.isNavigationCommand;
}
