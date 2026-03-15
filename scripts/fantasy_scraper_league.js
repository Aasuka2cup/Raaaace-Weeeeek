/**
 * F1 Fantasy League Scraper
 *
 * Scrapes team lineups and points composition from a public F1 Fantasy league
 * leaderboard. Extracts each team's lineup (5 drivers + 2 constructors) and
 * points breakdown for a specific race (Chinese Grand Prix).
 *
 * Reference: thirdparty/fantasy-data/fantasy_scraper_V3.1.js
 *
 * Usage:
 *   # First install Playwright browsers (one-time):
 *   cd thirdparty/fantasy-data && npx playwright install chromium
 *
 *   # Then run from scripts directory:
 *   cd scripts && node fantasy_scraper_league.js
 *
 *   # To run without browser window: add --headless
 *   # To save page HTML when no teams found: add --debug
 *   # Uses persistent profile by default (saves login). Add --no-profile for fresh browser.
 *
 * Output: data/raaaace_weeeeek/league_871710_china.json
 */

const path = require('path');

// Resolve playwright from thirdparty/fantasy-data
const playwrightPath = path.resolve(__dirname, '..', 'thirdparty', 'fantasy-data', 'node_modules', 'playwright');
const { chromium } = require(playwrightPath);

const fs = require('fs').promises;

const BASE_URL = 'https://fantasy.formula1.com/en/';
const LEAGUE_URL = 'https://fantasy.formula1.com/en/leagues/leaderboard/public/871710';
const TARGET_RACE = 'China'; // Chinese Grand Prix (Round 2)
const OUTPUT_DIR = path.join(__dirname, '..', 'data', 'raaaace_weeeeek');
const OUTPUT_FILE = path.join(OUTPUT_DIR, 'league_871710_china.json');

const USER_DATA_DIR = path.join(__dirname, '..', 'data', 'playwright-fantasy-profile');

const CONFIG = {
    BROWSER_HEADLESS: false, // Set true to run without window; use --headless to override
    USE_PERSISTENT_PROFILE: true, // Use saved login; set false or --no-profile for fresh browser
    DELAYS: {
        PAGE_LOAD: 5000,
        POPUP_WAIT: 3000,
        BETWEEN_TEAMS: 2000,
        POPUP_CLOSE: 1000,
    },
};

/**
 * Handle cookie consent dialog (same as fantasy_scraper_V3.1.js).
 * Must run before navigating to league URL – the popup blocks the page.
 */
async function handleCookieConsent(page) {
    const iframeSelectors = ['#sp_message_iframe_1336275', 'iframe[id*="sp_message"]', 'iframe[title*="cookie"], iframe[title*="Cookie"]'];
    for (const sel of iframeSelectors) {
        try {
            const iframeElement = await page.$(sel);
            if (iframeElement) {
                const iframe = await iframeElement.contentFrame();
                if (iframe) {
                    await iframe.click('button:has-text("Essential only cookies")', { timeout: 5000 });
                    console.log('✅ Cookie consent handled');
                    await page.waitForTimeout(2000);
                    return;
                }
            }
        } catch (e) {}
    }
    console.log('ℹ️  No cookie consent dialog');
}

/**
 * Select the Chinese Grand Prix on the league page dropdown.
 * The page has a dropdown showing "Overall", "Australian Grand Prix", "Chinese Grand Prix".
 * Must click the trigger to open, then click "Chinese Grand Prix" in the list.
 */
async function selectChineseGrandPrix(page) {
    try {
        // Click the dropdown trigger to open the menu (Overall / Australian GP / Chinese GP)
        const combobox = page.getByRole('combobox');
        if ((await combobox.count()) > 0) {
            await combobox.first().click();
        } else {
            await page.getByText(/Grand Prix/, { exact: false }).first().click();
        }
        await page.waitForTimeout(500);

        // Click "Chinese Grand Prix" in the opened dropdown list
        await page.getByRole('option', { name: 'Chinese Grand Prix' }).click();
        console.log('✅ Selected Chinese Grand Prix from dropdown');
        await page.waitForTimeout(CONFIG.DELAYS.POPUP_WAIT);
        return true;
    } catch (e) {
        // Fallback: click by text (trigger may not have combobox role)
        try {
            await page.getByText(/Grand Prix/, { exact: false }).first().click();
            await page.waitForTimeout(500);
            await page.getByText('Chinese Grand Prix').click();
            console.log('✅ Selected Chinese Grand Prix from dropdown (fallback)');
            await page.waitForTimeout(CONFIG.DELAYS.POPUP_WAIT);
            return true;
        } catch (e2) {}
    }

    console.log('⚠️  Could not find China dropdown option. Try --debug to inspect.');
    return false;
}

