# Architecture — Website Automation Agent

## What this project is

This agent automates a web browser — it launches a browser, goes to a URL,
finds form fields on the page, and fills them in automatically.

It's built as a mini version of browser automation tools like Browser Use.
The core idea is "give the agent a set of tools, and let it decide how to use them".

---

## Agent Pattern: START → THINK → TOOL → OBSERVE → OUTPUT

Every action the agent takes follows this flow:

```
START   — Agent wakes up, reads config from .env
THINK   — Agent figures out what to do next
TOOL    — Agent calls a specific tool (click, scroll, type, etc.)
OBSERVE — Agent sees what happened (element found? text typed? error?)
OUTPUT  — Agent reports what it did and saves screenshots
```

This is the same reasoning loop used by larger AI agents (like ReAct).
The difference here is that the steps are explicit and hardcoded to the task.

---

## Tools (the agent's capabilities)

Each tool does exactly one thing. They're kept small on purpose so they're easy to understand and test individually.

| Tool               | What it does                                           |
|--------------------|--------------------------------------------------------|
| `open_browser`     | Launches a Playwright browser window                   |
| `navigate_to_url`  | Goes to a given URL and waits for the page to load     |
| `take_screenshot`  | Saves a PNG of the current browser view                |
| `scroll`           | Scrolls the page up or down by N pixels                |
| `click_on_screen`  | Clicks at exact (x, y) pixel coordinates              |
| `double_click`     | Double-clicks at (x, y) — useful for selecting text    |
| `send_keys`        | Types text into a field (optionally targets a selector)|

---

## Smart Element Finder

The tricky part of browser automation is finding the right element on the page.
Rather than guessing one selector and failing if it's wrong, the agent keeps a list
of selectors ordered from most specific to most generic:

```
input#name                          ← try this first (exact match)
input[name='username']              ← fallback 1
input[placeholder*='shadcn']        ← fallback 2
form input[type='text']:first-of-type ← fallback 3
input[type='text']                  ← last resort
```

If the first selector doesn't find anything within 5 seconds, it moves to the next.
This makes the agent resilient to small page changes.

---

## Error Handling

Every major step is wrapped in try/except:
- If an element isn't found → log the error, take a screenshot, continue
- If the whole agent crashes → take a screenshot of the error state
- Network timeouts → Playwright has built-in timeout handling, we use TIMEOUT_MS from .env

---

## File Structure

```
Website Automation Agent/
├── agent.py          ← main Python agent (uses asyncio + Playwright)
├── agent.js          ← same logic in JavaScript/Node.js
├── .env              ← your config (NOT committed to git)
├── .env.example      ← template showing what goes in .env
├── .gitignore        ← ignores .env, node_modules, screenshots, etc.
├── requirements.txt  ← Python dependencies
├── package.json      ← Node.js dependencies
├── screenshots/      ← auto-created, screenshots saved here per run
├── README.md         ← setup and usage guide
└── ARCHITECTURE.md   ← this file
```

---

## Why Playwright?

- Works with Chromium, Firefox, and WebKit (we use Chromium by default)
- Has a great async API in Python and a native JS library
- Handles SPAs (like the shadcn docs page) much better than simple HTTP fetching
- Built-in screenshot, wait-for-element, and navigation tools

---

## Configuration (via .env)

All settings live in `.env` so you never need to edit the code to change behavior:

| Variable           | What it controls                                |
|--------------------|-------------------------------------------------|
| `TARGET_URL`       | Which page to open                              |
| `FILL_NAME`        | What to type in the Name field                  |
| `FILL_DESCRIPTION` | What to type in the Description field           |
| `BROWSER`          | `chromium` / `firefox` / `webkit`               |
| `HEADLESS`         | `true` = invisible, `false` = you can watch it  |
| `TIMEOUT`          | How long to wait for elements (ms)              |
| `OPENAI_API_KEY`   | Optional — for AI-powered element detection     |
