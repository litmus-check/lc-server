/// <reference types="node" />
import process from 'node:process';
import winston from 'winston';
import * as path from 'path';
import * as fs from 'fs';

const { format, createLogger, transports } = winston;
const { combine, timestamp, printf, colorize } = format;

// Check if running in Docker environment
const isDocker = process.env.DOCKER_ENV === 'true' || 
                 process.env.NODE_ENV === 'production' ||
                 process.env.IN_DOCKER === 'true' ||
                 process.env.FORCE_PLAIN_LOGS === 'true' ||
                 (process.platform === 'linux' && fs.existsSync('/.dockerenv'));

// Custom format to match Python's logging format
const customFormat = printf(({ level, message, timestamp, ...metadata }) => {
    const seen = new WeakSet();
    const metadataStr = Object.keys(metadata).length ? JSON.stringify(metadata, (key, value) => {
        if (typeof value === 'object' && value !== null) {
            if (seen.has(value)) {
                return '[Circular]';
            }
            seen.add(value);
        }
        return value;
    }) : '';
    return `[${timestamp}] [${level.toUpperCase()}] ${message} ${metadataStr}`;
});

// Ensure logs directory exists with absolute path
const logDir = path.resolve(process.cwd(), 'logs');
if (!fs.existsSync(logDir)) {
    fs.mkdirSync(logDir, { recursive: true });
}

// Get run_id from command line arguments (5th argument, index 5)
const runId = process.argv[5] || 'app';
const logFilePath = path.join(logDir, `${runId}.log`);

// Choose console format based on environment
const consoleFormat = isDocker 
    ? combine(
        timestamp({ format: 'YYYY-MM-DD HH:mm:ss' }),
        customFormat
      )
    : combine(
        colorize(),
        timestamp({ format: 'YYYY-MM-DD HH:mm:ss' }),
        customFormat
      );

export const logger = createLogger({
    level: 'silly',
    format: combine(
        timestamp({ format: 'YYYY-MM-DD HH:mm:ss' }),
        customFormat
    ),
    transports: [
        new transports.Console({
            format: consoleFormat
        }),
        new transports.File({
            filename: logFilePath,
            format: combine(
                timestamp({ format: 'YYYY-MM-DD HH:mm:ss' }),
                customFormat
            )
        })
    ]
}); 