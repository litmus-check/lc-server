import * as fs from 'fs';
import * as path from 'path';
import { logger } from './logger';
import * as AdmZip from 'adm-zip';

interface TraceEvent {
    type: string;
    callId?: string;
    title?: string;
    sha1?: string;
    method?: string;
}

interface ScreenshotWithOverlay {
    path: string;
    actionName: string;
    url: string;
    frameType: 'before' | 'after';
    groupIndex: number;
}

function createLogString(
    groupIndex: number,
    frameType: 'before' | 'after',
    actionName: string,
    url: string
): string {
    return `#${groupIndex} | ${frameType.toUpperCase()} | ${actionName} | ${url}`;
}

async function createGifFromTrace(traceFile: string, outputGif: string) {
    try {
        // Create temporary directory for processing
        const tempDir = path.join(path.dirname(outputGif), 'temp_gif_processing');
        if (!fs.existsSync(tempDir)) {
            fs.mkdirSync(tempDir, { recursive: true });
        }

        logger.info(`Creating GIF from trace: ${traceFile}`);
        logger.info(`Output GIF: ${outputGif}`);

        // Extract the zip file using adm-zip
        const zip = new AdmZip.default(traceFile);
        zip.extractAllTo(tempDir, true);

        // Read and parse the trace file
        const tracePath = path.join(tempDir, 'trace.trace');
        const traceContent = fs.readFileSync(tracePath, 'utf-8');
        const traceLines = traceContent.split('\n');

        const screenshots: ScreenshotWithOverlay[] = [];
        let groupCounter = 0;
        let previousScreenshot: string | null = null;
        let activeGroups = new Map<string, { actionName: string; url: string; startScreenshot: string | null }>();

        // Parse trace file to collect screenshots
        for (const line of traceLines) {
            if (!line.trim()) continue;
            
            const event: TraceEvent = JSON.parse(line);

            // Handle tracing group start
            if (event.type === 'before' && event.method === 'tracingGroup') {
                const title = event.title || `UNKNOWN_ACTION | No URL`;
                const [actionPart, urlPart] = title.split(' | ');
                const actionName = actionPart.toUpperCase().replace(/[^A-Z0-9_]/g, '_');
                const url = urlPart || 'No URL';
                
                groupCounter++;
                
                // Store the group info and the previous screenshot (if available)
                activeGroups.set(event.callId!, {
                    actionName: actionName,
                    url: url,
                    startScreenshot: previousScreenshot
                });
                
                logger.debug(`Created group: ${actionName} with URL: ${url}, callId: ${event.callId}`);
            }

            // Handle tracing group end
            if (event.type === 'after') {
                const activeGroup = activeGroups.get(event.callId!);
                if (activeGroup) {
                    // Add start screenshot (before the action)
                    if (activeGroup.startScreenshot) {
                        const resourcePath = path.join(tempDir, 'resources', activeGroup.startScreenshot);
                        screenshots.push({
                            path: resourcePath,
                            actionName: activeGroup.actionName,
                            url: activeGroup.url,
                            frameType: 'before',
                            groupIndex: groupCounter
                        });
                        logger.debug(`Added start screenshot for group ${groupCounter}: ${activeGroup.actionName}`);
                    }
                    
                    // Add end screenshot (after the action) - use current screenshot if available
                    if (previousScreenshot) {
                        const resourcePath = path.join(tempDir, 'resources', previousScreenshot);
                        screenshots.push({
                            path: resourcePath,
                            actionName: activeGroup.actionName,
                            url: activeGroup.url,
                            frameType: 'after',
                            groupIndex: groupCounter
                        });
                        logger.debug(`Added end screenshot for group ${groupCounter}: ${activeGroup.actionName}`);
                    }
                    
                    // Remove from active groups
                    activeGroups.delete(event.callId!);
                }
            }

            // Collect screenshots and update previous screenshot
            if (event.type === 'screencast-frame') {
                previousScreenshot = event.sha1!; // Store only the sha1 hash
            }
        }

        logger.info(`Created ${screenshots.length} screenshots from ${groupCounter} groups`);

        // Create GIF from screenshots
        await createGifFromScreenshots(screenshots, outputGif);
        logger.info(`Created GIF at: ${outputGif}`);

    } catch (error) {
        logger.error('Error creating GIF from trace:', error);
        throw error;
    }
}

async function createGifFromScreenshots(
    gifScreenshots: ScreenshotWithOverlay[],
    outputPath: string,
    width: number = 1920,
    height: number = 1080,
    frameDelay: number = 1000
): Promise<void> {
    return new Promise(async (resolve, reject) => {
        try {
            const imagePaths: string[] = [];
            const overlayTexts: string[] = [];

            // Process each screenshot
            for (const screenshot of gifScreenshots) {
                imagePaths.push(screenshot.path);
                
                // Create overlay text using the specified format
                const overlayText = createLogString(
                    screenshot.groupIndex,
                    screenshot.frameType,
                    screenshot.actionName,
                    screenshot.url
                );
                overlayTexts.push(overlayText);
                
                logger.debug(`Added screenshot with overlay: ${overlayText}`);
            }

            if (imagePaths.length === 0) {
                logger.warn('No screenshots found to create GIF');
                resolve();
                return;
            }

            logger.info(`Creating GIF from ${imagePaths.length} screenshots with dimensions ${width}x${height}`);

            // Create GIF with overlays
            await createGifWithOverlays(imagePaths, outputPath, width, height, frameDelay, (index) => overlayTexts[index]);

            logger.info(`GIF created successfully at: ${outputPath}`);
            resolve();
        } catch (error) {
            logger.error('Error creating GIF:', error);
            reject(error);
        }
    });
}