/**
 * Close popup window
 */
async function closePopup(page) {
    try {
        const closeButton = await page.$('.si-popup__close');
        if (closeButton) {
            await closeButton.click();
            await page.waitForTimeout(CONFIG.DELAYS.POPUP_CLOSE);
            return;
        }
    } catch (e) {}
    await page.keyboard.press('Escape');
    await page.waitForTimeout(CONFIG.DELAYS.POPUP_CLOSE);
}

/**
 * Extract points breakdown from a race accordion element (China).
 * Used for detailed event-level breakdown if needed.
 */
async function extractRacePointsBreakdown(raceElement) {
    const breakdown = [];
    try {
        const tables = await raceElement.$$('table.si-tbl');
        for (const table of tables) {
            const rows = await table.$$('tbody tr');
            for (const row of rows) {
                const cells = await row.$$('td');
                if (cells.length >= 3) {
                    const eventName = (await cells[0].textContent())?.trim() || '';
                    const pointsText = (await cells[2].textContent())?.trim() || '';
                    const isNegative = await cells[2].evaluate((cell) => cell.classList.contains('si-negative'));

                    let points = 0;
                    if (pointsText && pointsText !== '-') {
                        const pointsMatch = pointsText.match(/(-?)(\d+)/);
                        if (pointsMatch) {
                            points = parseInt(pointsMatch[2]);
                            if (isNegative || pointsMatch[1] === '-') points = -Math.abs(points);
                        }
                    }
                    if (eventName) {
                        breakdown.push({ event: eventName, points });
                    }
                }
            }
        }
    } catch (e) {
        console.log(`   ⚠️  Error extracting breakdown: ${e.message}`);
    }
    return breakdown;
}

/**
 * Extract lineup (drivers + constructors) with individual China points from team popup.
 * Team detail shows: George Russell 42 PTS, Charles Leclerc 28 PTS, Mercedes 52 PTS, etc.
 */
