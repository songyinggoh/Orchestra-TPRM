"""Quick ADC verification — Drive, Sheets, Docs."""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

def test():
    import google.auth
    from googleapiclient.discovery import build

    scopes = [
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/documents",
    ]
    creds, project = google.auth.default(scopes=scopes)
    print(f"Project : {project}")
    print(f"Account : {getattr(creds, 'client_id', 'service-account')[:30]}...")

    # Drive — list vendor folder
    drive = build("drive", "v3", credentials=creds)
    folder_id = os.environ["DRIVE_VENDOR_FOLDER_ID"]
    result = drive.files().list(
        q=f"'{folder_id}' in parents",
        pageSize=5,
        fields="files(id,name)",
    ).execute()
    files = result.get("files", [])
    print(f"\nDrive OK — {len(files)} file(s) in vendor folder:")
    for f in files:
        print(f"  {f['name']} ({f['id']})")

    # Sheets — get template metadata
    sheets = build("sheets", "v4", credentials=creds)
    sheet_id = os.environ["SHEETS_VENDOR_TEMPLATE_ID"]
    meta = sheets.spreadsheets().get(spreadsheetId=sheet_id, fields="properties/title").execute()
    print(f"\nSheets OK — template: {meta['properties']['title']}")

    # Docs — get template metadata
    docs = build("docs", "v1", credentials=creds)
    doc_id = os.environ["DOCS_MA_TEMPLATE_ID"]
    doc = docs.documents().get(documentId=doc_id, fields="title").execute()
    print(f"Docs   OK — template: {doc['title']}")

    print("\nAll 3 Workspace APIs accessible.")

test()
