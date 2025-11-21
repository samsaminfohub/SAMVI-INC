import os
from minio import Minio
from minio.error import S3Error
import streamlit as st

class MinioHandler:
    def __init__(self):
        self.client = Minio(
            os.getenv("MINIO_ENDPOINT", "localhost:9000"),
            access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
            secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
            secure=False
        )
        self.bucket_name = "documents"

    def ensure_bucket_exists(self):
        """Ensure the documents bucket exists"""
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                st.info(f"Created bucket: {self.bucket_name}")
        except S3Error as e:
            st.error(f"MinIO Error: {e}")

    def list_files(self):
        """List all PDF files in the bucket"""
        try:
            objects = self.client.list_objects(self.bucket_name, recursive=True)
            return [obj.object_name for obj in objects if obj.object_name.endswith('.pdf')]
        except S3Error as e:
            st.error(f"Error listing files: {e}")
            return []

    def download_file(self, object_name, file_path):
        """Download a file from MinIO to local path"""
        try:
            self.client.fget_object(self.bucket_name, object_name, file_path)
            return True
        except S3Error as e:
            st.error(f"Error downloading {object_name}: {e}")
            return False

    def upload_file(self, file_path, object_name):
        """Upload a local file to MinIO"""
        try:
            self.client.fput_object(self.bucket_name, object_name, file_path)
            return True
        except S3Error as e:
            st.error(f"Error uploading {object_name}: {e}")
            return False
