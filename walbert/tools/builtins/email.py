"""
Email tools - IMAP/SMTP based email management.

Adopted from AI-Builder engine best practices:
- Uses ToolResult for consistent return types
- Proper error handling and logging
"""

import imaplib
import smtplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
import os
import json
from typing import List, Dict, Any

from walbert.tools.base import BaseTool, ToolResult

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

    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "instance", "config.json")
    if not os.path.exists(config_path):
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


class ListEmailsTool(BaseTool):
    name = "email_list"
    description = "List emails from an IMAP mailbox."
    parameters = {"mailbox": "string?", "count": "string?", "search": "string?"}

    def execute(self, params: dict) -> ToolResult:
        try:
            config = _get_email_config()
            imap = _connect_imap(config)

            mailbox = params.get("mailbox", "INBOX")
            count = int(params.get("count", "20"))
            search = params.get("search", "")

            imap.select(mailbox, readonly=True)

            if search:
                status, messages = imap.search(None, search)
            else:
                status, messages = imap.search(None, 'ALL')

            if status != 'OK':
                imap.close()
                imap.logout()
                return ToolResult(False, "", error="IMAP search failed")

            msg_nums = messages[0].split()
            if not msg_nums:
                imap.close()
                imap.logout()
                return ToolResult(True, "No emails found.")

            start = max(0, len(msg_nums) - count)
            msg_nums = msg_nums[start:]

            results = []
            for num in msg_nums:
                status, msg_data = imap.fetch(num, '(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])')
                if status == 'OK' and msg_data and msg_data[0]:
                    raw = msg_data[0][1] if isinstance(msg_data[0][1], bytes) else msg_data[0][1].encode()
                    msg = email.message_from_bytes(raw)
                    subj_decoded = email.header.decode_header(msg.get('Subject', ''))
                    subject = str(email.header.make_header(subj_decoded))
                    frm_decoded = email.header.decode_header(msg.get('From', ''))
                    frm = str(email.header.make_header(frm_decoded))
                    date = msg.get('Date', 'Unknown')
                    uid = num.decode()
                    results.append(f"  UID {uid}: {subject[:80]} | From: {frm[:40]} | {date}")

            imap.close()
            imap.logout()

            return ToolResult(
                True, f"# Emails in {mailbox} (showing {len(results)} of {len(msg_nums)} total)\n" + "\n".join(results),
                summary=f"{len(results)} emails in {mailbox}"
            )
        except Exception as e:
            logger.error(f"Error listing emails: {e}", exc_info=True)
            return ToolResult(False, "", error=f"Error listing emails: {e}")


class ReadEmailTool(BaseTool):
    name = "email_read"
    description = "Read a specific email by UID from an IMAP mailbox."
    parameters = {"uid": "string", "mailbox": "string?"}

    def execute(self, params: dict) -> ToolResult:
        try:
            config = _get_email_config()
            imap = _connect_imap(config)
            mailbox = params.get("mailbox", "INBOX")
            uid = params["uid"]

            imap.select(mailbox, readonly=True)

            status, msg_data = imap.fetch(str(uid), '(BODY.PEEK[])')
            if status != 'OK' or not msg_data[0]:
                imap.close()
                imap.logout()
                return ToolResult(False, "", error=f"Email UID {uid} not found")

            msg = email.message_from_bytes(msg_data[0][1])
            subject = str(email.header.make_header(email.header.decode_header(msg.get('Subject', ''))))
            frm = str(email.header.make_header(email.header.decode_header(msg.get('From', ''))))
            date = msg.get('Date', 'Unknown')
            to_addr = msg.get('To', 'Unknown')

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

            return ToolResult(
                True, f"# Email UID {uid}\n# Subject: {subject}\n# From: {frm}\n# To: {to_addr}\n# Date: {date}\n\n{body}",
                summary=f"Read email UID {uid}: {subject[:50]}"
            )
        except Exception as e:
            logger.error(f"Error reading email: {e}", exc_info=True)
            return ToolResult(False, "", error=f"Error reading email: {e}")


