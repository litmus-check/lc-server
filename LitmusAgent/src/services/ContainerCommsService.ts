import { createClient, RedisClientType } from 'redis';
import { logger } from '../utils/logger';
import { Action } from '../types/actions';


export class ContainerCommsService {
    private client: RedisClientType;
    private connected: boolean = false;
    private connecting: boolean = false;
    private readonly MAX_RETRIES = 3;
    private readonly RETRY_DELAY = 1000; // 1 second
    private connectionPromise: Promise<void> | null = null;
    private static readonly INSTRUCTION_STATUS_KEY_SUFFIX = ':instruction_status';

    constructor() {
        const redisUrl = process.env.REDIS_URL || 'redis://localhost:6379';
        
        logger.debug(`[ContainerCommsService] Initializing Redis client with URL: ${redisUrl}`);
        
        this.client = createClient({
            url: `${redisUrl}`,
            socket: {
                reconnectStrategy: (retries) => {
                    logger.debug(`[ContainerCommsService] Reconnection attempt ${retries}`);
                    if (retries > 10) {
                        logger.error('[ContainerCommsService] Redis max reconnection attempts reached');
                        return new Error('Redis max reconnection attempts reached');
                    }
                    return Math.min(retries * 100, 3000);
                }
            }
        });

        this.client.on('error', (err: Error) => {
            logger.error('ContainerCommsService Client Error:', err);
            this.connected = false;
            this.connecting = false;
            this.connectionPromise = null;
        });

        this.client.on('connect', () => {
            logger.debug('ContainerCommsService Client Connected');
            this.connected = true;
            this.connecting = false;
            this.connectionPromise = null;
        });

        this.client.on('end', () => {
            logger.debug('ContainerCommsService Client Connection Ended');
            this.connected = false;
            this.connecting = false;
            this.connectionPromise = null;
        });

        this.client.on('ready', () => {
            logger.debug('ContainerCommsService Client Ready');
        });

        this.client.on('reconnecting', () => {
            logger.debug('ContainerCommsService Client Reconnecting');
        });
    }

    private async retryOperation<T>(operation: () => Promise<T>): Promise<T> {
        let lastError: Error | null = null;
        
        for (let i = 0; i < this.MAX_RETRIES; i++) {
            try {
                // logger.debug(`[ContainerCommsService] Attempting operation (attempt ${i + 1}/${this.MAX_RETRIES})`);
                await this.ensureConnection();
                const result = await operation();
                // logger.debug(`[ContainerCommsService] Operation completed successfully on attempt ${i + 1}`);
                return result;
            } catch (error) {
                lastError = error as Error;
                logger.warn(`[ContainerCommsService] Redis operation failed (attempt ${i + 1}/${this.MAX_RETRIES}):`, error);
                
                if (i < this.MAX_RETRIES - 1) {
                    logger.debug(`[ContainerCommsService] Waiting ${this.RETRY_DELAY}ms before retry`);
                    await new Promise(resolve => setTimeout(resolve, this.RETRY_DELAY));
                    // Reset connection state on error
                    this.connected = false;
                    this.connecting = false;
                    this.connectionPromise = null;
                    logger.debug('[ContainerCommsService] Reset connection state after error');
                }
            }
        }
        
        logger.error(`[ContainerCommsService] Operation failed after ${this.MAX_RETRIES} attempts`);
        throw lastError || new Error('Redis operation failed after all retries');
    }

    async connect(): Promise<void> {
        // If already connected, return immediately
        if (this.connected) {
            logger.debug('[ContainerCommsService] Already connected, skipping connection');
            return;
        }

        // If a connection is in progress, wait for it
        if (this.connectionPromise) {
            logger.debug('[ContainerCommsService] Connection in progress, waiting for existing promise');
            return this.connectionPromise;
        }

        // Start new connection
        this.connectionPromise = (async () => {
            try {
                if (!this.connected && !this.connecting) {
                    logger.debug('[ContainerCommsService] Starting new Redis connection');
                    this.connecting = true;
                    await this.client.connect();
                    logger.debug('[ContainerCommsService] Redis connection established successfully');
                }
            } catch (error) {
                this.connecting = false;
                this.connectionPromise = null;
                logger.error('[ContainerCommsService] Failed to connect to Redis:', error);
                throw error;
            }
        })();

        return this.connectionPromise;
    }

