#!/usr/bin/env node

/**
 * URL Pattern Clone Demo - Simplified Glob Features
 * 
 * This script demonstrates simplified URLPattern features:
 * - `*` can appear anywhere
 * - Matches any sequence of characters
 * - Regex is anchored (`^...$`)
 * 
 * Run with: npx ts-node src/utils/demo.ts
 */

import { URLPatternClone } from '../URLPatternClone';

console.log('🚀 Simplified URL Pattern Clone Demo\n');

// Test cases for simplified glob support
const testCases = [
  {
    name: 'Suffix Wildcard',
    pattern: new URLPatternClone('github.co*'),
    tests: [
      ['https://github.com', true],
      ['https://github.co123', true],
      ['https://gitlab.com', false],
    ],
  },
  {
    name: 'Prefix Wildcard',
    pattern: new URLPatternClone('*.example.com'),
    tests: [
      ['abc.example.com', true],
      ['http://abc.example.com', true],
      ['example.com', false],
    ],
  },
  {
    name: 'Anywhere Wildcard',
    pattern: new URLPatternClone('exampl.blog.*.com'),
    tests: [
      ['exampl.blog.123.com', true],
      ['exampl.blog.hello.com', true],
      ['exampl.blog.com', false],
    ],
  },
  {
    name: 'Loose Wildcard',
    pattern: new URLPatternClone('*example.com'),
    tests: [
      ['example.com', true],
      ['abc.example.com', true],
      ['http://example.com', true],
      ['http://abc.example.com', true],
      ['wrong.com', false],
    ],
  },
  {
    name: 'Wildcard Protocol',
    pattern: new URLPatternClone('*://github.com'),
    tests: [
      ['http://github.com', true],
      ['https://github.com', true],
      ['ftp://github.com', true],
      ['ssh://github.com', true],
    ],
  },
  {
    name: 'HTTP only',
    pattern: new URLPatternClone('http://*'),
    tests: [
      ['http://abc.com', true],
      ['http://xyz.org/path', true],
      ['https://abc.com', false],
    ],
  },
  {
    name: 'HTTP with path suffix',
    pattern: new URLPatternClone('http://github.com*'),
    tests: [
      ['http://github.com', true],
      ['http://github.com/abc', true],
      ['http://github.com123', true],
      ['https://github.com/abc', false],
    ],
  },
  {
    name:'',
    pattern: new URLPatternClone('https://parabank.parasoft.com/parabank/*'),
    tests: [
      ['https://parabank.parasoft.com/parabank/admin.htm', true],
      ['https://parabank.parasoft.com/parabank/admin.htm/abc', true],
      ['https://parabank.parasoft.com/parabank/admin.htm123', true],
      ['https://parabank.parasoft.com/parabank/admin.htm/abc', true],
    ],
  },
];

let totalPassed = 0;
let totalFailed = 0;

console.log('📋 Running Simplified URL Pattern Tests\n');
console.log('=====================================\n');

for (const testCase of testCases) {
  console.log(`🔍 ${testCase.name}`);
  console.log(`Pattern: ${testCase.pattern.pattern}`);
  console.log(`Regex: ${testCase.pattern.getRegexString}\n`);

  let passed = 0;
  let failed = 0;

  for (const [url, expected] of testCase.tests) {
    const result = testCase.pattern.test(url as string);
    if (result === expected) {
      console.log(`  ✅ PASS: ${url} (expected ${expected}, got ${result})`);
      passed++;
      totalPassed++;
    } else {
      console.log(`  ❌ FAIL: ${url} (got ${result}, expected ${expected})`);
      failed++;
      totalFailed++;
    }
  }

  console.log(`  Results: ${passed} passed, ${failed} failed\n`);
}

console.log('=====================================');
console.log(`📊 Summary: ${totalPassed} passed, ${totalFailed} failed\n`);
console.log('🎉 Simplified Demo completed successfully!');
