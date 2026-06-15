"""
Website Automation Agent — AI-Driven Version
---------------------------------------------
This is a real AI agent, not a script.

Instead of hardcoding which elements to click, we:
1. Take a screenshot + read the page DOM at each step
2. Send that info to an LLM and ask "what should I do next?"
3. The LLM returns a tool call as JSON
4. We execute it
5. Repeat until the LLM says "done"

This is called the ReAct pattern (Reasoning + Acting in a loop).

LLM used: meta/llama-3.1-8b-instruct via NVIDIA NIM API
Browser:  Playwright (Chromium)

Run with: python3 agent.py
"""

import os
import json
import time
import asyncio
import base64
from datetime import datetime
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv
from playwright.async_api import async_playwright, Page, Browser, TimeoutError as PlaywrightTimeout

# load .env before anything else
load_dotenv()

# --- config from environment ---
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
LLM_MODEL      = os.getenv("LLM_MODEL", "meta/llama-3.1-8b-instruct")
TARGET_URL     = os.getenv("TARGET_URL", "https://ui.shadcn.com/docs/forms/react-hook-form")
FILL_NAME      = os.getenv("FILL_NAME", "Tanishq Singh")
FILL_DESC      = os.getenv("FILL_DESCRIPTION", "Auto-filled by AI agent!")
BROWSER_TYPE   = os.getenv("BROWSER", "chromium")
HEADLESS       = os.getenv("HEADLESS", "false").lower() == "true"
TIMEOUT_MS     = int(os.getenv("TIMEOUT", "30000"))
MAX_STEPS      = int(os.getenv("MAX_STEPS", "20"))

# screenshots go here
SCREENSHOTS_DIR = Path("screenshots")
SCREENSHOTS_DIR.mkdir(exist_ok=True)

# --- NVIDIA NIM client (OpenAI-compatible API) ---
if not NVIDIA_API_KEY:
    print("[ERROR] NVIDIA_API_KEY not found in .env — please add it and try again.")
    exit(1)

llm = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=NVIDIA_API_KEY
)


# =============================================================================
# LOGGING — color-coded terminal output so you can follow what's happening
# =============================================================================

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
# THE 7 TOOLS — each does exactly one thing
# The LLM decides which one to call and with what params
# =============================================================================

async def take_screenshot(page: Page, label: str = "step") -> str:
    """Saves a PNG of the current browser view and returns the file path."""
    path = str(SCREENSHOTS_DIR / f"{label}_{int(time.time())}.png")
    await page.screenshot(path=path, full_page=False)
    log("TOOL", f"take_screenshot → {path}")
    return path


async def open_browser(pw) -> tuple[Browser, Page]:
    """Launches Chromium and returns (browser, page)."""
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
    """Goes to the given URL and waits for it to load."""
    log("TOOL", f"navigate_to_url → {url}")
    await page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_MS)
    await page.wait_for_timeout(2500)  # let React render
    title = await page.title()
    log("OBSERVE", f"Loaded: {title}")
    return f"Navigated to {url}. Page title: {title}"


async def scroll(page: Page, pixels: int) -> str:
    """Scrolls the page by 'pixels' (positive = down, negative = up)."""
    log("TOOL", f"scroll → {pixels}px")
    await page.evaluate(f"window.scrollBy(0, {pixels})")
    await page.wait_for_timeout(600)
    pos = await page.evaluate("window.scrollY")
    return f"Scrolled {pixels}px. Current scroll position: {pos}px"


async def click_on_screen(page: Page, x: int, y: int) -> str:
    """Clicks at exact pixel coordinates (x, y)."""
    log("TOOL", f"click_on_screen → ({x}, {y})")
    await page.mouse.click(x, y)
    await page.wait_for_timeout(400)
    return f"Clicked at ({x}, {y})"


