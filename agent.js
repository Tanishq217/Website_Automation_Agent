/**
 * Website Automation Agent - JavaScript Version
 * -----------------------------------------------
 * Same logic as agent.py but written in Node.js with Playwright.
 *
 * The agent reads the page DOM at each step, asks an LLM what to do,
 * and then does it. No selectors are hardcoded in the code.
 *
 * Run: node agent.js
 */

import { chromium, firefox, webkit } from 'playwright';
import { mkdir } from 'fs/promises';
import OpenAI from 'openai';
import dotenv from 'dotenv';
dotenv.config();

const NVIDIA_API_KEY  = process.env.NVIDIA_API_KEY;
const LLM_MODEL       = process.env.LLM_MODEL       || 'meta/llama-3.3-70b-instruct';
const TARGET_URL      = process.env.TARGET_URL       || 'https://ui.shadcn.com/docs/forms/react-hook-form';
const FILL_NAME       = process.env.FILL_NAME        || 'Tanishq Singh';
const FILL_DESC       = process.env.FILL_DESCRIPTION || 'Auto-filled by an AI agent!';
const BROWSER_TYPE    = process.env.BROWSER          || 'chromium';
const HEADLESS        = process.env.HEADLESS         === 'true';
const TIMEOUT_MS      = parseInt(process.env.TIMEOUT   || '30000', 10);
const MAX_STEPS       = parseInt(process.env.MAX_STEPS || '20',    10);
const SCREENSHOTS_DIR = 'screenshots';

await mkdir(SCREENSHOTS_DIR, { recursive: true });

if (!NVIDIA_API_KEY) {
    console.error('[ERROR] NVIDIA_API_KEY is missing from .env');
    process.exit(1);
}

// NVIDIA NIM uses the same API format as OpenAI, just a different base URL
const llm = new OpenAI({
    baseURL: 'https://integrate.api.nvidia.com/v1',
    apiKey:  NVIDIA_API_KEY,
});


// --- colored terminal output ---

function log(tag, message) {
    const ts = new Date().toLocaleTimeString('en-GB');
    const colors = {
        START:   '\x1b[96m', THINK:   '\x1b[93m', LLM:    '\x1b[35m',
        TOOL:    '\x1b[92m', OBSERVE: '\x1b[94m', ERROR:  '\x1b[91m',
        OUTPUT:  '\x1b[95m',
    };
    const reset = '\x1b[0m';
    console.log(`[${ts}] ${colors[tag] || ''}[${tag}]${reset}  ${message}`);
}


// =============================================================================
// TOOLS
// =============================================================================

async function take_screenshot(page, label = 'step') {
    const path = `${SCREENSHOTS_DIR}/${label}_${Date.now()}.png`;
    await page.screenshot({ path, fullPage: false });
    log('TOOL', `take_screenshot → ${path}`);
    return path;
}

async function open_browser() {
    log('TOOL', `open_browser → ${BROWSER_TYPE} (headless=${HEADLESS})`);
    const launchers = { chromium, firefox, webkit };
    const browser = await (launchers[BROWSER_TYPE] || chromium).launch({
        headless: HEADLESS,
        args: ['--start-maximized'],
    });
    const ctx  = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await ctx.newPage();
    log('OBSERVE', 'Browser ready');
    return { browser, page };
}

async function navigate_to_url(page, url) {
    log('TOOL', `navigate_to_url → ${url}`);
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: TIMEOUT_MS });
    await page.waitForTimeout(2500); // wait for JS to finish rendering
    const title = await page.title();
    log('OBSERVE', `Loaded: ${title}`);
    return `Navigated to ${url}. Page title: ${title}`;
}

async function scroll(page, pixels) {
    log('TOOL', `scroll → ${pixels}px`);
    await page.evaluate((px) => window.scrollBy(0, px), pixels);
    await page.waitForTimeout(600);
    const pos = await page.evaluate(() => window.scrollY);
    return `Scrolled ${pixels}px. Current position: ${pos}px`;
}

async function click_on_screen(page, x, y) {
    log('TOOL', `click_on_screen → (${x}, ${y})`);
    await page.mouse.click(x, y);
    await page.waitForTimeout(400);
    return `Clicked at (${x}, ${y})`;
}

async function double_click(page, x, y) {
    log('TOOL', `double_click → (${x}, ${y})`);
    await page.mouse.dblclick(x, y);
    await page.waitForTimeout(400);
    return `Double-clicked at (${x}, ${y})`;
}

