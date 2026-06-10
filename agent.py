"""
Website Automation Agent
------------------------
This is the main agent. It uses Playwright to open a browser,
navigate to a URL, find form fields on the page, and fill them in.

Think of it like a robot that knows how to use a browser,
but instead of clicking around randomly, it knows exactly
what tools to use at each step.

Run it with: python agent.py
"""

import os
import time
import asyncio
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright, Page, Browser, TimeoutError as PlaywrightTimeout

# load everything from .env before we do anything else
load_dotenv()

# grab config from environment
TARGET_URL    = os.getenv("TARGET_URL",    "https://ui.shadcn.com/docs/forms/react-hook-form")
FILL_NAME     = os.getenv("FILL_NAME",     "Tanishq Singh")
FILL_DESC     = os.getenv("FILL_DESCRIPTION", "This form was auto-filled by a Playwright automation agent!")
BROWSER_TYPE  = os.getenv("BROWSER",       "chromium")
HEADLESS      = os.getenv("HEADLESS",      "false").lower() == "true"
TIMEOUT_MS    = int(os.getenv("TIMEOUT",   "30000"))

# where screenshots get saved
SCREENSHOTS_DIR = Path("screenshots")
SCREENSHOTS_DIR.mkdir(exist_ok=True)


# -------------------------------------------------------------------
# LOGGING — simple colored terminal output so we can follow along
# -------------------------------------------------------------------

def log(tag: str, message: str):
    ts = datetime.now().strftime("%H:%M:%S")
    colors = {
        "START":   "\033[96m",   # cyan
        "THINK":   "\033[93m",   # yellow
        "TOOL":    "\033[92m",   # green
        "OBSERVE": "\033[94m",   # blue
        "ERROR":   "\033[91m",   # red
        "OUTPUT":  "\033[95m",   # purple
    }
    reset = "\033[0m"
    color = colors.get(tag, "")
    print(f"[{ts}] {color}[{tag}]{reset}  {message}")


# -------------------------------------------------------------------
# TOOL: take_screenshot
# Saves a PNG of whatever the browser is showing right now
# -------------------------------------------------------------------

async def take_screenshot(page: Page, label: str = "screenshot") -> str:
    filename = SCREENSHOTS_DIR / f"{label}_{int(time.time())}.png"
    await page.screenshot(path=str(filename), full_page=False)
    log("TOOL", f"take_screenshot → saved to {filename}")
    return str(filename)


# -------------------------------------------------------------------
# TOOL: navigate_to_url
# Points the browser at a specific URL and waits for the page to load
# -------------------------------------------------------------------

async def navigate_to_url(page: Page, url: str):
    log("TOOL", f"navigate_to_url → {url}")
    await page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_MS)
    # give any JS-rendered content a moment to appear
    await page.wait_for_timeout(2000)
    log("OBSERVE", f"Page loaded: {await page.title()}")


# -------------------------------------------------------------------
# TOOL: scroll
# Scrolls the page by a given number of pixels (positive = down)
# -------------------------------------------------------------------

async def scroll(page: Page, pixels: int = 400):
    log("TOOL", f"scroll → {pixels}px")
    await page.evaluate(f"window.scrollBy(0, {pixels})")
    await page.wait_for_timeout(500)


# -------------------------------------------------------------------
# TOOL: click_on_screen
# Clicks at exact (x, y) coordinates on the page
# Useful when we know where something is visually
# -------------------------------------------------------------------

async def click_on_screen(page: Page, x: int, y: int):
    log("TOOL", f"click_on_screen → ({x}, {y})")
    await page.mouse.click(x, y)
    await page.wait_for_timeout(300)


# -------------------------------------------------------------------
# TOOL: double_click
# Double-clicks at (x, y) — needed to select all text in some fields
# -------------------------------------------------------------------

async def double_click(page: Page, x: int, y: int):
    log("TOOL", f"double_click → ({x}, {y})")
    await page.mouse.dblclick(x, y)
    await page.wait_for_timeout(300)


# -------------------------------------------------------------------
# TOOL: send_keys
# Types text into whatever element is currently focused
# Can also target a specific selector
# -------------------------------------------------------------------

async def send_keys(page: Page, text: str, selector: str = None):
    if selector:
        log("TOOL", f"send_keys → '{text}' into selector: {selector}")
        await page.locator(selector).fill(text)
    else:
        log("TOOL", f"send_keys → '{text}' (typing into focused element)")
        await page.keyboard.type(text, delay=60)


# -------------------------------------------------------------------
# TOOL: open_browser
# Spins up a Playwright browser instance and returns it + a new page
# -------------------------------------------------------------------

async def open_browser(playwright_instance) -> tuple:
    log("TOOL", f"open_browser → launching {BROWSER_TYPE} (headless={HEADLESS})")

    browser_map = {
        "chromium": playwright_instance.chromium,
        "firefox":  playwright_instance.firefox,
        "webkit":   playwright_instance.webkit,
    }
    launcher = browser_map.get(BROWSER_TYPE, playwright_instance.chromium)

    browser: Browser = await launcher.launch(
        headless=HEADLESS,
        args=["--start-maximized"]
    )
    context = await browser.new_context(
        viewport={"width": 1440, "height": 900},
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0"
    )
    page = await context.new_page()
    log("OBSERVE", "Browser launched and new page created")
    return browser, page


