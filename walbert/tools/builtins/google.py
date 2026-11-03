"""
Google tools - Google services via Google API with OAuth.

Adopted from AI-Builder engine best practices:
- Uses ToolResult for consistent return types
- Proper error handling and logging
"""

import os
import json
import logging
from typing import Dict, Any

from walbert.tools.base import BaseTool, ToolResult

logger = logging.getLogger("walbert.tools.builtins.google")

# OAuth token paths
TOKEN_DIR = "instance/google_oauth"


def _get_oauth_scopes() -> list:
    """Return the OAuth scopes needed."""
    return [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/calendar.events",
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/drive.file",
    ]


def _get_google_credentials():
    """Get Google OAuth credentials."""
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import Flow
        from google.auth.transport.requests import Request

        token_path = os.path.join(TOKEN_DIR, "google_token.json")
        client_secrets_path = os.path.join(TOKEN_DIR, "client_secret.json")

        creds = None
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, _get_oauth_scopes())

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(client_secrets_path):
                    return None, "Google OAuth not configured. Place client_secret.json in instance/google_oauth/ and run: python -c \"from walbert.tools.builtins.google import _init_oauth; _init_oauth()\""

                flow = Flow.from_client_secrets_file(
                    client_secrets_path,
                    scopes=_get_oauth_scopes(),
                    redirect_uri="http://localhost:8088/oauth2callback"
                )
                auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
                return None, f"Please authorize at: {auth_url}\n\nAfter authorizing, the token will be saved automatically."

            os.makedirs(TOKEN_DIR, exist_ok=True)
            with open(token_path, 'w') as f:
                f.write(json.dumps({
                    "token": creds.token,
                    "refresh_token": creds.refresh_token,
                    "token_uri": creds.token_uri,
                    "client_id": creds.client_id,
                    "client_secret": creds.client_secret,
                    "scopes": creds.scopes
                }))

        return creds, None
    except ImportError:
        return None, "Google API libraries not installed. Run: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
    except Exception as e:
        return None, f"Google OAuth error: {e}"


def _init_oauth():
    """Interactive OAuth initialization."""
    from google_auth_oauthlib.flow import Flow
    import webbrowser

    client_secrets_path = os.path.join(TOKEN_DIR, "client_secret.json")
    if not os.path.exists(client_secrets_path):
        print(f"Error: {client_secrets_path} not found")
        return

    flow = Flow.from_client_secrets_file(
        client_secrets_path,
        scopes=_get_oauth_scopes(),
        redirect_uri="http://localhost:8088/oauth2callback"
    )
    auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
    print(f"Opening browser for Google OAuth authorization...")
    print(f"URL: {auth_url}")
    webbrowser.open(auth_url)
    print("Paste the authorization code here: ")
    auth_code = input().strip()
    flow.fetch_token(code=auth_code)

    os.makedirs(TOKEN_DIR, exist_ok=True)
    with open(os.path.join(TOKEN_DIR, "google_token.json"), 'w') as f:
        json.dump({
            "token": flow.credentials.token,
            "refresh_token": flow.credentials.refresh_token,
            "token_uri": flow.credentials.token_uri,
            "client_id": flow.credentials.client_id,
            "client_secret": flow.credentials.client_secret,
            "scopes": flow.credentials.scopes
        }, f)
    print("OAuth credentials saved successfully!")


class GoogleSearchTool(BaseTool):
    name = "google_search"
    description = "Search Google using the Custom Search API."
    parameters = {"query": "string", "num": "string?"}

    def execute(self, params: dict) -> ToolResult:
        try:
            from googleapiclient.discovery import build

            api_key = os.environ.get("GOOGLE_API_KEY")
            cx = os.environ.get("GOOGLE_CX")

            if not api_key or not cx:
                return ToolResult(False, "", error="Google Search requires GOOGLE_API_KEY and GOOGLE_CX environment variables.")

            num = int(params.get("num", "5"))
            service = build("customsearch", "v1", developerKey=api_key)
            res = service.cse().list(q=params["query"], cx=cx, num=num).execute()

            if "items" not in res:
                return ToolResult(True, "No results found.")

            results = []
            for i, item in enumerate(res["items"], 1):
                results.append(f"  {i}. {item.get('title', 'No title')}")
                results.append(f"     {item.get('link', 'N/A')}")
                snippet = item.get('snippet', '')
                if len(snippet) > 200:
                    snippet = snippet[:200] + "..."
                results.append(f"     {snippet}")
                results.append("")

            return ToolResult(
                True, f"# Google Search: {params['query']}\n" + "\n".join(results),
                summary=f"{len(res['items'])} results for '{params['query']}'"
            )
        except Exception as e:
            return ToolResult(False, "", error=f"Error searching Google: {e}")