async function extractTeamDataFromPopup(page, rank) {
    const popup = await page.$('.si-popup__container');
    if (!popup) return null;

    const teamData = await page.evaluate(() => {
        const popup = document.querySelector('.si-popup__container');
        if (!popup) return null;

        const constructorNames = ['McLaren', 'Red Bull', 'Ferrari', 'Mercedes', 'Aston Martin', 'Alpine', 'Haas', 'Williams', 'Sauber', 'Racing Bulls', 'Audi', 'Cadillac'];

        const drivers = [];
        const constructors = [];
        let teamName = 'Unknown Team';
        let manager = '';
        let totalPoints = 0;
        let costCap = '';
        let limitless = false;
        let turboDriver = null;

        // Team name and manager
        const teamNameEl = popup.querySelector('.si-player__name, [class*="player__name"], [class*="team__name"], h2, h3');
        if (teamNameEl) teamName = teamNameEl.textContent.trim();

        const fullText = popup.innerText || '';

        // Manager (often below team name)
        const managerMatch = fullText.match(/Manager[:\s]+([A-Za-z\s]+)/i) || fullText.match(/(?:^|\n)([A-Za-z]+\s+[A-Za-z]+)\s*(?:\n|$)/);
        if (managerMatch) manager = managerMatch[1].trim();

        // Total points: "237 PTS" or "237 Pts"
        const totalMatch = fullText.match(/(\d+)\s*PTS?\s*(?:$|\n)/i);
        if (totalMatch) totalPoints = parseInt(totalMatch[1]);

        // Cost cap: "$0.0M" or similar
        const costMatch = fullText.match(/\$([\d.]+)M?/);
        if (costMatch) costCap = `$${costMatch[1]}M`;

        limitless = /limitless/i.test(fullText);

        // Find rows with "Name XX PTS" pattern - driver/constructor list items
        const rows = popup.querySelectorAll('[class*="si-"] [class*="list"], [class*="driCon"], [class*="row"], li, [role="listitem"]');
        const seenDrivers = new Set();
        const seenConstructors = new Set();

        for (const row of rows) {
            const text = (row.textContent || '').trim();
            const ptsMatch = text.match(/(\d+)\s*PTS?/i);
            if (!ptsMatch) continue;

            const points = parseInt(ptsMatch[1]);
            const namePart = text.replace(/\d+\s*PTS?.*/i, '').replace(/\s*2X\s*/i, '').trim();

            if (constructorNames.some((c) => namePart.includes(c))) {
                const match = constructorNames.find((c) => namePart.includes(c));
                if (match && !seenConstructors.has(match)) {
                    seenConstructors.add(match);
                    constructors.push({ name: match, points });
                }
            } else if (namePart && namePart.length > 3 && /^[A-Za-z]/.test(namePart) && !/^\d+$/.test(namePart)) {
                if (!seenDrivers.has(namePart) && drivers.length < 5) {
                    seenDrivers.add(namePart);
                    const isTurbo = /2X|turbo/i.test(text);
                    drivers.push({ name: namePart, points, turbo: isTurbo });
                    if (isTurbo) turboDriver = namePart;
                }
            }
        }

        // Fallback: regex from full text for names + points
        if (drivers.length < 5) {
            const driverNames = ['George Russell', 'Charles Leclerc', 'Lewis Hamilton', 'Kimi Antonelli', 'Lando Norris', 'Max Verstappen', 'Oscar Piastri', 'Carlos Sainz', 'Sergio Pérez', 'Fernando Alonso', 'Lance Stroll', 'Pierre Gasly', 'Esteban Ocon', 'Nico Hülkenberg', 'Kevin Magnussen', 'Valtteri Bottas', 'Guanyu Zhou', 'Alexander Albon', 'Logan Sargeant', 'Yuki Tsunoda', 'Daniel Ricciardo', 'Oliver Bearman', 'Isack Hadjar', 'Gabriel Bortoleto', 'Liam Lawson', 'Franco Colapinto', 'Jack Doohan', 'Arvid Lindblad'];
            for (const d of driverNames) {
                const re = new RegExp(d.replace(/\s+/g, '\\s+') + '[^\\d]*(\\d+)\\s*PTS?', 'i');
                const m = fullText.match(re);
                if (m && !seenDrivers.has(d)) {
                    seenDrivers.add(d);
                    drivers.push({ name: d, points: parseInt(m[1]), turbo: false });
                }
            }
        }
        for (const c of constructorNames) {
            const re = new RegExp(c.replace(/\s+/g, '\\s+') + '[^\\d]*(\\d+)\\s*PTS?', 'i');
            const m = fullText.match(re);
            if (m && !seenConstructors.has(c)) {
                seenConstructors.add(c);
                constructors.push({ name: c, points: parseInt(m[1]) });
            }
        }

        return { teamName, manager, totalPoints, costCap, limitless, turboDriver, drivers, constructors };
    });

    if (!teamData) return null;

    return {
        rank,
        teamName: teamData.teamName,
        manager: teamData.manager,
        totalPoints: teamData.totalPoints,
        costCap: teamData.costCap,
        limitless: teamData.limitless,
        turboDriver: teamData.turboDriver,
        drivers: teamData.drivers,
        constructors: teamData.constructors,
        chinaGrandPrix: {
            totalPoints: teamData.totalPoints,
            drivers: teamData.drivers,
            constructors: teamData.constructors,
        },
    };
}

/**
 * Extract team data from a team page (when navigation occurs instead of popup).
 * Same structure as popup: drivers/constructors with individual points.
 */
