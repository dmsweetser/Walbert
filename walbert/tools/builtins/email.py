"""
Email tools - IMAP/SMTP based email management.
Configuration is read from instance/config.json or environment variables.
"""

import imaplib
import smtplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
import os
import json
import re
from typing import List, Dict, Any

logger = logging.getLogger("walbert.tools.builtins.email")

# Default email config (override via config.json or env vars)
_DEFAULT_CONFIG = {
    "imap_host": "imap.gmail.com",
    "imap_port": 993,
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 587,
    "use_ssl": True,
}


def _get_email_config() -> Dict[str, Any]:
    """Get email configuration from config.json or environment variables."""
    config = dict(_DEFAULT_CONFIG)
    
    # Try config.json first
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "instance", "config.json")
    if not os.path.exists(config_path):
        # Try relative to CWD
        config_path = "instance/config.json"
    
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                data = json.load(f)
            email_cfg = data.get("email", {})
            if email_cfg:
                config.update(email_cfg)
        except Exception as e:
            logger.debug(f"Could not load email config from {config_path}: {e}")
    
    # Override with environment variables
    for key in ["imap_host", "imap_port", "smtp_host", "smtp_port", "use_ssl"]:
        env_val = os.environ.get(f"WALBERT_EMAIL_{key.upper()}")
        if env_val is not None:
            if key == "use_ssl":
                config[key] = env_val.lower() in ("true", "1", "yes")
            elif key in ("imap_port", "smtp_port"):
                config[key] = int(env_val)
            else:
                config[key] = env_val
    
    return config


def _get_credentials() -> tuple:
    """Get email credentials from config.json or environment variables."""
    username = os.environ.get("WALBERT_EMAIL_USERNAME")
    password = os.environ.get("WALBERT_EMAIL_PASSWORD")
    
    if not username or not password:
        config_path = "instance/config.json"
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    data = json.load(f)
                email_cfg = data.get("email", {})
                username = username or email_cfg.get("username", "")
                password = password or email_cfg.get("password", "")
            except Exception:
                pass
    
    if not username or not password:
        return None, None
    
    # Handle app passwords that might be in quotes
    password = password.strip("'\"")
    return username, password


def _connect_imap(config: Dict[str, Any]) -> imaplib.IMAP4_SSL:
    """Connect to IMAP server."""
    username, password = _get_credentials()
    if not username or not password:
        raise ValueError("Email credentials not configured. Set WALBERT_EMAIL_USERNAME and WALBERT_EMAIL_PASSWORD env vars, or add 'email' section to instance/config.json")
    
    host = config.get("imap_host", "imap.gmail.com")
    port = config.get("imap_port", 993)
    
    imap = imaplib.IMAP4_SSL(host, port)
    imap.login(username, password)
    return imap


def list_emails(mailbox: str = "INBOX", count: int = 20, search: str = "", **kwargs) -> str:
    """List emails from an IMAP mailbox."""
    try:
        config = _get_email_config()
        imap = _connect_imap(config)
        
        imap.select(mailbox, readonly=True)
        
        # Search criteria
        if search:
            status, messages = imap.search(None, search)
        else:
            status, messages = imap.search(None, 'ALL')
        
        if status != 'OK':
            imap.close()
            imap.logout()
            return f"Error: IMAP search failed"
        
        msg_nums = messages[0].split()
        if not msg_nums:
            imap.close()
            imap.logout()
            return "No emails found."
        
        # Get most recent N emails
        start = max(0, len(msg_nums) - count)
        msg_nums = msg_nums[start:]
        
        results = []
        for num in msg_nums:
            status, msg_data = imap.fetch(num, '(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])')
            if status == 'OK' and msg_data and msg_data[0]:
                raw = msg_data[0][1] if isinstance(msg_data[0][1], bytes) else msg_data[0][1].encode()
                msg = email.message_from_bytes(raw)
                subj_decoded = email.header.decode_header(msg.get('Subject', ''))
                subject = email.header.make_header(subj_decoded)
                subject = str(subject)
                frm_decoded = email.header.decode_header(msg.get('From', ''))
                frm = email.header.make_header(frm_decoded)
                frm = str(frm)
                date = msg.get('Date', 'Unknown')
                uid = num.decode()
                results.append(f"  UID {uid}: {subject[:80]} | From: {frm[:40]} | {date}")
        
        imap.close()
        imap.logout()
        
        return f"# Emails in {mailbox} (showing {len(results)} of {len(msg_nums)} total)\n" + "\n".join(results)
    except Exception as e:
        logger.error(f"Error listing emails: {e}", exc_info=True)
        return f"Error listing emails: {e}"


