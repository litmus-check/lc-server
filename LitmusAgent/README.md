# Litmus Browser Agent

A TypeScript implementation of a browser automation agent for Litmus, built on top of Playwright.

## Features

- Browser automation with Playwright
- Action handling for common browser interactions
- State management and memory tracking
- Screenshot capture before and after actions
- Trace recording for debugging
- Logging with Winston
- TypeScript support

## Installation

```bash
npm install
```

## Usage

```typescript
import { BrowserAgent } from './src/browser/BrowserAgent';

// Create a new browser agent instance
const agent = new BrowserAgent({
    config: {
        headless: true,
        viewport: { width: 1280, height: 720 },
        timeout: 30000,
        retryAttempts: 3,
        waitBetweenActions: 1000,
        screenshotBeforeAction: true,
        screenshotAfterAction: true
    },
    testRunId: 'test-123'
});

// Initialize the browser
await agent.initialize();

// Execute actions
const result = await agent.executeAction({
    type: 'click',
    target: 'button.submit'
});

// Clean up
await agent.cleanup();
```

## Action Types

The agent supports the following action types:

- `click`: Click on an element
- `input`: Input text into a field
- `select`: Select an option from a dropdown
- `verify`: Verify element content or state
- `switchTab`: Switch between browser tabs
- `hover`: Hover over an element
- `scroll`: Scroll the page in a specified direction (up, down, left, right) with a pixel value
- `wait`: Wait for a specified duration
- `done`: Mark an action sequence as complete

## State Management

The agent maintains state information including:

- Current URL and all open tabs
- Active tab index
- Interactable elements on the page
- Action execution history
- Error tracking

## Memory

The agent's memory system tracks:

- Instruction history
- Action execution results
- Playwright scripts
- Error logs

## Logging

Logs are written to both console and file with the following levels:

- DEBUG: Detailed debugging information
- INFO: General operational information
- WARN: Warning messages
- ERROR: Error messages

## Development

```bash
# Install dependencies
npm install

# Build
npm run build

# Run tests
npm test

# Development mode
npm run dev
```

## License

MIT 