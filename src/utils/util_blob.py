from azure.storage.blob import BlobServiceClient, BlobClient
import os
import traceback
import re
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv("app.env")) 
import json
from log_config.logger import logger

try:
    STORAGE_ACCOUNT_NAME = os.environ.get("STORAGE_ACCOUNT_NAME")
    STORAGE_ACCOUNT_KEY = os.environ.get("STORAGE_ACCOUNT_KEY")
    FILE_UPLOADS_CONTAINER_NAME = os.environ.get("CONTAINER_NAME")

    connection_string = f"DefaultEndpointsProtocol=https;AccountName={STORAGE_ACCOUNT_NAME};AccountKey={STORAGE_ACCOUNT_KEY};EndpointSuffix=core.windows.net"

    blob_service_client = BlobServiceClient.from_connection_string(connection_string)

    container_client = blob_service_client.get_container_client(FILE_UPLOADS_CONTAINER_NAME)
except Exception as e:
    logger.error(f"An error occurred: {str(e)}")
    logger.error(traceback.format_exc())

def upload_blob(file_path, folder_name, file_name):
    """
    Uploads a file to blob storage.
    Args:
        file_path: Local file path.
        folder_name: Folder name in blob storage.
        file_name: File name in blob storage.
    Returns:
        Blob URL of the uploaded file.
    """
    try:
        #Check if the file exists
        if not os.path.exists(file_path):
            return "File not found"

        blob_client = container_client.get_blob_client(f'{folder_name}/{file_name}')
        with open(file_path, "rb") as data:
            blob_client.upload_blob(data, overwrite=True)
        
        # Return URL with proper path structure
        url_path = f'{folder_name}/{file_name}'
        return f'https://{STORAGE_ACCOUNT_NAME}.blob.core.windows.net/{FILE_UPLOADS_CONTAINER_NAME}/{url_path}'
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        logger.error(traceback.format_exc())
        raise e
    
def fetch_blob(blob_url, file_path):
    """
    Fetches a file from blob storage.
    Args:
        blob_url: Blob URL of the file.
        file_path: Local file path to save the file.
    """
    try:
        blob_client = BlobClient.from_blob_url(blob_url, credential=STORAGE_ACCOUNT_KEY)
        data = blob_client.download_blob()
        with open(file_path, "wb") as f:
            f.write(data.readall())
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        logger.error(traceback.format_exc())
        raise e

def delete_blob(blob_url):
    """
    Deletes a file from blob storage.
    Args:
        blob_url: Blob URL of the file.
    """
    try:
        blob_client = BlobClient.from_blob_url(blob_url, credential=STORAGE_ACCOUNT_KEY)
        blob_client.delete_blob()
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        logger.error(traceback.format_exc())
        raise e


def download_blob_as_bytes(blob_url):
    """
    Downloads a file from blob storage and returns it as bytes.
    Args:
        blob_url: Blob URL of the file.
    Returns:
        Bytes content of the file, or None on error.
    """
    try:
        blob_client = BlobClient.from_blob_url(blob_url, credential=STORAGE_ACCOUNT_KEY)
        data = blob_client.download_blob()
        return data.readall()
    except Exception as e:
        logger.error(f"Error downloading blob from {blob_url}: {str(e)}")
        logger.error(traceback.format_exc())
        return None

def upload_json_blob(json_data, folder_name, file_name):
    """
    Uploads JSON data directly to blob storage.
    Args:
        json_data: Dictionary or JSON-serializable object to upload.
        folder_name: Folder name in blob storage.
        file_name: File name in blob storage.
    Returns:
        Blob URL of the uploaded file.
    """
    try:
        # Convert to JSON string and then to bytes
        json_string = json.dumps(json_data, default=str)
        json_bytes = json_string.encode('utf-8')
        
        blob_client = container_client.get_blob_client(f'{folder_name}/{file_name}')
        blob_client.upload_blob(json_bytes, overwrite=True)
        
        # Return URL with proper path structure
        url_path = f'{folder_name}/{file_name}'
        return f'https://{STORAGE_ACCOUNT_NAME}.blob.core.windows.net/{FILE_UPLOADS_CONTAINER_NAME}/{url_path}'
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        logger.error(traceback.format_exc())
        raise e