def read_email(uid: int, mailbox: str = "INBOX", **kwargs) -> str:
    """Read a specific email by UID."""
    try:
        config = _get_email_config()
        imap = _connect_imap(config)
        imap.select(mailbox, readonly=True)
        
        status, msg_data = imap.fetch(str(uid), '(BODY.PEEK[])')
        if status != 'OK' or not msg_data[0]:
            imap.close()
            imap.logout()
            return f"Error: Email UID {uid} not found"
        
        msg = email.message_from_bytes(msg_data[0][1])
        subject = email.header.make_header(email.header.decode_header(msg.get('Subject', '')))
        subject = str(subject)
        frm = email.header.make_header(email.header.decode_header(msg.get('From', '')))
        frm = str(frm)
        date = msg.get('Date', 'Unknown')
        to_addr = msg.get('To', 'Unknown')
        
        # Extract body
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))
                if "attachment" in content_disposition:
                    continue
                if content_type == "text/plain":
                    charset = part.get_content_charset() or 'utf-8'
                    raw_body = part.get_payload(decode=True)
                    if isinstance(raw_body, bytes):
                        body = raw_body.decode(charset, errors='replace')
                    else:
                        body = str(raw_body)
                    break
                elif content_type == "text/html" and not body:
                    charset = part.get_content_charset() or 'utf-8'
                    raw_body = part.get_payload(decode=True)
                    if isinstance(raw_body, bytes):
                        body = raw_body.decode(charset, errors='replace')
                    else:
                        body = str(raw_body)
        else:
            charset = msg.get_content_charset() or 'utf-8'
            raw_body = msg.get_payload(decode=True)
            if isinstance(raw_body, bytes):
                body = raw_body.decode(charset, errors='replace')
            else:
                body = str(raw_body)
        
        imap.close()
        imap.logout()
        
        return f"# Email UID {uid}\n# Subject: {subject}\n# From: {frm}\n# To: {to_addr}\n# Date: {date}\n\n{body}"
    except Exception as e:
        logger.error(f"Error reading email: {e}", exc_info=True)
        return f"Error reading email: {e}"


def send_email(to: str, subject: str, body: str, html: str = "", from_addr: str = "", **kwargs) -> str:
    """Send an email via SMTP."""
    try:
        config = _get_email_config()
        username, password = _get_credentials()
        if not username or not password:
            return "Error: Email credentials not configured"
        
        sender = from_addr or username
        
        msg = MIMEMultipart("alternative")
        msg["From"] = sender
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        if html:
            msg.attach(MIMEText(html, "html"))
        
        smtp_host = config.get("smtp_host", "smtp.gmail.com")
        smtp_port = config.get("smtp_port", 587)
        
        if config.get("use_ssl", True):
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
            server.starttls()
        
        server.login(username, password)
        server.sendmail(sender, [to], msg.as_string())
        server.quit()
        
        return f"Email sent successfully to {to}"
    except Exception as e:
        logger.error(f"Error sending email: {e}", exc_info=True)
        return f"Error sending email: {e}"


def search_emails(criteria: str, mailbox: str = "INBOX", **kwargs) -> str:
    """Search emails in an IMAP mailbox."""
    try:
        config = _get_email_config()
        imap = _connect_imap(config)
        imap.select(mailbox, readonly=True)
        
        status, messages = imap.search(None, criteria)
        if status != 'OK':
            imap.close()
            imap.logout()
            return f"Error: Search failed"
        
        msg_nums = messages[0].split()
        if not msg_nums:
            imap.close()
            imap.logout()
            return f"No emails matching: {criteria}"
        
        results = []
        for num in msg_nums[:50]:  # Limit to 50 results
            status, msg_data = imap.fetch(num, '(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])')
            if status == 'OK' and msg_data and msg_data[0]:
                raw = msg_data[0][1] if isinstance(msg_data[0][1], bytes) else msg_data[0][1].encode()
                msg = email.message_from_bytes(raw)
                subj_decoded = email.header.decode_header(msg.get('Subject', ''))
                subject = email.header.make_header(subj_decoded)
                subject = str(subject)
                frm_decoded = email.header.decode_header(msg.get('From', ''))
                frm = email.header.make_header(frm_decoded)
                frm = str(frm)
                date = msg.get('Date', 'Unknown')
                results.append(f"  UID {num.decode()}: {subject[:80]} | From: {frm[:40]} | {date}")
        
        imap.close()
        imap.logout()
        
        total = len(msg_nums)
        shown = min(50, total)
        return f"# Search results for '{criteria}' in {mailbox} ({total} total, showing {shown})\n" + "\n".join(results)
    except Exception as e:
        logger.error(f"Error searching emails: {e}", exc_info=True)
        return f"Error searching emails: {e}"
