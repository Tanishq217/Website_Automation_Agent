/**
 * Website Automation Agent — JavaScript Version
 * -----------------------------------------------
 * Same logic as agent.py but written in Node.js.
 * Uses the same Playwright library under the hood.
 *
 * Run it with: node agent.js
 */

import { chromium, firefox, webkit } from 'playwright';
import { createWriteStream } from 'fs';
import { mkdir } from 'fs/promises';
import path from 'path';
import dotenv from 'dotenv';
dotenv.config();

// pull config from .env file (or use sensible defaults)
const TARGET_URL   = process.env.TARGET_URL    || 'https://ui.shadcn.com/docs/forms/react-hook-form';
const FILL_NAME    = process.env.FILL_NAME     || 'Tanishq Singh';
const FILL_DESC    = process.env.FILL_DESCRIPTION || 'This form was auto-filled by a Playwright automation agent!';
const BROWSER_TYPE = process.env.BROWSER       || 'chromium';
const HEADLESS     = process.env.HEADLESS      === 'true';
const TIMEOUT_MS   = parseInt(process.env.TIMEOUT || '30000', 10);

const SCREENSHOTS_DIR = 'screenshots';

// make sure the screenshots folder exists
await mkdir(SCREENSHOTS_DIR, { recursive: true });


// -------------------------------------------------------------------
// LOGGING — same colored output style as the Python version
// -------------------------------------------------------------------

function log(tag, message) {
    const ts = new Date().toLocaleTimeString('en-GB');
    const colors = {
        START:   '\x1b[96m',
        THINK:   '\x1b[93m',
        TOOL:    '\x1b[92m',
        OBSERVE: '\x1b[94m',
        ERROR:   '\x1b[91m',
        OUTPUT:  '\x1b[95m',
    };
    const reset = '\x1b[0m';
    const color = colors[tag] || '';
    console.log(`[${ts}] ${color}[${tag}]${reset}  ${message}`);
}


// -------------------------------------------------------------------
// TOOL: take_screenshot
// -------------------------------------------------------------------

async function take_screenshot(page, label = 'screenshot') {
    const filename = path.join(SCREENSHOTS_DIR, `${label}_${Date.now()}.png`);
    await page.screenshot({ path: filename, fullPage: false });
    log('TOOL', `take_screenshot → saved to ${filename}`);
    return filename;
}


// -------------------------------------------------------------------
// TOOL: open_browser
// -------------------------------------------------------------------

async function open_browser() {
    log('TOOL', `open_browser → launching ${BROWSER_TYPE} (headless=${HEADLESS})`);

    const launchers = { chromium, firefox, webkit };
    const launcher  = launchers[BROWSER_TYPE] || chromium;

    const browser = await launcher.launch({
        headless: HEADLESS,
        args: ['--start-maximized'],
    });

    const context = await browser.newContext({
        viewport: { width: 1440, height: 900 },
        userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0',
    });

    const page = await context.newPage();
    log('OBSERVE', 'Browser launched and new page created');
    return { browser, page };
}


// -------------------------------------------------------------------
// TOOL: navigate_to_url
// -------------------------------------------------------------------

async function navigate_to_url(page, url) {
    log('TOOL', `navigate_to_url → ${url}`);
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: TIMEOUT_MS });
    await page.waitForTimeout(2000);
    log('OBSERVE', `Page loaded: ${await page.title()}`);
}


// -------------------------------------------------------------------
// TOOL: scroll
// -------------------------------------------------------------------

async function scroll(page, pixels = 400) {
    log('TOOL', `scroll → ${pixels}px`);
    await page.evaluate((px) => window.scrollBy(0, px), pixels);
    await page.waitForTimeout(500);
}


// -------------------------------------------------------------------
// TOOL: click_on_screen
// -------------------------------------------------------------------

async function click_on_screen(page, x, y) {
    log('TOOL', `click_on_screen → (${x}, ${y})`);
    await page.mouse.click(x, y);
    await page.waitForTimeout(300);
}


// -------------------------------------------------------------------
// TOOL: double_click
// -------------------------------------------------------------------

async function double_click(page, x, y) {
    log('TOOL', `double_click → (${x}, ${y})`);
    await page.mouse.dblclick(x, y);
    await page.waitForTimeout(300);
}


// -------------------------------------------------------------------
// TOOL: send_keys
// -------------------------------------------------------------------

async function send_keys(page, text, selector = null) {
    if (selector) {
        log('TOOL', `send_keys → '${text}' into selector: ${selector}`);
        await page.locator(selector).fill(text);
    } else {
        log('TOOL', `send_keys → '${text}' (typing into focused element)`);
        await page.keyboard.type(text, { delay: 60 });
    }
}


