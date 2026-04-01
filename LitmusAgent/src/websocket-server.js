const WebSocket = require('ws');

function startWebSocketServer(port = 8080) {
    // Listen on all interfaces (0.0.0.0) so Docker containers can connect
    const wss = new WebSocket.Server({ host: '0.0.0.0', port: port });

    console.log(`WebSocket server started on 0.0.0.0:${port}`);
    console.log(`Accessible from Docker containers via: ws://host.docker.internal:${port}`);

    // Store active connections by compose_id
    const connections = new Map();

    wss.on('connection', (ws, req) => {
        try {
            // Parse compose_id from query parameters
            // Support both root path and /stream path (or any path)
            const url = new URL(req.url, `http://localhost:${port}`);
            const composeId = url.searchParams.get('compose_id');
            
            console.log(`[WebSocket] New connection attempt - Path: ${url.pathname}, Query: ${url.search}`);
            
            if (!composeId) {
                console.warn('Connection rejected: no compose_id provided in query string');
                ws.close(1008, 'compose_id is required');
                return;
            }

            console.log(`[${composeId}] Client connected`);
            
            // Store connection
            if (!connections.has(composeId)) {
                connections.set(composeId, []);
            }
            connections.get(composeId).push({
                ws: ws,
                connectedAt: new Date()
            });

            // Track frame count for logging (only for the first connection, assuming it's the agent)
            let frameCount = 0;
            const frameLogInterval = setInterval(() => {
                if (frameCount > 0) {
                    console.log(`[${composeId}] Received ${frameCount} frames in the last second`);
                    frameCount = 0;
                }
            }, 1000);

            // Handle messages (screencast frames from agent)
            ws.on('message', (message) => {
                try {
                    const data = JSON.parse(message);
                    frameCount++;
                    
                    // Log first frame and then every 30 frames to avoid spam
                    if (frameCount === 1 || frameCount % 30 === 0) {
                        const dataSize = Buffer.byteLength(message, 'utf8');
                        console.log(`[${composeId}] Frame #${frameCount} received - Size: ${(dataSize / 1024).toFixed(2)}KB, SessionId: ${data.sessionId}`);
                    }
                    
                    // Forward frame to all other connected clients for this compose_id
                    const composeConnections = connections.get(composeId) || [];
                    let forwardedCount = 0;
                    composeConnections.forEach(conn => {
                        // Forward to all other connections (excluding the sender)
                        if (conn.ws !== ws && conn.ws.readyState === WebSocket.OPEN) {
                            conn.ws.send(message);
                            forwardedCount++;
                        }
                    });
                    
                    if (forwardedCount === 0 && frameCount === 1) {
                        console.log(`[${composeId}] No other clients connected. Frames are being received but not forwarded.`);
                    }
                } catch (e) {
                    console.error(`[${composeId}] Error parsing message:`, e);
                }
            });

            ws.on('error', (error) => {
                console.error(`[${composeId}] WebSocket error:`, error.message);
            });

            ws.on('close', (code, reason) => {
                clearInterval(frameLogInterval);
                console.log(`[${composeId}] Client disconnected. Code: ${code}, Reason: ${reason.toString()}`);
                
                // Remove connection
                const composeConnections = connections.get(composeId);
                if (composeConnections) {
                    const index = composeConnections.findIndex(c => c.ws === ws);
                    if (index !== -1) {
                        composeConnections.splice(index, 1);
                    }
                    if (composeConnections.length === 0) {
                        connections.delete(composeId);
                    }
                }
            });
        } catch (error) {
            console.error('Error handling connection:', error);
            ws.close(1011, 'Internal server error');
        }
    });

    // Return the server instance for cleanup
    return wss;
}

// Export for use in index.ts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { startWebSocketServer };
}

// If run directly, start the server
if (require.main === module) {
    const port = process.env.WS_PORT || 8080;
    const wss = startWebSocketServer(parseInt(port));
    
    // Graceful shutdown
    process.on('SIGINT', () => {
        console.log('\nShutting down WebSocket server...');
        wss.close(() => {
            console.log('WebSocket server closed');
            process.exit(0);
        });
    });

    process.on('SIGTERM', () => {
        console.log('\nShutting down WebSocket server...');
        wss.close(() => {
            console.log('WebSocket server closed');
            process.exit(0);
        });
    });
}
