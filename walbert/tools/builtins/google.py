"""
Google tools - Google services via Google API with OAuth.
Requires: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
"""

import os
import json
import logging
from typing import Dict, Any

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
        
        # Check if we have a token file
        creds = None
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, _get_oauth_scopes())
        
        # If no valid credentials, try to use client secrets
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
            
            # Save credentials
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
    """Interactive OAuth initialization - called from CLI."""
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


def search(query: str, num: int = 5, **kwargs) -> str:
    """Search Google using Custom Search API."""
    try:
        from googleapiclient.discovery import build
        
        api_key = os.environ.get("GOOGLE_API_KEY")
        cx = os.environ.get("GOOGLE_CX")
        
        if not api_key or not cx:
            return "Google Search requires GOOGLE_API_KEY and GOOGLE_CX environment variables. Get them at https://developers.google.com/custom-search/v1/introduction"
        
        service = build("customsearch", "v1", developerKey=api_key)
        res = service.cse().list(q=query, cx=cx, num=num).execute()
        
        if "items" not in res:
            return "No results found."
        
        results = []
        for i, item in enumerate(res["items"], 1):
            results.append(f"  {i}. {item.get('title', 'No title')}")
            results.append(f"     {item.get('link', 'N/A')}")
            snippet = item.get('snippet', '')
            if len(snippet) > 200:
                snippet = snippet[:200] + "..."
            results.append(f"     {snippet}")
            results.append("")
        
        return f"# Google Search: {query}\n" + "\n".join(results)
    except Exception as e:
        return f"Error searching Google: {e}"


