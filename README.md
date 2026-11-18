# Automated Daily GeM Tender Monitoring Pipeline

An end-to-end data pipeline that automatically extracts active tenders from the Government e-Marketplace (GeM), applies multi-keyword regex filtering with `pandas`, deduplicates previously seen bids via JSON state tracking, and delivers daily email digests via Gmail SMTP.

## Architecture
1. **Extraction:** Apify Scraper (`apify-client`) fetches active GeM tender records.
2. **Filtering & Parsing:** `pandas` + `regex` cross-filter titles, categories, and departments while extracting `GEM/YYYY/...` bid numbers, closing dates, and document URLs.
3. **Stateful Deduplication:** Tracks notified bid IDs in `seen_tenders.json` via automated Git commits so stakeholders never receive duplicate alerts.
4. **CI/CD Orchestration:** GitHub Actions runs the workflow daily at 03:00 UTC (08:30 AM IST) and dispatches multi-recipient BCC alerts via Python `smtplib`.

## Required Repository Secrets
- `APIFY_TOKEN`
- `RECIPIENT_EMAIL`
- `BCC_EMAILS`
- `GMAIL_APP_PASSWORD`
