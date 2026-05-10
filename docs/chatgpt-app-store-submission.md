# ChatGPT App Store Submission

Use this as the dashboard checklist for publishing Public Texas State and Austin City Search.

## Dashboard Values

- App name: Public Texas State and Austin City Search
- Subtitle: Find TX and Austin data
- Category: Productivity
- MCP URL: https://civic.pagonya.co/mcp
- Website URL: https://civic.pagonya.co/
- Privacy policy URL: https://civic.pagonya.co/privacy.html
- Support URL: https://civic.pagonya.co/support.html
- Icon: `assets/texas-civic-data-health-icon.png`
- Submission JSON: `chatgpt-app-submission.json`

## Short Description

Public Texas State and Austin City Search helps users search State of Texas and City of Austin public datasets, find official permit/license/service starting points, and fetch bounded read-only rows from public Socrata datasets. Austin dataset-health checks are secondary context for quality caveats. The app is free to use without authentication, independently operated, and is not affiliated with or endorsed by the State of Texas or City of Austin.

## Review Notes

- Public HTTPS MCP endpoint is available at `https://civic.pagonya.co/mcp`.
- The app is free to use and unauthenticated for review.
- All MCP tools are read-only, non-destructive, and do not change public internet state.
- The app cannot submit permit applications, file 3-1-1 requests, send email, update public records, or guarantee legal permit requirements.
- The static site publishes the privacy policy, support page, and this review checklist.

## Manual Gates

Before clicking `Submit for review`, verify:

- OpenAI organization identity verification is complete for the publishing name.
- The submitting project uses global data residency.
- `support@pagonya.co` receives mail.
- The positive and negative test prompts in `chatgpt-app-submission.json` pass in ChatGPT web.
- At least the primary workflows pass in ChatGPT mobile.
- Screenshots show real ChatGPT results for service-guide search and public dataset row retrieval.

## Suggested Screenshots

- ChatGPT answer for: "Using Public Texas State and Austin City Search, how do I start a food business permit process in Texas and Austin, and what public datasets can help me research it?"
- ChatGPT answer for: "Using Public Texas State and Austin City Search, find a relevant public permit dataset and show a small row sample from it."
- Optional: the public site at https://civic.pagonya.co/ showing the report and support/privacy links.

## Dashboard Flow

1. Open https://platform.openai.com/apps-manage.
2. Create or edit the Public Texas State and Austin City Search app draft.
3. Enter the dashboard values above.
4. Upload `chatgpt-app-submission.json` if the form supports import, or paste its app info, tool justifications, and test cases manually.
5. Upload the icon and screenshots.
6. Run the dashboard validation.
7. Click `Submit for review` only after the manual gates are complete.
8. After approval, click `Publish` in the dashboard.
