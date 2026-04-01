import { logger } from './logger';
import { ContainerCommsService } from '../services/ContainerCommsService';

/**
 * Creates a litmus_log function for user scripts to log messages to Redis
 * @param containerCommsService - The ContainerCommsService instance for Redis communication
 * @param runId - The run ID to associate logs with
 * @param instructionId - Optional instruction ID to associate logs with a specific instruction
 * @param trackPromises - Optional array to track pending log promises (for awaiting completion)
 * @returns A function that can be used as litmus_log in user scripts
 */
export function litmusLogger(
    containerCommsService: ContainerCommsService | null,
    runId: string | undefined,
    instructionId?: string | undefined,
    trackPromises?: Promise<void>[]
): (value: any, logType?: string) => void {
    return (value: any, logType: string = 'INFO'): void => {
        if (!containerCommsService || !runId) {
            logger.error('litmus_log: containerCommsService or runId not available');
            return;
        }

        // Create the log promise - this will be tracked and awaited
        const logPromise = (async () => {
            try {
                // Convert value to string representation
                let logMessage: string;
                if (typeof value === 'object') {
                    logMessage = JSON.stringify(value, null, 2);
                } else {
                    logMessage = String(value);
                }

                // Format log message with type
                const formattedLogMessage = `[${logType.toUpperCase()}] ${logMessage}`;

                // Log to Redis based on log type, with instructionId so it appears under the instruction
                const logEntry: any = {
                    timestamp: new Date().toISOString(),
                    instructionId: instructionId
                };

                if (logType.toUpperCase() === 'ERROR') {
                    logEntry.error = formattedLogMessage;
                } else if (logType.toUpperCase() === 'WARNING' || logType.toUpperCase() === 'WARN') {
                    logEntry.warning = formattedLogMessage;
                } else {
                    logEntry.info = formattedLogMessage;
                }

                await containerCommsService.addLog(runId, logEntry);
            } catch (error) {
                logger.error(`[litmus_log] Failed to log message: ${error instanceof Error ? error.message : String(error)}`, error);
                // Re-throw to ensure the promise is marked as rejected
                throw error;
            }
        })();

        // Track the promise if tracking array is provided
        if (trackPromises) {
            trackPromises.push(logPromise);
        }
    };
}