async function createGifWithOverlays(
    imagePaths: string[],
    outputPath: string,
    width: number,
    height: number,
    frameDelay: number = 1000,
    getOverlayText?: (index: number) => string
): Promise<void> {
    return new Promise(async (resolve, reject) => {
        try {
            const { createCanvas, loadImage } = require('canvas');
            
            // Get dimensions from first image
            let gifWidth = width;
            let gifHeight = height;
            
            try {
                const firstImage = await loadImage(imagePaths[0]);
                gifWidth = firstImage.width;
                gifHeight = firstImage.height;
                logger.info(`Using first image dimensions: ${gifWidth}x${gifHeight}`);
            } catch (error) {
                logger.warn(`Failed to get first image dimensions, using viewport: ${width}x${height}`);
            }

            const GIFEncoder = require('gifencoder');
            const encoder = new GIFEncoder(gifWidth, gifHeight);
            const canvas = createCanvas(gifWidth, gifHeight);
            const ctx = canvas.getContext('2d');

            const output = fs.createWriteStream(outputPath);
            encoder.createReadStream().pipe(output);

            encoder.start();
            encoder.setRepeat(0);
            encoder.setDelay(frameDelay);
            encoder.setQuality(10);

            for (let i = 0; i < imagePaths.length; i++) {
                const imagePath = imagePaths[i];
                const overlayText = getOverlayText ? getOverlayText(i) : undefined;

                try {
                    const frameCtx = await drawImageWithOverlay(imagePath, gifWidth, gifHeight, overlayText);
                    ctx.drawImage(frameCtx.canvas, 0, 0);
                    encoder.addFrame(ctx);
                    logger.debug(`Added frame ${i + 1}/${imagePaths.length}: ${overlayText || 'No overlay'}`);
                } catch (error) {
                    logger.warn(`Failed to add frame ${imagePath}: ${error}`);
                }
            }

            encoder.finish();

            output.on('close', () => resolve());
            output.on('error', reject);
        } catch (error) {
            reject(error);
        }
    });
}

async function drawImageWithOverlay(
    imagePath: string,
    width: number,
    height: number,
    overlayText?: string
): Promise<CanvasRenderingContext2D> {
    const { createCanvas, loadImage } = require('canvas');
    
    const canvas = createCanvas(width, height);
    const ctx = canvas.getContext('2d');

    try {
        // Load the image
        const image = await loadImage(imagePath);
        
        // Calculate centering position
        const imageWidth = image.width;
        const imageHeight = image.height;
        
        // Fill background with white
        ctx.fillStyle = 'white';
        ctx.fillRect(0, 0, width, height);
        
        // If image dimensions match canvas, draw directly; otherwise center
        if (imageWidth === width && imageHeight === height) {
            ctx.drawImage(image, 0, 0);
        } else {
            // Center the image without scaling
            const x = (width - imageWidth) / 2;
            const y = (height - imageHeight) / 2;
            ctx.drawImage(image, x, y);
        }

        // Add overlay if text is provided
        if (overlayText) {
            // Calculate font size based on width
            const finalFontSize = Math.max(11, Math.min(20, Math.floor(width / 100)));
            
            // Create semi-transparent background for text at the top
            const overlayHeight = finalFontSize + 8; // 14px font + 5px padding = 19px height
            ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
            ctx.fillRect(0, 0, width, overlayHeight);

            // Add text with white color and black outline
            ctx.fillStyle = 'white';
            ctx.strokeStyle = 'black';
            ctx.lineWidth = 2;
            ctx.font = `bold ${finalFontSize}px Arial`;
            ctx.textAlign = 'left';

            // Calculate text position (centered vertically in overlay)
            const textX = Math.max(10, Math.floor(width * 0.02));
            const textY = finalFontSize + 1; // Reduced from +5 to +1 for smaller overlay

            // Draw text with outline
            ctx.strokeText(overlayText, textX, textY);
            ctx.fillText(overlayText, textX, textY);
        }
    } catch (error) {
        logger.warn(`Failed to process image ${imagePath}: ${error}`);
        // Draw a placeholder if image loading fails
        ctx.fillStyle = '#f0f0f0';
        ctx.fillRect(0, 0, width, height);
        ctx.fillStyle = 'black';
        ctx.font = '16px Arial';
        ctx.fillText('Image not available', 10, height / 2);
    }

    return ctx;
}

export { createGifFromTrace, createLogString }; 