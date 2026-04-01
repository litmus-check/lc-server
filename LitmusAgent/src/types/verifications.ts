import { z } from "zod";
import {
    VERIFICATION_TARGETS,
    VERIFICATION_PAGE_PROPERTIES,
    VERIFICATION_ELEMENT_PROPERTIES,
    VERIFICATION_CHECKS
} from "../config/constants";
import { formatCodeValue, StateTemplateDetector } from "../utils/stateVariableUtils";

// Instruction structure based on verification_examples.md
export interface VerificationInstruction {
    action: "verify";
    args: Array<{
        key: string;
        value: string | number | boolean | null;
    }>;
    id: string;
    playwright_actions: string[];
    type: "AI" | "Non-AI";
}

// Helper function to get arg value by key
export function getArgValue(instruction: VerificationInstruction, key: string): any {
    const arg = instruction.args.find(arg => arg.key === key);
    return arg ? arg.value : null;
}

// Verification function return type
export interface VerificationResult {
    code: string;           // Playwright code to execute
    success: boolean;       // Whether verification passed
    message: string;        // Success/failure message
}

// Verification functions that return Playwright code based on instruction structure
export class VerificationFunctions {
    /**
     * Escape special regex characters in a string
     */
    private static escapeRegex(value: string): string {
        return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }

    /**
     * Escape a value for safe embedding in a single-quoted string within a template literal
     * Escapes single quotes and ensures backslashes are properly escaped
     */
    private static escapeForSingleQuotedString(value: any): string {
        return this.escapeRegex(String(value))
            .replace(/\\/g, '\\\\')  // Escape backslashes for string context
            .replace(/'/g, "\\'");   // Escape single quotes
    }
    /**
     * Generate Playwright code for verifications
     */
    static generateVerificationCode(instruction: VerificationInstruction, selectorObj?: any, actionHandler?: any, elementSelector?: string): string {
        const target = getArgValue(instruction, 'target');
        const property = getArgValue(instruction, 'property');
        const check = getArgValue(instruction, 'check');
        const value = getArgValue(instruction, 'value');
        const subProperty = getArgValue(instruction, 'sub_property');
        const locator = getArgValue(instruction, 'locator');     // User provided locator
        const expectedResult = getArgValue(instruction, 'expected_result');

        let verificationCode: string;
        
        if (target === VERIFICATION_TARGETS.PAGE) {
            verificationCode = this.generatePageVerificationCode(property, check, value);
        } else if (target === VERIFICATION_TARGETS.ELEMENT) {
            verificationCode = this.generateElementVerificationCode(property, check, value, subProperty, locator, selectorObj, actionHandler, elementSelector);
        } else {
            throw new Error(`Unsupported target: ${target}`);
        }

        // If expected_result is false, negate the verification
        if (expectedResult === false) {
            verificationCode = this.negateVerification(verificationCode);
        }

        return verificationCode;
    }

    /**
     * Generate Playwright code for page verifications
     */
    private static generatePageVerificationCode(property: any, check: any, value: any): string {
        if (property === VERIFICATION_PAGE_PROPERTIES.VERIFY_TITLE) {
            if (check === VERIFICATION_CHECKS.CONTAINS) {
                // For CONTAINS, use regex pattern matching
                if (StateTemplateDetector(String(value))) {
                    // State variable: use new RegExp with template literal
                    return `await expect(page).toHaveTitle(new RegExp(\`${value}\`));`;
                } else {
                    // Static value: use escaped regex
                    return `await expect(page).toHaveTitle(new RegExp('${this.escapeForSingleQuotedString(value)}'));`;
                }
            } else if (check === VERIFICATION_CHECKS.IS) {
                const formattedValue = formatCodeValue(value);
                return `await expect(page).toHaveTitle(${formattedValue});`;
            }
        } else if (property === VERIFICATION_PAGE_PROPERTIES.VERIFY_URL) {
            if (check === VERIFICATION_CHECKS.CONTAINS) {
                // For CONTAINS, use regex pattern matching
                if (StateTemplateDetector(String(value))) {
                    // State variable: use new RegExp with template literal
                    return `await expect(page).toHaveURL(new RegExp(\`${value}\`));`;
                } else {
                    // Static value: use escaped regex
                    return `await expect(page).toHaveURL(new RegExp('${this.escapeForSingleQuotedString(value)}'));`;
                }
            } else if (check === VERIFICATION_CHECKS.IS) {
                const formattedValue = formatCodeValue(value);
                return `await expect(page).toHaveURL(${formattedValue});`;
            }
        }
        
        throw new Error(`Unsupported page property/check combination: ${property}/${check}`);
    }

    /**
     * Generate Playwright code for element verifications
     */
    private static generateElementVerificationCode(property: any, check: any, value: any, subProperty: any, locator: any, selectorObj?: any, actionHandler?: any, elementSelector?: string): string {
        const selector = locator;

        // Extract the element selector once if we have actionHandler and selectorObj
        if (!elementSelector) {
            if (actionHandler && selectorObj) {
                // Use generateScriptForSelector to get the selector part only
                const fullScript = actionHandler.generateScriptForSelector(selectorObj, 'toBeVisible');
                // Extract just the selector part (remove await and .toBeVisible())
                elementSelector = fullScript.replace(/^await\s+/, '').replace(/\.toBeVisible\(\);$/, '');
            } else {
                // Fallback to page.locator if no selector object provided
                elementSelector = `page.locator('${selector}')`;
            }
        }

        // Property-based verifications
        switch (property) {
            case VERIFICATION_ELEMENT_PROPERTIES.VERIFY_TEXT:
                return this.generateTextVerificationCode(check, value, elementSelector);
            case VERIFICATION_ELEMENT_PROPERTIES.VERIFY_CLASS:
                return this.generateClassVerificationCode(check, value, elementSelector);
            case VERIFICATION_ELEMENT_PROPERTIES.VERIFY_ATTRIBUTE:
                return this.generateAttributeVerificationCode(check, value, subProperty, elementSelector);
            case VERIFICATION_ELEMENT_PROPERTIES.VERIFY_COUNT:
                return this.generateCountVerificationCode(check, value, elementSelector);
            case VERIFICATION_ELEMENT_PROPERTIES.VERIFY_VALUE:
                return this.generateValueVerificationCode(check, value, elementSelector);
            case VERIFICATION_ELEMENT_PROPERTIES.VERIFY_CSS:
                return this.generateCSSVerificationCode(check, value, subProperty, elementSelector);
            case VERIFICATION_ELEMENT_PROPERTIES.VERIFY_IF_VISIBLE:
                return `await expect(${elementSelector}).toBeVisible();`;
            case VERIFICATION_ELEMENT_PROPERTIES.VERIFY_IF_CHECKED:
                return `await expect(${elementSelector}).toBeChecked();`;
            case VERIFICATION_ELEMENT_PROPERTIES.VERIFY_IF_EMPTY:
                return `await expect(${elementSelector}).toBeEmpty();`;
            case VERIFICATION_ELEMENT_PROPERTIES.VERIFY_IF_IN_VIEWPORT:
                return `await expect(${elementSelector}).toBeInViewport();`;
            default:
                throw new Error(`Unsupported element property: ${property}`);
        }
    }

    /**
     * Generate Playwright code for text verifications
     */
    private static generateTextVerificationCode(check: any, value: any, elementSelector: string | undefined): string {
        if (check === VERIFICATION_CHECKS.CONTAINS) {
            // For CONTAINS, use regex pattern matching
            if (StateTemplateDetector(String(value))) {
                // State variable: use new RegExp with template literal
                return `await expect(${elementSelector}).toHaveText(new RegExp(\`${value}\`));`;
            } else {
                // Static value: use escaped regex
                return `await expect(${elementSelector}).toHaveText(new RegExp('${this.escapeForSingleQuotedString(value)}'));`;
            }
        } else if (check === VERIFICATION_CHECKS.IS) {
            const formattedValue = formatCodeValue(value);
            return `await expect(${elementSelector}).toHaveText(${formattedValue});`;
        }
        throw new Error(`Unsupported text check: ${check}`);
    }

    /**
     * Generate Playwright code for class verifications
     */
    private static generateClassVerificationCode(check: any, value: any, elementSelector: string | undefined): string {
        if (check === VERIFICATION_CHECKS.CONTAINS) {
            // For CONTAINS, use regex pattern matching
            if (StateTemplateDetector(String(value))) {
                // State variable: use new RegExp with template literal
                return `await expect(${elementSelector}).toHaveClass(new RegExp(\`${value}\`));`;
            } else {
                // Static value: use escaped regex
                return `await expect(${elementSelector}).toHaveClass(new RegExp('${this.escapeForSingleQuotedString(value)}'));`;
            }
        } else if (check === VERIFICATION_CHECKS.IS) {
            const formattedValue = formatCodeValue(value);
            return `await expect(${elementSelector}).toHaveClass(${formattedValue});`;
        }
        throw new Error(`Unsupported class check: ${check}`);
    }

    /**
     * Generate Playwright code for attribute verifications
     */
    private static generateAttributeVerificationCode(check: any, value: any, subProperty: any, elementSelector: string | undefined): string {
        if (!subProperty) {
            throw new Error('Sub-property is required for attribute verifications');
        }
        
        if (check === VERIFICATION_CHECKS.CONTAINS) {
            // For CONTAINS, use regex pattern matching
            if (StateTemplateDetector(String(value))) {
                // State variable: use new RegExp with template literal
                return `await expect(${elementSelector}).toHaveAttribute('${subProperty}', new RegExp(\`${value}\`));`;
            } else {
                // Static value: use escaped regex
                return `await expect(${elementSelector}).toHaveAttribute('${subProperty}', new RegExp('${this.escapeForSingleQuotedString(value)}'));`;
            }
        } else if (check === VERIFICATION_CHECKS.IS) {
            const formattedValue = formatCodeValue(value);
            return `await expect(${elementSelector}).toHaveAttribute('${subProperty}', ${formattedValue});`;
        }
        throw new Error(`Unsupported attribute check: ${check}`);
    }

    /**
     * Generate Playwright code for count verifications
     */
    private static generateCountVerificationCode(check: any, value: any, elementSelector: string | undefined): string {
        switch (check) {
            case VERIFICATION_CHECKS.IS:
                return `await expect(${elementSelector}).toHaveCount(${value});`;
            case VERIFICATION_CHECKS.GREATER_THAN:
                return `const count = await ${elementSelector}.count(); await expect(count).toBeGreaterThan(${value});`;
            case VERIFICATION_CHECKS.LESS_THAN:
                return `const count = await ${elementSelector}.count(); await expect(count).toBeLessThan(${value});`;
            case VERIFICATION_CHECKS.GREATER_THAN_OR_EQUAL:
                return `const count = await ${elementSelector}.count(); await expect(count).toBeGreaterThanOrEqual(${value});`;
            case VERIFICATION_CHECKS.LESS_THAN_OR_EQUAL:
                return `const count = await ${elementSelector}.count(); await expect(count).toBeLessThanOrEqual(${value});`;
            default:
                throw new Error(`Unsupported count check: ${check}`);
        }
    }

    /**
     * Generate Playwright code for value verifications
     */
    private static generateValueVerificationCode(check: any, value: any, elementSelector: string | undefined): string {
        if (check === VERIFICATION_CHECKS.CONTAINS) {
            // For CONTAINS, use regex pattern matching
            if (StateTemplateDetector(String(value))) {
                // State variable: use new RegExp with template literal
                return `await expect(${elementSelector}).toHaveValue(new RegExp(\`${value}\`));`;
            } else {
                // Static value: use escaped regex
                return `await expect(${elementSelector}).toHaveValue(new RegExp('${this.escapeForSingleQuotedString(value)}'));`;
            }
        } else if (check === VERIFICATION_CHECKS.IS) {
            const formattedValue = formatCodeValue(value);
            return `await expect(${elementSelector}).toHaveValue(${formattedValue});`;
        }
        throw new Error(`Unsupported value check: ${check}`);
    }

    /**
     * Generate Playwright code for CSS verifications
     */
    private static generateCSSVerificationCode(check: any, value: any, subProperty: any, elementSelector: string | undefined): string {
        if (!subProperty) {
            throw new Error('Sub-property is required for CSS verifications');
        }
        
        if (check === VERIFICATION_CHECKS.CONTAINS) {
            // For CONTAINS, use regex pattern matching
            if (StateTemplateDetector(String(value))) {
                // State variable: use new RegExp with template literal
                return `await expect(${elementSelector}).toHaveCSS('${subProperty}', new RegExp(\`${value}\`));`;
            } else {
                // Static value: use escaped regex
                return `await expect(${elementSelector}).toHaveCSS('${subProperty}', new RegExp('${this.escapeForSingleQuotedString(value)}'));`;
            }
        } else if (check === VERIFICATION_CHECKS.IS) {
            const formattedValue = formatCodeValue(value);
            return `await expect(${elementSelector}).toHaveCSS('${subProperty}', ${formattedValue});`;
        }
        throw new Error(`Unsupported CSS check: ${check}`);
    }

    /**
     * Generate Playwright code from selector object
     */
    public static generateScriptFromSelector(elementResult: any, instructionForGen: any): string {
        const elementSelector = elementResult.script;
        const code = VerificationFunctions.generateVerificationCode(instructionForGen, undefined, undefined, elementSelector);
        return code;
    }

    /**
     * Negate a verification by converting positive assertions to negative ones
     */
    private static negateVerification(verificationCode: string): string {
        // Replace positive assertions with negative ones
        return verificationCode
            .replace(/\.toBeVisible\(\)/g, '.not.toBeVisible()')
            .replace(/\.toBeChecked\(\)/g, '.not.toBeChecked()')
            .replace(/\.toBeEmpty\(\)/g, '.not.toBeEmpty()')
            .replace(/\.toBeInViewport\(\)/g, '.not.toBeInViewport()')
            .replace(/\.toHaveText\(/g, '.not.toHaveText(')
            .replace(/\.toHaveClass\(/g, '.not.toHaveClass(')
            .replace(/\.toHaveAttribute\(/g, '.not.toHaveAttribute(')
            .replace(/\.toHaveValue\(/g, '.not.toHaveValue(')
            .replace(/\.toHaveCSS\(/g, '.not.toHaveCSS(')
            .replace(/\.toHaveCount\(/g, '.not.toHaveCount(')
            .replace(/\.toHaveTitle\(/g, '.not.toHaveTitle(')
            .replace(/\.toHaveURL\(/g, '.not.toHaveURL(')
            .replace(/\.toBeGreaterThan\(/g, '.not.toBeGreaterThan(')
            .replace(/\.toBeLessThan\(/g, '.not.toBeLessThan(')
            .replace(/\.toBeGreaterThanOrEqual\(/g, '.not.toBeGreaterThanOrEqual(')
            .replace(/\.toBeLessThanOrEqual\(/g, '.not.toBeLessThanOrEqual(');
    }


}
