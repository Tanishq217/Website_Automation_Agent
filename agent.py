"""
Website Automation Agent - Python Version
------------------------------------------
This agent uses an LLM to control a real browser and fill out web forms.

How it works:
  1. Open browser, navigate to the target page
  2. Read what's on the page (inputs, labels, buttons)
  3. Ask the LLM what to do next
  4. Do it (click, scroll, type, etc.)
  5. Repeat until the form is submitted

The LLM decides which element to interact with at each step,
so this works on any page - not just one specific website.

Run: python3 agent.py
"""

import os
import json
import time
import asyncio
import re
from datetime import datetime
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv
from playwright.async_api import async_playwright, Page, Browser

# read config from .env file
load_dotenv()

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
LLM_MODEL      = os.getenv("LLM_MODEL", "meta/llama-3.3-70b-instruct")
TARGET_URL     = os.getenv("TARGET_URL", "https://ui.shadcn.com/docs/forms/react-hook-form")
FILL_NAME      = os.getenv("FILL_NAME", "Tanishq Singh")
FILL_DESC      = os.getenv("FILL_DESCRIPTION", "Auto-filled by an AI agent using NVIDIA NIM and Playwright!")
BROWSER_TYPE   = os.getenv("BROWSER", "chromium")
HEADLESS       = os.getenv("HEADLESS", "false").lower() == "true"
TIMEOUT_MS     = int(os.getenv("TIMEOUT", "30000"))
MAX_STEPS      = int(os.getenv("MAX_STEPS", "20"))

# all screenshots saved here
SCREENSHOTS_DIR = Path("screenshots")
SCREENSHOTS_DIR.mkdir(exist_ok=True)

# check API key before we do anything
if not NVIDIA_API_KEY:
    print("[ERROR] NVIDIA_API_KEY is missing from .env")
    exit(1)

# connect to NVIDIA NIM - it uses the same API format as OpenAI
llm = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=NVIDIA_API_KEY
)


# --- colored terminal logging so we can follow what the agent is doing ---

def log(tag: str, message: str):
    ts = datetime.now().strftime("%H:%M:%S")
    colors = {
        "START":   "\033[96m",
        "THINK":   "\033[93m",
        "LLM":     "\033[35m",
        "TOOL":    "\033[92m",
        "OBSERVE": "\033[94m",
        "ERROR":   "\033[91m",
        "OUTPUT":  "\033[95m",
    }
    reset = "\033[0m"
    color = colors.get(tag, "")
    print(f"[{ts}] {color}[{tag}]{reset}  {message}")


# =============================================================================
# TOOLS
# Each function does one specific browser action.
# The LLM picks which one to call at each step.
# =============================================================================

async def take_screenshot(page: Page, label: str = "step") -> str:
    """Save a screenshot of the current browser view."""
    path = str(SCREENSHOTS_DIR / f"{label}_{int(time.time())}.png")
    await page.screenshot(path=path, full_page=False)
    log("TOOL", f"take_screenshot → {path}")
    return path


async def open_browser(pw) -> tuple[Browser, Page]:
    """Launch the browser and open a new tab."""
    log("TOOL", f"open_browser → {BROWSER_TYPE} (headless={HEADLESS})")
    launchers = {
        "chromium": pw.chromium,
        "firefox":  pw.firefox,
        "webkit":   pw.webkit,
    }
    browser = await launchers.get(BROWSER_TYPE, pw.chromium).launch(
        headless=HEADLESS,
        args=["--start-maximized"]
    )
    ctx  = await browser.new_context(viewport={"width": 1440, "height": 900})
    page = await ctx.new_page()
    log("OBSERVE", "Browser ready")
    return browser, page


async def navigate_to_url(page: Page, url: str) -> str:
    """Go to a URL and wait for the page to load."""
    log("TOOL", f"navigate_to_url → {url}")
    await page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_MS)
    await page.wait_for_timeout(2500)  # wait for JS frameworks to render
    title = await page.title()
    log("OBSERVE", f"Loaded: {title}")
    return f"Navigated to {url}. Page title: {title}"


