import { BlobServiceClient, StorageSharedKeyCredential, BlockBlobClient } from '@azure/storage-blob';
import * as dotenv from 'dotenv';
import * as fs from 'fs';
import * as path from 'path';
import { logger } from './logger';

// Load environment variables
dotenv.config();

/**
 * Simple download utility for Azure Blob Storage
 */
export class DownloadUtils {
    private static instance: DownloadUtils;
    private blobServiceClient: BlobServiceClient | null = null;
    private accountName: string = '';
    private accountKey: string = '';

    private constructor() {
        this.initialize();
    }

    /**
     * Get the singleton instance of DownloadUtils
     */
    public static getInstance(): DownloadUtils {
        if (!DownloadUtils.instance) {
            DownloadUtils.instance = new DownloadUtils();
        }
        return DownloadUtils.instance;
    }

    /**
     * Initialize the Azure Blob Service client
     */
    private initialize(): void {
        if (!this.blobServiceClient) {
            this.accountName = process.env.STORAGE_ACCOUNT_NAME || '';
            this.accountKey = process.env.STORAGE_ACCOUNT_KEY || '';

            if (!this.accountName || !this.accountKey) {
                throw new Error('Missing required environment variables: STORAGE_ACCOUNT_NAME and STORAGE_ACCOUNT_KEY');
            }

            const sharedKeyCredential = new StorageSharedKeyCredential(
                this.accountName,
                this.accountKey
            );

            this.blobServiceClient = new BlobServiceClient(
                `https://${this.accountName}.blob.core.windows.net`,
                sharedKeyCredential
            );
        }
    }

    /**
     * Download a file from Azure Blob Storage URL to a local file path
     * @param blobUrl - The complete Azure Blob Storage URL
     * @param localFolderPath - Local folder path where the file should be saved (without extension)
     * @returns Promise that resolves to the final local file path when download is complete
     */
    public async downloadFile(blobUrl: string, localFolderPath: string): Promise<string> {
        try {
            if (!this.blobServiceClient) {
                throw new Error('Azure Blob Service not initialized');
            }

            // Parse the blob URL to extract container name and blob name
            const urlParts = blobUrl.split('.blob.core.windows.net/');
            if (urlParts.length !== 2) {
                throw new Error('Invalid Azure Blob Storage URL format');
            }

            const pathAfterDomain = urlParts[1];
            const pathSegments = pathAfterDomain.split('/');
            
            if (pathSegments.length < 2) {
                throw new Error('Invalid Azure Blob Storage URL: missing container or blob name');
            }

            const containerName = pathSegments[0];
            const blobName = pathSegments.slice(1).join('/');

            // Extract the last ID and filename from the blob path
            const pathParts = blobName.split('/').filter(part => part.length > 0); // Filter out empty strings from double slashes
            const lastPart = pathParts[pathParts.length - 1]; // Get the actual filename (e.g., "fc.pdf")
            const secondLastPart = pathParts[pathParts.length - 2]; // Get the last ID (e.g., "3b03c47e-5f25-4c3b-afe8-6f9f1f1e41fc")
            
            // Create filename with last ID and original filename
            const finalFilename = `${secondLastPart}_${lastPart}`;
            const finalLocalPath = `${localFolderPath}/${finalFilename}`;

            // Ensure the directory exists before downloading
            if (!fs.existsSync(localFolderPath)) {
                fs.mkdirSync(localFolderPath, { recursive: true });
                logger.info(`Created directory: ${localFolderPath}`);
            }

            logger.info(`Downloading file from ${blobUrl} to ${finalLocalPath}`);

            // Get container client
            const containerClient = this.blobServiceClient.getContainerClient(containerName);
            
            // Get block blob client
            const blockBlobClient: BlockBlobClient = containerClient.getBlockBlobClient(blobName);

            // Download the file
            await blockBlobClient.downloadToFile(finalLocalPath);

            logger.info(`Successfully downloaded file to ${finalLocalPath}`);
            return finalLocalPath;
        } catch (error) {
            const errorMessage = error instanceof Error ? error.message : String(error);
            logger.error(`Failed to download file from ${blobUrl}:`, error);
            throw new Error(`Download failed: ${errorMessage}`);
        }
    }

    /**
     * Download JSON content from Azure Blob Storage URL and return as parsed object
     * @param blobUrl - The complete Azure Blob Storage URL
     * @returns Promise that resolves to the parsed JSON object
     */
    public async downloadJson(blobUrl: string): Promise<any> {
        try {
            if (!this.blobServiceClient) {
                throw new Error('Azure Blob Service not initialized');
            }

            // Parse the blob URL to extract container name and blob name
            const urlParts = blobUrl.split('.blob.core.windows.net/');
            if (urlParts.length !== 2) {
                throw new Error('Invalid Azure Blob Storage URL format');
            }

            const pathAfterDomain = urlParts[1];
            const pathSegments = pathAfterDomain.split('/');
            
            if (pathSegments.length < 2) {
                throw new Error('Invalid Azure Blob Storage URL: missing container or blob name');
            }

            const containerName = pathSegments[0];
            const blobName = pathSegments.slice(1).join('/');

            logger.info(`Downloading JSON from ${blobUrl}`);

            // Get container client
            const containerClient = this.blobServiceClient.getContainerClient(containerName);
            
            // Get block blob client
            const blockBlobClient: BlockBlobClient = containerClient.getBlockBlobClient(blobName);

            // Download the blob content
            const downloadResponse = await blockBlobClient.download(0);
            const content = await this.streamToBuffer(downloadResponse.readableStreamBody!);
            const jsonString = content.toString('utf-8');
            const jsonObject = JSON.parse(jsonString);

            logger.info(`Successfully downloaded and parsed JSON from ${blobUrl}`);
            return jsonObject;
        } catch (error) {
            const errorMessage = error instanceof Error ? error.message : String(error);
            logger.error(`Failed to download JSON from ${blobUrl}:`, error);
            throw new Error(`JSON download failed: ${errorMessage}`);
        }
    }

    /**
     * Helper method to convert a readable stream to a buffer
     */
    private async streamToBuffer(readableStream: NodeJS.ReadableStream): Promise<Buffer> {
        return new Promise((resolve, reject) => {
            const chunks: Buffer[] = [];
            readableStream.on('data', (data: Buffer) => {
                chunks.push(data);
            });
            readableStream.on('end', () => {
                resolve(Buffer.concat(chunks));
            });
            readableStream.on('error', reject);
        });
    }
} 