    async disconnect(): Promise<void> {
        try {
            if (this.connected) {
                logger.debug('[ContainerCommsService] Disconnecting from Redis');
                await this.client.quit();
                this.connected = false;
                this.connecting = false;
                this.connectionPromise = null;
                logger.debug('[ContainerCommsService] Redis disconnected successfully');
            } else {
                logger.debug('[ContainerCommsService] Not connected, skipping disconnect');
            }
        } catch (error) {
            logger.error('[ContainerCommsService] Failed to disconnect from Redis:', error);
            throw error;
        }
    }

    async set(key: string, value: any): Promise<void> {
        return this.retryOperation(async () => {
            if (typeof value === 'string') {
                await this.client.set(key, value);
                return;
            }

            // instruction_status is stored in a dedicated Redis hash key.
            // Never persist it in the main session JSON.
            const incomingValue = (value && typeof value === 'object' && !Array.isArray(value))
                ? { ...value }
                : value;
            if (incomingValue && typeof incomingValue === 'object') {
                delete incomingValue.instruction_status;
            }

            // Always merge data for compose sessions
            const existingData = await this.get(key);
            // logger.debug(`[ContainerCommsService] Setting data for key: ${key}`);
            // logger.debug(`[ContainerCommsService] Existing data: ${JSON.stringify(existingData, null, 2)}`);
            // logger.debug(`[ContainerCommsService] New data: ${JSON.stringify(value, null, 2)}`);
            
            if (existingData) {
                const existingValue = { ...existingData };
                // Merge the new value with existing data
                value = {
                    ...existingValue,
                    ...incomingValue,
                    // If both have instructions, merge them
                    instructions: incomingValue.instructions || existingValue.instructions || {}
                };
                // logger.debug(`[ContainerCommsService] Merged data: ${JSON.stringify(value, null, 2)}`);
            } else {
                value = incomingValue;
            }
            
            const stringValue = typeof value === 'string' ? value : JSON.stringify(value);
            await this.client.set(key, stringValue);
            // logger.debug(`[ContainerCommsService] Successfully set Redis key: ${key}`);
        });
    }

    private getInstructionStatusKey(runId: string): string {
        return `${runId}${ContainerCommsService.INSTRUCTION_STATUS_KEY_SUFFIX}`;
    }

    async setInstructionStatus(runId: string, instructionId: string, status: string): Promise<void> {
        return this.retryOperation(async () => {
            const statusKey = this.getInstructionStatusKey(runId);
            await this.client.hSet(statusKey, instructionId, status);
            logger.debug(
                `[ContainerCommsService] Set instruction_status[${instructionId}]=${status} in hash (runId: ${runId})`,
            );
        });
    }

    async getInstructionStatuses(runId: string): Promise<Record<string, string>> {
        return this.retryOperation(async () => {
            const statusKey = this.getInstructionStatusKey(runId);
            return await this.client.hGetAll(statusKey);
        });
    }

    async get(key: string): Promise<any> {
        return this.retryOperation(async () => {
            const value = await this.client.get(key);
            // logger.debug(`[ContainerCommsService] Getting data for key: ${key}`);
            // logger.debug(`[ContainerCommsService] Raw Redis value: ${value}`);
            
            if (value) {
                try {
                    const parsedValue = JSON.parse(value);
                    const instructionStatuses = await this.client.hGetAll(this.getInstructionStatusKey(key));
                    if (Object.keys(instructionStatuses).length > 0) {
                        parsedValue.instruction_status = instructionStatuses;
                    } else {
                        delete parsedValue.instruction_status;
                    }
                    //logger.debug(`[ContainerCommsService] Parsed value: ${JSON.stringify(parsedValue, null, 2)}`);
                    return parsedValue;
                } catch {
                    logger.debug(`[ContainerCommsService] Value is not JSON, returning as is`);
                    return value;
                }
            }
            logger.error(`[ContainerCommsService] No value found for key: ${key}`);
            return null;
        });
    }

