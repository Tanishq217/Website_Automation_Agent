/**
 * Website Automation Agent — AI-Driven, JavaScript Version
 * ----------------------------------------------------------
 * Same logic as agent.py but written in Node.js.
 *
 * The LLM (meta/llama-3.1-8b via NVIDIA NIM) reads the page DOM
 * at each step and decides what to do next.
 * No selectors are hardcoded — the AI figures them out.
 *
 * Run with: node agent.js
 */

import { chromium, firefox, webkit } from 'playwright';
import { mkdir } from 'fs/promises';
import OpenAI from 'openai';
import dotenv from 'dotenv';
dotenv.config();

const NVIDIA_API_KEY = process.env.NVIDIA_API_KEY;
const LLM_MODEL      = process.env.LLM_MODEL      || 'meta/llama-3.1-8b-instruct';
const TARGET_URL     = process.env.TARGET_URL      || 'https://ui.shadcn.com/docs/forms/react-hook-form';
const FILL_NAME      = process.env.FILL_NAME       || 'Tanishq Singh';
const FILL_DESC      = process.env.FILL_DESCRIPTION || 'Auto-filled by AI agent!';
const BROWSER_TYPE   = process.env.BROWSER         || 'chromium';
const HEADLESS       = process.env.HEADLESS        === 'true';
const TIMEOUT_MS     = parseInt(process.env.TIMEOUT || '30000', 10);
const MAX_STEPS      = parseInt(process.env.MAX_STEPS || '20', 10);
const SCREENSHOTS_DIR = 'screenshots';

await mkdir(SCREENSHOTS_DIR, { recursive: true });

if (!NVIDIA_API_KEY) {
    console.error('[ERROR] NVIDIA_API_KEY not found in .env');
    process.exit(1);
}

// NVIDIA NIM is OpenAI-compatible, so we just point the client at their URL
const llm = new OpenAI({
    baseURL: 'https://integrate.api.nvidia.com/v1',
    apiKey:  NVIDIA_API_KEY,
});


// ---- logging ----------------------------------------------------------------

function log(tag, message) {
    const ts = new Date().toLocaleTimeString('en-GB');
    const colors = {
        START:   '\x1b[96m', THINK: '\x1b[93m', LLM: '\x1b[35m',
        TOOL:    '\x1b[92m', OBSERVE: '\x1b[94m',
        ERROR:   '\x1b[91m', OUTPUT: '\x1b[95m',
    };
    const reset = '\x1b[0m';
    console.log(`[${ts}] ${colors[tag] || ''}[${tag}]${reset}  ${message}`);
}


// ---- tools ------------------------------------------------------------------

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
    await page.waitForTimeout(2500);
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

    // try LLM's selector first, then fallbacks
    const fallbacks = [selector];
    if (selector.toLowerCase().includes('input'))    fallbacks.push("input[type='text']", 'input');
    if (selector.toLowerCase().includes('textarea')) fallbacks.push('textarea');

    for (const sel of fallbacks) {
        try {
            const elem = page.locator(sel).first();
            await elem.waitFor({ state: 'visible', timeout: 5000 });
            await elem.click({ clickCount: 3 });
            await page.waitForTimeout(200);
            await page.keyboard.type(text, { delay: 50 });
            await page.waitForTimeout(300);
            log('OBSERVE', `Typed into '${sel}' successfully`);
            return `SUCCESS: Typed '${text}' into element matching '${sel}'`;
        } catch {
            log('THINK', `Selector '${sel}' failed — trying next`);
        }
    }
    return `FAILED: Could not find any element matching '${selector}' or fallbacks.`;
}


// ---- page context extractor -------------------------------------------------