async function send_keys(page, selector, text) {
    log('TOOL', `send_keys → selector='${selector}' text='${text}'`);

    // try what the LLM suggested first, then simpler fallbacks
    const fallbacks = [selector];
    if (selector.toLowerCase().includes('input'))    fallbacks.push("input[type='text']", 'input');
    if (selector.toLowerCase().includes('textarea')) fallbacks.push('textarea');

    for (const sel of fallbacks) {
        try {
            const elem = page.locator(sel).first();
            await elem.waitFor({ state: 'visible', timeout: 5000 });
            await elem.click({ clickCount: 3 }); // select existing text first
            await page.waitForTimeout(200);
            await page.keyboard.type(text, { delay: 50 }); // type with delay
            await page.waitForTimeout(300);
            log('OBSERVE', `Typed into '${sel}'`);
            return `SUCCESS: Typed '${text}' into element matching '${sel}'`;
        } catch {
            log('THINK', `Selector '${sel}' failed, trying next`);
        }
    }
    return `FAILED: Could not find element matching '${selector}'. Try a different selector.`;
}

async function click_element(page, selector) {
    // scrolls the element into view then clicks it - used for Submit buttons
    log('TOOL', `click_element → selector='${selector}'`);
    try {
        const elem = page.locator(selector).first();
        await elem.waitFor({ state: 'visible', timeout: 8000 });
        await elem.scrollIntoViewIfNeeded();
        await elem.click();
        await page.waitForTimeout(1000);
        log('OBSERVE', `Clicked '${selector}'`);
        return `SUCCESS: Clicked element matching '${selector}'`;
    } catch (e) {
        log('THINK', `click_element failed for '${selector}': ${e.message}`);
        return `FAILED: Could not click '${selector}'. Error: ${e.message.substring(0, 100)}`;
    }
}


// =============================================================================
// PAGE CONTEXT
// Reads all form elements from the page so the LLM knows what's there.
// =============================================================================

async function get_page_context(page) {
    const title   = await page.title();
    const url     = page.url();
    const scrollY = await page.evaluate(() => window.scrollY);

    const elements = await page.evaluate(() => {
        const inputs  = [];
        const labels  = [];
        const buttons = [];

        document.querySelectorAll('input, textarea').forEach(el => {
            const rect = el.getBoundingClientRect();
            inputs.push({
                tag:         el.tagName.toLowerCase(),
                name:        el.getAttribute('name') || '',
                id:          el.id || '',
                placeholder: el.placeholder || '',
                hasValue:    el.value.length > 0,
                inViewport:  rect.top >= 0 && rect.bottom <= window.innerHeight,
            });
        });

        document.querySelectorAll('label').forEach(el => {
            labels.push({
                text:    el.textContent.trim().substring(0, 80),
                htmlFor: el.htmlFor || '',
            });
        });

        document.querySelectorAll('button').forEach(el => {
            buttons.push({
                text: el.textContent.trim().substring(0, 60),
                type: el.getAttribute('type') || 'button',
            });
        });

        return { inputs, labels, buttons };
    });

    return { title, url, scroll_y: scrollY, ...elements };
}


// =============================================================================
// LLM INTEGRATION
// Sends the page state to the LLM and gets back a tool call as JSON.
// =============================================================================

const SYSTEM_PROMPT = `You are a browser automation agent.

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

2. All inputs shown to you exist in the page DOM. Fill them with send_keys
   even if they say 'not in viewport'. Do not keep scrolling if inputs are listed.

3. Build CSS selectors from the input attributes:
   name='username' on an input  -> use "input[name='username']"
   name='bio' on a textarea     -> use "textarea[name='bio']"
   textarea with no name        -> use "textarea"

4. Order: fill Name, fill Description, click Submit button, call done.

5. If send_keys returns FAILED, try a simpler selector next time.`;


async function ask_llm(task, pageCtx, history) {
    // describe all the form elements on the page
    const inputList = pageCtx.inputs.map(el =>
        `  - <${el.tag}> name=${JSON.stringify(el.name)} id=${JSON.stringify(el.id)} ` +
        `placeholder=${JSON.stringify(el.placeholder)} ` +
        `(${el.inViewport ? 'in viewport' : 'not in viewport but in DOM'})` +
        `${el.hasValue ? ' [has value]' : ' [empty]'}`
    ).join('\n');

    const labelList  = pageCtx.labels.map(l  => `  - ${JSON.stringify(l.text)} for=${JSON.stringify(l.htmlFor)}`).join('\n');
    const buttonList = pageCtx.buttons.map(b => `  - ${JSON.stringify(b.text)} type=${b.type}`).join('\n');
    const histList   = history.length
        ? history.map((h, i) => `  ${i + 1}. ${h.tool}(${JSON.stringify(h.params)}) → ${h.result}`).join('\n')
        : '  No actions yet.';

    const userMessage = `TASK: ${task}

CURRENT PAGE STATE:
Title: ${pageCtx.title}
URL: ${pageCtx.url}
Scroll position: ${pageCtx.scroll_y}px

Form elements found (all exist in DOM):
${inputList || '  (none found)'}

Labels:
${labelList || '  (none found)'}

Buttons:
${buttonList || '  (none found)'}

Actions taken so far:
${histList}

What should you do next? Respond with ONLY valid JSON.`;

    log('LLM', `Asking ${LLM_MODEL} what to do...`);

    const response = await llm.chat.completions.create({
        model:       LLM_MODEL,
        messages:    [
            { role: 'system', content: SYSTEM_PROMPT },
            { role: 'user',   content: userMessage },
        ],
        temperature: 0.1,  // low = consistent JSON output
        max_tokens:  300,
    });

    let raw = response.choices[0].message.content.trim();
    log('LLM', `Response: ${raw}`);

    // remove markdown code fences if the model includes them
    if (raw.startsWith('```')) {
        raw = raw.split('```')[1];
        if (raw.startsWith('json')) raw = raw.slice(4);
        raw = raw.trim();
    }

    // extract just the JSON object in case there's extra text
    const match = raw.match(/\{[\s\S]*\}/);
    if (match) raw = match[0];

    return JSON.parse(raw);
}


