// @ts-ignore - imap types may not be available
import Imap from 'imap';
import { logger } from '../utils/logger';

export interface EmailData {
    subject: string;
    content: string;
    from: string;
    date: string;
    to: string;
    messageId: string;
}

export class GmailClient {
    private imap!: Imap;

    constructor() {
        this.initializeImap();
    }

    private initializeImap() {
        const username = process.env.GMAIL_ACCOUNT || '';
        const password = process.env.GMAIL_APP_PASSWORD || '';
        
        // Debug logging
        logger.info(`Gmail authentication - Username: ${username ? '✅ Set' : '❌ Not set'}`);
        logger.info(`Gmail authentication - Password: ${password ? '✅ Set' : '❌ Not set'}`);
        
        if (!username || !password) {
            logger.error('Gmail authentication credentials are missing. Please check environment variables.');
            throw new Error('Gmail authentication credentials are missing');
        }
        
        // Gmail IMAP configuration
        this.imap = new Imap({
            user: username,
            password: password,
            host: 'imap.gmail.com',
            port: 993,
            tls: true,
            tlsOptions: { rejectUnauthorized: false }
        });
    }

        /**
     * Fetches the last N emails from the inbox
     * @returns Promise<EmailData[]> Array of email data
     */
    async getLastEmails(count: number = 5): Promise<EmailData[]> {
        return new Promise((resolve, reject) => {
            const emailData: EmailData[] = [];
            let emailsProcessed = 0;
            let connectionClosed = false;

            const cleanup = () => {
                if (!connectionClosed) {
                    connectionClosed = true;
                    this.imap.end();
                }
            };

            this.imap.once('ready', () => {
                logger.info('IMAP connection ready');
                
                this.imap.openBox('INBOX', false, (err, box) => {
                    if (err) {
                        logger.error('Error opening inbox:', err);
                        cleanup();
                        reject(err);
                        return;
                    }

                    // Get the last N messages (latest first)
                    const totalMessages = box.messages.total;
                    const start = Math.max(1, totalMessages - count + 1);
                    const end = totalMessages;

                    logger.info(`Fetching messages ${start} to ${end} (latest first)`);

                    const fetch = this.imap.seq.fetch(`${start}:${end}`, {
                        bodies: ['HEADER.FIELDS (FROM TO SUBJECT DATE)', 'TEXT'],
                        struct: true
                    });

                    fetch.on('message', (msg, seqno) => {
                        let buffer = '';
                        let header = '';

                        msg.on('body', (stream, info) => {
                            if (info.which === 'TEXT') {
                                stream.on('data', (chunk) => {
                                    buffer += chunk.toString('utf8');
                                });
                            } else {
                                stream.on('data', (chunk) => {
                                    header += chunk.toString('utf8');
                                });
                            }
                        });

                        msg.once('end', () => {
                            try {
                                const emailInfo = this.parseEmailData(header, buffer);
                                emailData.push(emailInfo);
                                emailsProcessed++;

                                // Only close connection after all messages are processed
                                if (emailsProcessed >= Math.min(count, totalMessages)) {
                                    setTimeout(() => cleanup(), 100); // Small delay to ensure all data is processed
                                }
                            } catch (error) {
                                logger.error('Error parsing email:', error);
                                emailsProcessed++;
                                
                                if (emailsProcessed >= Math.min(count, totalMessages)) {
                                    setTimeout(() => cleanup(), 100);
                                }
                            }
                        });
                    });

                    fetch.once('error', (err) => {
                        logger.error('Fetch error:', err);
                        cleanup();
                        reject(err);
                    });

                    fetch.once('end', () => {
                        logger.info('Fetch completed');
                        // Don't close connection here - let it close after all messages are processed
                    });
                });
            });

            this.imap.once('error', (err) => {
                logger.error('IMAP connection error:', err);
                cleanup();
                reject(err);
            });

            this.imap.once('end', () => {
                logger.info(`Successfully fetched ${emailData.length} emails`);
                // Reverse the array to get latest emails first
                const reversedEmails = emailData.reverse();
                resolve(reversedEmails);
            });

            this.imap.connect();
        });
    }

    /**
     * Parse email data from IMAP response
     */
    private parseEmailData(header: string, body: string): EmailData {
        // Parse headers
        const subjectMatch = header.match(/Subject: (.+)/i);
        const fromMatch = header.match(/From: (.+)/i);
        const dateMatch = header.match(/Date: (.+)/i);
        const toMatch = header.match(/To: (.+)/i);

        const subject = subjectMatch ? subjectMatch[1].trim() : 'No Subject';
        const from = fromMatch ? fromMatch[1].trim() : 'Unknown Sender';
        const date = dateMatch ? dateMatch[1].trim() : 'Unknown Date';
        const to = toMatch ? toMatch[1].trim() : 'Unknown Recipient';

        // log the subject 
        logger.info(`Subject: ${subject}`);

        // Clean up the body content
        const content = this.cleanEmailContent(body);

        return {
            subject,
            content,
            from,
            date,
            to,
            messageId: `msg_${Date.now()}_${Math.random()}`
        };
    }

    /**
     * Clean up email content
     */
    private cleanEmailContent(content: string): string {
        return content
            .replace(/\r\n/g, '\n') // Normalize line endings
            .replace(/\r/g, '\n') // Replace carriage returns
            .replace(/\n\s*\n/g, '\n') // Remove multiple empty lines
            .trim();
    }

    /**
     * Test connection to Gmail
     */
    async testConnection(): Promise<boolean> {
        return new Promise((resolve) => {
            let resolved = false;

            const cleanup = () => {
                if (!resolved) {
                    resolved = true;
                    this.imap.end();
                }
            };

            this.imap.once('ready', () => {
                logger.info('Gmail IMAP connection test successful');
                cleanup();
                resolve(true);
            });

            this.imap.once('error', (err) => {
                logger.error('Gmail IMAP connection test failed:', err);
                cleanup();
                resolve(false);
            });

            this.imap.connect();
        });
    }
}
