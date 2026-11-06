"""
OCI Email Delivery Handler

Uses Oracle Cloud Infrastructure Email Delivery service for transactional and bulk email.
Reads configuration from SystemConfig (database) with environment variable fallback.
Supports both Instance Principals (Oracle VMs) and config file authentication.
"""

import logging
from flask import current_app
from . import BaseChannelHandler

logger = logging.getLogger(__name__)


class OCIEmailHandler(BaseChannelHandler):
    """Email handler for OCI Email Delivery REST API."""
    channel_name = 'oci_email'

    def __init__(self):
        self.region = self._get_config('OCI_EMAIL_REGION', 'eu-frankfurt-1')
        self.compartment_id = self._get_config('OCI_EMAIL_COMPARTMENT_ID')
        self.sender = self._get_config('OCI_EMAIL_SENDER_ADDRESS', 'noreply@pamoja.space')
        self.use_suppression = self._get_config('OCI_EMAIL_SUPPRESSION_LIST', True, 'bool')
        # Credential resolution can perform network I/O against OCI instance
        # metadata. Keep it lazy so importing notifications never blocks app
        # startup on non-OCI hosts or in tests without OCI configuration.
        self._email_client = None

    def _get_config(self, key: str, default=None, value_type: str = 'str'):
        """Read from SystemConfig (DB) first, then env, then default."""
        try:
            from app.models.system_config import SystemConfig
            val = SystemConfig.get(key)
            if val is not None:
                return val
        except Exception:
            pass

        import os
        env_val = os.getenv(key)
        if env_val is not None:
            if value_type == 'bool':
                return env_val.lower() in ('true', '1', 'yes', 'on')
            if value_type == 'int':
                try:
                    return int(env_val)
                except ValueError:
                    return default
            return env_val
        return default

    def _init_client(self):
        """Initialize OCI Email client with appropriate authentication."""
        # Quick check: are we on Oracle Cloud? Try metadata service with 2s timeout
        on_oracle_cloud = self._check_oracle_metadata()
        
        if on_oracle_cloud:
            try:
                import oci
                self.signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
                self.config = {'region': self.region}
                self._email_client = oci.email.EmailClient(self.config, signer=self.signer)
                logger.info("[OCI Email] Using Instance Principals authentication")
                return
            except Exception as e:
                logger.warning(f"[OCI Email] Instance Principals failed, falling back: {e}")
        
        # Fallback: config file authentication
        try:
            import oci
            self.config = oci.config.from_file()
            self._email_client = oci.email.EmailClient(self.config)
            logger.info("[OCI Email] Using config file authentication")
        except Exception as e2:
            logger.error(f"[OCI Email] Failed to initialize client: {e2}")
            self._email_client = None
    
    def _check_oracle_metadata(self) -> bool:
        """Return True only when OCI's authenticated instance metadata is valid.

        A TCP listener on 169.254.169.254 is not proof of an OCI instance:
        other cloud runners also expose link-local metadata services. Confirm
        the OCI v2 endpoint and its authenticated response before asking the
        OCI SDK to construct an Instance Principals signer.
        """
        import json
        from urllib.error import HTTPError, URLError
        from urllib.request import Request, urlopen

        request = Request(
            "http://169.254.169.254/opc/v2/instance/",
            headers={"Authorization": "Bearer Oracle"},
            method="GET",
        )
        try:
            with urlopen(request, timeout=1.5) as response:
                if getattr(response, "status", 200) != 200:
                    return False
                payload = json.loads(response.read(65536).decode("utf-8"))
            return (
                isinstance(payload, dict)
                and bool(payload.get("id"))
                and bool(payload.get("region"))
            )
        except (HTTPError, URLError, OSError, ValueError, UnicodeDecodeError):
            return False

    @property
    def email_client(self):
        # No compartment means OCI email is not configured. Do not probe
        # instance metadata or require a local OCI config file in that case.
        if self._email_client is None and self.compartment_id:
            self._init_client()
        return self._email_client

    def validate_recipient(self, recipient: dict) -> bool:
        email = recipient.get('email')
        return bool(email and '@' in email)

    def deliver(self, notification, recipient: dict) -> dict:
        to_email = recipient.get('email')
        if not to_email:
            return {'success': False, 'response_code': 400, 'response_body': 'No recipient email'}

        if not self.compartment_id:
            return {
                'success': False,
                'response_code': 500,
                'response_body': 'OCI_EMAIL_COMPARTMENT_ID not configured (set in /admin/settings/system)'
            }

        if self.email_client is None:
            return {
                'success': False,
                'response_code': 500,
                'response_body': 'OCI Email client not initialized (check authentication)'
            }

        subject = notification.subject or 'Notification'
        body_text = notification.body or ''
        body_html = getattr(notification, 'html_body', None) or body_text

        try:
            import oci
            import requests
            import json
            from oci.signer import Signer
            
            # Use REST API directly (OCI SDK v2.x removed send_email)
            # Endpoint: POST https://email.{region}.oci.oraclecloud.com/20170907/actions/sendEmail
            
            endpoint = f"https://email.{self.region}.oci.oraclecloud.com/20170907/actions/sendEmail"
            
            payload = {
                "compartmentId": self.compartment_id,
                "sender": self.sender,
                "recipients": [to_email],
                "subject": subject,
                "bodyText": body_text,
                "bodyHtml": body_html
            }
            
            # Sign request using OCI signer
            if hasattr(self, 'signer') and self.signer:
                signer = self.signer
            else:
                # Config file auth
                config = oci.config.from_file()
                signer = Signer(
                    tenancy=config["tenancy"],
                    user=config["user"],
                    fingerprint=config["fingerprint"],
                    private_key_file_location=config["key_file"],
                    pass_phrase=config.get("pass_phrase")
                )
            
            # Prepare request
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            # Prepare request for signing
            import requests
            req = requests.Request(
                method='POST',
                url=endpoint,
                headers=headers,
                json=payload
            )
            prepped = req.prepare()
            
            # Sign the request
            signed = signer.do_request_sign(prepped)
            
            # Send signed request
            session = requests.Session()
            response = session.send(signed, timeout=30)
            
        except oci.exceptions.ServiceError as e:
            logger.error(f"[OCI Email] Failed to {to_email}: {e.code} - {e.message}")
            return {
                'success': False,
                'response_code': e.status,
                'response_body': f"{e.code}: {e.message}"
            }
        except Exception as e:
            logger.error(f"[OCI Email] Unexpected error: {e}")
            return {
                'success': False,
                'response_code': 500,
                'response_body': str(e)
            }