def gmail_read(max_results: int = 10, label_ids: str = "INBOX", query: str = "", **kwargs) -> str:
    """Read Gmail messages via Google API."""
    try:
        from googleapiclient.discovery import build
        
        creds, err = _get_google_credentials()
        if err:
            return f"Google OAuth not ready: {err}"
        
        service = build("gmail", "v1", credentials=creds)
        
        # Build query
        gmail_query = query
        if label_ids and label_ids != "INBOX":
            gmail_query = f"label:{label_ids}" + (" " + query if query else "")
        elif label_ids == "INBOX":
            gmail_query = query if query else "in:inbox"
        
        results = service.users().messages().list(
            userId="me",
            q=gmail_query,
            maxResults=max_results
        ).execute()
        
        messages = results.get("messages", [])
        if not messages:
            return f"No Gmail messages found matching: {gmail_query or 'in:inbox'}"
        
        output = []
        for msg_summary in messages:
            msg = service.users().messages().get(
                userId="me",
                id=msg_summary["id"],
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"]
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
        
        return f"# Gmail: {len(output)//4} messages\n" + "\n".join(output)
    except Exception as e:
        return f"Error reading Gmail: {e}"


def gmail_send(to: str, subject: str, body: str, html: str = "", **kwargs) -> str:
    """Send email via Gmail API."""
    try:
        from googleapiclient.discovery import build
        from email.mime.text import MIMEText
        import base64
        
        creds, err = _get_google_credentials()
        if err:
            return f"Google OAuth not ready: {err}"
        
        service = build("gmail", "v1", credentials=creds)
        
        # Build message
        if html:
            msg = MIMEText(f"{body}\n\n{html}", "html")
        else:
            msg = MIMEText(body, "plain")
        
        msg["to"] = to
        msg["subject"] = subject
        msg["from"] = "me"
        
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        
        sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
        
        return f"Email sent successfully. Message ID: {sent['id']}"
    except Exception as e:
        return f"Error sending email via Gmail: {e}"


def calendar_list(max_results: int = 10, time_min: str = "", **kwargs) -> str:
    """List upcoming Google Calendar events."""
    try:
        from googleapiclient.discovery import build
        from datetime import datetime, timezone
        
        creds, err = _get_google_credentials()
        if err:
            return f"Google OAuth not ready: {err}"
        
        service = build("calendar", "v3", credentials=creds)
        
        now = datetime.now(timezone.utc).isoformat() if not time_min else time_min
        
        events_result = service.events().list(
            calendarId="primary",
            timeMin=now,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime"
        ).execute()
        
        events = events_result.get("items", [])
        if not events:
            return "No upcoming calendar events."
        
        output = []
        for event in events:
            start = event.get("start", {}).get("dateTime", event.get("start", {}).get("date", "N/A"))
            end = event.get("end", {}).get("dateTime", event.get("end", {}).get("date", "N/A"))
            summary = event.get("summary", "(No title)")
            location = event.get("location", "")
            output.append(f"  {start} - {end}: {summary}")
            if location:
                output.append(f"    Location: {location}")
        
        return f"# Google Calendar ({len(events)} upcoming events)\n" + "\n".join(output)
    except Exception as e:
        return f"Error listing calendar events: {e}"


def calendar_create(summary: str, start_time: str, end_time: str, description: str = "", attendees: str = "", **kwargs) -> str:
    """Create a Google Calendar event."""
    try:
        from googleapiclient.discovery import build
        
        creds, err = _get_google_credentials()
        if err:
            return f"Google OAuth not ready: {err}"
        
        service = build("calendar", "v3", credentials=creds)
        
        event = {
            "summary": summary,
            "start": {"dateTime": start_time},
            "end": {"dateTime": end_time},
        }
        if description:
            event["description"] = description
        if attendees:
            event["attendees"] = [{"email": a.strip()} for a in attendees.split(",")]
        
        created = service.events().insert(calendarId="primary", body=event).execute()
        
        return f"Calendar event created: {created.get('htmlLink', 'N/A')}\nTitle: {summary}\nStart: {start_time}\nEnd: {end_time}"
    except Exception as e:
        return f"Error creating calendar event: {e}"


def drive_list(max_results: int = 20, q: str = "", **kwargs) -> str:
    """List files in Google Drive."""
    try:
        from googleapiclient.discovery import build
        
        creds, err = _get_google_credentials()
        if err:
            return f"Google OAuth not ready: {err}"
        
        service = build("drive", "v3", credentials=creds)
        
        query = q or "trashed=false"
        
        results = service.files().list(
            pageSize=max_results,
            q=query,
            fields="files(id, name, mimeType, modifiedTime, size, parents)"
        ).execute()
        
        files = results.get("files", [])
        if not files:
            return "No files found in Google Drive."
        
        output = []
        for f in files:
            size = f.get("size", "N/A")
            if size and size != "N/A":
                try:
                    size = f"{int(size) / 1024 / 1024:.1f} MB"
                except:
                    pass
            output.append(f"  {f['name']} | {f.get('mimeType', 'file')} | {size} | Modified: {f.get('modifiedTime', 'N/A')}")
        
        return f"# Google Drive ({len(files)} files)\n" + "\n".join(output)
    except Exception as e:
        return f"Error listing Google Drive files: {e}"


def drive_upload(file_path: str, name: str = "", parents: str = "", **kwargs) -> str:
    """Upload a local file to Google Drive."""
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        
        creds, err = _get_google_credentials()
        if err:
            return f"Google OAuth not ready: {err}"
        
        if not os.path.exists(file_path):
            return f"Error: File not found: {file_path}"
        
        service = build("drive", "v3", credentials=creds)
        
        upload_name = name or os.path.basename(file_path)
        media = MediaFileUpload(file_path, mimetype="application/octet-stream")
        
        body = {"name": upload_name}
        if parents:
            body["parents"] = [parents]
        
        created = service.files().create(body=body, media_body=media, fields="id, name, webViewLink").execute()
        
        return f"File uploaded to Google Drive:\n  Name: {created.get('name')}\n  ID: {created.get('id')}\n  Link: {created.get('webViewLink', 'N/A')}"
    except Exception as e:
        return f"Error uploading to Google Drive: {e}"
