"""
Genesis Protocol - Email Service

Supports multiple email providers:
- Console (development/debug)
- SMTP (generic)
- SendGrid
- Mailgun
- AWS SES

Configure via environment variables:
- EMAIL_PROVIDER: console|smtp|sendgrid|mailgun|ses
- SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD (for SMTP)
- SENDGRID_API_KEY (for SendGrid)
- MAILGUN_API_KEY, MAILGUN_DOMAIN (for Mailgun)
- AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SES_REGION (for SES)
- FROM_EMAIL: sender email address
"""

import os
import sys
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict

logger = logging.getLogger(__name__)


class EmailService:
    """Email service with multiple provider support."""
    
    def __init__(self):
        self.provider = os.environ.get('EMAIL_PROVIDER', 'console').lower()
        self.from_email = os.environ.get('FROM_EMAIL', 'noreply@genesis.ai')
        self.from_name = os.environ.get('FROM_NAME', 'Genesis AI')
        self._init_provider()
    
    def _init_provider(self):
        """Initialize email provider."""
        providers = {
            'console': self._init_console,
            'smtp': self._init_smtp,
            'sendgrid': self._init_sendgrid,
            'mailgun': self._init_mailgun,
            'ses': self._init_ses
        }
        
        init_func = providers.get(self.provider, self._init_console)
        init_func()
        
        logger.info(f"Email service initialized with provider: {self.provider}")
    
    def _init_console(self):
        """Console logger (development)."""
        self._send_method = self._send_console
        logger.info("Email provider: Console (logs to console)")
    
    def _init_smtp(self):
        """SMTP configuration."""
        self.smtp_host = os.environ.get('SMTP_HOST', 'localhost')
        self.smtp_port = int(os.environ.get('SMTP_PORT', '587'))
        self.smtp_user = os.environ.get('SMTP_USER', '')
        self.smtp_password = os.environ.get('SMTP_PASSWORD', '')
        self.smtp_tls = os.environ.get('SMTP_TLS', 'true').lower() == 'true'
        self._send_method = self._send_smtp
        logger.info(f"Email provider: SMTP ({self.smtp_host}:{self.smtp_port})")
    
    def _init_sendgrid(self):
        """SendGrid configuration."""
        self.sendgrid_api_key = os.environ.get('SENDGRID_API_KEY', '')
        self._send_method = self._send_sendgrid
        logger.info("Email provider: SendGrid")
    
    def _init_mailgun(self):
        """Mailgun configuration."""
        self.mailgun_api_key = os.environ.get('MAILGUN_API_KEY', '')
        self.mailgun_domain = os.environ.get('MAILGUN_DOMAIN', '')
        self._send_method = self._send_mailgun
        logger.info(f"Email provider: Mailgun ({self.mailgun_domain})")
    
    def _init_ses(self):
        """AWS SES configuration."""
        self.aws_region = os.environ.get('AWS_SES_REGION', 'us-east-1')
        self._send_method = self._send_ses
        logger.info(f"Email provider: AWS SES ({self.aws_region})")
    
    def send(self, to_email: str, subject: str, html_content: str, 
             text_content: str = None) -> bool:
        """
        Send email to recipient.
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML body
            text_content: Plain text body (optional)
        
        Returns:
            True if sent successfully
        """
        try:
            result = self._send_method(to_email, subject, html_content, text_content)
            if result:
                logger.info(f"Email sent to {to_email}: {subject}")
            return result
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return False
    
    def _send_console(self, to_email: str, subject: str, 
                      html_content: str, text_content: str) -> bool:
        """Log email to console (development)."""
        print("\n" + "="*60)
        print(f"📧 EMAIL (Development Mode)")
        print("="*60)
        print(f"To: {to_email}")
        print(f"From: {self.from_name} <{self.from_email}>")
        print(f"Subject: {subject}")
        print("-"*60)
        print(f"Body:\n{text_content or html_content[:200]}")
        print("="*60 + "\n")
        return True
    
    def _send_smtp(self, to_email: str, subject: str,
                   html_content: str, text_content: str) -> bool:
        """Send via SMTP."""
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"{self.from_name} <{self.from_email}>"
        msg['To'] = to_email
        
        if text_content:
            msg.attach(MIMEText(text_content, 'plain'))
        msg.attach(MIMEText(html_content, 'html'))
        
        with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
            if self.smtp_tls:
                server.starttls()
            if self.smtp_user and self.smtp_password:
                server.login(self.smtp_user, self.smtp_password)
            server.send_message(msg)
        
        return True
    
    def _send_sendgrid(self, to_email: str, subject: str,
                       html_content: str, text_content: str) -> bool:
        """Send via SendGrid API."""
        import urllib.request
        import json
        
        data = {
            "personalizations": [{"to": [{"email": to_email}]}],
            "from": {"email": self.from_email, "name": self.from_name},
            "subject": subject,
            "content": [
                {"type": "text/plain", "value": text_content or html_content},
                {"type": "text/html", "value": html_content}
            ]
        }
        
        req = urllib.request.Request(
            "https://api.sendgrid.com/v3/mail/send",
            data=json.dumps(data).encode(),
            headers={
                "Authorization": f"Bearer {self.sendgrid_api_key}",
                "Content-Type": "application/json"
            },
            method="POST"
        )
        
        with urllib.request.urlopen(req) as response:
            return response.status == 202
    
    def _send_mailgun(self, to_email: str, subject: str,
                      html_content: str, text_content: str) -> bool:
        """Send via Mailgun API."""
        import urllib.request
        import urllib.parse
        
        data = urllib.parse.urlencode({
            "from": f"{self.from_name} <{self.from_email}>",
            "to": to_email,
            "subject": subject,
            "text": text_content or html_content,
            "html": html_content
        }).encode()
        
        req = urllib.request.Request(
            f"https://api.mailgun.net/v3/{self.mailgun_domain}/messages",
            data=data,
            headers={"Authorization": f"Basic api:{self.mailgun_api_key}"},
            method="POST"
        )
        
        with urllib.request.urlopen(req) as response:
            return response.status == 200
    
    def _send_ses(self, to_email: str, subject: str,
                  html_content: str, text_content: str) -> bool:
        """Send via AWS SES."""
        try:
            import boto3
            client = boto3.client('ses', region_name=self.aws_region)
            client.send_email(
                Source=f"{self.from_name} <{self.from_email}>",
                Destination={'ToAddresses': [to_email]},
                Message={
                    'Subject': {'Data': subject, 'Charset': 'UTF-8'},
                    'Body': {
                        'Text': {'Data': text_content or html_content, 'Charset': 'UTF-8'},
                        'Html': {'Data': html_content, 'Charset': 'UTF-8'}
                    }
                }
            )
            return True
        except ImportError:
            logger.error("boto3 not installed. Install with: pip install boto3")
            return False
    
    # ============ Template Methods ============
    
    def send_verification_email(self, to_email: str, username: str, 
                                verification_url: str) -> bool:
        """Send email verification email."""
        subject = "Verify your Genesis AI account"
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; background: #0a0a0f; color: #fff; padding: 40px; }}
                .container {{ max-width: 600px; margin: 0 auto; background: #1a1a24; border-radius: 16px; padding: 40px; }}
                h1 {{ color: #6366f1; }}
                .btn {{ display: inline-block; background: #6366f1; color: white; padding: 14px 28px; 
                       text-decoration: none; border-radius: 8px; margin: 20px 0; }}
                .footer {{ color: #888; font-size: 12px; margin-top: 30px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>⚡ Verify Your Email</h1>
                <p>Hi {username},</p>
                <p>Thank you for registering with Genesis AI! Please verify your email address by clicking the button below:</p>
                <a href="{verification_url}" class="btn">Verify Email</a>
                <p>Or copy this link: <code>{verification_url}</code></p>
                <p>This link expires in 24 hours.</p>
                <div class="footer">
                    <p>Genesis Protocol v3.0 - Multi-LLM AI Platform</p>
                </div>
            </div>
        </body>
        </html>
        """
        text = f"Hi {username},\n\nVerify your Genesis AI account: {verification_url}\n\nLink expires in 24 hours."
        return self.send(to_email, subject, html, text)
    
    def send_password_reset_email(self, to_email: str, username: str,
                                  reset_url: str) -> bool:
        """Send password reset email."""
        subject = "Reset your Genesis AI password"
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; background: #0a0a0f; color: #fff; padding: 40px; }}
                .container {{ max-width: 600px; margin: 0 auto; background: #1a1a24; border-radius: 16px; padding: 40px; }}
                h1 {{ color: #f59e0b; }}
                .btn {{ display: inline-block; background: #f59e0b; color: #000; padding: 14px 28px; 
                       text-decoration: none; border-radius: 8px; margin: 20px 0; }}
                .footer {{ color: #888; font-size: 12px; margin-top: 30px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🔑 Password Reset Request</h1>
                <p>Hi {username},</p>
                <p>We received a request to reset your password. Click the button below to set a new password:</p>
                <a href="{reset_url}" class="btn">Reset Password</a>
                <p>Or copy this link: <code>{reset_url}</code></p>
                <p><strong>Security Notice:</strong> This link expires in 1 hour. If you didn't request this, please ignore this email.</p>
                <div class="footer">
                    <p>Genesis Protocol v3.0 - Multi-LLM AI Platform</p>
                </div>
            </div>
        </body>
        </html>
        """
        text = f"Hi {username},\n\nReset your password: {reset_url}\n\nThis link expires in 1 hour."
        return self.send(to_email, subject, html, text)
    
    def send_welcome_email(self, to_email: str, username: str) -> bool:
        """Send welcome email after verification."""
        subject = "Welcome to Genesis AI!"
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; background: #0a0a0f; color: #fff; padding: 40px; }}
                .container {{ max-width: 600px; margin: 0 auto; background: #1a1a24; border-radius: 16px; padding: 40px; }}
                h1 {{ color: #22c55e; }}
                .btn {{ display: inline-block; background: #6366f1; color: white; padding: 14px 28px; 
                       text-decoration: none; border-radius: 8px; margin: 20px 0; }}
                .footer {{ color: #888; font-size: 12px; margin-top: 30px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🎉 Welcome to Genesis AI!</h1>
                <p>Hi {username},</p>
                <p>Your account has been verified. You're now ready to experience the future of AI assistance!</p>
                <p><strong>Features include:</strong></p>
                <ul>
                    <li>⚡ Multi-LLM Intelligence (GPT-4, Claude, Gemini)</li>
                    <li>📋 Autonomous Task Planning</li>
                    <li>🔧 Tool Usage & Web Search</li>
                    <li>💾 Long-term Memory</li>
                    <li>🎤 Voice Assistant</li>
                </ul>
                <a href="#" class="btn">Start Chatting</a>
                <div class="footer">
                    <p>Genesis Protocol v3.0 - Multi-LLM AI Platform</p>
                </div>
            </div>
        </body>
        </html>
        """
        text = f"Welcome to Genesis AI, {username}!\n\nYour account is verified. Start chatting now!"
        return self.send(to_email, subject, html, text)


# Singleton
_email_service: Optional[EmailService] = None


def get_email_service() -> EmailService:
    """Get email service singleton."""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service