    async del(key: string): Promise<void> {
        return this.retryOperation(async () => {
            await this.client.del(key);
            await this.client.del(this.getInstructionStatusKey(key));
            logger.debug(`[ContainerCommsService] Deleted Redis key: ${key}`);
        });
    }

    async exists(key: string): Promise<boolean> {
        return this.retryOperation(async () => {
            const result = await this.client.exists(key);
            return result === 1;
        });
    }

    private async ensureConnection(): Promise<void> {
        if (!this.connected) {
            logger.debug('[ContainerCommsService] Connection not established, connecting...');
            await this.connect();
        } else {
            // logger.debug('[ContainerCommsService] Connection already established');
        }
    }

    /**
     * Creates a log instruction string from an instruction object
     * @param instruction The instruction object to convert to a log string
     * @returns A formatted log instruction string
     */
    private createLogInstructionString(instruction: any): string {
        let instructionStr = "Executing instruction: " + instruction.action;

        // If action type is AI then add prompt/target to instruction string
        if (instruction.type === 'ai' && instruction.target) {
            instructionStr += ` | ${instruction.target}`;
        }

        // If action type is Run Script then don't add script arg to instruction string
        if (instruction.action === 'run_script') {
            return instructionStr;
        }

        // Add value if present
        if (instruction.value !== undefined) {
            instructionStr += ` | ${instruction.value}`;
        }

        // Add all argument values to the instruction string
        if (instruction.args) {
            for (const arg of instruction.args) {
                instructionStr += ` | ${arg.value}`;
            }
        }

        return instructionStr;
    }

    /**
     * Creates a log entry for an action execution
     * @param action The action that was executed
     * @param result The result of the action execution
     * @returns A formatted log entry
     */
    private createActionLogEntry(action: Action, result: any): string {
        let logEntry = `Action: ${action.type}`;

        // Add elementId if present
        if (action.elementId) {
            logEntry += ` | Element: ${action.elementId}`;
        }

        // Add specific action properties
        if ('prompt' in action) {
            logEntry += ` | Prompt: ${action.prompt}`;
        }
        if ('value' in action) {
            logEntry += ` | Value: ${action.value}`;
        }
        if ('url' in action) {
            logEntry += ` | URL: ${action.url}`;
        }
        if ('file' in action) {
            logEntry += ` | File: ${action.file}`;
        }
        if ('direction' in action) {
            logEntry += ` | Direction: ${action.direction}`;
        }

        // Add result information
        if (result.success !== undefined) {
            logEntry += ` | Success: ${result.success}`;
        }
        if (result.message) {
            logEntry += ` | Message: ${result.message}`;
        }

        return logEntry;
    }

    /** Known queued log messages (Python backend may write any of these). */
    private static readonly QUEUED_LOG_MESSAGES = [
        'Test run queued',
        'Test run queued with triage mode',
        'Test run queued with healing mode'
    ];

    private static getQueuedLogMessageForMode(mode: string): string {
        if (mode === 'triage') return 'Test run queued with triage mode';
        if (mode === 'heal') return 'Test run queued with healing mode';
        return 'Test run queued';
    }

