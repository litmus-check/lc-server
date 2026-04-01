import { VerificationExtractor } from '../LLM/VerificationExtractor';
import { GmailClient } from './GmailClient';
import { logger } from '../utils/logger';
import { ContainerCommsService } from '../services/ContainerCommsService';
import { LLMLogContext } from '../LLM/LLM';

export interface EmailVerificationResult {
    success: boolean;
    verificationType?: string;
    verificationValue?: string;
    error?: string;
}

export class EmailVerificationService {
    private containerCommsService: ContainerCommsService;
    private runId: string;
    private goalId: string;
    private stepCount: number;

    constructor(
        containerCommsService: ContainerCommsService,
        runId: string,
        goalId: string,
        stepCount: number
    ) {
        this.containerCommsService = containerCommsService;
        this.runId = runId;
        this.goalId = goalId;
        this.stepCount = stepCount;
    }

    async executeVerifyEmailAction(prompt: string, retries: number = 3, toEmail?: string, logContext?: LLMLogContext): Promise<EmailVerificationResult> {
        let lastError: string | undefined;
        
        for (let attempt = 1; attempt <= retries; attempt++) {
            try {
                logger.info(`Executing verify_email action (attempt ${attempt}/${retries}): Waiting 15 seconds before checking emails...`);
                await this.containerCommsService.addLog(this.runId, {
                    info: `Goal step ${this.stepCount}: Starting verify_email action (attempt ${attempt}/${retries}) - waiting 10 seconds before checking emails${toEmail ? ` for emails sent to ${toEmail}` : ''}`,
                    timestamp: new Date().toISOString(),
                    instructionId: this.goalId
                });

                // Wait for 10 seconds
                await new Promise(resolve => setTimeout(resolve, 15000));
                
                logger.info(`15 seconds elapsed, now checking emails for verification (attempt ${attempt}/${retries})...`);
                await this.containerCommsService.addLog(this.runId, {
                    info: `Goal step ${this.stepCount}: 10 seconds elapsed, checking emails for verification (attempt ${attempt}/${retries})`,
                    timestamp: new Date().toISOString(),
                    instructionId: this.goalId
                });

                // Initialize Gmail client and verification extractor
                const gmailClient = new GmailClient();
                const verificationExtractor = new VerificationExtractor();

                // Fetch last 5 emails (latest first)
                const emails = await gmailClient.getLastEmails(5);
                logger.info(`Fetched ${emails.length} emails for verification`);

                if (emails.length === 0) {
                    logger.warn('No emails found for verification');
                    lastError = 'No emails found';
                    
                    if (attempt < retries) {
                        logger.info(`No emails found on attempt ${attempt}, will retry in 10 seconds...`);
                        await this.containerCommsService.addLog(this.runId, {
                            info: `Goal step ${this.stepCount}: No emails found on attempt ${attempt}, will retry in 10 seconds`,
                            timestamp: new Date().toISOString(),
                            instructionId: this.goalId
                        });
                        continue;
                    } else {
                        await this.containerCommsService.addLog(this.runId, {
                            error: `Goal step ${this.stepCount}: No emails found for verification after ${retries} attempts`,
                            timestamp: new Date().toISOString(),
                            instructionId: this.goalId
                        });
                        return { success: false, error: 'No emails found' };
                    }
                }

                // Filter emails by recipient if toEmail is provided
                let filteredEmails = emails;
                if (toEmail) {
                    filteredEmails = emails.filter(email => {
                        // Check if the email content contains the target email address
                        const emailContent = email.content.toLowerCase();
                        const targetEmail = toEmail.toLowerCase();
                        return emailContent.includes(targetEmail) || email.subject.toLowerCase().includes(targetEmail) || email.to.toLowerCase().includes(targetEmail);
                    });
                    
                    logger.info(`Filtered emails for ${toEmail}: ${filteredEmails.length} out of ${emails.length} emails`);
                    
                    if (filteredEmails.length === 0) {
                        logger.warn(`No emails found for ${toEmail}`);
                        lastError = `No emails found for ${toEmail}`;
                        
                        if (attempt < retries) {
                            logger.info(`No emails for ${toEmail} on attempt ${attempt}, will retry in 10 seconds...`);
                            await this.containerCommsService.addLog(this.runId, {
                                info: `Goal step ${this.stepCount}: No emails for ${toEmail} on attempt ${attempt}, will retry in 10 seconds`,
                                timestamp: new Date().toISOString(),
                                instructionId: this.goalId
                            });
                            continue;
                        } else {
                            await this.containerCommsService.addLog(this.runId, {
                                error: `Goal step ${this.stepCount}: No emails found for ${toEmail} after ${retries} attempts`,
                                timestamp: new Date().toISOString(),
                                instructionId: this.goalId
                            });
                            return { success: false, error: `No emails found for ${toEmail}` };
                        }
                    }
                }

                // Extract verification from emails using the prompt from the action
                const verificationResult = await verificationExtractor.getFirstValidVerification(filteredEmails, prompt, logContext);
                
                if (verificationResult && verificationResult.args && verificationResult.args.value !== 'none') {
                    const verificationType = verificationResult.args.type;
                    const verificationValue = verificationResult.args.value;
                    
                    logger.info(`Found verification ${verificationType}: ${verificationValue} on attempt ${attempt}`);
                    console.log(`🎉 Verification found: ${verificationType} - ${verificationValue}`);
                    
                    // Log to container comms
                    await this.containerCommsService.addLog(this.runId, {
                        info: `Goal step ${this.stepCount}: Found verification ${verificationType}: ${verificationValue} on attempt ${attempt}`,
                        timestamp: new Date().toISOString(),
                        instructionId: this.goalId
                    });

                    // Store verification in session for future use
                    let session = await this.containerCommsService.get(this.runId);
                    if (session) {
                        if (!session.verification) {
                            session.verification = {};
                        }
                        session.verification[verificationType] = verificationValue;
                        session.verification.timestamp = new Date().toISOString();
                        await this.containerCommsService.set(this.runId, session);
                    }

                    // Call goal agent step again with the verification result
                    logger.info('Calling goal agent step again with verification result...');
                    await this.containerCommsService.addLog(this.runId, {
                        info: `Goal step ${this.stepCount}: Calling goal agent step again with verification result`,
                        timestamp: new Date().toISOString(),
                        instructionId: this.goalId
                    });

                    return {
                        success: true,
                        verificationType,
                        verificationValue
                    };
                } else {
                    logger.warn(`No verification code or link found in emails on attempt ${attempt}`);
                    lastError = 'No verification found';
                    
                    if (attempt < retries) {
                        logger.info(`No verification found on attempt ${attempt}, will retry in 10 seconds...`);
                        await this.containerCommsService.addLog(this.runId, {
                            info: `Goal step ${this.stepCount}: No verification found on attempt ${attempt}, will retry in 10 seconds`,
                            timestamp: new Date().toISOString(),
                            instructionId: this.goalId
                        });
                        continue;
                    } else {
                        await this.containerCommsService.addLog(this.runId, {
                            error: `Goal step ${this.stepCount}: No verification code or link found in emails after ${retries} attempts`,
                            timestamp: new Date().toISOString(),
                            instructionId: this.goalId
                        });
                        return { success: false, error: 'No verification found' };
                    }
                }

            } catch (error) {
                logger.error(`Error during verify_email action on attempt ${attempt}:`, error);
                lastError = error instanceof Error ? error.message : String(error);
                
                if (attempt < retries) {
                    logger.info(`Error on attempt ${attempt}, will retry in 10 seconds...`);
                    await this.containerCommsService.addLog(this.runId, {
                        info: `Goal step ${this.stepCount}: Error on attempt ${attempt}, will retry in 15 seconds: ${lastError}`,
                        timestamp: new Date().toISOString(),
                        instructionId: this.goalId
                    });
                    continue;
                } else {
                    await this.containerCommsService.addLog(this.runId, {
                        error: `Goal step ${this.stepCount}: Error during verify_email action after ${retries} attempts: ${lastError}`,
                        timestamp: new Date().toISOString(),
                        instructionId: this.goalId
                    });
                    return { 
                        success: false, 
                        error: lastError
                    };
                }
            }
        }

        // This should never be reached, but just in case
        return { 
            success: false, 
            error: lastError || 'Unknown error occurred' 
        };
    }

    getVerificationHistoryMessage(verificationType: string, verificationValue: string): string {
        return `Verification Found: ${verificationType.toUpperCase()} - ${verificationValue}`;
    }
}