# -------------------------------------------------------------------
# SMART ELEMENT FINDER
# Tries a list of selectors one by one until something works.
# This is the "intelligent" part — if the first guess fails, we try more.
# -------------------------------------------------------------------

async def find_element(page: Page, selectors: list, description: str = "element"):
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            await locator.wait_for(state="visible", timeout=5000)
            log("OBSERVE", f"Found '{description}' using selector: {selector}")
            return locator
        except PlaywrightTimeout:
            log("THINK", f"Selector not found: {selector} — trying next...")
        except Exception as e:
            log("THINK", f"Selector error ({selector}): {e} — trying next...")
    return None


# -------------------------------------------------------------------
# THE MAIN AGENT LOOP
# This is where the agent actually thinks and acts.
# It follows: START → THINK → TOOL → OBSERVE → OUTPUT
# -------------------------------------------------------------------

async def run_agent():
    log("START", "Website Automation Agent is starting up")
    log("START", f"Target URL : {TARGET_URL}")
    log("START", f"Fill Name  : {FILL_NAME}")
    log("START", f"Fill Desc  : {FILL_DESC}")
    print()

    async with async_playwright() as pw:

        # STEP 1: Launch the browser
        log("THINK", "Step 1 — Open a browser window")
        browser, page = await open_browser(pw)

        try:
            # STEP 2: Go to the target URL
            log("THINK", "Step 2 — Navigate to the target page")
            await navigate_to_url(page, TARGET_URL)
            await take_screenshot(page, "01_page_loaded")

            # STEP 3: Scroll down to find the form preview
            # The shadcn docs page shows a live form demo somewhere in the middle
            log("THINK", "Step 3 — Scrolling down to find the form demo area")
            await scroll(page, 800)
            await take_screenshot(page, "02_after_scroll")

            # STEP 4: Find the Name input
            # We try multiple selectors because the page might render differently
            log("THINK", "Step 4 — Looking for the Name field")
            name_selectors = [
                "input#name",                          # exact ID match
                "input[name='username']",              # by name attribute
                "input[placeholder*='shadcn']",        # placeholder text hint
                "form input[type='text']:first-of-type",  # first text input in a form
                "input[type='text']",                  # any text input as fallback
            ]
            name_field = await find_element(page, name_selectors, "Name field")

            if name_field:
                log("THINK", "Step 5 — Clicking the Name field and typing")
                await name_field.click()
                await page.wait_for_timeout(300)
                # clear any existing text first with triple-click
                await name_field.triple_click()
                await send_keys(page, FILL_NAME, selector=None)
                await take_screenshot(page, "03_name_filled")
                log("OBSERVE", f"Name field filled with: '{FILL_NAME}'")
            else:
                log("ERROR", "Could not find the Name field — taking screenshot for debugging")
                await take_screenshot(page, "03_name_not_found")

            # STEP 5: Find the Description textarea
            log("THINK", "Step 6 — Looking for the Description field")
            desc_selectors = [
                "textarea#bio",                      # ID used in shadcn form example
                "textarea[name='bio']",              # name attribute
                "textarea",                          # any textarea on the page
                "input[name='description']",         # sometimes it's an input
            ]
            desc_field = await find_element(page, desc_selectors, "Description field")

            if desc_field:
                log("THINK", "Step 7 — Clicking the Description field and typing")
                await desc_field.click()
                await page.wait_for_timeout(300)
                await desc_field.triple_click()
                await send_keys(page, FILL_DESC, selector=None)
                await take_screenshot(page, "04_desc_filled")
                log("OBSERVE", f"Description field filled with: '{FILL_DESC}'")
            else:
                log("ERROR", "Could not find the Description field — taking screenshot")
                await take_screenshot(page, "04_desc_not_found")

            # STEP 6: Scroll a bit more so the Submit button is visible
            log("THINK", "Step 8 — Scrolling to find the Submit button")
            await scroll(page, 300)

            # STEP 7: Click Submit
            submit_selectors = [
                "button[type='submit']",
                "form button:last-of-type",
                "button:has-text('Submit')",
            ]
            submit_btn = await find_element(page, submit_selectors, "Submit button")

            if submit_btn:
                log("THINK", "Step 9 — Clicking Submit button")
                await submit_btn.click()
                await page.wait_for_timeout(1500)
                await take_screenshot(page, "05_after_submit")
                log("OBSERVE", "Form submitted!")
            else:
                log("ERROR", "Could not find submit button")
                await take_screenshot(page, "05_submit_not_found")

            # STEP 8: Done!
            print()
            log("OUTPUT", "Agent finished successfully!")
            log("OUTPUT", f"Screenshots saved in: ./{SCREENSHOTS_DIR}/")
            print()

        except Exception as err:
            log("ERROR", f"Something went wrong: {err}")
            await take_screenshot(page, "error_state")
            raise

        finally:
            # wait a bit before closing so you can see the result
            await page.wait_for_timeout(3000)
            await browser.close()
            log("OUTPUT", "Browser closed. Agent is done.")


# entry point — just run the agent
if __name__ == "__main__":
    asyncio.run(run_agent())