    /**
     * Ensures a "Test run queued" log exists in Redis for the given runId.
     * No-op for compose mode. Creates the session and adds the log if missing (e.g. when the agent starts before Python wrote it).
     * @param runId The run ID
     * @param mode The run mode ('script' | 'triage' | 'heal' | 'compose'). Compose is skipped; message is derived from mode.
     */
    async ensureTestRunQueuedLog(runId: string, mode: string): Promise<void> {
        if (mode === 'compose') return;

        const message = ContainerCommsService.getQueuedLogMessageForMode(mode);
        try {
            let session = await this.get(runId);
            if (!session) {
                session = { logs: { current_logs: [] }, counter: 0 };
            }
            if (!session.logs) {
                session.logs = { current_logs: [] };
            }
            if (!session.logs.current_logs) {
                session.logs.current_logs = [];
            }

            const currentLogs = session.logs.current_logs;
            const hasQueuedLog = currentLogs.some(
                (entry: { instruction: string; logs: Array<{ info?: string }> }) =>
                    entry.instruction === 'system' &&
                    entry.logs?.some((log: { info?: string }) =>
                        log.info && ContainerCommsService.QUEUED_LOG_MESSAGES.includes(log.info)
                    )
            );

            if (!hasQueuedLog) {
                const timestamp = new Date().toISOString();
                currentLogs.push({
                    instruction: 'system',
                    logs: [{ info: message, timestamp }]
                });
                await this.set(runId, session);
                logger.debug(`[ContainerCommsService] Added queued log for runId: ${runId}: ${message}`);
            }
        } catch (error) {
            logger.error('[ContainerCommsService] Failed to ensure Test run queued log in Redis:', error);
            throw error;
        }
    }

    /**
     * Add a log to Redis with the same format as the Python implementation
     * @param runId The run ID to add the log to
     * @param log The log object to add
     */
    async addLog(runId: string, log: { info?: string; error?: string; warning?: string; timestamp: string; instructionId?: string; instruction?: any; action?: Action; result?: any }): Promise<void> {
        try {
            const session = await this.get(runId);
            if (session) {
                // Initialize logs as an object if it doesn't exist
                if (!session.logs) {
                    session.logs = {
                        "current_logs": []
                    };
                }
            }
                
                // Create the log entry
                let logEntry: any = {
                    timestamp: log.timestamp
                };


            // If we have an instruction, create the instruction log string
            if (log.instruction) {
                logEntry.info = this.createLogInstructionString(log.instruction);
            }
            // If we have an action and result, create the action log entry
            else if (log.action && log.result) {
                logEntry.info = this.createActionLogEntry(log.action, log.result);
            }
            // Otherwise use the provided info or error
            else {
                if (log.info) logEntry.info = log.info;
                if (log.error) logEntry.error = log.error;
                if (log.warning) logEntry.warning = log.warning;
            }

            const current_logs = session.logs.current_logs;

            const previousLog = current_logs.length > 0 ? current_logs[current_logs.length - 1] : null;
            
            // If instructionId is provided, store log under that instruction
            if (log.instructionId) {
                // Check if _ is present in the instructionId. If yes, remove _ and all the characters after _
                if (log.instructionId.includes('_')) {
                    log.instructionId = log.instructionId.split('_')[0];
                }

                // Check if the previous log for the instructionId is same as current instructionId
                if (previousLog && previousLog.instruction === log.instructionId) {
                    // If the previous log is same as current instructionId, then add the log to the previous log
                    previousLog.logs.push(logEntry);
                } else {
                    // If the previous log is not same as current instructionId, then add the log to the new instructionId
                    current_logs.push({
                        instruction: log.instructionId,
                        logs: [logEntry]
                    });
                }
            } else {
                // Check if the previous log for the instructionId is same as current instructionId
                if (previousLog && previousLog.instruction === "system") {
                    // If the previous log is same as current instructionId, then add the log to the previous log
                    previousLog.logs.push(logEntry);
                } else {
                    // If the previous log is not same as current instructionId, then add the log to the new instructionId
                    current_logs.push({
                        instruction: "system",
                        logs: [logEntry]
                    });
                }
            }
            
            // Save the updated session
            await this.set(runId, session);
        } catch (error) {
            logger.error('[ContainerCommsService] Failed to add log to Redis:', error);
            throw error;
        }
    }
} 