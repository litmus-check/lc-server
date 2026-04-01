import { Page } from 'playwright';
import { logger } from '../utils/logger';
import { ContainerCommsService } from '../services/ContainerCommsService';

export class PerformanceMonitoring {
    private page: Page;
    private containerCommsService: ContainerCommsService | null;
    private runId: string | null;

    constructor(page: Page, containerCommsService?: ContainerCommsService, runId?: string) {
        this.page = page;
        this.containerCommsService = containerCommsService || null;
        this.runId = runId || null;
    }

    /**
     * Set up performance monitoring for page load metrics
     */
    public async setupPerformanceMonitoring(): Promise<void> {
        await this.page.evaluate(() => {
            // Set up PerformanceObserver for paint timing only
            const paintObserver = new PerformanceObserver((list) => {
                for (const entry of list.getEntries()) {
                    if (entry.name === 'first-paint') {
                        console.log("First Paint:", entry.startTime, "ms");
                    } else if (entry.name === 'first-contentful-paint') {
                        console.log("First Contentful Paint:", entry.startTime, "ms");
                    }
                }
            });
            paintObserver.observe({ type: "paint", buffered: true });

            // Store observers globally for cleanup
            (window as any).performanceObservers = [paintObserver];
        });
    }

    /**
     * Wait for page load with timeout
     * @param page The page to wait for
     * @param timeoutMs Timeout in milliseconds (default: 15000)
     * @returns Promise that resolves when page is loaded or timeout is reached
     */
    public async waitForPageLoadWithTimeout(page: any, timeoutMs: number = 15000): Promise<boolean> {
        try {
            await page.waitForLoadState('networkidle', { timeout: timeoutMs });
            return true;
        } catch (error) {
            logger.warn(`Page did not reach networkidle state within ${timeoutMs}ms, proceeding with metrics collection anyway`);
            return false;
        }
    }

    /**
     * Collect performance metrics after page load
     */
    public async collectPerformanceMetrics(): Promise<any> {
        return await this.page.evaluate(() => {
            return new Promise((resolve) => {
                const metrics: any = {
                    allNavigationEntries: null,
                    pageLoadTime: null,
                    domContentLoadTime: null,
                    firstPaint: null,
                    firstContentfulPaint: null,
                    largestContentfulPaint: null,
                    allPaintEntries: null,
                    allLcpEntries: null
                };

                // Get navigation timing data
                const navigationEntries = performance.getEntriesByType('navigation');
                if (navigationEntries.length > 0) {
                    const navEntry = navigationEntries[0] as PerformanceNavigationTiming;
                    metrics.allNavigationEntries = navigationEntries;
                    metrics.pageLoadTime = navEntry.loadEventEnd - navEntry.startTime;
                    metrics.domContentLoadTime = navEntry.domContentLoadedEventEnd - navEntry.startTime;
                }

                // Get paint timing data
                const paintEntries = performance.getEntriesByType('paint');
                metrics.allPaintEntries = paintEntries;
                for (const entry of paintEntries) {
                    if (entry.name === 'first-paint') {
                        metrics.firstPaint = entry.startTime;
                    } else if (entry.name === 'first-contentful-paint') {
                        metrics.firstContentfulPaint = entry.startTime;
                    }
                }

                // Get LCP using Promise-based approach with buffered entry check
                const resolved = { done: false };
                const lcpObserver = new PerformanceObserver((l) => {
                    const entries = l.getEntries();
                    const last = entries[entries.length - 1];
                    metrics.allLcpEntries = entries;
                    if (last) {
                        metrics.largestContentfulPaint = last.startTime;
                    }
                    if (!resolved.done) {
                        resolved.done = true;
                        if ((window as any).performanceObservers) {
                            (window as any).performanceObservers.forEach((observer: PerformanceObserver) => observer.disconnect());
                            delete (window as any).performanceObservers;
                        }
                        lcpObserver.disconnect();
                        resolve(metrics);
                    }
                });
                lcpObserver.observe({ type: 'largest-contentful-paint', buffered: true });
                
                // Also check any buffered entries immediately
                const buffered = performance.getEntriesByType('largest-contentful-paint') as any[];
                if (buffered.length && !resolved.done) {
                    metrics.largestContentfulPaint = buffered[buffered.length - 1].startTime;
                    resolved.done = true;
                    if ((window as any).performanceObservers) {
                        (window as any).performanceObservers.forEach((observer: PerformanceObserver) => observer.disconnect());
                        delete (window as any).performanceObservers;
                    }
                    lcpObserver.disconnect();
                    resolve(metrics);
                }
            });
        });
    }