class SendEmailTool(BaseTool):
    name = "email_send"
    description = "Send an email via SMTP."
    parameters = {"to": "string", "subject": "string", "body": "string", "html": "string?", "from_addr": "string?"}

    def execute(self, params: dict) -> ToolResult:
        try:
            config = _get_email_config()
            username, password = _get_credentials()
            if not username or not password:
                return ToolResult(False, "", error="Email credentials not configured")

            sender = params.get("from_addr") or username

            msg = MIMEMultipart("alternative")
            msg["From"] = sender
            msg["To"] = params["to"]
            msg["Subject"] = params["subject"]
            msg.attach(MIMEText(params["body"], "plain"))
            if params.get("html"):
                msg.attach(MIMEText(params["html"], "html"))

            smtp_host = config.get("smtp_host", "smtp.gmail.com")
            smtp_port = config.get("smtp_port", 587)

            if config.get("use_ssl", True):
                server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30)
            else:
                server = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
                server.starttls()

            server.login(username, password)
            server.sendmail(sender, [params["to"]], msg.as_string())
            server.quit()

            return ToolResult(
                True, f"Email sent successfully to {params['to']}",
                summary=f"Sent to {params['to']}: {params['subject']}"
            )
        except Exception as e:
            logger.error(f"Error sending email: {e}", exc_info=True)
            return ToolResult(False, "", error=f"Error sending email: {e}")


class SearchEmailsTool(BaseTool):
    name = "email_search"
    description = "Search emails in an IMAP mailbox by criteria."
    parameters = {"criteria": "string", "mailbox": "string?"}

    def execute(self, params: dict) -> ToolResult:
        try:
            config = _get_email_config()
            imap = _connect_imap(config)
            mailbox = params.get("mailbox", "INBOX")

            imap.select(mailbox, readonly=True)

            status, messages = imap.search(None, params["criteria"])
            if status != 'OK':
                imap.close()
                imap.logout()
                return ToolResult(False, "", error="Search failed")

            msg_nums = messages[0].split()
            if not msg_nums:
                imap.close()
                imap.logout()
                return ToolResult(True, f"No emails matching: {params['criteria']}")

            results = []
            for num in msg_nums[:50]:
                status, msg_data = imap.fetch(num, '(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])')
                if status == 'OK' and msg_data and msg_data[0]:
                    raw = msg_data[0][1] if isinstance(msg_data[0][1], bytes) else msg_data[0][1].encode()
                    msg = email.message_from_bytes(raw)
                    subj_decoded = email.header.decode_header(msg.get('Subject', ''))
                    subject = str(email.header.make_header(subj_decoded))
                    frm_decoded = email.header.decode_header(msg.get('From', ''))
                    frm = str(email.header.make_header(frm_decoded))
                    date = msg.get('Date', 'Unknown')
                    results.append(f"  UID {num.decode()}: {subject[:80]} | From: {frm[:40]} | {date}")

            imap.close()
            imap.logout()

            total = len(msg_nums)
            shown = min(50, total)
            return ToolResult(
                True, f"# Search results for '{params['criteria']}' in {mailbox} ({total} total, showing {shown})\n" + "\n".join(results),
                summary=f"{shown}/{total} results for '{params['criteria']}'"
            )
        except Exception as e:
            logger.error(f"Error searching emails: {e}", exc_info=True)
            return ToolResult(False, "", error=f"Error searching emails: {e}")


# ===================================================================
# Backward-compatible function wrappers
# ===================================================================

def list_emails(mailbox: str = "INBOX", count: str = "20", search: str = "", **kwargs) -> str:
    """Legacy wrapper for ListEmailsTool."""
    tool = ListEmailsTool(kwargs.get("root_dir", ""))
    result = tool.execute({"mailbox": mailbox, "count": count, "search": search})
    return result.content if result.success else f"Error: {result.error}"


def read_email(uid: str, mailbox: str = "INBOX", **kwargs) -> str:
    """Legacy wrapper for ReadEmailTool."""
    tool = ReadEmailTool(kwargs.get("root_dir", ""))
    result = tool.execute({"uid": uid, "mailbox": mailbox})
    return result.content if result.success else f"Error: {result.error}"


def send_email(to: str, subject: str, body: str, html: str = "", from_addr: str = "", **kwargs) -> str:
    """Legacy wrapper for SendEmailTool."""
    tool = SendEmailTool(kwargs.get("root_dir", ""))
    result = tool.execute({"to": to, "subject": subject, "body": body, "html": html, "from_addr": from_addr})
    return result.content if result.success else f"Error: {result.error}"


def search_emails(criteria: str, mailbox: str = "INBOX", **kwargs) -> str:
    """Legacy wrapper for SearchEmailsTool."""
    tool = SearchEmailsTool(kwargs.get("root_dir", ""))
    result = tool.execute({"criteria": criteria, "mailbox": mailbox})
    return result.content if result.success else f"Error: {result.error}"
