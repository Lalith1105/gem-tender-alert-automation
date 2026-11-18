import json
import os
import re
import smtplib
from email.message import EmailMessage
import pandas as pd
from apify_client import ApifyClient

APIFY_TOKEN = os.getenv("APIFY_TOKEN")
raw_recipients = [e.strip() for e in os.getenv("RECIPIENT_EMAIL", "").split(",") if e.strip()]
SENDER_EMAIL = raw_recipients[0] if raw_recipients else ""
EXTRA_FROM_TO = raw_recipients[1:]
BCC_EMAILS = os.getenv("BCC_EMAILS", "").strip()
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
SEEN_FILE = "seen_tenders.json"

client = ApifyClient(APIFY_TOKEN)


def load_seen_ids():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    return set()


def save_seen_ids(seen_ids):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen_ids), f, indent=2)


def run_tender_check():
    run_input = {
        "source": "gem",
        "keywords": ["data analytics", "cloud services", "BI dashboard", "software development"],
        "status": "active",
        "maxResults": 50,
        "includePdfDetails": False,
    }

    print("Running GeM scraper on Apify...")
    run = client.actor("fascinating_lentil/india-government-tenders-scraper").call(
        run_input=run_input
    )

    raw_items = list(client.dataset(run.default_dataset_id).iterate_items())
    df = pd.DataFrame(raw_items)

    if df.empty:
        print("No data returned from Apify.")
        return

    text_cols = [
        col
        for col in ["title", "category", "department", "ministry", "description"]
        if col in df.columns
    ]
    df["combined_text"] = df[text_cols].fillna("").agg(" ".join, axis=1).str.lower()

    primary_terms = r"analytics|cloud|dashboard|software|data"
    domain_terms = r"ministry|department|development|services|consulting|implementation"

    filtered_df = df[
        df["combined_text"].str.contains(primary_terms, regex=True)
        & df["combined_text"].str.contains(domain_terms, regex=True)
    ].copy()
    filtered_df.drop(columns=["combined_text"], inplace=True)

    if filtered_df.empty:
        print("No matching tenders found today.")
        return

    id_col = next(
        (
            c
            for c in [
                "bidNumber",
                "bid_number",
                "bidNo",
                "bid_no",
                "tender_id",
                "tenderId",
                "id",
                "url",
                "bidUrl",
                "bid_url",
            ]
            if c in filtered_df.columns
        ),
        None,
    )

    if id_col is None:
        filtered_df["_fallback_id"] = (
            filtered_df.drop(columns=["source"], errors="ignore")
            .fillna("")
            .astype(str)
            .agg("|".join, axis=1)
        )
        id_col = "_fallback_id"

    seen_ids = load_seen_ids()
    new_tenders = filtered_df[~filtered_df[id_col].astype(str).isin(seen_ids)].copy()

    if new_tenders.empty:
        print("Matching tenders found, but all were already emailed previously.")
        return

    def get_field(row, candidates, default="N/A"):
        for key in candidates:
            val = row.get(key)
            if pd.notna(val) and str(val).strip() not in ("", "None", "nan", "NA"):
                return str(val).strip()
        return default

    lines = [f"Found {len(new_tenders)} new GeM tender(s):\n"]
    for _, row in new_tenders.iterrows():
        row_dict = row.to_dict()

        bid_no = get_field(
            row,
            ["bid_number", "bidNumber", "bidNo", "bid_no", "b_bid_number", "tender_id", "id"],
            "",
        )
        if not bid_no or not bid_no.startswith("GEM/"):
            for val in row_dict.values():
                match = re.search(r"GEM/\d{4}/[A-Z]+/\d+", str(val))
                if match:
                    bid_no = match.group(0)
                    break
        if not bid_no:
            bid_no = "Bid Number Not Listed"

        title = get_field(
            row,
            ["title", "item_category", "category", "items", "item_description", "description"],
            "GeM Bid Notice",
        )
        dept = get_field(
            row,
            ["department", "ministry", "organisation", "buyer_dept", "dept_name"],
            "Unknown Dept",
        )
        end_date = get_field(
            row,
            ["bid_end_date", "end_date", "endDate", "closing_date", "final_end_date_time"],
            "Check on GeM Portal",
        )
        link = get_field(
            row,
            ["bid_url", "bidUrl", "document_url", "pdf_url", "detail_url", "url"],
            "",
        )

        if link and "all-bids" not in link:
            link_line = f"  Direct Document Link: {link}"
        else:
            link_line = (
                f"  GeM Portal: https://bidplus.gem.gov.in/all-bids "
                f"(Paste '{bid_no}' into 'Enter Keyword' search box)"
            )

        lines.append(
            f"- [{bid_no}] {title}\n"
            f"  Department: {dept}\n"
            f"  Closing Date: {end_date}\n"
            f"{link_line}\n"
        )

    email_body = "\n".join(lines)

    if not GMAIL_APP_PASSWORD:
        raise ValueError("GMAIL_APP_PASSWORD secret is missing.")

    bcc_list = EXTRA_FROM_TO + [e.strip() for e in BCC_EMAILS.split(",") if e.strip()]

    msg = EmailMessage()
    msg["Subject"] = f"GeM Tender Alert: {len(new_tenders)} New Matching Tender(s)"
    msg["From"] = SENDER_EMAIL
    msg["To"] = SENDER_EMAIL
    if bcc_list:
        msg["Bcc"] = ", ".join(bcc_list)
    msg.set_content(email_body)

    print(f"Sending Gmail alert from {SENDER_EMAIL} with {len(bcc_list)} BCC recipient(s)...")
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(SENDER_EMAIL, GMAIL_APP_PASSWORD)
        smtp.send_message(msg)

    seen_ids.update(new_tenders[id_col].astype(str).tolist())
    save_seen_ids(seen_ids)
    print("Done! Seen tender IDs updated.")


if __name__ == "__main__":
    run_tender_check()
