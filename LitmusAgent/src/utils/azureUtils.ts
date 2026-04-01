import { BlobServiceClient, StorageSharedKeyCredential, ContainerClient, BlockBlobClient } from '@azure/storage-blob';
import * as dotenv from 'dotenv';

// Load environment variables from .env file
dotenv.config();

// Environment variable interface
interface AzureConfig {
    AZURE_STORAGE_ACCOUNT_NAME: string;
    AZURE_STORAGE_ACCOUNT_KEY: string;
    AZURE_STORAGE_CONTAINER_NAME: string;
}

// Validate environment variables
function validateEnvConfig(): AzureConfig {
    const config: AzureConfig = {
        AZURE_STORAGE_ACCOUNT_NAME: process.env.STORAGE_ACCOUNT_NAME || '',
        AZURE_STORAGE_ACCOUNT_KEY: process.env.STORAGE_ACCOUNT_KEY || '',
        AZURE_STORAGE_CONTAINER_NAME: process.env.CONTAINER_NAME || ''
    };

    const missingVars = Object.entries(config)
        .filter(([_, value]) => !value)
        .map(([key]) => key);

    if (missingVars.length > 0) {
        throw new Error(`Missing required environment variables: ${missingVars.join(', ')}`);
    }

    return config;
}

export class AzureBlobService {
    private static instance: AzureBlobService;
    private blobServiceClient: BlobServiceClient | null = null;
    private accountName: string = '';
    private accountKey: string = '';
    private defaultContainerName: string = '';

    private constructor() {}

    /**
     * Get the singleton instance of AzureBlobService
     */
    public static getInstance(): AzureBlobService {
        if (!AzureBlobService.instance) {
            AzureBlobService.instance = new AzureBlobService();
            AzureBlobService.instance.initialize();
        }
        return AzureBlobService.instance;
    }

    /**
     * Initialize the Azure Blob Service client using environment variables
     */
    private initialize(): void {
        if (!this.blobServiceClient) {
            const config = validateEnvConfig();
            this.accountName = config.AZURE_STORAGE_ACCOUNT_NAME;
            this.accountKey = config.AZURE_STORAGE_ACCOUNT_KEY;
            this.defaultContainerName = config.AZURE_STORAGE_CONTAINER_NAME;

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
     * Get container client
     * @param containerName - Name of the container (optional, uses default from .env if not provided)
     * @returns ContainerClient instance
     */
    private getContainerClient(containerName?: string): ContainerClient {
        if (!this.blobServiceClient) {
            throw new Error('Azure Blob Service not initialized');
        }
        const targetContainer = containerName || this.defaultContainerName;
        return this.blobServiceClient.getContainerClient(targetContainer);
    }

    /**
     * Get block blob client
     * @param blobName - Name of the blob
     * @param containerName - Name of the container (optional, uses default from .env if not provided)
     * @returns BlockBlobClient instance
     */
    private getBlockBlobClient(blobName: string, containerName?: string): BlockBlobClient {
        const containerClient = this.getContainerClient(containerName);
        return containerClient.getBlockBlobClient(blobName);
    }

    /**
     * Upload a file to Azure Blob Storage
     * @param blobName - Name to give the blob in Azure
     * @param filePath - Local path of the file to upload
     * @param folderPath - Path within the container where the file should be uploaded (e.g., 'folder1/folder2/')
     * @param containerName - Name of the container (optional, uses default from .env if not provided)
     * @returns Promise that resolves with the blob URL when upload is complete
     */
    public async uploadFile(
        blobName: string, 
        filePath: string, 
        folderPath: string = '', 
        containerName?: string
    ): Promise<string> {
        try {
            // Ensure folder path ends with a slash if not empty
            const normalizedFolderPath = folderPath ? 
                (folderPath.endsWith('/') ? folderPath : `${folderPath}/`) : '';
            
            // Combine folder path with blob name
            const fullBlobPath = `${normalizedFolderPath}${blobName}`;
            
            const blockBlobClient = this.getBlockBlobClient(fullBlobPath, containerName);
            await blockBlobClient.uploadFile(filePath);
            console.log(`File ${filePath} uploaded successfully to ${fullBlobPath}`);
            return blockBlobClient.url;
        } catch (error) {
            console.error('Error uploading file to Azure Blob Storage:', error);
            throw error;
        }
    }

    /**
     * Download a file from Azure Blob Storage
     * @param blobName - Name of the blob to download
     * @param filePath - Local path where the file should be saved
     * @param containerName - Name of the container (optional, uses default from .env if not provided)
     * @returns Promise that resolves when download is complete
     */
    public async downloadFile(blobName: string, filePath: string, containerName?: string): Promise<void> {
        try {
            const blockBlobClient = this.getBlockBlobClient(blobName, containerName);
            await blockBlobClient.downloadToFile(filePath);
            console.log(`File ${blobName} downloaded successfully to ${filePath}`);
        } catch (error) {
            console.error('Error downloading file from Azure Blob Storage:', error);
            throw error;
        }
    }

    /**
     * Delete a blob from Azure Blob Storage
     * @param blobName - Name of the blob to delete
     * @param containerName - Name of the container (optional, uses default from .env if not provided)
     * @returns Promise that resolves when deletion is complete
     */
    public async deleteBlob(blobName: string, containerName?: string): Promise<void> {
        try {
            const blockBlobClient = this.getBlockBlobClient(blobName, containerName);
            await blockBlobClient.delete();
            console.log(`Blob ${blobName} deleted successfully`);
        } catch (error) {
            console.error('Error deleting blob from Azure Blob Storage:', error);
            throw error;
        }
    }

    /**
     * List all blobs in a container
     * @param containerName - Name of the container (optional, uses default from .env if not provided)
     * @returns Promise that resolves with an array of blob names
     */
    public async listBlobs(containerName?: string): Promise<string[]> {
        try {
            const containerClient = this.getContainerClient(containerName);
            const blobs: string[] = [];
            for await (const blob of containerClient.listBlobsFlat()) {
                blobs.push(blob.name);
            }
            return blobs;
        } catch (error) {
            console.error('Error listing blobs from Azure Blob Storage:', error);
            throw error;
        }
    }

    /**
     * Check if a blob exists
     * @param blobName - Name of the blob to check
     * @param containerName - Name of the container (optional, uses default from .env if not provided)
     * @returns Promise that resolves with a boolean indicating if the blob exists
     */
    public async blobExists(blobName: string, containerName?: string): Promise<boolean> {
        try {
            const blockBlobClient = this.getBlockBlobClient(blobName, containerName);
            return await blockBlobClient.exists();
        } catch (error) {
            console.error('Error checking blob existence in Azure Blob Storage:', error);
            throw error;
        }
    }
}
