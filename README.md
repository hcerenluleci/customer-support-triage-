# customer-support-triage-

AI-powered banking customer support triage system built with FastAPI.  
The system validates incoming tickets, classifies them using AI and rule-based fallback logic, routes them to the correct support destination, sends Slack notifications for technical issues, and stores ticket metadata in Google Sheets.

## Features

- FastAPI-based REST API
- JSON ticket submission
- Input validation
- AI-powered ticket classification using Groq
- Rule-based fallback classification
- Priority assignment
- Category-based routing
- Slack integration
- Google Sheets integration
- Metadata logging
- Delivery status tracking

## HW3 Modifications

For the HW3 requirements, the following updates were implemented in `main.py`:

- Updated input format to:
  - `name`
  - `email`
  - `message`

- Added input validation:
  - Missing field detection
  - Invalid email detection
  - `validation_errors` tracking

- Invalid tickets are still stored with:
  - `validation_status = "Invalid"`

- Added AI classification for banking ticket categories:
  - `billing`
  - `fraud`
  - `loan`
  - `card_issue`
  - `technical`
  - `general`

- Added priority classification:
  - `low`
  - `medium`
  - `high`

- Added rule-based fallback logic for fraud and technical issue detection.

- Added category-based routing:
  - `fraud` → fraud/security team
  - `billing` → finance team
  - `loan` → loan department
  - `card_issue` → card support
  - `technical` → technical support
  - `general` → shared inbox

- Added Slack notification integration for technical issues.

- Added Google Sheets integration for ticket storage.

- Added delivery status tracking:
  - `success`
  - `failed`
  - `none`

- Stored metadata fields:
  - `timestamp`
  - `name`
  - `email`
  - `message`
  - `validation_status`
  - `validation_errors`
  - `category`
  - `priority`
  - `route`
  - `delivery_status`

## Security Note

The actual `.env` file and `credentials.json` file are excluded from GitHub for security reasons.

Use `.env.example` as a template and configure local credentials manually.