// -------------------------------------------------------------------
// SMART ELEMENT FINDER
// Tries a list of selectors — stops at first one that works
// -------------------------------------------------------------------

async function find_element(page, selectors, description = 'element') {
    for (const selector of selectors) {
        try {
            const locator = page.locator(selector).first();
            await locator.waitFor({ state: 'visible', timeout: 5000 });
            log('OBSERVE', `Found '${description}' using selector: ${selector}`);
            return locator;
        } catch {
            log('THINK', `Selector not found: ${selector} — trying next...`);
        }
    }
    return null;
}


// -------------------------------------------------------------------
// THE MAIN AGENT — START → THINK → TOOL → OBSERVE → OUTPUT
// -------------------------------------------------------------------

async function run_agent() {
    log('START', 'Website Automation Agent (JS) is starting up');
    log('START', `Target URL : ${TARGET_URL}`);
    log('START', `Fill Name  : ${FILL_NAME}`);
    log('START', `Fill Desc  : ${FILL_DESC}`);
    console.log();

    // STEP 1: Open browser
    log('THINK', 'Step 1 — Open a browser window');
    const { browser, page } = await open_browser();

    try {
        // STEP 2: Navigate
        log('THINK', 'Step 2 — Navigate to the target page');
        await navigate_to_url(page, TARGET_URL);
        await take_screenshot(page, '01_page_loaded');

        // STEP 3: Scroll to find the live demo form
        log('THINK', 'Step 3 — Scrolling down to find the form demo area');
        await scroll(page, 800);
        await take_screenshot(page, '02_after_scroll');

        // STEP 4: Find and fill the Name input
        log('THINK', 'Step 4 — Looking for the Name field');
        const nameField = await find_element(page, [
            'input#name',
            "input[name='username']",
            "input[placeholder*='shadcn']",
            'form input[type="text"]:first-of-type',
            'input[type="text"]',
        ], 'Name field');

        if (nameField) {
            log('THINK', 'Step 5 — Clicking and filling the Name field');
            await nameField.click();
            await page.waitForTimeout(300);
            await nameField.selectText();
            await send_keys(page, FILL_NAME);
            await take_screenshot(page, '03_name_filled');
            log('OBSERVE', `Name field filled with: '${FILL_NAME}'`);
        } else {
            log('ERROR', 'Could not find the Name field');
            await take_screenshot(page, '03_name_not_found');
        }

        // STEP 5: Find and fill the Description textarea
        log('THINK', 'Step 6 — Looking for the Description field');
        const descField = await find_element(page, [
            'textarea#bio',
            "textarea[name='bio']",
            'textarea',
            "input[name='description']",
        ], 'Description field');

        if (descField) {
            log('THINK', 'Step 7 — Clicking and filling the Description field');
            await descField.click();
            await page.waitForTimeout(300);
            await descField.selectText();
            await send_keys(page, FILL_DESC);
            await take_screenshot(page, '04_desc_filled');
            log('OBSERVE', `Description field filled with: '${FILL_DESC}'`);
        } else {
            log('ERROR', 'Could not find the Description field');
            await take_screenshot(page, '04_desc_not_found');
        }

        // STEP 6: Submit the form
        log('THINK', 'Step 8 — Looking for Submit button');
        await scroll(page, 300);

        const submitBtn = await find_element(page, [
            "button[type='submit']",
            'form button:last-of-type',
            "button:has-text('Submit')",
        ], 'Submit button');

        if (submitBtn) {
            log('THINK', 'Step 9 — Clicking the Submit button');
            await submitBtn.click();
            await page.waitForTimeout(1500);
            await take_screenshot(page, '05_after_submit');
            log('OBSERVE', 'Form submitted!');
        } else {
            log('ERROR', 'Could not find submit button');
            await take_screenshot(page, '05_submit_not_found');
        }

        console.log();
        log('OUTPUT', 'Agent finished successfully!');
        log('OUTPUT', `Screenshots saved in: ./${SCREENSHOTS_DIR}/`);
        console.log();

    } catch (err) {
        log('ERROR', `Something went wrong: ${err.message}`);
        await take_screenshot(page, 'error_state');
        throw err;
    } finally {
        await page.waitForTimeout(3000);
        await browser.close();
        log('OUTPUT', 'Browser closed. Agent is done.');
    }
}

// kick it off
run_agent().catch((err) => {
    console.error('Agent crashed:', err);
    process.exit(1);
});