async function extractTeamDataFromPage(page, rank) {
    const teamData = await page.evaluate(() => {
        const root = document.querySelector('.si-main__container, main') || document.body;
        const constructorNames = ['McLaren', 'Red Bull', 'Ferrari', 'Mercedes', 'Aston Martin', 'Alpine', 'Haas', 'Williams', 'Sauber', 'Racing Bulls', 'Audi', 'Cadillac'];

        const drivers = [];
        const constructors = [];
        let teamName = 'Unknown Team';
        let manager = '';
        let totalPoints = 0;
        let costCap = '';
        const fullText = root.innerText || '';

        const teamNameEl = root.querySelector('.si-player__name, [class*="team__name"], h1, h2');
        if (teamNameEl) teamName = teamNameEl.textContent.trim();

        const totalMatch = fullText.match(/(\d+)\s*PTS?\s*(?:$|\n)/i);
        if (totalMatch) totalPoints = parseInt(totalMatch[1]);

        const costMatch = fullText.match(/\$([\d.]+)M?/);
        if (costMatch) costCap = `$${costMatch[1]}M`;

        const driverNames = ['George Russell', 'Charles Leclerc', 'Lewis Hamilton', 'Kimi Antonelli', 'Lando Norris', 'Max Verstappen', 'Oscar Piastri', 'Carlos Sainz', 'Sergio Pérez', 'Fernando Alonso', 'Lance Stroll', 'Pierre Gasly', 'Esteban Ocon', 'Nico Hülkenberg', 'Kevin Magnussen', 'Valtteri Bottas', 'Guanyu Zhou', 'Alexander Albon', 'Logan Sargeant', 'Yuki Tsunoda', 'Daniel Ricciardo', 'Oliver Bearman', 'Isack Hadjar', 'Gabriel Bortoleto', 'Liam Lawson', 'Franco Colapinto', 'Jack Doohan', 'Arvid Lindblad'];

        const seenDrivers = new Set();
        const seenConstructors = new Set();

        for (const d of driverNames) {
            const re = new RegExp(d.replace(/\s+/g, '\\s+') + '[^\\d]*(\\d+)\\s*PTS?', 'i');
            const m = fullText.match(re);
            if (m && !seenDrivers.has(d)) {
                seenDrivers.add(d);
                drivers.push({ name: d, points: parseInt(m[1]), turbo: /2X|turbo/i.test(fullText) });
            }
        }
        for (const c of constructorNames) {
            const re = new RegExp(c.replace(/\s+/g, '\\s+') + '[^\\d]*(\\d+)\\s*PTS?', 'i');
            const m = fullText.match(re);
            if (m && !seenConstructors.has(c)) {
                seenConstructors.add(c);
                constructors.push({ name: c, points: parseInt(m[1]) });
            }
        }

        return { teamName, manager, totalPoints, costCap, limitless: /limitless/i.test(fullText), turboDriver: null, drivers, constructors };
    });

    if (!teamData) return null;

    return {
        rank,
        teamName: teamData.teamName,
        manager: teamData.manager,
        totalPoints: teamData.totalPoints,
        costCap: teamData.costCap,
        limitless: teamData.limitless,
        turboDriver: teamData.turboDriver,
        drivers: teamData.drivers,
        constructors: teamData.constructors,
        chinaGrandPrix: {
            totalPoints: teamData.totalPoints,
            drivers: teamData.drivers,
            constructors: teamData.constructors,
        },
    };
}

/**
 * Find clickable team rows on the league leaderboard.
 * League page may use: team links, table rows, or list items.
 */
async function findTeamRows(page) {
    const selectors = [
        'a[href*="/team/"]',
        'a[href*="team"]',
        '[class*="leaderboard"] a',
        '[class*="leaderboard"] [class*="card"], [class*="leaderboard"] [class*="row"]',
        '.si-main__container a[href*="team"]',
        'table tbody tr',
        '[class*="leaderboard"] tr',
        '[class*="league"] tr',
        '[class*="si-"] [class*="list-item"]',
        '[class*="si-"] [class*="card"]',
    ];

    for (const sel of selectors) {
        try {
            const elements = await page.$$(sel);
            if (elements.length > 0) {
                console.log(`   📋 Found ${elements.length} elements with selector: ${sel}`);
                return elements;
            }
        } catch (e) {}
    }
    return [];
}