async function get_page_context(page) {
    const title   = await page.title();
    const url     = page.url();
    const scrollY = await page.evaluate(() => window.scrollY);

    const elements = await page.evaluate(() => {
        const inputs  = [];
        const labels  = [];
        const buttons = [];

        document.querySelectorAll('input, textarea').forEach(el => {
            inputs.push({
                tag:         el.tagName.toLowerCase(),
                type:        el.getAttribute('type') || '',
                name:        el.getAttribute('name') || '',
                id:          el.id || '',
                placeholder: el.placeholder || '',
                visible:     el.offsetParent !== null,
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


// ---- LLM decision maker -----------------------------------------------------

const SYSTEM_PROMPT = `You are an expert browser automation agent.

Your job is to complete a given task by controlling a web browser step by step.

You have these tools available:
- navigate_to_url  : params: { url }
- scroll           : params: { pixels }  (positivef = down, negative = up)
- click_on_screen  : params: { x, y }   (pixel coordinates)
- double_click     : params: { x, y }
- send_keys        : params: { selector, text }  (CSS selector + text to type)
- take_screenshot  : params: {}
- done             : params: { message }  (call this when the task is fully complete)

IMPORTANT RULES:
1. Always respond with ONLY valid JSON — no markdown, no explanation outside JSON.
2. Format: {"reasoning": "...", "tool": "tool_name", "params": {...}}
3. For send_keys, pick the MOST SPECIFIC selector from the page elements listed.
4. Scroll down to find elements that might be below the fold.
5. After filling all fields, click Submit, then call done.
6. If send_keys returned FAILED, try a different selector.`;

async function ask_llm(task, pageCtx, history) {
    const inputList = pageCtx.inputs.map(el =>
        `  - <${el.tag}> type=${JSON.stringify(el.type)} name=${JSON.stringify(el.name)} ` +
        `id=${JSON.stringify(el.id)} placeholder=${JSON.stringify(el.placeholder)} ` +
        `(${el.visible ? 'visible' : 'not visible'})`
    ).join('\n');

    const labelList  = pageCtx.labels.map(l  => `  - ${JSON.stringify(l.text)} for=${JSON.stringify(l.htmlFor)}`).join('\n');
    const buttonList = pageCtx.buttons.map(b => `  - ${JSON.stringify(b.text)} type=${b.type}`).join('\n');
    const histList   = history.length
        ? history.map((h, i) => `  ${i + 1}. ${h.tool}(${JSON.stringify(h.params)}) → ${h.result}`).join('\n')
        : '  No actions taken yet.';

    const userMessage = `TASK: ${task}

CURRENT PAGE STATE:
Title: ${pageCtx.title}
URL: ${pageCtx.url}
Scroll position: ${pageCtx.scroll_y}px

Form inputs and textareas:
${inputList || '  (none found — try scrolling)'}

Labels:
${labelList || '  (none found)'}

Buttons:
${buttonList || '  (none found)'}

Actions taken so far:
${histList}

What should you do next? Respond with ONLY valid JSON.`;

    log('LLM', `Asking ${LLM_MODEL} for next action...`);

    const response = await llm.chat.completions.create({
        model:       LLM_MODEL,
        messages:    [
            { role: 'system', content: SYSTEM_PROMPT },
            { role: 'user',   content: userMessage },
        ],
        temperature: 0.1,
        max_tokens:  300,
    });

    let raw = response.choices[0].message.content.trim();
    log('LLM', `Response: ${raw}`);

    // strip markdown fences if model adds them
    if (raw.startsWith('```')) {
        raw = raw.split('```')[1];
        if (raw.startsWith('json')) raw = raw.slice(4);
        raw = raw.trim();
    }

    // try to extract JSON if there's extra text
    const match = raw.match(/\{[\s\S]*\}/);
    if (match) raw = match[0];

    return JSON.parse(raw);
}


// ---- main agent loop --------------------------------------------------------

async function run_agent() {
    log('START', '=== AI-Driven Website Automation Agent (JS) ===');
    log('START', `LLM Model  : ${LLM_MODEL}`);
    log('START', `Target URL : ${TARGET_URL}`);
    log('START', `Fill Name  : ${FILL_NAME}`);
    log('START', `Fill Desc  : ${FILL_DESC}`);
    console.log();

    const task = `Navigate to ${TARGET_URL}. Find the form on the page and fill in: ` +
                 `Name/Username field with '${FILL_NAME}' and Description/Bio field with '${FILL_DESC}'. ` +
                 `Then click the Submit button.`;

    const { browser, page } = await open_browser();

    try {
        await take_screenshot(page, '00_start');
        const navResult = await navigate_to_url(page, TARGET_URL);
        await take_screenshot(page, '01_page_loaded');

        const history = [
            { tool: 'navigate_to_url', params: { url: TARGET_URL }, result: navResult }
        ];

        for (let step = 1; step <= MAX_STEPS; step++) {
            console.log();
            log('THINK', `--- Step ${step} of ${MAX_STEPS} ---`);

            const pageCtx = await get_page_context(page);
            const action  = await ask_llm(task, pageCtx, history);

            const { tool, params = {}, reasoning = '' } = action;

            log('THINK', `LLM reasoning: ${reasoning}`);
            log('THINK', `LLM chose: ${tool}(${JSON.stringify(params)})`);

            let result;

            if (tool === 'done') {
                log('OUTPUT', `LLM says done: ${params.message || ''}`);
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
        log('OUTPUT', 'Agent finished!');
        log('OUTPUT', `Screenshots saved in: ./${SCREENSHOTS_DIR}/`);
        log('OUTPUT', `Total LLM calls made: ${history.length}`);
        console.log();

    } catch (err) {
        log('ERROR', `Agent crashed: ${err.message}`);
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