class GmailReadTool(BaseTool):
    name = "google_gmail_read"
    description = "Read Gmail messages via Google API (requires OAuth)."
    parameters = {"max_results": "string?", "label_ids": "string?", "query": "string?"}

    def execute(self, params: dict) -> ToolResult:
        try:
            from googleapiclient.discovery import build

            creds, err = _get_google_credentials()
            if err:
                return ToolResult(False, "", error=f"Google OAuth not ready: {err}")

            service = build("gmail", "v1", credentials=creds)

            max_results = int(params.get("max_results", "10"))
            label_ids = params.get("label_ids", "INBOX")
            query = params.get("query", "")

            gmail_query = query
            if label_ids and label_ids != "INBOX":
                gmail_query = f"label:{label_ids}" + (" " + query if query else "")
            elif label_ids == "INBOX":
                gmail_query = query if query else "in:inbox"

            results = service.users().messages().list(
                userId="me", q=gmail_query, maxResults=max_results
            ).execute()

            messages = results.get("messages", [])
            if not messages:
                return ToolResult(True, f"No Gmail messages found matching: {gmail_query or 'in:inbox'}")

            output = []
            for msg_summary in messages:
                msg = service.users().messages().get(
                    userId="me", id=msg_summary["id"],
                    format="metadata", metadataHeaders=["From", "Subject", "Date"]
                ).execute()

                headers = msg.get("payload", {}).get("headers", [])
                subject = from_addr = date = ""
                for h in headers:
                    if h["name"] == "Subject":
                        subject = h["value"][:100]
                    elif h["name"] == "From":
                        from_addr = h["value"][:60]
                    elif h["name"] == "Date":
                        date = h["value"][:40]

                output.append(f"  From: {from_addr}")
                output.append(f"  Subject: {subject}")
                output.append(f"  Date: {date}")
                output.append(f"  ID: {msg['id']}")
                output.append("")

            return ToolResult(
                True, f"# Gmail: {len(output)//4} messages\n" + "\n".join(output),
                summary=f"{len(output)//4} messages"
            )
        except Exception as e:
            return ToolResult(False, "", error=f"Error reading Gmail: {e}")


class GmailSendTool(BaseTool):
    name = "google_gmail_send"
    description = "Send an email via Gmail API (requires OAuth)."
    parameters = {"to": "string", "subject": "string", "body": "string", "html": "string?"}

    def execute(self, params: dict) -> ToolResult:
        try:
            from googleapiclient.discovery import build
            from email.mime.text import MIMEText
            import base64

            creds, err = _get_google_credentials()
            if err:
                return ToolResult(False, "", error=f"Google OAuth not ready: {err}")

            service = build("gmail", "v1", credentials=creds)

            if params.get("html"):
                msg = MIMEText(f"{params['body']}\n\n{params['html']}", "html")
            else:
                msg = MIMEText(params["body"], "plain")

            msg["to"] = params["to"]
            msg["subject"] = params["subject"]
            msg["from"] = "me"

            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()

            return ToolResult(
                True, f"Email sent successfully. Message ID: {sent['id']}",
                summary=f"Sent to {params['to']}: {params['subject']}"
            )
        except Exception as e:
            return ToolResult(False, "", error=f"Error sending email via Gmail: {e}")