async def scroll(page: Page, pixels: int) -> str:
    """Scroll the page by a given number of pixels (positive = down)."""
    log("TOOL", f"scroll → {pixels}px")
    await page.evaluate(f"window.scrollBy(0, {pixels})")
    await page.wait_for_timeout(600)
    pos = await page.evaluate("window.scrollY")
    return f"Scrolled {pixels}px. Current scroll position: {pos}px"


async def click_on_screen(page: Page, x: int, y: int) -> str:
    """Click at specific pixel coordinates on the screen."""
    log("TOOL", f"click_on_screen → ({x}, {y})")
    await page.mouse.click(x, y)
    await page.wait_for_timeout(400)
    return f"Clicked at ({x}, {y})"


async def double_click(page: Page, x: int, y: int) -> str:
    """Double-click at specific pixel coordinates."""
    log("TOOL", f"double_click → ({x}, {y})")
    await page.mouse.dblclick(x, y)
    await page.wait_for_timeout(400)
    return f"Double-clicked at ({x}, {y})"


async def send_keys(page: Page, selector: str, text: str) -> str:
    """
    Type text into a form field found by CSS selector.
    If the first selector fails, tries simpler fallback selectors.
    """
    log("TOOL", f"send_keys → selector='{selector}' text='{text}'")

    # start with what the LLM suggested, add simpler fallbacks just in case
    fallbacks = [selector]
    if "input" in selector.lower():
        fallbacks += ["input[type='text']", "input"]
    if "textarea" in selector.lower():
        fallbacks += ["textarea"]

    for sel in fallbacks:
        try:
            elem = page.locator(sel).first
            await elem.wait_for(state="visible", timeout=5000)
            await elem.click(click_count=3)  # select all existing text first
            await page.wait_for_timeout(200)
            await page.keyboard.type(text, delay=50)  # type with slight delay
            await page.wait_for_timeout(300)
            log("OBSERVE", f"Typed into '{sel}'")
            return f"SUCCESS: Typed '{text}' into element matching '{sel}'"
        except Exception as e:
            log("THINK", f"Selector '{sel}' failed: {e}")

    return f"FAILED: Could not find element matching '{selector}'. Try a different selector."


async def click_element(page: Page, selector: str) -> str:
    """
    Click an element by CSS selector (used for buttons like Submit).
    Scrolls the element into view before clicking.
    """
    log("TOOL", f"click_element → selector='{selector}'")
    try:
        elem = page.locator(selector).first
        await elem.wait_for(state="visible", timeout=8000)
        await elem.scroll_into_view_if_needed()
        await elem.click()
        await page.wait_for_timeout(1000)
        log("OBSERVE", f"Clicked '{selector}'")
        return f"SUCCESS: Clicked element matching '{selector}'"
    except Exception as e:
        log("THINK", f"click_element failed for '{selector}': {e}")
        return f"FAILED: Could not click '{selector}'. Error: {str(e)[:100]}"


# =============================================================================
# PAGE CONTEXT
# Reads the current page's DOM to get a list of all form elements.
# This is sent to the LLM so it knows what's on the page.
# =============================================================================

async def get_page_context(page: Page) -> dict:
    """
    Extract all inputs, labels, and buttons from the current page.
    The LLM uses this information to decide what to interact with.
    """
    title = await page.title()
    url   = page.url

    elements = await page.evaluate("""() => {
        const result = { inputs: [], labels: [], buttons: [] };

        document.querySelectorAll('input, textarea').forEach(el => {
            const rect = el.getBoundingClientRect();
            result.inputs.push({
                tag:         el.tagName.toLowerCase(),
                name:        el.getAttribute('name') || '',
                id:          el.id || '',
                placeholder: el.placeholder || '',
                hasValue:    el.value.length > 0,
                inViewport:  rect.top >= 0 && rect.bottom <= window.innerHeight
            });
        });

        document.querySelectorAll('label').forEach(el => {
            result.labels.push({
                text:    el.textContent.trim().substring(0, 80),
                htmlFor: el.htmlFor || ''
            });
        });

        document.querySelectorAll('button').forEach(el => {
            result.buttons.push({
                text: el.textContent.trim().substring(0, 60),
                type: el.getAttribute('type') || 'button'
            });
        });

        return result;
    }""")

    scroll_y = await page.evaluate("window.scrollY")

    return {
        "title":   title,
        "url":     url,
        "scroll_y": scroll_y,
        "inputs":  elements["inputs"],
        "labels":  elements["labels"],
        "buttons": elements["buttons"],
    }


