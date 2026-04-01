import { AzureBlobService } from './azureUtils';
import { logger } from './logger';

export interface UploadResult {
    url: string;
    success: boolean;
    error?: string;
}

export interface UploadOptions {
    containerName?: string;
    folderPath?: string;
    deleteAfterUpload?: boolean;
}

/**
 * Generic upload utility that abstracts file upload functionality
 * This allows components to upload files without directly depending on specific storage providers
 */
export class UploadUtils {
    private static instance: UploadUtils;
    private azureService: AzureBlobService;

    private constructor() {
        this.azureService = AzureBlobService.getInstance();
    }

    /**
     * Get the singleton instance of UploadUtils
     */
    public static getInstance(): UploadUtils {
        if (!UploadUtils.instance) {
            UploadUtils.instance = new UploadUtils();
        }
        return UploadUtils.instance;
    }

    /**
     * Upload a file to storage
     * @param fileName - Name to give the file in storage
     * @param filePath - Local path of the file to upload
     * @param options - Upload options including container, folder path, and cleanup settings
     * @returns Promise that resolves with the upload result
     */
    public async uploadFile(
        fileName: string, 
        filePath: string, 
        options: UploadOptions = {}
    ): Promise<UploadResult> {
        try {
            logger.info(`Uploading file ${filePath} as ${fileName}`);
            
            const url = await this.azureService.uploadFile(
                fileName,
                filePath,
                options.folderPath || '',
                options.containerName
            );

            logger.info(`Successfully uploaded ${fileName} to ${url}`);

            // Delete local file after upload if requested
            if (options.deleteAfterUpload) {
                try {
                    const fs = await import('fs');
                    await fs.promises.unlink(filePath);
                    logger.info(`Deleted local file ${filePath} after successful upload`);
                } catch (deleteError) {
                    logger.warn(`Failed to delete local file ${filePath} after upload:`, deleteError);
                }
            }

            return {
                url,
                success: true
            };
        } catch (error) {
            const errorMessage = error instanceof Error ? error.message : String(error);
            logger.error(`Failed to upload file ${fileName}:`, error);
            
            return {
                url: '',
                success: false,
                error: errorMessage
            };
        }
    }

    /**
     * Upload multiple files in parallel
     * @param files - Array of file upload requests
     * @returns Promise that resolves with array of upload results
     */
    public async uploadFiles(
        files: Array<{ fileName: string; filePath: string; options?: UploadOptions }>
    ): Promise<UploadResult[]> {
        const uploadPromises = files.map(file => 
            this.uploadFile(file.fileName, file.filePath, file.options)
        );
        
        return Promise.all(uploadPromises);
    }

    /**
     * Upload a trace file with standard naming and container
     * @param runId - The run ID for naming the file
     * @param tracePath - Local path of the trace file
     * @param options - Additional upload options
     * @returns Promise that resolves with the upload result
     */
    public async uploadTrace(runId: string, tracePath: string, options: UploadOptions = {}): Promise<UploadResult> {
        const fileName = `${runId}.zip`;
        return this.uploadFile(fileName, tracePath, {
            folderPath: 'trace_urls',
            deleteAfterUpload: options.deleteAfterUpload ?? true,
            ...options
        });
    }

    /**
     * Upload a GIF file with standard naming and container
     * @param runId - The run ID for naming the file
     * @param gifPath - Local path of the GIF file
     * @param options - Additional upload options
     * @returns Promise that resolves with the upload result
     */
    public async uploadGif(runId: string, gifPath: string, options: UploadOptions = {}): Promise<UploadResult> {
        const fileName = `${runId}.gif`;
        return this.uploadFile(fileName, gifPath, {
            folderPath: 'gif_urls',
            deleteAfterUpload: options.deleteAfterUpload ?? true,
            ...options
        });
    }
} 