class CalendarListTool(BaseTool):
    name = "google_calendar_list"
    description = "List upcoming Google Calendar events (requires OAuth)."
    parameters = {"max_results": "string?", "time_min": "string?"}

    def execute(self, params: dict) -> ToolResult:
        try:
            from googleapiclient.discovery import build
            from datetime import datetime, timezone

            creds, err = _get_google_credentials()
            if err:
                return ToolResult(False, "", error=f"Google OAuth not ready: {err}")

            service = build("calendar", "v3", credentials=creds)

            time_min = params.get("time_min", "")
            now = datetime.now(timezone.utc).isoformat() if not time_min else time_min
            max_results = int(params.get("max_results", "10"))

            events_result = service.events().list(
                calendarId="primary", timeMin=now,
                maxResults=max_results, singleEvents=True,
                orderBy="startTime"
            ).execute()

            events = events_result.get("items", [])
            if not events:
                return ToolResult(True, "No upcoming calendar events.")

            output = []
            for event in events:
                start = event.get("start", {}).get("dateTime", event.get("start", {}).get("date", "N/A"))
                end = event.get("end", {}).get("dateTime", event.get("end", {}).get("date", "N/A"))
                summary = event.get("summary", "(No title)")
                location = event.get("location", "")
                output.append(f"  {start} - {end}: {summary}")
                if location:
                    output.append(f"    Location: {location}")

            return ToolResult(
                True, f"# Google Calendar ({len(events)} upcoming events)\n" + "\n".join(output),
                summary=f"{len(events)} upcoming events"
            )
        except Exception as e:
            return ToolResult(False, "", error=f"Error listing calendar events: {e}")


class CalendarCreateTool(BaseTool):
    name = "google_calendar_create"
    description = "Create a Google Calendar event (requires OAuth)."
    parameters = {
        "summary": "string", "start_time": "string", "end_time": "string",
        "description": "string?", "attendees": "string?"
    }

    def execute(self, params: dict) -> ToolResult:
        try:
            from googleapiclient.discovery import build

            creds, err = _get_google_credentials()
            if err:
                return ToolResult(False, "", error=f"Google OAuth not ready: {err}")

            service = build("calendar", "v3", credentials=creds)

            event = {
                "summary": params["summary"],
                "start": {"dateTime": params["start_time"]},
                "end": {"dateTime": params["end_time"]},
            }
            if params.get("description"):
                event["description"] = params["description"]
            if params.get("attendees"):
                event["attendees"] = [{"email": a.strip()} for a in params["attendees"].split(",")]

            created = service.events().insert(calendarId="primary", body=event).execute()

            return ToolResult(
                True, f"Calendar event created: {created.get('htmlLink', 'N/A')}\nTitle: {params['summary']}\nStart: {params['start_time']}\nEnd: {params['end_time']}",
                summary=f"Created event: {params['summary']}"
            )
        except Exception as e:
            return ToolResult(False, "", error=f"Error creating calendar event: {e}")


class DriveListTool(BaseTool):
    name = "google_drive_list"
    description = "List files in Google Drive (requires OAuth)."
    parameters = {"max_results": "string?", "q": "string?"}

    def execute(self, params: dict) -> ToolResult:
        try:
            from googleapiclient.discovery import build

            creds, err = _get_google_credentials()
            if err:
                return ToolResult(False, "", error=f"Google OAuth not ready: {err}")

            service = build("drive", "v3", credentials=creds)

            q = params.get("q", "")
            query = q or "trashed=false"
            max_results = int(params.get("max_results", "20"))

            results = service.files().list(
                pageSize=max_results, q=query,
                fields="files(id, name, mimeType, modifiedTime, size, parents)"
            ).execute()

            files = results.get("files", [])
            if not files:
                return ToolResult(True, "No files found in Google Drive.")

            output = []
            for f in files:
                size = f.get("size", "N/A")
                if size and size != "N/A":
                    try:
                        size = f"{int(size) / 1024 / 1024:.1f} MB"
                    except:
                        pass
                output.append(f"  {f['name']} | {f.get('mimeType', 'file')} | {size} | Modified: {f.get('modifiedTime', 'N/A')}")

            return ToolResult(
                True, f"# Google Drive ({len(files)} files)\n" + "\n".join(output),
                summary=f"{len(files)} files"
            )
        except Exception as e:
            return ToolResult(False, "", error=f"Error listing Google Drive files: {e}")


