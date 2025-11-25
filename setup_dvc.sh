#!/bin/bash

# Initialize DVC if not already initialized
if [ ! -d ".dvc" ]; then
    echo "Initializing DVC..."
    dvc init --no-scm
else
    echo "DVC already initialized."
fi

# Configure MinIO remote
echo "Configuring MinIO remote..."
# We use the 'documents' bucket but a subfolder 'dvc-storage' to avoid cluttering the raw files
dvc remote add -d minio s3://documents/dvc-storage -f

# Configure endpoint
# Note: When running inside Docker, use 'http://minio:9000'
# If running locally, you might need 'http://localhost:9000'
dvc remote modify minio endpointurl http://minio:9000

dvc remote modify minio access_key_id minioadmin
dvc remote modify minio secret_access_key minioadmin
dvc remote modify minio use_ssl false

echo "DVC configuration complete."
echo "Remote 'minio' set to 's3://documents/dvc-storage'."
echo "You can now use 'dvc add documents/' to track your documents."