# =============================================================================
# LLM INTEGRATION
# Sends the current page state to the LLM and gets back a tool call.
# The LLM returns JSON like: { "tool": "send_keys", "params": {...} }
# =============================================================================

SYSTEM_PROMPT = """You are a browser automation agent.

Your job is to complete a given task by controlling a web browser step by step.

Available tools:
- scroll          : params: { pixels }            - scroll the page
- send_keys       : params: { selector, text }    - type into a form field
- click_element   : params: { selector }          - click a button by CSS selector
- click_on_screen : params: { x, y }             - click at pixel coordinates
- double_click    : params: { x, y }             - double-click at coordinates
- navigate_to_url : params: { url }               - go to a URL
- take_screenshot : params: {}                    - capture the screen
- done            : params: { message }           - call this after the form is submitted

Rules:
1. Only respond with valid JSON. No extra text.
   Format: {"reasoning": "one sentence", "tool": "tool_name", "params": {...}}

2. All inputs shown to you exist in the page DOM. You can fill them with send_keys
   even if they say 'not in viewport'. Do not keep scrolling if inputs are listed.

3. Build CSS selectors from the input attributes:
   name='username' on an <input>  -> use selector "input[name='username']"
   name='bio' on a <textarea>     -> use selector "textarea[name='bio']"
   no name on a textarea          -> use selector "textarea"

4. Order: fill Name field, fill Description field, click Submit, then call done.

5. If send_keys returns FAILED, try a simpler selector next time.
"""


def ask_llm(task: str, page_context: dict, history: list) -> dict:
    """
    Send the current page state and action history to the LLM.
    Returns the next action the agent should take as a dict.
    """
    # build a readable description of what's on the page right now
    ctx_lines = [
        f"Title: {page_context['title']}",
        f"URL: {page_context['url']}",
        f"Scroll position: {page_context['scroll_y']}px",
        "",
        "Form elements found in page (all exist in DOM, can be filled directly):",
    ]
    for el in page_context["inputs"]:
        status = "in viewport" if el.get("inViewport") else "not in viewport but in DOM"
        filled = " [has value]" if el.get("hasValue") else " [empty]"
        ctx_lines.append(
            f"  - <{el['tag']}> name={el['name']!r} id={el['id']!r} "
            f"placeholder={el['placeholder']!r} ({status}){filled}"
        )

    ctx_lines.append("\nLabels:")
    for lb in page_context["labels"]:
        ctx_lines.append(f"  - {lb['text']!r} (for={lb['htmlFor']!r})")

    ctx_lines.append("\nButtons:")
    for btn in page_context["buttons"]:
        ctx_lines.append(f"  - {btn['text']!r} type={btn['type']!r}")

    # build history of what we've already done
    history_lines = ["Actions taken so far:"] if history else ["No actions yet."]
    for i, h in enumerate(history, 1):
        history_lines.append(f"  {i}. {h['tool']}({h['params']}) → {h['result']}")

    user_message = f"""TASK: {task}

CURRENT PAGE STATE:
{chr(10).join(ctx_lines)}

{chr(10).join(history_lines)}

What should you do next? Respond with ONLY valid JSON."""

    log("LLM", f"Asking {LLM_MODEL} what to do...")

    response = llm.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_message},
        ],
        temperature=0.1,  # low = consistent JSON output
        max_tokens=300,
    )

    raw = response.choices[0].message.content.strip()
    log("LLM", f"Response: {raw}")

    # remove markdown code fences if the model includes them
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # if there's extra text around the JSON, extract just the {...} part
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError(f"LLM returned non-JSON: {raw}")


# =============================================================================
# MAIN AGENT LOOP
# This is where everything runs together.
# At each step: read page → ask LLM → run tool → repeat
# =============================================================================