class DriveUploadTool(BaseTool):
    name = "google_drive_upload"
    description = "Upload a local file to Google Drive (requires OAuth)."
    parameters = {"file_path": "string", "name": "string?", "parents": "string?"}

    def execute(self, params: dict) -> ToolResult:
        try:
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload

            creds, err = _get_google_credentials()
            if err:
                return ToolResult(False, "", error=f"Google OAuth not ready: {err}")

            if not os.path.exists(params["file_path"]):
                return ToolResult(False, "", error=f"File not found: {params['file_path']}")

            service = build("drive", "v3", credentials=creds)

            upload_name = params.get("name") or os.path.basename(params["file_path"])
            media = MediaFileUpload(params["file_path"], mimetype="application/octet-stream")

            body = {"name": upload_name}
            if params.get("parents"):
                body["parents"] = [params["parents"]]

            created = service.files().create(body=body, media_body=media, fields="id, name, webViewLink").execute()

            return ToolResult(
                True, f"File uploaded to Google Drive:\n  Name: {created.get('name')}\n  ID: {created.get('id')}\n  Link: {created.get('webViewLink', 'N/A')}",
                summary=f"Uploaded: {upload_name}"
            )
        except Exception as e:
            return ToolResult(False, "", error=f"Error uploading to Google Drive: {e}")


# ===================================================================
# Backward-compatible function wrappers
# ===================================================================

def search(query: str, num: str = "5", **kwargs) -> str:
    """Legacy wrapper for GoogleSearchTool."""
    tool = GoogleSearchTool(kwargs.get("root_dir", ""))
    result = tool.execute({"query": query, "num": num})
    return result.content if result.success else f"Error: {result.error}"


def gmail_read(max_results: str = "10", label_ids: str = "INBOX", query: str = "", **kwargs) -> str:
    """Legacy wrapper for GmailReadTool."""
    tool = GmailReadTool(kwargs.get("root_dir", ""))
    result = tool.execute({"max_results": max_results, "label_ids": label_ids, "query": query})
    return result.content if result.success else f"Error: {result.error}"


def gmail_send(to: str, subject: str, body: str, html: str = "", **kwargs) -> str:
    """Legacy wrapper for GmailSendTool."""
    tool = GmailSendTool(kwargs.get("root_dir", ""))
    result = tool.execute({"to": to, "subject": subject, "body": body, "html": html})
    return result.content if result.success else f"Error: {result.error}"


def calendar_list(max_results: str = "10", time_min: str = "", **kwargs) -> str:
    """Legacy wrapper for CalendarListTool."""
    tool = CalendarListTool(kwargs.get("root_dir", ""))
    result = tool.execute({"max_results": max_results, "time_min": time_min})
    return result.content if result.success else f"Error: {result.error}"


def calendar_create(summary: str, start_time: str, end_time: str, description: str = "", attendees: str = "", **kwargs) -> str:
    """Legacy wrapper for CalendarCreateTool."""
    tool = CalendarCreateTool(kwargs.get("root_dir", ""))
    result = tool.execute({"summary": summary, "start_time": start_time, "end_time": end_time, "description": description, "attendees": attendees})
    return result.content if result.success else f"Error: {result.error}"


def drive_list(max_results: str = "20", q: str = "", **kwargs) -> str:
    """Legacy wrapper for DriveListTool."""
    tool = DriveListTool(kwargs.get("root_dir", ""))
    result = tool.execute({"max_results": max_results, "q": q})
    return result.content if result.success else f"Error: {result.error}"


def drive_upload(file_path: str, name: str = "", parents: str = "", **kwargs) -> str:
    """Legacy wrapper for DriveUploadTool."""
    tool = DriveUploadTool(kwargs.get("root_dir", ""))
    result = tool.execute({"file_path": file_path, "name": name, "parents": parents})
    return result.content if result.success else f"Error: {result.error}"