async def double_click(page: Page, x: int, y: int) -> str:
    """Double-clicks at (x, y)."""
    log("TOOL", f"double_click → ({x}, {y})")
    await page.mouse.dblclick(x, y)
    await page.wait_for_timeout(400)
    return f"Double-clicked at ({x}, {y})"


async def send_keys(page: Page, selector: str, text: str) -> str:
    """
    Finds an element using the given CSS selector and types text into it.
    Tries the selector first. If that fails, tries common fallbacks.
    Returns a result string the LLM will read.
    """
    log("TOOL", f"send_keys → selector='{selector}' text='{text}'")

    # build a fallback list starting with whatever the LLM suggested
    fallbacks = [selector]

    # add some general fallbacks in case the LLM's selector is slightly off
    if "input" in selector.lower():
        fallbacks += ["input[type='text']", "input"]
    if "textarea" in selector.lower():
        fallbacks += ["textarea"]

    for sel in fallbacks:
        try:
            elem = page.locator(sel).first
            await elem.wait_for(state="visible", timeout=5000)
            await elem.click(click_count=3)  # triple-click selects all existing text
            await page.wait_for_timeout(200)
            await page.keyboard.type(text, delay=50)
            await page.wait_for_timeout(300)
            log("OBSERVE", f"Typed into '{sel}' successfully")
            return f"SUCCESS: Typed '{text}' into element matching '{sel}'"
        except Exception as e:
            log("THINK", f"Selector '{sel}' failed: {e}")

    return f"FAILED: Could not find any element matching '{selector}' or fallbacks. Try a different selector."


async def click_element(page: Page, selector: str) -> str:
    """
    Clicks an element found by CSS selector.
    Used for clicking the Submit button or any other clickable element.
    """
    log("TOOL", f"click_element → selector='{selector}'")
    try:
        elem = page.locator(selector).first
        await elem.wait_for(state="visible", timeout=8000)
        await elem.scroll_into_view_if_needed()
        await elem.click()
        await page.wait_for_timeout(1000)
        log("OBSERVE", f"Clicked element '{selector}' successfully")
        return f"SUCCESS: Clicked element matching '{selector}'"
    except Exception as e:
        log("THINK", f"click_element failed for '{selector}': {e}")
        return f"FAILED: Could not click '{selector}'. Error: {str(e)[:100]}"


# =============================================================================
# PAGE CONTEXT EXTRACTOR
# Gets relevant info from the current page to give to the LLM.
# The LLM uses this to decide which selectors to use — nothing is hardcoded.
# =============================================================================

async def get_page_context(page: Page) -> dict:
    """
    Reads the live DOM and returns a clean summary:
    - All inputs/textareas/buttons with their attributes
    - All labels on the page
    - Current scroll position
    This is what the LLM "sees" when deciding what to do.

    NOTE: 'inDOM' means the element exists in the HTML even if you haven't
    scrolled to it yet. You can still fill it with send_keys using its selector.
    """
    title = await page.title()
    url   = page.url

    elements = await page.evaluate("""() => {
        const result = { inputs: [], labels: [], buttons: [] };

        document.querySelectorAll('input, textarea').forEach(el => {
            const rect = el.getBoundingClientRect();
            result.inputs.push({
                tag:         el.tagName.toLowerCase(),
                type:        el.getAttribute('type') || '',
                name:        el.getAttribute('name') || '',
                id:          el.id || '',
                placeholder: el.placeholder || '',
                hasValue:    el.value.length > 0,
                inViewport:  rect.top >= 0 && rect.bottom <= window.innerHeight,
                inDOM:       true
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
        "title":    title,
        "url":      url,
        "scroll_y": scroll_y,
        "inputs":   elements["inputs"],
        "labels":   elements["labels"],
        "buttons":  elements["buttons"],
    }


# =============================================================================
# LLM DECISION MAKER
# This is what makes the agent "intelligent".
# It sends the current page state + task + history to the LLM,
# and the LLM returns the next tool to call.
# =============================================================================

SYSTEM_PROMPT = """You are an expert browser automation agent.

Your job is to complete tasks by controlling a web browser step by step.

Available tools:
- scroll          : params: { pixels }            — scroll the page
- send_keys       : params: { selector, text }    — type into a form field
- click_element   : params: { selector }          — click a button/link by CSS selector
- click_on_screen : params: { x, y }             — click at pixel coordinates
- double_click    : params: { x, y }             — double-click at coordinates
- navigate_to_url : params: { url }               — go to a URL
- take_screenshot : params: {}                    — capture the screen
- done            : params: { message }           — call ONLY after form is submitted

CRITICAL RULES — read carefully:
1. ONLY respond with valid JSON. No extra text, no markdown fences.
   Format: {"reasoning": "one sentence", "tool": "tool_name", "params": {...}}

2. ALL inputs listed to you EXIST IN THE DOM. You can fill them with send_keys
   even if they say 'not in viewport'. Do NOT keep scrolling once you see inputs listed.

3. Build CSS selectors from the input attributes shown:
   name='username' on an <input>  → use selector "input[name='username']"
   name='bio' on a <textarea>     → use selector "textarea[name='bio']"
   no name but it's a textarea    → use selector "textarea"

4. Order of operations:
   a) Fill the Name/Username field with send_keys
   b) Fill the Description/Bio field with send_keys
   c) Click the Submit button with click_element using selector "button[type='submit']"
   d) Call done