// =============================================================================
// MAIN LOOP
// At each step: read page → ask LLM → run tool → repeat
// =============================================================================

async function run_agent() {
    log('START', 'Website Automation Agent starting');
    log('START', `Model      : ${LLM_MODEL}`);
    log('START', `Target URL : ${TARGET_URL}`);
    log('START', `Fill Name  : ${FILL_NAME}`);
    log('START', `Fill Desc  : ${FILL_DESC}`);
    console.log();

    const task = `Navigate to ${TARGET_URL}. Find the form and fill: ` +
                 `Name/Username field with '${FILL_NAME}', ` +
                 `Description/Bio field with '${FILL_DESC}'. ` +
                 `Then click Submit.`;

    const { browser, page } = await open_browser();

    try {
        await take_screenshot(page, '00_start');
        const navResult = await navigate_to_url(page, TARGET_URL);
        await take_screenshot(page, '01_page_loaded');

        // scroll to bring form into view before starting the LLM loop
        log('THINK', 'Scrolling to form area...');
        await scroll(page, 800);
        await page.waitForTimeout(1000);

        try {
            const firstInput = page.locator('input, textarea').first();
            await firstInput.scrollIntoViewIfNeeded();
            await page.waitForTimeout(500);
            log('OBSERVE', 'Form inputs now in viewport');
        } catch {
            log('THINK', 'Could not scroll input into view, continuing anyway');
        }

        await take_screenshot(page, '01b_form_visible');

        // history tracks every action so the LLM has full context each step
        const history = [
            { tool: 'navigate_to_url', params: { url: TARGET_URL }, result: navResult }
        ];

        for (let step = 1; step <= MAX_STEPS; step++) {
            console.log();
            log('THINK', `Step ${step} of ${MAX_STEPS}`);

            const pageCtx = await get_page_context(page);
            const action  = await ask_llm(task, pageCtx, history);

            const { tool, params = {}, reasoning = '' } = action;

            log('THINK', `Reasoning: ${reasoning}`);
            log('THINK', `Action: ${tool}(${JSON.stringify(params)})`);

            let result;

            if (tool === 'done') {
                log('OUTPUT', `Task complete: ${params.message || ''}`);
                await take_screenshot(page, 'final_done');
                break;
            } else if (tool === 'navigate_to_url') {
                result = await navigate_to_url(page, params.url);
            } else if (tool === 'scroll') {
                result = await scroll(page, parseInt(params.pixels, 10));
            } else if (tool === 'click_on_screen') {
                result = await click_on_screen(page, params.x, params.y);
            } else if (tool === 'double_click') {
                result = await double_click(page, params.x, params.y);
            } else if (tool === 'click_element') {
                result = await click_element(page, params.selector || 'button');
            } else if (tool === 'send_keys') {
                result = await send_keys(page, params.selector, params.text);
            } else if (tool === 'take_screenshot') {
                result = await take_screenshot(page, `step_${String(step).padStart(2, '0')}`);
            } else {
                result = `Unknown tool: ${tool}`;
                log('ERROR', result);
            }

            await take_screenshot(page, `step_${String(step).padStart(2, '0')}_${tool}`);
            history.push({ tool, params, result });
            log('OBSERVE', `Result: ${result}`);
            await page.waitForTimeout(800);
        }

        console.log();
        log('OUTPUT', 'Agent done.');
        log('OUTPUT', `Screenshots saved in: ./${SCREENSHOTS_DIR}/`);
        log('OUTPUT', `LLM calls made: ${history.length}`);
        console.log();

    } catch (err) {
        log('ERROR', `Something went wrong: ${err.message}`);
        await take_screenshot(page, 'error_state');
        throw err;
    } finally {
        await page.waitForTimeout(3000);
        await browser.close();
        log('OUTPUT', 'Browser closed.');
    }
}

run_agent().catch(err => {
    console.error('Fatal error:', err);
    process.exit(1);
});