async def run_agent():
    log("START", "Website Automation Agent starting")
    log("START", f"Model      : {LLM_MODEL}")
    log("START", f"Target URL : {TARGET_URL}")
    log("START", f"Fill Name  : {FILL_NAME}")
    log("START", f"Fill Desc  : {FILL_DESC}")
    print()

    # this is the instruction given to the LLM at every step
    task = (
        f"Navigate to {TARGET_URL}. "
        f"Find the form and fill: "
        f"Name/Username field with '{FILL_NAME}', "
        f"Description/Bio field with '{FILL_DESC}'. "
        f"Then click Submit."
    )

    async with async_playwright() as pw:
        browser, page = await open_browser(pw)

        try:
            await take_screenshot(page, "00_start")

            # go to the page
            nav_result = await navigate_to_url(page, TARGET_URL)
            await take_screenshot(page, "01_page_loaded")

            # scroll down so the form is visible before we start the LLM loop
            log("THINK", "Scrolling to form area...")
            await scroll(page, 800)
            await page.wait_for_timeout(1000)

            # scroll the first input into view specifically
            try:
                first_input = page.locator("input, textarea").first
                await first_input.scroll_into_view_if_needed()
                await page.wait_for_timeout(500)
                log("OBSERVE", "Form inputs now in viewport")
            except Exception:
                log("THINK", "Could not scroll input into view, continuing anyway")

            await take_screenshot(page, "01b_form_visible")

            # keep a history of every action taken so the LLM has context
            history = [
                {"tool": "navigate_to_url", "params": {"url": TARGET_URL}, "result": nav_result}
            ]

            # main decision loop - runs until LLM says "done" or we hit MAX_STEPS
            for step in range(1, MAX_STEPS + 1):
                print()
                log("THINK", f"Step {step} of {MAX_STEPS}")

                # read current page state
                page_ctx = await get_page_context(page)

                # ask LLM what to do
                action = ask_llm(task, page_ctx, history)

                tool   = action.get("tool", "")
                params = action.get("params", {})
                reason = action.get("reasoning", "")

                log("THINK", f"Reasoning: {reason}")
                log("THINK", f"Action: {tool}({params})")

                # run the tool the LLM picked
                if tool == "done":
                    log("OUTPUT", f"Task complete: {params.get('message', '')}")
                    await take_screenshot(page, "final_done")
                    break

                elif tool == "navigate_to_url":
                    result = await navigate_to_url(page, params["url"])

                elif tool == "scroll":
                    result = await scroll(page, int(params.get("pixels", 400)))

                elif tool == "click_on_screen":
                    result = await click_on_screen(page, int(params["x"]), int(params["y"]))

                elif tool == "double_click":
                    result = await double_click(page, int(params["x"]), int(params["y"]))

                elif tool == "click_element":
                    result = await click_element(page, params.get("selector", "button"))

                elif tool == "send_keys":
                    result = await send_keys(
                        page,
                        params.get("selector", "input"),
                        params.get("text", "")
                    )

                elif tool == "take_screenshot":
                    result = await take_screenshot(page, f"step_{step:02d}")

                else:
                    result = f"Unknown tool: {tool}"
                    log("ERROR", result)

                # screenshot after every step for verification
                await take_screenshot(page, f"step_{step:02d}_{tool}")

                # add this step to history so LLM knows what happened
                history.append({
                    "tool":   tool,
                    "params": params,
                    "result": result,
                })

                log("OBSERVE", f"Result: {result}")
                await page.wait_for_timeout(800)

            else:
                log("ERROR", f"Stopped after {MAX_STEPS} steps without completing the task.")

            print()
            log("OUTPUT", "Agent done.")
            log("OUTPUT", f"Screenshots saved in: ./{SCREENSHOTS_DIR}/")
            log("OUTPUT", f"LLM calls made: {len(history)}")
            print()

        except Exception as err:
            log("ERROR", f"Something went wrong: {err}")
            await take_screenshot(page, "error_state")
            raise

        finally:
            await page.wait_for_timeout(3000)
            await browser.close()
            log("OUTPUT", "Browser closed.")


if __name__ == "__main__":
    asyncio.run(run_agent())