5. If send_keys returns FAILED, try a simpler selector on the next step.
"""

def ask_llm(task: str, page_context: dict, history: list) -> dict:
    """
    Sends the current situation to the LLM and gets back a tool call.
    Returns a dict like: { "reasoning": "...", "tool": "scroll", "params": {"pixels": 400} }
    """
    # build a readable context string from the page state
    ctx_lines = [
        f"Title: {page_context['title']}",
        f"URL: {page_context['url']}",
        f"Scroll position: {page_context['scroll_y']}px",
        "",
        "Inputs/textareas found in page DOM (inDOM=True means you CAN fill them with send_keys):",
    ]
    for el in page_context["inputs"]:
        viewport_note = "in viewport" if el.get("inViewport") else "not in viewport but EXISTS IN DOM"
        filled_note   = " [ALREADY HAS VALUE]" if el.get("hasValue") else " [EMPTY - needs filling]"
        ctx_lines.append(
            f"  - <{el['tag']}> name={el['name']!r} id={el['id']!r} "
            f"placeholder={el['placeholder']!r} ({viewport_note}){filled_note}"
        )

    ctx_lines.append("\nLabels:")
    for lb in page_context["labels"]:
        ctx_lines.append(f"  - {lb['text']!r} (for={lb['htmlFor']!r})")

    ctx_lines.append("\nButtons:")
    for btn in page_context["buttons"]:
        ctx_lines.append(f"  - {btn['text']!r} type={btn['type']!r}")

    # build action history
    history_lines = ["Actions taken so far:"] if history else ["No actions taken yet."]
    for i, h in enumerate(history, 1):
        history_lines.append(f"  {i}. {h['tool']}({h['params']}) → {h['result']}")

    user_message = f"""TASK: {task}

CURRENT PAGE STATE:
{chr(10).join(ctx_lines)}

{chr(10).join(history_lines)}

