# Website Automation Agent

A browser automation agent that uses an LLM to fill out web forms automatically.
The agent navigates to a page, reads what's on it, asks an AI what to do next,
and then does it — no manual steps needed.

---

## What it does

1. Opens a real Chrome browser
2. Goes to `https://ui.shadcn.com/docs/forms/react-hook-form`
3. Reads all the form elements on the page
4. Asks the LLM: "what should I do next?"
5. Types the Name, types the Description, clicks Submit
6. Saves screenshots at every step so you can review what happened

---

## Project Structure

```
Website Automation Agent/
├── agent.py          ← Python version (main one to run)
├── agent.js          ← JavaScript/Node.js version (same logic)
├── .env              ← your config — API key, what to type, etc.
├── .env.example      ← copy this to make your own .env
├── requirements.txt  ← Python packages
├── package.json      ← Node.js packages
├── screenshots/      ← screenshots saved here after each run
├── README.md         ← this file
└── ARCHITECTURE.md   ← design explanation
```

---

## Setup — Python

### 1. Create virtual environment

```bash
cd "Website Automation Agent"
python -m venv .venv
source .venv/bin/activate       # Mac/Linux
# .venv\Scripts\activate        # Windows
```

### 2. Install packages

```bash
pip install -r requirements.txt
```

### 3. Install the Chromium browser

```bash
playwright install chromium
```

### 4. Set up your .env

```bash
cp .env.example .env
```

Open `.env` and add your NVIDIA API key. The key field looks like:

```
NVIDIA_API_KEY=nvapi-xxxxxxxxxxxx
```

Get a free key at: https://build.nvidia.com

### 5. Run

```bash
python agent.py
```

Watch the browser open, scroll to the form, and fill it in.
Screenshots are saved to `./screenshots/` after every step.

---

## Setup — JavaScript

### 1. Install packages

```bash
npm install
```

### 2. Install Playwright browsers

```bash
npx playwright install chromium
```

### 3. Set up .env (same as Python setup above)

### 4. Run

```bash
node agent.js
```

---

## .env Configuration

| Variable           | Default value                                | What it does                            |
|--------------------|----------------------------------------------|-----------------------------------------|
| `NVIDIA_API_KEY`   | (required)                                   | Your NVIDIA NIM API key                 |
| `LLM_MODEL`        | meta/llama-3.3-70b-instruct                  | Which LLM to use for decisions          |
| `TARGET_URL`       | https://ui.shadcn.com/docs/forms/...         | The page to automate                    |
| `FILL_NAME`        | Tanishq Singh                                | Typed into the Name field               |
| `FILL_DESCRIPTION` | Auto-filled by an AI agent...                | Typed into the Description field        |
| `BROWSER`          | chromium                                     | `chromium`, `firefox`, or `webkit`      |
| `HEADLESS`         | false                                        | `false` = browser visible, `true` = not |
| `TIMEOUT`          | 30000                                        | Element wait timeout (milliseconds)     |
| `MAX_STEPS`        | 20                                           | Max LLM decision steps before stopping  |

---

## Tools the Agent Has

| Tool               | What it does                                        |
|--------------------|-----------------------------------------------------|
| `open_browser`     | Launches the browser                                |
| `navigate_to_url`  | Goes to a URL and waits for page load               |
| `take_screenshot`  | Saves current view as PNG                           |
| `scroll`           | Scrolls up or down by pixels                        |
| `click_on_screen`  | Clicks at (x, y) pixel coordinates                  |
| `double_click`     | Double-clicks at (x, y)                             |
| `send_keys`        | Types text into a form field using a CSS selector   |
| `click_element`    | Clicks a button found by CSS selector               |

---

## Troubleshooting

**"NVIDIA_API_KEY not found"**
Create a `.env` file from `.env.example` and add your key.

**Browser doesn't open**
Run `playwright install chromium` (Python) or `npx playwright install chromium` (JS).

**Agent runs but doesn't complete**
Check the screenshots in `./screenshots/` to see what the agent saw at each step.
Try increasing `MAX_STEPS=30` in `.env`.

**Slow page loading**
Add `TIMEOUT=60000` to `.env` for a 60-second timeout instead of 30.

---

## References

- [Playwright Docs](https://playwright.dev/)
- [NVIDIA NIM](https://build.nvidia.com)
- [Browser Use (inspiration)](https://github.com/browser-use/browser-use)
- [shadcn/ui Forms](https://ui.shadcn.com/docs/forms/react-hook-form)