    /**
     * Collect performance metrics with timeout protection
     * @param timeoutMs Timeout in milliseconds (default: 15000)
     * @returns Promise that resolves with metrics or empty metrics on timeout
     */
    public async collectPerformanceMetricsWithTimeout(timeoutMs: number = 15000): Promise<any> {
        try {
            // Create a timeout promise
            const timeoutPromise = new Promise((_, reject) => {
                setTimeout(() => reject(new Error('Performance metrics collection timeout')), timeoutMs);
            });

            // Race between metrics collection and timeout
            const metrics = await Promise.race([
                this.collectPerformanceMetrics(),
                timeoutPromise
            ]);

            return metrics;
        } catch (error) {
            logger.warn(`Performance metrics collection timed out after ${timeoutMs}ms`);
            return {
                allNavigationEntries: null,
                pageLoadTime: null,
                domContentLoadTime: null,
                firstPaint: null,
                firstContentfulPaint: null,
                largestContentfulPaint: null,
                allPaintEntries: null,
                allLcpEntries: null
            };
        }
    }

    /**
     * Log performance metrics to console and Redis
     */
    public async logPerformanceMetrics(metrics: any, url: string, instructionId?: string): Promise<void> {
        const logId = instructionId ;
        
        const performanceLog = {
            logId: logId,
            url: url,
            allNavigationEntries: metrics.allNavigationEntries ? JSON.stringify(metrics.allNavigationEntries) : 'N/A',
            pageLoadTime: metrics.pageLoadTime ? `${(metrics.pageLoadTime / 1000).toFixed(3)}s` : 'N/A',
            domContentLoadTime: metrics.domContentLoadTime ? `${(metrics.domContentLoadTime / 1000).toFixed(3)}s` : 'N/A',
            firstPaint: metrics.firstPaint ? `${(metrics.firstPaint / 1000).toFixed(3)}s` : 'N/A',
            firstContentfulPaint: metrics.firstContentfulPaint ? `${(metrics.firstContentfulPaint / 1000).toFixed(3)}s` : 'N/A',
            largestContentfulPaint: metrics.largestContentfulPaint ? `${(metrics.largestContentfulPaint / 1000).toFixed(3)}s` : 'N/A',
            allPaintEntries: metrics.allPaintEntries ? JSON.stringify(metrics.allPaintEntries) : 'N/A',
            allLcpEntries: metrics.allLcpEntries ? JSON.stringify(metrics.allLcpEntries) : 'N/A'
        };

        // Log to console
        logger.info(`Performance Metrics [${logId}]:`, performanceLog);
       

       // Log to Redis if available
        if (this.containerCommsService && this.runId) {
            try {
                // Log each metric separately with unique identifiers
                await this.containerCommsService.addLog(this.runId, {
                    info: `[${logId}] Performance Metrics for ${url}:`,
                    timestamp: new Date().toISOString()
                });
                
                await this.containerCommsService.addLog(this.runId, {
                    info: `[${logId}] 1. Page Load Time: ${performanceLog.pageLoadTime}`,
                    timestamp: new Date().toISOString()
                });
                
                await this.containerCommsService.addLog(this.runId, {
                    info: `[${logId}] 2. DOM Content Load Time: ${performanceLog.domContentLoadTime}`,
                    timestamp: new Date().toISOString()
                });
                
                await this.containerCommsService.addLog(this.runId, {
                    info: `[${logId}] 3. First Paint Time: ${performanceLog.firstPaint}`,
                    timestamp: new Date().toISOString()
                });
                
                await this.containerCommsService.addLog(this.runId, {
                    info: `[${logId}] 4. First Contentful Paint: ${performanceLog.firstContentfulPaint}`,
                    timestamp: new Date().toISOString()
                });
                
                await this.containerCommsService.addLog(this.runId, {
                    info: `[${logId}] 5. Largest Contentful Paint: ${performanceLog.largestContentfulPaint}`,
                    timestamp: new Date().toISOString()
                });
            } catch (error) {
                logger.error('Failed to log performance metrics to Redis:', error);
            }
        }
    }
}