What should you do next? Remember: respond with ONLY valid JSON."""

    log("LLM", f"Asking {LLM_MODEL} for next action...")

    response = llm.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_message},
        ],
        temperature=0.1,   # low temperature = more predictable JSON output
        max_tokens=300,
    )

    raw = response.choices[0].message.content.strip()
    log("LLM", f"Response: {raw}")

    # strip markdown code fences if the model adds them anyway
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # if the LLM gives bad JSON, extract the first {...} block manually
        import re
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError(f"LLM returned non-JSON response: {raw}")


# =============================================================================
# MAIN AGENT LOOP — START → THINK → TOOL → OBSERVE → OUTPUT
# =============================================================================

async def run_agent():
    log("START", "=== AI-Driven Website Automation Agent ===")
    log("START", f"LLM Model  : {LLM_MODEL}")
    log("START", f"Target URL : {TARGET_URL}")
    log("START", f"Fill Name  : {FILL_NAME}")
    log("START", f"Fill Desc  : {FILL_DESC}")
    print()

    # the task description the LLM gets every step
    task = (
        f"Navigate to {TARGET_URL}. "
        f"Find the form on the page and fill in: "
        f"Name/Username field with '{FILL_NAME}' and "
        f"Description/Bio field with '{FILL_DESC}'. "
        f"Then click the Submit button."
    )

    async with async_playwright() as pw:
        browser, page = await open_browser(pw)

        try:
            # take an initial screenshot before starting the loop
            await take_screenshot(page, "00_start")

            # navigate to the target URL first (we always do this manually)
            nav_result = await navigate_to_url(page, TARGET_URL)
            await take_screenshot(page, "01_page_loaded")

            # scroll down to bring the form demo into view
            # 800px puts us past the intro docs and into the live demo section
            log("THINK", "Pre-scrolling to bring form into viewport...")
            await scroll(page, 800)
            await page.wait_for_timeout(1000)

            # try to scroll the first input into view so it's definitely visible
            # this way the LLM sees 'inViewport: true' and knows to fill it
            try:
                first_input = page.locator("input, textarea").first
                await first_input.scroll_into_view_if_needed()
                await page.wait_for_timeout(500)
                log("OBSERVE", "Scrolled first input into viewport")
            except Exception:
                log("THINK", "Could not pre-scroll input into view — LLM will handle")

            await take_screenshot(page, "01b_form_in_view")

            # history of everything the agent has done — LLM reads this each step
            history = [
                {"tool": "navigate_to_url", "params": {"url": TARGET_URL}, "result": nav_result}
            ]

            # THE MAIN LOOP
            for step in range(1, MAX_STEPS + 1):
                print()
                log("THINK", f"--- Step {step} of {MAX_STEPS} ---")

                # get the current state of the page
                page_ctx = await get_page_context(page)

                # ask the LLM what to do
                action = ask_llm(task, page_ctx, history)

                tool   = action.get("tool", "")
                params = action.get("params", {})
                reason = action.get("reasoning", "")

                log("THINK", f"LLM reasoning: {reason}")
                log("THINK", f"LLM chose: {tool}({params})")

                # execute whichever tool the LLM picked
                if tool == "done":
                    log("OUTPUT", f"LLM says we're done: {params.get('message', '')}")
                    await take_screenshot(page, f"final_done")
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
                    result = await send_keys(page, params.get("selector", "input"), params.get("text", ""))

                elif tool == "take_screenshot":
                    result = await take_screenshot(page, f"step_{step:02d}")

                else:
                    result = f"Unknown tool: {tool}"
                    log("ERROR", result)

                # take a screenshot after every action so we can see progress
                screenshot_path = await take_screenshot(page, f"step_{step:02d}_{tool}")

                # record what happened so the LLM knows next time
                history.append({
                    "tool":   tool,
                    "params": params,
                    "result": result,
                })

                log("OBSERVE", f"Result: {result}")

                # small pause between steps
                await page.wait_for_timeout(800)

            else:
                log("ERROR", f"Reached max steps ({MAX_STEPS}) without the LLM calling 'done'.")

            print()
            log("OUTPUT", "Agent finished!")
            log("OUTPUT", f"Screenshots saved in: ./{SCREENSHOTS_DIR}/")
            log("OUTPUT", f"Total LLM calls made: {len(history)}")
            print()

        except Exception as err:
            log("ERROR", f"Agent crashed: {err}")
            await take_screenshot(page, "error_state")
            raise

        finally:
            await page.wait_for_timeout(3000)
            await browser.close()
            log("OUTPUT", "Browser closed.")


if __name__ == "__main__":
    asyncio.run(run_agent())