/**
 * Run the scraping logic (shared by both launch modes)
 */
async function runScraper(page) {
    const results = {
        leagueUrl: LEAGUE_URL,
        targetRace: TARGET_RACE,
        scrapedAt: new Date().toISOString(),
        teams: [],
    };

    try {
        console.log('🏁 F1 Fantasy League Scraper');
        console.log(`📊 Target: ${LEAGUE_URL}`);
        console.log(`🏆 Race: ${TARGET_RACE} Grand Prix\n`);

        await handleCookieConsent(page);

        // Wait for main content
        await page.waitForSelector('.si-main__container, main, [class*="leaderboard"], [class*="league"]', { timeout: 30000 }).catch(() => {});
        await page.waitForTimeout(CONFIG.DELAYS.PAGE_LOAD);

        // Select Chinese Grand Prix before scraping
        console.log('📅 Selecting Chinese Grand Prix...');
        await selectChineseGrandPrix(page);

        const teamRows = await findTeamRows(page);

        if (teamRows.length === 0) {
            console.log('⚠️  No team rows found. The league page structure may have changed.');
            console.log('   Try inspecting the page and updating selectors in findTeamRows().');
            if (process.argv.includes('--debug')) {
                const html = await page.content();
                const debugPath = path.join(OUTPUT_DIR, 'league_page_debug.html');
                await fs.mkdir(OUTPUT_DIR, { recursive: true });
                await fs.writeFile(debugPath, html, 'utf8');
                console.log(`   Debug: saved page HTML to ${debugPath}`);
            }
            console.log('   Saving empty results.');
        } else {
            const maxTeams = teamRows.length;
            console.log(`\n📋 Processing ${maxTeams} teams...\n`);

            for (let i = 0; i < maxTeams; i++) {
                try {
                    const row = teamRows[i];
                    const text = (await row.textContent())?.trim() || '';
                    if (!text || text.length < 3) continue;

                    console.log(`   [${i + 1}/${maxTeams}] Clicking: ${text.substring(0, 50)}...`);

                    const tagName = await row.evaluate((el) => el.tagName?.toLowerCase());
                    const href = await row.getAttribute('href').catch(() => null);
                    const isLink = tagName === 'a' && !!href;

                    await row.click();

                    // Wait for popup OR navigation (team links may navigate)
                    const popup = await page.waitForSelector('.si-popup__container', { timeout: 5000 }).catch(() => null);

                    const rank = i + 1;
                    if (popup) {
                        const teamData = await extractTeamDataFromPopup(page, rank);
                        if (teamData) {
                            results.teams.push(teamData);
                            const pts = teamData.totalPoints ?? teamData.chinaGrandPrix?.totalPoints ?? 0;
                            const lineup = [...(teamData.drivers || []).map((d) => `${d.name} ${d.points}`), ...(teamData.constructors || []).map((c) => `${c.name} ${c.points}`)].join(', ');
                            console.log(`      ✅ #${rank} ${teamData.teamName} | ${pts} pts | ${lineup}`);
                        }
                        await closePopup(page);
                    } else if (isLink && page.url().includes('/team/')) {
                        await page.waitForSelector('.si-main__container, main', { timeout: 8000 }).catch(() => null);
                        const teamData = await extractTeamDataFromPage(page, rank);
                        if (teamData) {
                            results.teams.push(teamData);
                            const pts = teamData.totalPoints ?? 0;
                            const lineup = [...(teamData.drivers || []).map((d) => `${d.name} ${d.points}`), ...(teamData.constructors || []).map((c) => `${c.name} ${c.points}`)].join(', ');
                            console.log(`      ✅ #${rank} ${teamData.teamName} | ${pts} pts | ${lineup}`);
                        }
                        await page.goBack();
                        await page.waitForLoadState('load');
                    }

                    await page.waitForTimeout(CONFIG.DELAYS.BETWEEN_TEAMS);
                } catch (err) {
                    console.log(`      ⚠️  Error: ${err.message}`);
                    await page.keyboard.press('Escape');
                    await page.waitForTimeout(500);
                }
            }
        }

        await fs.mkdir(OUTPUT_DIR, { recursive: true });
        await fs.writeFile(OUTPUT_FILE, JSON.stringify(results, null, 2), 'utf8');
        console.log(`\n💾 Saved to ${OUTPUT_FILE}`);
        console.log(`   Teams: ${results.teams.length}`);
    } catch (error) {
        console.error('❌ Scraper failed:', error.message);
        throw error;
    }
}

