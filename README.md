# Website Automation Agent

An intelligent browser automation agent that navigates to a web page and automatically fills out forms — no manual interaction needed.

Built as Assignment 04 for the GenAI Projects series. Inspired by browser-use tools.

---

## What it does

1. Opens a real browser (Chromium by default)
2. Navigates to `https://ui.shadcn.com/docs/forms/react-hook-form`
3. Scrolls down to the live form demo
4. Finds the **Name** and **Description** fields automatically
5. Types configured values into both fields
6. Clicks Submit
7. Takes screenshots at every step so you can see what happened

---

## Project Structure

```
Website Automation Agent/
├── agent.py          ← Python version (run this one)
├── agent.js          ← JavaScript/Node.js version (same logic)
├── .env              ← your config (never committed to git)
├── .env.example      ← copy this to create your .env
├── requirements.txt  ← Python packages needed
├── package.json      ← Node.js packages needed
├── screenshots/      ← screenshots saved here after each run
├── README.md         ← this file
└── ARCHITECTURE.md   ← design decisions and agent workflow
```

---

## Setup — Python (Recommended)

### Step 1 — Create a virtual environment

```bash
cd "Website Automation Agent"
python -m venv .venv
source .venv/bin/activate      # Mac/Linux
# or on Windows: .venv\Scripts\activate
```

### Step 2 — Install Python packages

```bash
pip install -r requirements.txt
```

### Step 3 — Install Playwright browsers

This downloads the actual Chromium browser binary:

```bash
playwright install chromium
```

### Step 4 — Create your .env file

```bash
cp .env.example .env
```

You can edit `.env` to change what gets typed into the form, or leave the defaults.

### Step 5 — Run the agent

```bash
python agent.py
```

You'll see the browser open, the agent scroll, find the form, and type into it.
Screenshots are saved in `./screenshots/`.

---

## Setup — JavaScript (Alternative)

### Step 1 — Install Node packages

```bash
npm install
```

### Step 2 — Install Playwright browsers

```bash
npm run install-browsers
```

### Step 3 — Create your .env file (if not done already)

```bash
cp .env.example .env
```

### Step 4 — Run the agent

```bash
node agent.js
```

---

## Configuration (.env)

Edit `.env` to customize behavior:

| Variable           | Default                                               | What it does                          |
|--------------------|-------------------------------------------------------|---------------------------------------|
| `TARGET_URL`       | https://ui.shadcn.com/docs/forms/react-hook-form      | Page to automate                      |
| `FILL_NAME`        | Tanishq Singh                                         | Goes in the Name input                |
| `FILL_DESCRIPTION` | This form was auto-filled...                          | Goes in the Description textarea      |
| `BROWSER`          | chromium                                              | `chromium`, `firefox`, or `webkit`    |
| `HEADLESS`         | false                                                 | `true` = no window, `false` = visible |
| `TIMEOUT`          | 30000                                                 | Max wait time in milliseconds         |
| `OPENAI_API_KEY`   | (empty)                                               | Optional, for AI element detection    |

---

## Tools the Agent Has

| Tool               | Description                                         |
|--------------------|-----------------------------------------------------|
| `open_browser`     | Launches the browser                                |
| `navigate_to_url`  | Goes to a specific URL                              |
| `take_screenshot`  | Saves the current screen as PNG                     |
| `scroll`           | Scrolls up or down                                  |
| `click_on_screen`  | Clicks at exact x,y coordinates                     |
| `double_click`     | Double-clicks at x,y                                |
| `send_keys`        | Types text into a focused input                     |

---

## Troubleshooting

**"Browser not found" error**
Run `playwright install chromium` (Python) or `npm run install-browsers` (JS)

**"Element not found" — Name field missing**
The shadcn page might have updated their layout. Check `screenshots/02_after_scroll.png` to see what the agent saw. You might need to scroll further or update the selectors in `agent.py`.

**Page not loading**
Check your internet connection. Try setting `TIMEOUT=60000` in `.env` for slower connections.

**Want to see what's happening?**
Make sure `HEADLESS=false` in your `.env` — this shows the browser window so you can watch the agent work.

---

## References

- [Playwright Docs](https://playwright.dev/)
- [Browser Use (inspiration)](https://github.com/browser-use/browser-use)
- [ShadCN UI Forms](https://ui.shadcn.com/docs/forms/react-hook-form)
