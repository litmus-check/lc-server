import { Page, CDPSession } from 'playwright';
import { logger } from '../utils/logger';
import WebSocket = require('ws');

export class ScreencastService {
    private page: Page;
    private cdpSession: CDPSession | null = null;
    private ws: WebSocket | null = null;
    private isRunning: boolean = false;
    private composeId: string;
    private wsUrl: string;
    private frameCount: number = 0;

    constructor(page: Page, composeId: string, wsUrl: string) {
        this.page = page;
        this.composeId = composeId;
        this.wsUrl = wsUrl;
    }

    /**
     * Start the screencast service
     */
    public async start(): Promise<void> {
        if (this.isRunning) {
            logger.warn('Screencast service is already running');
            return;
        }

        try {
            logger.info(`[ScreencastService] Starting screencast for compose_id: ${this.composeId}`);
            
            // Create CDP Session
            this.cdpSession = await this.page.context().newCDPSession(this.page);
            logger.info('[ScreencastService] CDP session created');

            // Connect to websocket server
            await this.connectWebSocket();

            // Listen for screencast frames BEFORE starting screencast
            // This ensures we don't miss any frames
            this.cdpSession.on('Page.screencastFrame', async (frame: any) => {
                await this.handleScreencastFrame(frame);
            });
            logger.info('[ScreencastService] Screencast frame listener registered');

            // Start screencast
            await this.cdpSession.send('Page.startScreencast', { 
                format: 'jpeg', 
                quality: 80 
            });
            logger.info('[ScreencastService] Screencast started - waiting for frames...');

            this.isRunning = true;
            logger.info('[ScreencastService] Screencast service started successfully');
        } catch (error) {
            logger.error(`[ScreencastService] Failed to start screencast: ${error instanceof Error ? error.message : String(error)}`);
            throw error;
        }
    }

    /**
     * Connect to the websocket server
     * The websocket server should be running and accepting connections
     */
    private async connectWebSocket(): Promise<void> {
        return new Promise((resolve, reject) => {
            try {
                // Close existing connection if any
                if (this.ws) {
                    this.ws.removeAllListeners();
                    if (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING) {
                        this.ws.close();
                    }
                }

                // Use hardcoded port for testing if wsUrl is not provided
                // Default to localhost:8080 when websocket server runs in same process
                // Falls back to host.docker.internal for Docker containers if WS_HOST is set
                const wsHost = process.env.WS_HOST || '127.0.0.1';
                const wsPort = process.env.WS_PORT || '8080';
                const defaultWsUrl = `ws://${wsHost}:${wsPort}`;
                const urlToUse = this.wsUrl || defaultWsUrl;
                
                // Construct websocket URL with compose_id as query parameter
                const url = `${urlToUse}?compose_id=${this.composeId}`;
                logger.info(`[ScreencastService] Connecting to websocket: ${url}`);
                
                this.ws = new WebSocket(url);

                this.ws.on('open', () => {
                    logger.info('[ScreencastService] WebSocket connection opened');
                    resolve();
                });

                this.ws.on('error', (error) => {
                    logger.error(`[ScreencastService] WebSocket error: ${error.message}`);
                    // Don't reject on error if we're already running - allow reconnection attempts
                    if (!this.isRunning) {
                        reject(error);
                    }
                });

                this.ws.on('close', (code, reason) => {
                    logger.info(`[ScreencastService] WebSocket connection closed. Code: ${code}, Reason: ${reason.toString()}`);
                    this.ws = null;
                    
                    // Attempt to reconnect if service is still running
                    if (this.isRunning) {
                        logger.info('[ScreencastService] Attempting to reconnect in 2 seconds...');
                        setTimeout(async () => {
                            if (this.isRunning && !this.ws) {
                                try {
                                    await this.connectWebSocket();
                                } catch (reconnectError) {
                                    logger.error(`[ScreencastService] Reconnection failed: ${reconnectError instanceof Error ? reconnectError.message : String(reconnectError)}`);
                                }
                            }
                        }, 2000);
                    }
                });
            } catch (error) {
                logger.error(`[ScreencastService] Failed to create WebSocket: ${error instanceof Error ? error.message : String(error)}`);
                reject(error);
            }
        });
    }

    /**
     * Handle screencast frame from CDP
     * This function sends JPEG frames over websocket to the frontend
     */
    private async handleScreencastFrame(frame: any): Promise<void> {
        try {
            // Increment frame counter
            this.frameCount++;
            
            if (this.frameCount <= 3 || this.frameCount % 30 === 0) {
                logger.info(`[ScreencastService] Received frame #${this.frameCount}, sessionId: ${frame.sessionId}, data length: ${frame.data ? frame.data.length : 0}`);
            }

            // Send frame to client via websocket
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                // Send frame data and sessionId as JSON
                // frame.data is base64-encoded JPEG image
                const message = JSON.stringify({
                    data: frame.data,
                    sessionId: frame.sessionId
                });
                this.ws.send(message);
                
                if (this.frameCount <= 3 || this.frameCount % 30 === 0) {
                    logger.info(`[ScreencastService] Sent frame #${this.frameCount} to websocket`);
                }
            } else {
                // If websocket is not open, try to reconnect
                if (this.isRunning && (!this.ws || this.ws.readyState !== WebSocket.OPEN)) {
                    logger.warn('[ScreencastService] WebSocket not open, attempting to reconnect...');
                    try {
                        await this.connectWebSocket();
                    } catch (reconnectError) {
                        logger.error(`[ScreencastService] Failed to reconnect: ${reconnectError instanceof Error ? reconnectError.message : String(reconnectError)}`);
                    }
                }
            }

            // Acknowledge frame to keep stream going
            // This is critical - without acknowledging, the screencast will stop
            if (this.cdpSession) {
                try {
                    await this.cdpSession.send('Page.screencastFrameAck', { 
                        sessionId: frame.sessionId 
                    });
                } catch (e) {
                    // Ignore errors if session is closed
                    if (this.isRunning) {
                        logger.warn(`[ScreencastService] Failed to acknowledge frame: ${e instanceof Error ? e.message : String(e)}`);
                    }
                }
            }
        } catch (error) {
            logger.error(`[ScreencastService] Error handling screencast frame: ${error instanceof Error ? error.message : String(error)}`);
        }
    }

    /**
     * Stop the screencast service
     */
    public async stop(): Promise<void> {
        if (!this.isRunning) {
            return;
        }

        try {
            logger.info('[ScreencastService] Stopping screencast service');
            
            this.isRunning = false;

            // Stop screencast
            if (this.cdpSession) {
                try {
                    await this.cdpSession.send('Page.stopScreencast');
                } catch (e) {
                    logger.warn(`[ScreencastService] Error stopping screencast: ${e instanceof Error ? e.message : String(e)}`);
                }
                await this.cdpSession.detach();
                this.cdpSession = null;
            }

            // Close websocket connection
            if (this.ws) {
                this.ws.close();
                this.ws = null;
            }

            logger.info('[ScreencastService] Screencast service stopped');
        } catch (error) {
            logger.error(`[ScreencastService] Error stopping screencast service: ${error instanceof Error ? error.message : String(error)}`);
        }
    }

    /**
     * Check if the screencast service is running
     */
    public getIsRunning(): boolean {
        return this.isRunning;
    }
}
