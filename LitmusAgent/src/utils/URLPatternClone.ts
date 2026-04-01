export class URLPatternClone {
  private patternString: string;
  private compiledRegex: RegExp;
  private regexString: string;

  constructor(init: string) {
    this.patternString = init as string;
    this.regexString = '';
    this.compiledRegex = this.compilePattern(this.patternString);
  }

  private compilePattern(pattern: string): RegExp {
    // Use a placeholder that won't appear in URLs (using control characters)
    const WILDCARD_PLACEHOLDER = '\u0001__WILDCARD__\u0001';
    
    // 1. Save wildcards first with placeholder
    let regexStr = pattern.replace(/\*/g, WILDCARD_PLACEHOLDER);

    // 2. Escape regex special characters (including [ ] in query params, and ? for query strings)
    regexStr = regexStr.replace(/[.+^${}()|[\]\\?]/g, '\\$&');

    // 3. Restore wildcards as regex '.*' (placeholder won't be escaped since it uses control chars)
    regexStr = regexStr.replace(/\u0001__WILDCARD__\u0001/g, '.*');

    // 4. Add optional protocol if not provided
    if (!/^[a-z]+:\/\//i.test(pattern)) {
        regexStr = '^(https?:\\/\\/)?' + regexStr + '$';
    } else {
        regexStr = '^' + regexStr + '$';
    }
    this.regexString = regexStr;

    return new RegExp(regexStr);
}
  

  test(url: string): boolean {
    return this.compiledRegex.test(url);
  }

  get pattern(): string {
    return this.patternString;
  }

  get getRegexString(): string {
    return this.regexString;
  }
}

// Helper function
export function getURLPattern(init: string): URLPatternClone {
  return new URLPatternClone(init);
}

// --------------------
// Single-file Test Suite
// --------------------
// const testCases: [string, string, boolean][] = [
//   ['https://example.com/users/:id', 'https://example.com/users/123', true],
//   ['https://example.com/users/:id', 'https://example.com/users/abc', true],
//   ['https://*.example.com/*', 'https://shop.example.com/checkout', true],
//   ['https://*.example.com/*', 'https://blog.example.com/post/1', true],
//   ['https://*.example.com/*', 'https://example.com/', true],
//   ['https://*.example.com/*', 'https://another.com/', false],
//   ['https://example.com/product/:id(\\d+)', 'https://example.com/product/42', true],
//   ['https://example.com/product/:id(\\d+)', 'https://example.com/product/abc', false],
//   ['https?://example.com/*', 'http://example.com/home', true],
//   ['https?://example.com/*', 'https://example.com/home', true],
//   ['https?://example.com/*', 'ftp://example.com/home', false],
//   ['https://example.com/search?query=:q', 'https://example.com/search?query=playwright', true],
//   ['https://example.com/search?query=:q', 'https://example.com/search?query=123', true],
//   ['https://example.com/docs#:section', 'https://example.com/docs#intro', true],
//   ['https://example.com/docs#:section', 'https://example.com/docs#overview', true],
//   ['https://example.com/docs#:section', 'https://example.com/docs', true],
//   ['https://*.example.com/:slug([a-z-]+)/*', 'https://shop.example.com/product-item/extra', true],
//   ['https://*.example.com/:slug([a-z-]+)/*', 'https://shop.example.com/1234/extra', false],
// ];

// let passed = 0, failed = 0;

// for (const [patternStr, url, expected] of testCases) {
//   const pattern = new URLPatternClone(patternStr);
//   const result = pattern.test(url);
//   const status = result === expected ? '✅ PASS' : '❌ FAIL';
//   console.log(`${status}: Pattern=${patternStr}, URL=${url}, got=${result}, expected=${expected}`);
//   if (result === expected) passed++; else failed++;
// }

// console.log(`\nResults: ${passed} passed, ${failed} failed`);