/**
 * Main scraper
 */
async function main() {
    const launchOpts = { headless: CONFIG.BROWSER_HEADLESS };

    if (CONFIG.USE_PERSISTENT_PROFILE) {
        const context = await chromium.launchPersistentContext(USER_DATA_DIR, {
            ...launchOpts,
            viewport: null,
            acceptDownloads: false,
        });
        const page = context.pages()[0] || await context.newPage();

        // 1. Go to base URL first so cookie consent appears
        console.log('📄 Loading F1 Fantasy...');
        await page.goto(BASE_URL, { waitUntil: 'load', timeout: 60000 });
        await page.waitForTimeout(2000);

        // 2. Dismiss cookie consent
        console.log('🍪 Handling cookie consent...');
        await handleCookieConsent(page);

        // 3. League pages require login – redirect to /en if not logged in
        //    Log in on the current page FIRST, then we navigate to league
        console.log('');
        console.log('⚠️  F1 Fantasy league pages require you to be logged in.');
        console.log('   → Log in now in the browser window (if not already).');
        console.log('   → Press Enter here when you are logged in.');
        console.log('');
        await new Promise((resolve) => {
            process.stdin.once('data', resolve);
        });

        // 4. Navigate to league URL (session should now be valid)
        console.log(`📊 Navigating to league: ${LEAGUE_URL}`);
        await page.goto(LEAGUE_URL, { waitUntil: 'load', timeout: 60000 });
        const currentUrl = page.url();

        if (!currentUrl.includes('/leagues/') && !currentUrl.includes('leaderboard')) {
            console.log(`❌ Redirected to ${currentUrl} – league URL requires login.`);
            console.log('   Make sure you are fully logged in (check for "My Team" or your name in the header).');
            console.log('   Press Enter to retry navigation...');
            await new Promise((resolve) => process.stdin.once('data', resolve));
            await page.goto(LEAGUE_URL, { waitUntil: 'load', timeout: 60000 });
        }

        console.log(`✅ Current URL: ${page.url()}`);
        await runScraper(page);
        await context.close();
        return;
    }

    const browser = await chromium.launch(launchOpts);
    const page = await browser.newPage();

    // 1. Base URL first
    console.log('📄 Loading F1 Fantasy...');
    await page.goto(BASE_URL, { waitUntil: 'load', timeout: 60000 });
    await page.waitForTimeout(2000);

    // 2. Cookie consent
    console.log('🍪 Handling cookie consent...');
    await handleCookieConsent(page);

    // 3. Without persistent profile, login is not saved – prompt user
    console.log('');
    console.log('⚠️  League pages require login. Log in now, then press Enter...');
    await new Promise((resolve) => process.stdin.once('data', resolve));

    console.log(`📊 Navigating to league: ${LEAGUE_URL}`);
    await page.goto(LEAGUE_URL, { waitUntil: 'load', timeout: 60000 });
    const currentUrl = page.url();

    if (!currentUrl.includes('/leagues/') && !currentUrl.includes('leaderboard')) {
        console.log(`❌ Still at ${currentUrl}. Use --no-profile to run with persistent profile (saves login).`);
    } else {
        console.log(`✅ Current URL: ${currentUrl}`);
    }

    await runScraper(page);
    await browser.close();
}

// Parse flags
if (process.argv.includes('--headless')) {
    CONFIG.BROWSER_HEADLESS = true;
}
if (process.argv.includes('--no-profile')) {
    CONFIG.USE_PERSISTENT_PROFILE = false;
}

main().catch((e) => {
    console.error(e);
    process.exit(1);
});
