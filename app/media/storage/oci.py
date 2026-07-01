# app/media/storage/oci.py

import boto3
from botocore.client import Config as BotoConfig


class OCIStorageBackend(StorageBackend):
    """
    Oracle Cloud Object Storage via S3-compatible API.
    Uses boto3 with OCI endpoint.
    """

    def _get_client(self):
        from flask import current_app
        cfg = current_app.config
        return boto3.client(
            's3',
            region_name=cfg['OCI_REGION'],
            endpoint_url=cfg['OCI_ENDPOINT_URL'],
            aws_access_key_id=cfg['OCI_ACCESS_KEY'],
            aws_secret_access_key=cfg['OCI_SECRET_KEY'],
            config=BotoConfig(signature_version='s3')
        )

    def save(self, file_obj, storage_key: str, content_type: str) -> str:
        from flask import current_app
        client = self._get_client()
        bucket = current_app.config['OCI_BUCKET_NAME']
        client.upload_fileobj(
            file_obj,
            bucket,
            storage_key,
            ExtraArgs={
                'ContentType': content_type,
                'ACL': 'public-read'  # Accommodation photos are public
            }
        )
        cdn_base = current_app.config.get('CDN_BASE_URL', '')
        if cdn_base:
            return f"{cdn_base}/{storage_key}"
        return f"{current_app.config['OCI_ENDPOINT_URL']}/{bucket}/{storage_key}"

    def delete(self, storage_key: str) -> bool:
        from flask import current_app
        client = self._get_client()
        client.delete_object(
            Bucket=current_app.config['OCI_BUCKET_NAME'],
            Key=storage_key
        )
        return True

    def get_url(self, storage_key: str, expires_in: int = None) -> str:
        from flask import current_app
        if expires_in:
            # Signed URL for private content (KYC docs)
            client = self._get_client()
            return client.generate_presigned_url(
                'get_object',
                Params={'Bucket': current_app.config['OCI_BUCKET_NAME'], 'Key': storage_key},
                ExpiresIn=expires_in
            )
        cdn_base = current_app.config.get('CDN_BASE_URL', '')
        bucket = current_app.config['OCI_BUCKET_NAME']
        endpoint = current_app.config['OCI_ENDPOINT_URL']
        base = cdn_base if cdn_base else f"{endpoint}/{bucket}"
        return f"{base}/{storage_key}"

    def exists(self, storage_key: str) -> bool:
        from flask import current_app
        try:
            client = self._get_client()
            client.head_object(
                Bucket=current_app.config['OCI_BUCKET_NAME'],
                Key=storage_key
            )
            return True
        except Exception:
            return False

    def get_raw(self, storage_key: str):
        from flask import current_app
        client = self._get_client()
        bucket = current_app.config['OCI_BUCKET_NAME']
        obj = client.get_object(Bucket=bucket, Key=storage_key)
        return obj['Body']
