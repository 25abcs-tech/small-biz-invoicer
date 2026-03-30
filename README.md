# InvoBiz v1.1 Beta

**Chaos managed. Business organized.**

A free, open-source desktop invoicing and CRM app built for small business owners — runs entirely on your computer, no subscriptions, no cloud, no data sent anywhere.

Built with Python, CustomTkinter, SQLite, and ReportLab.

---

## What's New in v1.1

### Lead Finder (Map-Based Prospecting)
- Live interactive map powered by OpenStreetMap — search for businesses by type within a configurable radius
- Pins deduplicate automatically so the same business never appears twice
- **Search This Area** button lights up amber when you pan or zoom, just like Google Maps
- **Reset Pins** button re-anchors any drifting markers
- Tile caching so browsing the same area doesn't re-download map data, with an in-app cache size indicator and clear button
- One-click **Transfer to Leads** from the selected business card
- Saved Leads list with Approve / Draft Email / Add to CRM / Maps / X actions per lead
- **Import Approved to CRM** — moves all approved leads into your sales pipeline as Cold Leads and removes them from the list automatically
- **Delete All Leads** button (respects current filter)
- Stats strip: Total / New / Approved / Emailed

### Sales Pipeline & CRM
- Visual Kanban-style Sales Pipeline: Cold Lead → Contacted → Prospect → Proposal Sent → Won → Lost
- Pipeline columns scroll independently and sort newest first
- **Last Contacted** indicator on every client card — green (within 7 days), amber (8–30 days), red (30+ days), grey (never contacted)
- **View Sales Pipeline** button prominently placed in the Clients & CRM header
- Address field added to the client info card
- **Copy Name** and **Maps** buttons on every client card for quick research
- **Create Invoice** shortcut in the CRM header — opens a new invoice pre-filled with that client
- X and Edit labels on all call note and follow-up action buttons
- **Send Feedback** button in the sidebar footer — always visible, no digging through Settings

### Product Catalogue (New)
- Dedicated **Products** page in the main navigation
- Add products with SKU, product name, barcode/UPC, category, default price, and tax rate
- Products grouped by category with both SKU and barcode displayed on each card
- Supports product variants using base SKU + suffix (e.g. 00001-FR, 00001-EN)

### Invoicing
- **Searchable client picker** — type to filter instead of scrolling a long dropdown
- **Product auto-fill** in line items — type a name, SKU, or barcode, press Tab to cycle through matches, and all fields fill automatically
- Column headers on line items so every field is clearly labelled
- **Payment Terms** dropdown: Due on Receipt, Net 7, Net 14, Net 30, Net 45, Net 60, Net 90, or Custom Date
- **BC Tax bracket** dropdown with presets: No Tax (0%), GST only (5%), PST only (7%), GST + PST (12%), HST (13%), HST (15%)
- **Payment Plan** section with three modes:
  - Pay in Full (default)
  - Split Payment — choose deposit %, see live breakdown of deposit and balance
  - Installment Plan — choose number of payments and frequency (weekly / bi-weekly / monthly), with a live per-payment schedule
- Payment schedule **prints on the PDF** — split and installment plans show a full breakdown table in brand colours

### Bug Fixes & Performance
- Fixed "Not yet contacted" showing incorrectly for clients with existing call notes
- Fixed Import Approved to CRM silently failing due to a NOT NULL constraint
- Fixed invoice dialog crashing on open
- Fixed installment plan preview not updating when payment count or frequency changed
- Fixed map pins drifting during navigation
- Reduced Lead Finder CPU usage — position poll every 1 second instead of 400ms
- Lead list skips full rebuild when data hasn't changed
- Consolidated redundant DB connections across several methods

---

## Features (Full)

- **Dashboard** — revenue overview, recent invoices, outstanding balances
- **Invoices** — create, edit, PDF export, payment tracking
- **Products** — SKU/barcode catalogue with auto-fill in invoices
- **Clients & CRM** — full contact management with call notes, follow-ups, pipeline stages
- **Sales Pipeline** — Kanban view of your entire prospect and client pipeline
- **Fulfilment** — track order stages from packed to delivered, with carrier management
- **Lead Finder** — map-based business prospecting that feeds directly into your CRM
- **Settings** — business info, logo, payment instructions, currency, e-transfer email

### Technical
- Runs 100% locally — SQLite database, no internet required (except map tiles and Overpass API for Lead Finder)
- No subscriptions, no accounts, no data collection
- PDF invoices generated with ReportLab — brand colours, logo support, payment schedules
- Silent launch via `.vbs` file on Windows (no console window)
- Tile cache for offline map browsing of previously visited areas

---

## Download & Install

### For Everyone (Windows)
1. Go to the [Releases page](https://github.com/25abcs-tech/small-biz-invoicer/releases)
2. Download `InvoBiz-v1.1-Beta.zip`
3. Unzip it anywhere on your computer
4. Double-click `InvoBiz.exe` to launch — no installation required

> **First run:** Open **Settings** and fill in your business name, address, email, and logo. These appear on every invoice automatically.

### Updating from a Previous Version
Just replace the `.exe` file — that's it. Your data (clients, invoices, leads, settings) is stored in a separate `invoicer.db` file and is never touched by the update. The app will automatically add any new features to your existing database the first time it launches.



---

## Usage Tips

**Creating an invoice**
1. Go to Invoices → New Invoice
2. Type a client name to search — or open a client in the CRM and click **+ Create Invoice**
3. Type a product name, SKU, or barcode in the line item field — press Tab to autocomplete
4. Choose payment terms and tax bracket
5. Add a payment plan if needed — the schedule prints on the PDF

**Finding leads**
1. Go to Lead Finder → type a business type (e.g. "bookstores")
2. Click **Search Map** — pins appear for matching businesses
3. Click a pin → details appear in the right panel
4. Click **Transfer to Leads** to save it
5. Approve the leads you want to pursue
6. Click **Import Approved to CRM** — they become Cold Leads in your pipeline

---

## Roadmap

- [ ] Export leads to CSV
- [ ] Email integration (send invoices directly)
- [ ] Multi-currency support
- [ ] Recurring invoices
- [ ] Mac and iOS compatibility
- [ ] Calendar integration (Google Calendar / iCal sync for follow-ups and due dates)
- [ ] More apps coming from 25ABCs

---

## License

**InvoBiz is free during the Beta period.**

By downloading and using InvoBiz Beta you agree that:
- It is free to use for personal and business purposes during the Beta
- You may not resell, rebrand, or redistribute it as your own product
- Pricing for future stable releases has not yet been determined — Beta users will be notified before any paid model is introduced
- The software is provided as-is, without warranty

© 2026 Anna Elusini — 25ABCs. All rights reserved.

---

*Built with love (and a lot of Claude) in British Columbia, Canada.*
