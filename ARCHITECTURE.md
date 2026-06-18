# Architecture — Website Automation Agent

## Overview

This agent controls a real web browser using code and an LLM (Large Language Model).
Instead of hardcoding which buttons to click or which fields to find, the agent reads
the live page at each step and asks the LLM: "given what's on the page right now, what
should I do next?" The LLM returns a structured response saying which tool to call and
with what parameters.

This approach means the agent works on any page with a form — not just one specific site.

---

## How the Agent Works (Step by Step)

```
1. Start     → Read config from .env, open browser, go to URL
2. Observe   → Read all form elements from the page DOM (inputs, labels, buttons)
3. Think     → Send page state + task + history to LLM, get next action as JSON
4. Act       → Execute the tool the LLM chose (scroll, type, click, etc.)
5. Record    → Save result to history so LLM has context next step
6. Repeat    → Go back to step 2 until LLM says "done"
```

The LLM sees things like:
```
- <input> name='username' in viewport [empty]
- <textarea> name='bio' not in viewport but in DOM [empty]
- <button> text='Submit' type='submit'
```

And decides: "fill username first, then bio, then click submit."

---

## Tools

Each tool does exactly one thing. The LLM picks which one to call at each step.

| Tool               | Parameters                | What it does                                       |
|--------------------|---------------------------|---------------------------------------------------|
| `open_browser`     | none                      | Launches a Playwright browser window               |
| `navigate_to_url`  | `url`                     | Navigates to the given URL, waits for page load    |
| `take_screenshot`  | `label`                   | Saves a PNG of the current browser view            |
| `scroll`           | `pixels`                  | Scrolls down (positive) or up (negative)           |
| `click_on_screen`  | `x, y`                    | Mouse click at pixel coordinates                   |
| `double_click`     | `x, y`                    | Double-click at pixel coordinates                  |
| `send_keys`        | `selector, text`          | Finds element by CSS selector and types text        |
| `click_element`    | `selector`                | Finds element by CSS selector and clicks it         |
| `done`             | `message`                 | Signals the task is complete (LLM-only signal)      |

---

## Element Detection

The agent finds elements using CSS selectors built from live DOM data.

Before each LLM call, we run JavaScript in the browser to extract every input,
textarea, label, and button — with their `name`, `id`, and `placeholder` attributes.
The LLM uses these attributes to build a selector:

```
Input with name='username'  →  selector: "input[name='username']"
Textarea with name='bio'    →  selector: "textarea[name='bio']"
Submit button               →  selector: "button[type='submit']"
```

If the LLM's selector fails, `send_keys` tries simpler fallbacks automatically
before reporting failure back to the LLM.

---

## LLM Integration

We use **NVIDIA NIM** (free tier) with the model `meta/llama-3.3-70b-instruct`.

NVIDIA NIM is OpenAI API-compatible, so we use the standard `openai` Python package
with a different `base_url`:

```python
llm = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=os.getenv("NVIDIA_API_KEY")
)
```

Each LLM call returns JSON like:
```json
{
  "reasoning": "Username field is empty and in DOM, I'll fill it now.",
  "tool": "send_keys",
  "params": { "selector": "input[name='username']", "text": "Tanishq Singh" }
}
```

We use `temperature=0.1` so the model gives consistent, predictable JSON every time.

---

## Error Handling

- **Element not found**: `send_keys` tries multiple fallback selectors before failing
- **LLM bad JSON**: we strip markdown fences and extract `{...}` with regex as fallback
- **Timeout**: configurable via `TIMEOUT` in `.env` (default 30 seconds)
- **Full crash**: `try/finally` always closes the browser; `except` takes an error screenshot
- **Max steps**: if the LLM loops without completing, we stop after `MAX_STEPS` (default 20)

---

## Logging

Every action is logged to terminal with color-coded tags:

| Tag       | Color  | Meaning                               |
|-----------|--------|---------------------------------------|
| `START`   | Cyan   | Agent is starting up                  |
| `THINK`   | Yellow | Agent is deciding what to do          |
| `LLM`     | Purple | LLM request/response                  |
| `TOOL`    | Green  | A tool is being executed              |
| `OBSERVE` | Blue   | Result of the last action             |
| `ERROR`   | Red    | Something went wrong                  |
| `OUTPUT`  | Pink   | Final results and summary             |

---

## Configuration

Everything configurable is in `.env` — no need to touch the code:

| Variable           | What it controls                                |
|--------------------|-------------------------------------------------|
| `NVIDIA_API_KEY`   | API key for NVIDIA NIM                          |
| `LLM_MODEL`        | Which model to use (default: llama-3.3-70b)     |
| `TARGET_URL`       | Page to automate                                |
| `FILL_NAME`        | Text for the Name/Username field                |
| `FILL_DESCRIPTION` | Text for the Description field                  |
| `BROWSER`          | `chromium` / `firefox` / `webkit`               |
| `HEADLESS`         | Show browser window or not                      |
| `TIMEOUT`          | Max wait time for elements (ms)                 |
| `MAX_STEPS`        | Safety limit on LLM decision loop               |

---

## Why This Design?

**Why LLM-driven instead of hardcoded selectors?**
Hardcoded selectors break when the page updates. With an LLM reading the live DOM,
the agent adapts automatically.

**Why NVIDIA NIM?**
Free, fast, no credit card needed. Their models are available through an
OpenAI-compatible API so the integration is minimal.

**Why Playwright over Puppeteer?**
Playwright supports Chromium, Firefox, and WebKit from one library.
It also has better async support and more reliable element waiting.

**Why keep tools small?**
Each tool does exactly one thing — easier to debug, easier to explain, easier to test.
