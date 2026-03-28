/**
 * F1 Fantasy League Scraper
 *
 * Scrapes team lineups from an F1 Fantasy league leaderboard.
 * The target page may require login, so the script uses a persistent
 * Playwright browser profile by default and lets you log in once manually.
 *
 * Reference: JoshCBruce/fantasy-data/fantasy_scraper_V3.1.js
 *
 * Usage:
 *   node scripts/fantasy_scraper_league.js
 *   node scripts/fantasy_scraper_league.js --league-url "https://fantasy.formula1.com/en/leagues/leaderboard/public/871710"
 *   node scripts/fantasy_scraper_league.js --view "Chinese Grand Prix"
 *   node scripts/fantasy_scraper_league.js --view "Overall"
 *   node scripts/fantasy_scraper_league.js --output data/raaaace_weeeeek/custom.json --headless
 *   node scripts/fantasy_scraper_league.js --output-dir data/raaaace_weeeeek/debug-run
 *   node scripts/fantasy_scraper_league.js --cdp-url "http://127.0.0.1:9222"
 */

const path = require('path');

const { chromium } = require('playwright');

const fs = require('fs');
const fsp = fs.promises;

const BASE_URL = 'https://fantasy.formula1.com/en/';
const DEFAULT_LEAGUE_URL = 'https://fantasy.formula1.com/en/leagues/leaderboard/public/871710';
const DEFAULT_OUTPUT_DIR = path.join(__dirname, '..', 'data', 'raaaace_weeeeek');
const CONSTRUCTOR_NAMES = ['McLaren', 'Red Bull', 'Ferrari', 'Mercedes', 'Aston Martin', 'Alpine', 'Haas', 'Williams', 'Sauber', 'Racing Bulls', 'Audi', 'Cadillac'];
const DRIVER_NAMES = [
    'George Russell', 'Charles Leclerc', 'Lewis Hamilton', 'Kimi Antonelli', 'Lando Norris', 'Max Verstappen',
    'Oscar Piastri', 'Carlos Sainz', 'Sergio Pérez', 'Fernando Alonso', 'Lance Stroll', 'Pierre Gasly',
    'Esteban Ocon', 'Nico Hülkenberg', 'Kevin Magnussen', 'Valtteri Bottas', 'Guanyu Zhou', 'Alexander Albon',
    'Logan Sargeant', 'Yuki Tsunoda', 'Daniel Ricciardo', 'Oliver Bearman', 'Isack Hadjar', 'Gabriel Bortoleto',
    'Liam Lawson', 'Franco Colapinto', 'Jack Doohan', 'Arvid Lindblad'
];
const PLAYER_ID_NAME_MAP = {
    '13': 'Liam Lawson',
    '18': 'Pierre Gasly',
    '110': 'Lewis Hamilton',
    '111': 'Nico Hülkenberg',
    '114': 'Valtteri Bottas',
    '115': 'Charles Leclerc',
    '117': 'Lando Norris',
    '118': 'Esteban Ocon',
    '121': 'Sergio Pérez',
    '124': 'George Russell',
    '131': 'Max Verstappen',
    '1982': 'Oscar Piastri',
    '11031': 'Oliver Bearman',
    '11032': 'Isack Hadjar',
    '11051': 'Gabriel Bortoleto',
    '11059': 'Franco Colapinto',
    '11149': 'Arvid Lindblad',
    '11161': 'Kimi Antonelli',
};
const CHROME_EXECUTABLE_CANDIDATES = [
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Google Chrome Beta.app/Contents/MacOS/Google Chrome Beta',
    '/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary',
];

const USER_DATA_DIR = path.join(__dirname, '..', 'data', 'playwright-fantasy-profile');

const CONFIG = {
    BROWSER_HEADLESS: false, // Set true to run without window; use --headless to override
    USE_PERSISTENT_PROFILE: true, // Use saved login; set false or --no-profile for fresh browser
    BROWSER: 'chrome', // Prefer local Chrome because some sites block Playwright Chromium
    CDP_URL: null, // Connect to an already logged-in local Chrome via remote debugging
    LEAGUE_URL: DEFAULT_LEAGUE_URL,
    TARGET_RACE: null,
    OUTPUT_FILE: null,
    OUTPUT_DIR: null,
    DELAYS: {
        PAGE_LOAD: 5000,
        POPUP_WAIT: 3000,
        BETWEEN_TEAMS: 2000,
        POPUP_CLOSE: 1000,
    },
};

function getArgValue(flag) {
    const index = process.argv.indexOf(flag);
    if (index === -1 || index + 1 >= process.argv.length) {
        return null;
    }
    return process.argv[index + 1];
}

function escapeRegExp(value) {
    return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function slugify(value) {
    return value
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '') || 'overall';
}

function extractLeagueId(leagueUrl) {
    const match = leagueUrl.match(/\/public\/(\d+)/);
    return match ? match[1] : 'custom';
}

function getOutputDir() {
    return CONFIG.OUTPUT_DIR || DEFAULT_OUTPUT_DIR;
}

function getOutputFilePath() {
    if (CONFIG.OUTPUT_FILE) {
        return CONFIG.OUTPUT_FILE;
    }
    const leagueId = extractLeagueId(CONFIG.LEAGUE_URL);
    const raceSuffix = CONFIG.TARGET_RACE ? `_${slugify(CONFIG.TARGET_RACE)}` : '';
    return path.join(getOutputDir(), `league_${leagueId}${raceSuffix}.json`);
}

function buildLineup(teamData) {
    return {
        drivers: (teamData.drivers || []).map((driver) => driver.name),
        constructors: (teamData.constructors || []).map((constructor) => constructor.name),
    };
}

function normalizeName(value) {
    return (value || '')
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '');
}

function extractNamesInTextOrder(text, names) {
    const normalizedText = normalizeName(text);
    return names
        .map((name) => ({ name, index: normalizedText.indexOf(normalizeName(name)) }))
        .filter((entry) => entry.index >= 0)
        .sort((a, b) => a.index - b.index)
        .map((entry) => entry.name);
}

const CHIP_LABELS = {
    x3Boost: 'x3 Boost',
    noNegative: 'No Negative',
    wildcard: 'Wildcard',
    limitless: 'Limitless',
    finalFix: 'Final Fix',
    autopilot: 'Autopilot',
};

function isTruthyChipFlag(value) {
    if (value === null || value === undefined || value === false) {
        return false;
    }
    if (typeof value === 'number') {
        return value > 0;
    }
    if (typeof value === 'string') {
        const normalized = value.trim().toLowerCase();
        return normalized !== '' && normalized !== '0' && normalized !== 'false' && normalized !== 'null';
    }
    return Boolean(value);
}

function buildChipInfo(chipInfo = {}) {
    const normalized = {
        x3Boost: Boolean(chipInfo.x3Boost),
        x3BoostDriver: chipInfo.x3BoostDriver || null,
        noNegative: Boolean(chipInfo.noNegative),
        wildcard: Boolean(chipInfo.wildcard),
        limitless: Boolean(chipInfo.limitless),
        finalFix: Boolean(chipInfo.finalFix),
        autopilot: Boolean(chipInfo.autopilot),
    };

    if (normalized.x3BoostDriver) {
        normalized.x3Boost = true;
    }

    const used = [];
    if (normalized.x3Boost) used.push(CHIP_LABELS.x3Boost);
    if (normalized.noNegative) used.push(CHIP_LABELS.noNegative);
    if (normalized.wildcard) used.push(CHIP_LABELS.wildcard);
    if (normalized.limitless) used.push(CHIP_LABELS.limitless);
    if (normalized.finalFix) used.push(CHIP_LABELS.finalFix);
    if (normalized.autopilot) used.push(CHIP_LABELS.autopilot);

    return {
        ...normalized,
        used,
    };
}

function mergeChipInfo(baseChipInfo = null, nextChipInfo = null) {
    const base = buildChipInfo(baseChipInfo || {});
    const next = buildChipInfo(nextChipInfo || {});
    return buildChipInfo({
        x3Boost: base.x3Boost || next.x3Boost,
        x3BoostDriver: next.x3BoostDriver || base.x3BoostDriver || null,
        noNegative: base.noNegative || next.noNegative,
        wildcard: base.wildcard || next.wildcard,
        limitless: base.limitless || next.limitless,
        finalFix: base.finalFix || next.finalFix,
        autopilot: base.autopilot || next.autopilot,
    });
}

function normalizeTransferCount(value) {
    if (value === null || value === undefined || value === '') {
        return null;
    }
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : null;
}

function buildTransferInfo(transferInfo = {}) {
    const made = normalizeTransferCount(transferInfo.made);
    const allowed = normalizeTransferCount(transferInfo.allowed);
    const remaining = normalizeTransferCount(transferInfo.remaining);
    const penaltyPerTransfer = normalizeTransferCount(transferInfo.penaltyPerTransfer);

    let excess = normalizeTransferCount(transferInfo.excess);
    if (excess === null) {
        if (remaining !== null) {
            excess = Math.max(0, -remaining);
        } else if (made !== null && allowed !== null) {
            excess = Math.max(0, made - allowed);
        } else {
            excess = 0;
        }
    }

    let penaltyPoints = normalizeTransferCount(transferInfo.penaltyPoints);
    if (penaltyPoints === null && penaltyPerTransfer !== null) {
        penaltyPoints = excess * penaltyPerTransfer;
    }

    return {
        made,
        allowed,
        remaining,
        excess,
        overLimit: excess > 0,
        penaltyPerTransfer,
        penaltyPoints,
    };
}

function mergeTransferInfo(baseTransferInfo = null, nextTransferInfo = null) {
    const base = buildTransferInfo(baseTransferInfo || {});
    const next = buildTransferInfo(nextTransferInfo || {});
    return buildTransferInfo({
        made: next.made ?? base.made,
        allowed: next.allowed ?? base.allowed,
        remaining: next.remaining ?? base.remaining,
        excess: next.excess ?? base.excess,
        penaltyPerTransfer: next.penaltyPerTransfer ?? base.penaltyPerTransfer,
        penaltyPoints: next.penaltyPoints ?? base.penaltyPoints,
    });
}

function buildTeamDataFromLineup({ teamName, manager, drivers, constructors, totalPoints = null, costCap = '', limitless = false, turboDriver = null, chipInfo = null, transferInfo = null }) {
    const normalizedTurbo = normalizeName(turboDriver);
    const chips = mergeChipInfo({ limitless }, chipInfo);
    const transfer = buildTransferInfo(transferInfo || {});
    return {
        teamName: teamName || 'Unknown Team',
        manager: manager || '',
        totalPoints,
        costCap,
        limitless: chips.limitless,
        chip: chips.used.length === 1 ? chips.used[0] : null,
        chips,
        turboDriver: turboDriver || null,
        x3BoostDriver: chips.x3BoostDriver,
        excessTransfers: transfer.excess,
        transfer,
        drivers: (drivers || []).slice(0, 5).map((driver) => {
            const name = typeof driver === 'string' ? driver : driver.name;
            const points = typeof driver === 'string' ? null : (driver.points ?? null);
            const turbo = typeof driver === 'string'
                ? (!!normalizedTurbo && normalizeName(name) === normalizedTurbo)
                : (driver.turbo ?? (!!normalizedTurbo && normalizeName(name) === normalizedTurbo));
            return {
                name,
                points,
                turbo,
            };
        }),
        constructors: (constructors || []).slice(0, 2).map((constructor) => ({
            name: typeof constructor === 'string' ? constructor : constructor.name,
            points: typeof constructor === 'string' ? null : (constructor.points ?? null),
        })),
    };
}

function buildTeamResult(teamData, rank, selectedRaceName) {
    const chips = mergeChipInfo(
        { limitless: teamData.limitless },
        teamData.chips || {
            x3Boost: teamData.x3Boost,
            x3BoostDriver: teamData.x3BoostDriver,
            noNegative: teamData.noNegative,
            wildcard: teamData.wildcard,
            limitless: teamData.limitless,
            finalFix: teamData.finalFix,
            autopilot: teamData.autopilot,
        },
    );
    const transfer = mergeTransferInfo(
        teamData.transfer,
        {
            excess: teamData.excessTransfers,
        },
    );
    const result = {
        rank,
        teamName: teamData.teamName,
        manager: teamData.manager,
        lineup: buildLineup(teamData),
        totalPoints: teamData.totalPoints,
        costCap: teamData.costCap,
        limitless: chips.limitless,
        chip: chips.used.length === 1 ? chips.used[0] : null,
        chips,
        turboDriver: teamData.turboDriver,
        x3BoostDriver: chips.x3BoostDriver,
        excessTransfers: transfer.excess,
        transfer,
        drivers: teamData.drivers,
        constructors: teamData.constructors,
        selectedRace: {
            race: selectedRaceName || null,
            totalPoints: teamData.totalPoints,
            chip: chips.used.length === 1 ? chips.used[0] : null,
            chips,
            x3BoostDriver: chips.x3BoostDriver,
            excessTransfers: transfer.excess,
            transfer,
            drivers: teamData.drivers,
            constructors: teamData.constructors,
        },
    };
    if (teamData.__networkDebug) {
        result.__networkDebug = teamData.__networkDebug;
    }
    return result;
}

function applyTurboDriverToTeamResult(teamResult, turboDriver) {
    if (!teamResult || !turboDriver) {
        return teamResult;
    }

    const normalizedTurbo = normalizeName(turboDriver);
    const applyToDrivers = (drivers) => (drivers || []).map((driver) => ({
        ...driver,
        turbo: normalizeName(driver.name) === normalizedTurbo,
    }));

    teamResult.turboDriver = turboDriver;
    teamResult.drivers = applyToDrivers(teamResult.drivers);

    if (teamResult.selectedRace) {
        teamResult.selectedRace = {
            ...teamResult.selectedRace,
            drivers: applyToDrivers(teamResult.selectedRace.drivers),
        };
    }

    return teamResult;
}

function applyChipInfoToTeamResult(teamResult, chipInfo) {
    if (!teamResult || !chipInfo) {
        return teamResult;
    }

    const mergedChips = mergeChipInfo(teamResult.chips || { limitless: teamResult.limitless }, chipInfo);
    teamResult.limitless = mergedChips.limitless;
    teamResult.chip = mergedChips.used.length === 1 ? mergedChips.used[0] : null;
    teamResult.chips = mergedChips;
    teamResult.x3BoostDriver = mergedChips.x3BoostDriver;

    if (teamResult.selectedRace) {
        teamResult.selectedRace = {
            ...teamResult.selectedRace,
            chip: mergedChips.used.length === 1 ? mergedChips.used[0] : null,
            chips: mergedChips,
            x3BoostDriver: mergedChips.x3BoostDriver,
        };
    }

    return teamResult;
}

function applyTransferInfoToTeamResult(teamResult, transferInfo) {
    if (!teamResult || !transferInfo) {
        return teamResult;
    }

    const mergedTransfer = mergeTransferInfo(teamResult.transfer || { excess: teamResult.excessTransfers }, transferInfo);
    teamResult.excessTransfers = mergedTransfer.excess;
    teamResult.transfer = mergedTransfer;

    if (teamResult.selectedRace) {
        teamResult.selectedRace = {
            ...teamResult.selectedRace,
            excessTransfers: mergedTransfer.excess,
            transfer: mergedTransfer,
        };
    }

    return teamResult;
}

function harmonizeTeamResultWithRow(teamResult, expectedTeamName = '', fallbackManager = '', fallbackPoints = null) {
    if (!teamResult) {
        return null;
    }

    const expected = normalizeName(expectedTeamName);
    const actual = normalizeName(teamResult.teamName);
    const fallbackManagerNormalized = normalizeName(fallbackManager);
    const actualManagerNormalized = normalizeName(teamResult.manager);
    const pointsMatch = fallbackPoints !== null
        && teamResult.totalPoints !== null
        && Number(teamResult.totalPoints) === Number(fallbackPoints);

    const teamMatches = !expected || actual.includes(expected) || expected.includes(actual);
    const managerMatches = !!fallbackManagerNormalized && fallbackManagerNormalized === actualManagerNormalized;

    if (!teamMatches && !managerMatches && !pointsMatch) {
        return null;
    }

    const harmonized = { ...teamResult };

    if (expectedTeamName && normalizeName(expectedTeamName) !== normalizeName(teamResult.teamName)) {
        harmonized.detailTeamName = teamResult.teamName;
        harmonized.teamName = expectedTeamName;
    }

    if (!harmonized.manager && fallbackManager) {
        harmonized.manager = fallbackManager;
    }

    return harmonized;
}

async function saveNetworkDebugArtifact(teamResult) {
    const debugMeta = teamResult?.__networkDebug;
    if (!debugMeta) {
        return;
    }

    const debugDir = path.join(getOutputDir(), 'debug');
    const filename = `${String(teamResult.rank).padStart(2, '0')}_${slugify(teamResult.teamName || 'team')}_network.json`;
    const outputPath = path.join(debugDir, filename);

    const debugPayload = {
        rank: teamResult.rank,
        teamName: teamResult.teamName,
        detailTeamName: teamResult.detailTeamName || null,
        manager: teamResult.manager,
        totalPoints: teamResult.totalPoints,
        turboDriver: teamResult.turboDriver,
        url: debugMeta.url,
        status: debugMeta.status,
        score: debugMeta.score,
        depth: debugMeta.depth,
        expectedTeamName: debugMeta.expectedTeamName,
        fallbackManager: debugMeta.fallbackManager,
        rawNode: debugMeta.rawNode,
    };

    await fsp.mkdir(debugDir, { recursive: true });
    await fsp.writeFile(outputPath, JSON.stringify(debugPayload, null, 2), 'utf8');
}

async function saveCapturedResponsesArtifact(teamContext, responses) {
    if (!responses || responses.length === 0) {
        return;
    }

    const debugDir = path.join(getOutputDir(), 'debug');
    const filename = `${String(teamContext.rank).padStart(2, '0')}_${slugify(teamContext.teamName || 'team')}_responses.json`;
    const outputPath = path.join(debugDir, filename);

    const payload = {
        rank: teamContext.rank,
        teamName: teamContext.teamName,
        manager: teamContext.manager || '',
        totalResponses: responses.length,
        responses: responses.map((response) => ({
            url: response.url,
            status: response.status,
            payload: response.payload,
        })),
    };

    await fsp.mkdir(debugDir, { recursive: true });
    await fsp.writeFile(outputPath, JSON.stringify(payload, null, 2), 'utf8');
}

function startNetworkResponseCollector(page) {
    const responses = [];
    const listener = async (response) => {
        try {
            const request = response.request();
            if (!['fetch', 'xhr'].includes(request.resourceType())) {
                return;
            }

            const headers = response.headers();
            const contentType = headers['content-type'] || headers['Content-Type'] || '';
            const url = response.url();
            if (!/json|graphql|api|league|team|entry/i.test(`${contentType} ${url}`)) {
                return;
            }

            let payload = null;
            try {
                payload = await response.json();
            } catch (jsonError) {
                const text = await response.text().catch(() => '');
                if (!text) return;
                try {
                    payload = JSON.parse(text);
                } catch (parseError) {
                    return;
                }
            }

            responses.push({ url, status: response.status(), payload });
        } catch (error) {}
    };

    page.on('response', listener);

    return {
        getResponses() {
            return responses.slice();
        },
        stop() {
            page.off('response', listener);
        },
    };
}

function walkJsonCandidates(value, visit, state = { seen: new WeakSet(), count: 0 }, depth = 0) {
    if (value === null || value === undefined) return;
    if (depth > 7 || state.count > 400) return;
    if (typeof value !== 'object') return;
    if (state.seen.has(value)) return;
    state.seen.add(value);
    state.count += 1;

    visit(value, depth);

    if (Array.isArray(value)) {
        for (const item of value) {
            walkJsonCandidates(item, visit, state, depth + 1);
        }
        return;
    }

    for (const item of Object.values(value)) {
        walkJsonCandidates(item, visit, state, depth + 1);
    }
}

function pickStringField(node, preferredKeys) {
    if (!node || typeof node !== 'object' || Array.isArray(node)) {
        return '';
    }

    for (const [key, value] of Object.entries(node)) {
        if (typeof value !== 'string') continue;
        const normalizedKey = normalizeName(key);
        if (preferredKeys.some((candidate) => normalizedKey.includes(candidate))) {
            const trimmed = value.trim();
            if (trimmed) return trimmed;
        }
    }

    return '';
}

function pickNumberField(node, preferredKeys) {
    if (!node || typeof node !== 'object' || Array.isArray(node)) {
        return null;
    }

    for (const [key, value] of Object.entries(node)) {
        const normalizedKey = normalizeName(key);
        if (!preferredKeys.some((candidate) => normalizedKey.includes(candidate))) {
            continue;
        }
        if (typeof value === 'number' && Number.isFinite(value)) {
            return value;
        }
        if (typeof value === 'string') {
            const match = value.match(/-?\d+(?:\.\d+)?/);
            if (match) {
                return Number(match[0]);
            }
        }
    }

    return null;
}

function pickBooleanField(node, preferredKeys) {
    if (!node || typeof node !== 'object' || Array.isArray(node)) {
        return false;
    }

    for (const [key, value] of Object.entries(node)) {
        const normalizedKey = normalizeName(key);
        if (!preferredKeys.some((candidate) => normalizedKey.includes(candidate))) {
            continue;
        }
        if (typeof value === 'boolean') {
            return value;
        }
        if (typeof value === 'string' && /true|false/i.test(value)) {
            return /true/i.test(value);
        }
    }

    return false;
}

function detectTurboLikeValue(value) {
    if (typeof value === 'boolean') {
        return value;
    }
    if (typeof value === 'number') {
        return value === 2;
    }
    if (typeof value === 'string') {
        return /\b(2x|x2|turbo|double|multiplier.?2)\b/i.test(value);
    }
    return false;
}

function detectTurboInObject(node) {
    if (!node || typeof node !== 'object' || Array.isArray(node)) {
        return false;
    }

    for (const [key, value] of Object.entries(node)) {
        const normalizedKey = normalizeName(key);
        if (['turbo', 'isturbo', 'turbodriver', 'multiplier', 'drs', 'isdrs', 'double', 'x2', 'boost'].some((candidate) => normalizedKey.includes(candidate))) {
            if (detectTurboLikeValue(value)) {
                return true;
            }
        }
    }

    return false;
}

function mapCaptainIdToDriverName(node) {
    if (!node || typeof node !== 'object') {
        return null;
    }

    const capId = typeof node.capplayerid === 'string' || typeof node.capplayerid === 'number'
        ? String(node.capplayerid)
        : null;
    if (capId && PLAYER_ID_NAME_MAP[capId]) {
        return PLAYER_ID_NAME_MAP[capId];
    }

    if (Array.isArray(node.playerid)) {
        const captainEntry = node.playerid.find((entry) => entry && String(entry.iscaptain) === '1');
        if (captainEntry) {
            const captainId = String(captainEntry.id);
            if (PLAYER_ID_NAME_MAP[captainId]) {
                return PLAYER_ID_NAME_MAP[captainId];
            }
        }
    }

    return null;
}

function mapMegaCaptainIdToDriverName(node) {
    if (!node || typeof node !== 'object') {
        return null;
    }

    const megaCapId = typeof node.mgcapplayerid === 'string' || typeof node.mgcapplayerid === 'number'
        ? String(node.mgcapplayerid)
        : null;
    if (megaCapId && PLAYER_ID_NAME_MAP[megaCapId]) {
        return PLAYER_ID_NAME_MAP[megaCapId];
    }

    if (Array.isArray(node.playerid)) {
        const megaCaptainEntry = node.playerid.find((entry) => entry && String(entry.ismgcaptain) === '1');
        if (megaCaptainEntry) {
            const megaCaptainId = String(megaCaptainEntry.id);
            if (PLAYER_ID_NAME_MAP[megaCaptainId]) {
                return PLAYER_ID_NAME_MAP[megaCaptainId];
            }
        }
    }

    return null;
}

function extractChipInfoFromText(text = '', x3BoostDriver = null) {
    return buildChipInfo({
        x3Boost: /\bx3\s*boost\b|\bboost\s*x3\b/i.test(text) || !!x3BoostDriver,
        x3BoostDriver,
        noNegative: /\bno\s*negative\b/i.test(text),
        wildcard: /\bwildcard\b/i.test(text),
        limitless: /\blimitless\b/i.test(text),
        finalFix: /\bfinal\s*fix\b/i.test(text),
        autopilot: /\bautopilot\b/i.test(text),
    });
}

function extractChipInfoFromNode(node, expectedDrivers = []) {
    const normalizedExpectedDrivers = new Set((expectedDrivers || []).map((driver) => normalizeName(driver?.name || driver)));
    const megaDriverCandidate = mapMegaCaptainIdToDriverName(node);
    const x3BoostDriver = megaDriverCandidate && (!normalizedExpectedDrivers.size || normalizedExpectedDrivers.has(normalizeName(megaDriverCandidate)))
        ? megaDriverCandidate
        : null;

    return buildChipInfo({
        x3Boost: isTruthyChipFlag(node?.isboostertaken) || isTruthyChipFlag(node?.isextradrstaken) || !!x3BoostDriver,
        x3BoostDriver,
        noNegative: isTruthyChipFlag(node?.isnonigativetaken),
        wildcard: isTruthyChipFlag(node?.iswildcardtaken) || isTruthyChipFlag(node?.iswildcard) || isTruthyChipFlag(node?.is_wildcard_taken_gd_id),
        limitless: isTruthyChipFlag(node?.islimitlesstaken),
        finalFix: isTruthyChipFlag(node?.isfinalfixtaken),
        autopilot: isTruthyChipFlag(node?.isautopilottaken),
    });
}

function extractTransferInfoFromNode(node) {
    if (!node || typeof node !== 'object') {
        return buildTransferInfo({});
    }

    const teamInfo = node.team_info && typeof node.team_info === 'object' ? node.team_info : {};

    return buildTransferInfo({
        made: node.usersubs ?? teamInfo.usersubs ?? null,
        allowed: teamInfo.subsallowed ?? node.subsallowed ?? null,
        remaining: teamInfo.userSubsleft ?? node.usersubsleft ?? null,
        penaltyPerTransfer: node.extrasubscost ?? null,
    });
}

function extractTurboDriverFromCapturedResponses(responses = [], expectedDrivers = []) {
    const normalizedExpectedDrivers = new Set((expectedDrivers || []).map((driver) => normalizeName(driver?.name || driver)));

    for (const response of responses) {
        const payload = response?.payload;
        let turboDriver = null;

        walkJsonCandidates(payload, (candidate) => {
            if (turboDriver || !candidate || typeof candidate !== 'object' || Array.isArray(candidate)) {
                return;
            }

            turboDriver = mapCaptainIdToDriverName(candidate);
        });

        if (turboDriver) {
            if (!normalizedExpectedDrivers.size || normalizedExpectedDrivers.has(normalizeName(turboDriver))) {
                return turboDriver;
            }
        }
    }

    return null;
}

function extractChipInfoFromCapturedResponses(responses = [], expectedDrivers = []) {
    const normalizedExpectedDrivers = new Set((expectedDrivers || []).map((driver) => normalizeName(driver?.name || driver)));

    for (const response of responses) {
        const payload = response?.payload;
        let chipInfo = null;

        walkJsonCandidates(payload, (candidate) => {
            if (chipInfo || !candidate || typeof candidate !== 'object' || Array.isArray(candidate)) {
                return;
            }

            const turboDriverCandidate = mapCaptainIdToDriverName(candidate);
            const megaDriverCandidate = mapMegaCaptainIdToDriverName(candidate);
            const hasMatchingDriver = !normalizedExpectedDrivers.size
                || [turboDriverCandidate, megaDriverCandidate]
                    .filter(Boolean)
                    .some((name) => normalizedExpectedDrivers.has(normalizeName(name)));

            if (!hasMatchingDriver) {
                return;
            }

            const candidateChipInfo = extractChipInfoFromNode(candidate, expectedDrivers);
            if (candidateChipInfo.used.length > 0) {
                chipInfo = candidateChipInfo;
            }
        });

        if (chipInfo) {
            return chipInfo;
        }
    }

    return buildChipInfo({});
}

function extractTransferInfoFromCapturedResponses(responses = [], expectedDrivers = []) {
    const normalizedExpectedDrivers = new Set((expectedDrivers || []).map((driver) => normalizeName(driver?.name || driver)));

    for (const response of responses) {
        const payload = response?.payload;
        let transferInfo = null;

        walkJsonCandidates(payload, (candidate) => {
            if (transferInfo || !candidate || typeof candidate !== 'object' || Array.isArray(candidate)) {
                return;
            }

            const turboDriverCandidate = mapCaptainIdToDriverName(candidate);
            const megaDriverCandidate = mapMegaCaptainIdToDriverName(candidate);
            const hasMatchingDriver = !normalizedExpectedDrivers.size
                || [turboDriverCandidate, megaDriverCandidate]
                    .filter(Boolean)
                    .some((name) => normalizedExpectedDrivers.has(normalizeName(name)));

            if (!hasMatchingDriver) {
                return;
            }

            const candidateTransferInfo = extractTransferInfoFromNode(candidate);
            if (
                candidateTransferInfo.made !== null
                || candidateTransferInfo.allowed !== null
                || candidateTransferInfo.remaining !== null
                || candidateTransferInfo.penaltyPerTransfer !== null
            ) {
                transferInfo = candidateTransferInfo;
            }
        });

        if (transferInfo) {
            return transferInfo;
        }
    }

    return buildTransferInfo({});
}

function extractNamedEntriesFromNode(node, allowedNames, type) {
    const entries = [];
    const seen = new Map();

    walkJsonCandidates(node, (candidate) => {
        if (!candidate || typeof candidate !== 'object' || Array.isArray(candidate)) {
            return;
        }

        let serialized = '';
        try {
            serialized = JSON.stringify(candidate);
        } catch (error) {
            return;
        }

        const normalizedSerialized = normalizeName(serialized);
        const matchedName = allowedNames.find((name) => normalizedSerialized.includes(normalizeName(name)));
        if (!matchedName) {
            return;
        }

        const existing = seen.get(matchedName) || {
            name: matchedName,
            points: null,
            turbo: false,
            score: 0,
        };

        const points = pickNumberField(candidate, ['points', 'score', 'totalpoints']);
        const turbo = type === 'driver' ? detectTurboInObject(candidate) : false;
        const score =
            (points !== null ? 10 : 0) +
            (turbo ? 20 : 0) +
            Object.keys(candidate).length;

        if (score >= existing.score) {
            seen.set(matchedName, {
                name: matchedName,
                points,
                turbo,
                score,
            });
        }
    });

    for (const entry of seen.values()) {
        entries.push({
            name: entry.name,
            points: entry.points,
            turbo: entry.turbo,
        });
    }

    return entries;
}

function extractTeamDataFromNetworkResponses(responses, rank, selectedRaceName, expectedTeamName = '', fallbackManager = '') {
    const expected = normalizeName(expectedTeamName);
    const candidates = [];

    for (const response of responses) {
        walkJsonCandidates(response.payload, (node, depth) => {
            let serialized = '';
            try {
                serialized = JSON.stringify(node);
            } catch (error) {
                return;
            }

            if (!serialized || serialized.length < 40) {
                return;
            }

            const driverEntries = extractNamedEntriesFromNode(node, DRIVER_NAMES, 'driver');
            const constructorEntries = extractNamedEntriesFromNode(node, CONSTRUCTOR_NAMES, 'constructor');
            const drivers = driverEntries.length > 0 ? driverEntries : extractNamesInTextOrder(serialized, DRIVER_NAMES);
            const constructors = constructorEntries.length > 0 ? constructorEntries : extractNamesInTextOrder(serialized, CONSTRUCTOR_NAMES);
            if (drivers.length < 5 || constructors.length < 2) {
                return;
            }

            const teamName = pickStringField(node, ['teamname', 'entryname', 'fantasyteam', 'team', 'name', 'title']) || expectedTeamName;
            const manager = pickStringField(node, ['manager', 'managername', 'player', 'owner', 'username']) || fallbackManager;
            const totalPoints = pickNumberField(node, ['totalpoints', 'points', 'score']);
            const costCapValue = pickNumberField(node, ['costcap', 'budget', 'teamvalue']);
            const turboDriver = mapCaptainIdToDriverName(node)
                || pickStringField(node, ['turbodriver', 'turbo', 'drsdriver'])
                || driverEntries.find((driver) => driver.turbo)?.name
                || null;
            const chipInfo = mergeChipInfo(
                extractChipInfoFromNode(node, drivers),
                { limitless: pickBooleanField(node, ['limitless']) },
            );
            const transferInfo = extractTransferInfoFromNode(node);
            const score =
                drivers.length * 10 +
                constructors.length * 12 +
                (expected && serialized.toLowerCase().includes(expected) ? 50 : 0) +
                (teamName && expected && normalizeName(teamName).includes(expected) ? 30 : 0) +
                Math.max(0, 10 - depth) +
                (/league|entry|team/i.test(response.url) ? 8 : 0);

            candidates.push({
                score,
                url: response.url,
                data: buildTeamDataFromLineup({
                    teamName,
                    manager,
                    drivers,
                    constructors,
                    totalPoints,
                    costCap: costCapValue !== null ? `$${costCapValue}M` : '',
                    limitless: chipInfo.limitless,
                    turboDriver,
                    chipInfo,
                    transferInfo,
                }),
                debug: {
                    url: response.url,
                    status: response.status,
                    score,
                    depth,
                    expectedTeamName,
                    fallbackManager,
                    rawNode: node,
                },
            });
        });
    }

    candidates.sort((a, b) => b.score - a.score);
    const best = candidates[0];
    if (!best) {
        return null;
    }

    console.log(`      🌐 Parsed lineup from network: ${best.url}`);
    best.data.__networkDebug = best.debug;
    return buildTeamResult(best.data, rank, selectedRaceName);
}

function getChromeExecutablePath() {
    for (const candidate of CHROME_EXECUTABLE_CANDIDATES) {
        if (fs.existsSync(candidate)) {
            return candidate;
        }
    }
    return null;
}

function getCommonLaunchOptions() {
    return {
        headless: CONFIG.BROWSER_HEADLESS,
        args: [
            '--start-maximized',
            '--disable-blink-features=AutomationControlled',
            '--disable-features=AutomationControlled',
        ],
    };
}

function getLaunchAttempts() {
    const common = getCommonLaunchOptions();
    if (CONFIG.BROWSER === 'chromium') {
        return [{ label: 'Chromium', launchOptions: common }];
    }

    const chromeExecutablePath = getChromeExecutablePath();
    const chromeLaunchOptions = chromeExecutablePath
        ? { ...common, executablePath: chromeExecutablePath }
        : { ...common, channel: 'chrome' };

    return [
        { label: 'Google Chrome', launchOptions: chromeLaunchOptions },
        { label: 'Chromium', launchOptions: common },
    ];
}

async function createPage(page) {
    await page.addInitScript(() => {
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
        });
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en'],
        });
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5],
        });
        window.chrome = window.chrome || { runtime: {} };
    });
    await page.setViewportSize({ width: 1440, height: 1024 }).catch(() => {});
    return page;
}

async function launchPersistentContext() {
    const attempts = getLaunchAttempts();
    let lastError = null;

    for (const attempt of attempts) {
        try {
            console.log(`🌐 Launching ${attempt.label}...`);
            const context = await chromium.launchPersistentContext(USER_DATA_DIR, {
                ...attempt.launchOptions,
                viewport: null,
                acceptDownloads: false,
            });
            return { context, browserLabel: attempt.label };
        } catch (error) {
            lastError = error;
            console.log(`⚠️  Failed to launch ${attempt.label}: ${error.message}`);
        }
    }

    throw lastError || new Error('Unable to launch any supported browser');
}

async function launchBrowser() {
    const attempts = getLaunchAttempts();
    let lastError = null;

    for (const attempt of attempts) {
        try {
            console.log(`🌐 Launching ${attempt.label}...`);
            const browser = await chromium.launch(attempt.launchOptions);
            return { browser, browserLabel: attempt.label };
        } catch (error) {
            lastError = error;
            console.log(`⚠️  Failed to launch ${attempt.label}: ${error.message}`);
        }
    }

    throw lastError || new Error('Unable to launch any supported browser');
}

async function connectToExistingBrowser() {
    if (!CONFIG.CDP_URL) {
        throw new Error('CDP URL is required to connect to an existing browser');
    }

    console.log(`🔌 Connecting to existing Chrome at ${CONFIG.CDP_URL}...`);
    const browser = await chromium.connectOverCDP(CONFIG.CDP_URL);
    const contexts = browser.contexts();
    const context = contexts[0];
    if (!context) {
        throw new Error('No browser context found on the connected Chrome instance');
    }

    const allPages = contexts.flatMap((ctx) => ctx.pages());
    const existingLeaguePage = allPages.find((page) => {
        const url = page.url() || '';
        return url.includes(CONFIG.LEAGUE_URL) || url.includes('/leagues/leaderboard/public/');
    });
    if (existingLeaguePage) {
        console.log(`📄 Reusing existing league tab: ${existingLeaguePage.url()}`);
        return {
            browser,
            context: existingLeaguePage.context(),
            page: existingLeaguePage,
            browserLabel: 'Existing Chrome via CDP',
            shouldClosePage: false,
        };
    }
    throw new Error(
        `No existing league tab found for ${CONFIG.LEAGUE_URL}. ` +
        'Open that exact league page manually in the connected Chrome window, then rerun the scraper.'
    );
}

/**
 * Handle cookie consent dialog (same as fantasy_scraper_V3.1.js).
 * Must run before navigating to league URL – the popup blocks the page.
 */
async function handleCookieConsent(page) {
    const consentTexts = [
        'Essential only cookies',
        'Accept All Cookies',
        'Accept all cookies',
        'Accept',
        'Allow all',
        'Allow All',
        'I Agree',
        'Agree',
    ];
    const iframeSelectors = [
        '#sp_message_iframe_1336275',
        'iframe[id*="sp_message"]',
        'iframe[title*="cookie"]',
        'iframe[title*="Cookie"]',
        'iframe[src*="privacy"]',
        'iframe[src*="consent"]',
    ];

    const tryClickConsentButton = async (scope, description) => {
        for (const text of consentTexts) {
            try {
                const button = scope.getByRole('button', { name: new RegExp(`^${escapeRegExp(text)}$`, 'i') });
                if ((await button.count()) > 0) {
                    await button.first().click({ timeout: 3000 });
                    console.log(`✅ Cookie consent handled via ${description}: ${text}`);
                    await page.waitForTimeout(1500);
                    return true;
                }
            } catch (e) {}
            try {
                const button = scope.getByText(new RegExp(escapeRegExp(text), 'i'));
                if ((await button.count()) > 0) {
                    await button.first().click({ timeout: 3000 });
                    console.log(`✅ Cookie consent handled via ${description}: ${text}`);
                    await page.waitForTimeout(1500);
                    return true;
                }
            } catch (e) {}
        }
        return false;
    };

    await page.waitForTimeout(1500);

    for (const sel of iframeSelectors) {
        try {
            const iframeElements = await page.$$(sel);
            for (const iframeElement of iframeElements) {
                const iframe = await iframeElement.contentFrame();
                if (iframe && (await tryClickConsentButton(iframe, `iframe ${sel}`))) {
                    return true;
                }
            }
        } catch (e) {}
    }

    for (const frame of page.frames()) {
        try {
            const frameUrl = frame.url() || '';
            if (/cookie|consent|privacy|sourcepoint/i.test(frameUrl)) {
                if (await tryClickConsentButton(frame, `frame ${frameUrl}`)) {
                    return true;
                }
            }
        } catch (e) {}
    }

    if (await tryClickConsentButton(page, 'page')) {
        return true;
    }

    try {
        const overlayRemoved = await page.evaluate(() => {
            const selectors = [
                '#sp_message_container_1336275',
                '[id*="sp_message_container"]',
                '[class*="sp_message_container"]',
                '[class*="consent"]',
                '[class*="cookie"]',
                '[aria-label*="cookie"]',
            ];
            let removed = false;
            for (const selector of selectors) {
                for (const element of document.querySelectorAll(selector)) {
                    element.remove();
                    removed = true;
                }
            }
            if (removed) {
                document.body.style.overflow = 'auto';
            }
            return removed;
        });
        if (overlayRemoved) {
            console.log('✅ Cookie overlay removed as fallback');
            await page.waitForTimeout(1000);
            return true;
        }
    } catch (e) {}

    console.log('ℹ️  No cookie consent dialog handled');
    return false;
}

/**
 * Select a standings view from the league page dropdown.
 * Supports values such as "Overall" or "Chinese Grand Prix".
 */
async function selectRace(page, raceName) {
    if (!raceName) {
        return true;
    }

    const racePattern = new RegExp(escapeRegExp(raceName), 'i');
    try {
        const combobox = page.getByRole('combobox');
        if ((await combobox.count()) > 0) {
            await combobox.first().click();
        } else {
            await page.getByText(/Grand Prix|Overall/i, { exact: false }).first().click();
        }
        await page.waitForTimeout(500);

        const optionByRole = page.getByRole('option', { name: racePattern });
        if ((await optionByRole.count()) > 0) {
            await optionByRole.first().click();
        } else {
            await page.getByText(racePattern, { exact: false }).first().click();
        }
        console.log(`✅ Selected race from dropdown: ${raceName}`);
        await page.waitForTimeout(CONFIG.DELAYS.POPUP_WAIT);
        return true;
    } catch (e) {
        try {
            await page.getByText(/Grand Prix|Overall/i, { exact: false }).first().click();
            await page.waitForTimeout(500);
            await page.getByText(racePattern, { exact: false }).first().click();
            console.log(`✅ Selected race from dropdown (fallback): ${raceName}`);
            await page.waitForTimeout(CONFIG.DELAYS.POPUP_WAIT);
            return true;
        } catch (e2) {}
    }

    console.log(`⚠️  Could not find dropdown option for "${raceName}". Try --debug to inspect.`);
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
 * Extract lineup (drivers + constructors) with individual points from team popup.
 */
async function extractTeamDataFromPopup(page, rank, selectedRaceName) {
    const popup = await page.$('.si-popup__container');
    if (!popup) return null;

    const teamData = await page.evaluate(({ constructorNames, driverNames }) => {
        const popup = document.querySelector('.si-popup__container');
        if (!popup) return null;

        const drivers = [];
        const constructors = [];
        let teamName = 'Unknown Team';
        let manager = '';
        let totalPoints = 0;
        let costCap = '';
        let limitless = false;
        let turboDriver = null;
        let x3BoostDriver = null;

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
        const normalize = (value) => (value || '')
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, '');
        const extractNamesInTextOrder = (text, names) => names
            .map((name) => ({ name, index: normalize(text).indexOf(normalize(name)) }))
            .filter((entry) => entry.index >= 0)
            .sort((a, b) => a.index - b.index)
            .map((entry) => entry.name);

        for (const row of rows) {
            const text = (row.textContent || '').trim();
            const ptsMatch = text.match(/(\d+)\s*PTS?/i);
            const points = ptsMatch ? parseInt(ptsMatch[1]) : null;
            const namePart = text.replace(/\d+\s*PTS?.*/i, '').replace(/\s*2X\s*/i, '').trim();
            if (!namePart) continue;

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
                    if (/\b(3x|x3)\b/i.test(text)) x3BoostDriver = namePart;
                }
            }
        }

        // Fallback: scan the popup text itself so lineup extraction still works
        // even if the page structure or points labels change.
        for (const driverName of extractNamesInTextOrder(fullText, driverNames)) {
            if (!seenDrivers.has(driverName) && drivers.length < 5) {
                seenDrivers.add(driverName);
                drivers.push({ name: driverName, points: null, turbo: false });
            }
        }
        for (const constructorName of extractNamesInTextOrder(fullText, constructorNames)) {
            if (!seenConstructors.has(constructorName) && constructors.length < 2) {
                seenConstructors.add(constructorName);
                constructors.push({ name: constructorName, points: null });
            }
        }

        // Final fallback: regex from full text for names + points
        if (drivers.length < 5) {
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

        return {
            teamName,
            manager,
            totalPoints,
            costCap,
            limitless,
            turboDriver,
            x3BoostDriver,
            chips: {
                x3Boost: /\bx3\s*boost\b|\bboost\s*x3\b/i.test(fullText) || !!x3BoostDriver,
                x3BoostDriver,
                noNegative: /\bno\s*negative\b/i.test(fullText),
                wildcard: /\bwildcard\b/i.test(fullText),
                limitless: /\blimitless\b/i.test(fullText),
                finalFix: /\bfinal\s*fix\b/i.test(fullText),
                autopilot: /\bautopilot\b/i.test(fullText),
            },
            drivers,
            constructors,
        };
    }, { constructorNames: CONSTRUCTOR_NAMES, driverNames: DRIVER_NAMES });

    if (!teamData) return null;

    return buildTeamResult(teamData, rank, selectedRaceName);
}

/**
 * Extract team data from a team page (when navigation occurs instead of popup).
 */
async function extractTeamDataFromPage(page, rank, selectedRaceName) {
    const teamData = await page.evaluate(({ constructorNames, driverNames }) => {
        const root = document.querySelector('.si-main__container, main') || document.body;
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

        const seenDrivers = new Set();
        const seenConstructors = new Set();
        const normalize = (value) => (value || '')
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, '');
        const extractNamesInTextOrder = (text, names) => names
            .map((name) => ({ name, index: normalize(text).indexOf(normalize(name)) }))
            .filter((entry) => entry.index >= 0)
            .sort((a, b) => a.index - b.index)
            .map((entry) => entry.name);

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

        for (const driverName of extractNamesInTextOrder(fullText, driverNames)) {
            if (!seenDrivers.has(driverName) && drivers.length < 5) {
                seenDrivers.add(driverName);
                drivers.push({ name: driverName, points: null, turbo: false });
            }
        }
        for (const constructorName of extractNamesInTextOrder(fullText, constructorNames)) {
            if (!seenConstructors.has(constructorName) && constructors.length < 2) {
                seenConstructors.add(constructorName);
                constructors.push({ name: constructorName, points: null });
            }
        }

        const x3BoostDriver = /\bx3\s*boost\b|\bboost\s*x3\b/i.test(fullText) ? drivers[0]?.name || null : null;
        return {
            teamName,
            manager,
            totalPoints,
            costCap,
            limitless: /limitless/i.test(fullText),
            turboDriver: null,
            x3BoostDriver,
            chips: {
                x3Boost: /\bx3\s*boost\b|\bboost\s*x3\b/i.test(fullText) || !!x3BoostDriver,
                x3BoostDriver,
                noNegative: /\bno\s*negative\b/i.test(fullText),
                wildcard: /\bwildcard\b/i.test(fullText),
                limitless: /\blimitless\b/i.test(fullText),
                finalFix: /\bfinal\s*fix\b/i.test(fullText),
                autopilot: /\bautopilot\b/i.test(fullText),
            },
            drivers,
            constructors,
        };
    }, { constructorNames: CONSTRUCTOR_NAMES, driverNames: DRIVER_NAMES });

    if (!teamData) return null;

    return buildTeamResult(teamData, rank, selectedRaceName);
}

async function extractTeamDataFromSidePanel(page, rank, selectedRaceName, expectedTeamName = '', fallbackManager = '') {
    const teamData = await page.evaluate(async ({ constructorNames, driverNames, expectedTeamName, fallbackManager }) => {
        const normalize = (value) => (value || '')
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, '');
        const expected = normalize(expectedTeamName);
        const expectedManager = normalize(fallbackManager);
        const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
        const matchesName = (text, name) => normalize(text).includes(normalize(name));
        const extractNamesInTextOrder = (text, names) => names
            .map((name) => ({ name, index: normalize(text).indexOf(normalize(name)) }))
            .filter((entry) => entry.index >= 0)
            .sort((a, b) => a.index - b.index)
            .map((entry) => entry.name);

        const candidates = Array.from(document.querySelectorAll('aside, section, div'))
            .map((node) => {
                const rect = node.getBoundingClientRect();
                const text = (node.innerText || '').trim();
                const normalizedText = normalize(text);
                const lowerText = text.toLowerCase();
                const driverHits = driverNames.filter((name) => normalizedText.includes(normalize(name))).length;
                const constructorHits = constructorNames.filter((name) => normalizedText.includes(normalize(name))).length;
                const keywordHits = ['cost cap', 'points', 'pts', 'limitless'].filter((word) => lowerText.includes(word)).length;
                let score = driverHits * 5 + constructorHits * 7 + keywordHits * 2;

                if (expected && normalize(text).includes(expected)) {
                    score += 45;
                }
                if (expectedManager && normalizedText.includes(expectedManager)) {
                    score += 18;
                }
                if (rect.left >= window.innerWidth * 0.55) {
                    score += 10;
                }
                if (rect.right <= window.innerWidth * 0.52) {
                    score -= 35;
                }
                if (rect.width < 220 || rect.height < 200) {
                    score -= 20;
                }
                if (rect.width > window.innerWidth * 0.55) {
                    score -= 25;
                }

                return { node, rect, text, score };
            })
            .filter((entry) => entry.text.length > 30 && entry.score > 0)
            .sort((a, b) => b.score - a.score);

        const best = candidates[0];
        if (!best) {
            return null;
        }

        const container = best.node;
        const collectNodeText = (node) => {
            const pieces = [];
            const mainText = (node.innerText || '').trim();
            if (mainText) {
                pieces.push(mainText);
            }
            for (const element of node.querySelectorAll('[aria-label], [title], img[alt]')) {
                const attrText = element.getAttribute('aria-label') || element.getAttribute('title') || element.getAttribute('alt') || '';
                const trimmed = attrText.trim();
                if (trimmed) {
                    pieces.push(trimmed);
                }
            }
            return pieces.join('\n');
        };

        const scrollCandidates = [container, ...container.querySelectorAll('div, section, ul')];
        let scrollTarget = null;
        let bestScrollRoom = 0;
        for (const candidate of scrollCandidates) {
            const scrollRoom = candidate.scrollHeight - candidate.clientHeight;
            if (scrollRoom > bestScrollRoom + 40) {
                bestScrollRoom = scrollRoom;
                scrollTarget = candidate;
            }
        }

        const snapshots = new Set();
        snapshots.add(collectNodeText(container));

        if (scrollTarget && bestScrollRoom > 40) {
            const originalScrollTop = scrollTarget.scrollTop;
            const steps = 7;
            for (let i = 0; i < steps; i++) {
                const nextTop = Math.round((bestScrollRoom * i) / Math.max(1, steps - 1));
                scrollTarget.scrollTop = nextTop;
                scrollTarget.dispatchEvent(new Event('scroll', { bubbles: true }));
                await delay(120);
                snapshots.add(collectNodeText(container));
            }
            scrollTarget.scrollTop = originalScrollTop;
            scrollTarget.dispatchEvent(new Event('scroll', { bubbles: true }));
        }

        const fullText = Array.from(snapshots).join('\n');
        const lines = fullText.split('\n').map((line) => line.trim()).filter(Boolean);
        const drivers = [];
        const constructors = [];
        const seenDrivers = new Set();
        const seenConstructors = new Set();

        let teamName = expectedTeamName || 'Unknown Team';
        let manager = fallbackManager || '';
        let totalPoints = 0;
        let costCap = '';
        let limitless = /limitless/i.test(fullText);
        let turboDriver = null;
        let x3BoostDriver = null;

        const titleEl = container.querySelector('.si-player__name, [class*="player__name"], [class*="team__name"], h1, h2, h3');
        if (titleEl) {
            teamName = titleEl.textContent.trim();
        } else if (!expectedTeamName && lines.length > 0) {
            teamName = lines[0];
        }

        const titleIndex = lines.findIndex((line) => normalize(line) === normalize(teamName));
        if (titleIndex >= 0 && lines[titleIndex + 1] && !/\$|pts|points|limitless/i.test(lines[titleIndex + 1])) {
            manager = lines[titleIndex + 1];
        }

        const totalMatch = fullText.match(/(\d+)\s*PTS?\b/i);
        if (totalMatch) {
            totalPoints = parseInt(totalMatch[1], 10);
        }
        const costMatch = fullText.match(/\$([\d.]+)\s*M?/i);
        if (costMatch) {
            costCap = `$${costMatch[1]}M`;
        }

        const itemCandidates = Array.from(container.querySelectorAll('button, a, li, [role="button"], [class*="row"], [class*="card"], [class*="list-item"]'))
            .map((node) => {
                const text = (node.innerText || node.textContent || '').trim();
                const rect = node.getBoundingClientRect();
                const badgeText = Array.from(node.querySelectorAll('*'))
                    .map((child) => {
                        const parts = [
                            child.textContent || '',
                            child.getAttribute?.('aria-label') || '',
                            child.getAttribute?.('title') || '',
                            child.getAttribute?.('alt') || '',
                        ];
                        return parts.join(' ').trim();
                    })
                    .filter(Boolean)
                    .join(' ');
                return { text, badgeText, top: rect.top, width: rect.width, height: rect.height };
            })
            .filter((entry) => entry.text.length > 3 && entry.width > 140 && entry.height > 28)
            .sort((a, b) => a.top - b.top);

        for (const item of itemCandidates) {
            const text = item.text;
            const badgeText = item.badgeText || '';
            const normalizedText = normalize(text);
            const normalizedBadgeText = normalize(badgeText);
            const ptsMatch = text.match(/(-?\d+)\s*PTS?/i);
            const points = ptsMatch ? parseInt(ptsMatch[1], 10) : null;

            const driverMatch = driverNames.find((name) => normalizedText.includes(normalize(name)));
            if (driverMatch && !seenDrivers.has(driverMatch)) {
                seenDrivers.add(driverMatch);
                const isTurbo = /\b(2x|x2)\b/i.test(`${text} ${badgeText}`) || normalizedBadgeText.includes('2x') || normalizedBadgeText.includes('x2');
                const isX3Boost = /\b(3x|x3)\b/i.test(`${text} ${badgeText}`) || normalizedBadgeText.includes('3x') || normalizedBadgeText.includes('x3');
                drivers.push({ name: driverMatch, points, turbo: isTurbo });
                if (isTurbo) {
                    turboDriver = driverMatch;
                }
                if (isX3Boost) {
                    x3BoostDriver = driverMatch;
                }
                continue;
            }

            const constructorMatch = constructorNames.find((name) => normalizedText.includes(normalize(name)));
            if (constructorMatch && !seenConstructors.has(constructorMatch)) {
                seenConstructors.add(constructorMatch);
                constructors.push({ name: constructorMatch, points });
            }
        }

        for (const driverName of extractNamesInTextOrder(fullText, driverNames)) {
            if (!seenDrivers.has(driverName) && drivers.length < 5) {
                seenDrivers.add(driverName);
                drivers.push({ name: driverName, points: null, turbo: false });
            }
        }
        for (const constructorName of extractNamesInTextOrder(fullText, constructorNames)) {
            if (!seenConstructors.has(constructorName) && constructors.length < 2) {
                seenConstructors.add(constructorName);
                constructors.push({ name: constructorName, points: null });
            }
        }

        const rowTexts = fullText.split('\n').map((line) => line.trim()).filter(Boolean);
        for (const text of rowTexts) {
            const ptsMatch = text.match(/(-?\d+)\s*PTS?/i);
            const points = ptsMatch ? parseInt(ptsMatch[1], 10) : null;
            const normalizedText = normalize(text);

            const driverMatch = driverNames.find((name) => normalizedText.includes(normalize(name)));
            if (driverMatch) {
                const target = drivers.find((driver) => driver.name === driverMatch);
                if (target && target.points === null && points !== null) {
                    target.points = points;
                }
                if (/\b(2x|x2)\b/i.test(text)) {
                    turboDriver = driverMatch;
                    if (target) target.turbo = true;
                }
                if (/\b(3x|x3)\b/i.test(text)) {
                    x3BoostDriver = driverMatch;
                }
                continue;
            }

            const constructorMatch = constructorNames.find((name) => normalizedText.includes(normalize(name)));
            if (constructorMatch) {
                const target = constructors.find((constructor) => constructor.name === constructorMatch);
                if (target && target.points === null && points !== null) {
                    target.points = points;
                }
            }
        }

        if (drivers.length < 5 || constructors.length < 2) {
            return null;
        }

        return {
            teamName,
            manager,
            totalPoints,
            costCap,
            limitless,
            turboDriver,
            x3BoostDriver,
            chips: {
                x3Boost: /\bx3\s*boost\b|\bboost\s*x3\b/i.test(fullText) || !!x3BoostDriver,
                x3BoostDriver,
                noNegative: /\bno\s*negative\b/i.test(fullText),
                wildcard: /\bwildcard\b/i.test(fullText),
                limitless: /\blimitless\b/i.test(fullText),
                finalFix: /\bfinal\s*fix\b/i.test(fullText),
                autopilot: /\bautopilot\b/i.test(fullText),
            },
            drivers,
            constructors,
        };
    }, { constructorNames: CONSTRUCTOR_NAMES, driverNames: DRIVER_NAMES, expectedTeamName, fallbackManager });

    if (!teamData) return null;
    return buildTeamResult(teamData, rank, selectedRaceName);
}

async function getSidePanelSignature(page) {
    return page.evaluate(() => {
        const candidates = Array.from(document.querySelectorAll('aside, section, div'))
            .map((node) => {
                const rect = node.getBoundingClientRect();
                const text = (node.innerText || '').trim();
                let score = 0;
                if (rect.left >= window.innerWidth * 0.55) score += 10;
                if (rect.width >= 220 && rect.height >= 200) score += 10;
                if (/cost cap|limitless|x3 boost|points|pts/i.test(text)) score += 10;
                return { text, score };
            })
            .filter((entry) => entry.text.length > 20 && entry.score > 0)
            .sort((a, b) => b.score - a.score);

        return candidates[0]?.text.slice(0, 500) || '';
    }).catch(() => '');
}

async function sweepPageForSidePanelData(page, rank, selectedRaceName, expectedTeamName, fallbackManager, fallbackPoints) {
    const originalScrollY = await page.evaluate(() => window.scrollY).catch(() => 0);
    const steps = [0, 140, 280, 420, -140, -280];

    for (const step of steps) {
        if (step !== 0) {
            await page.evaluate((delta) => window.scrollBy(0, delta), step).catch(() => {});
            await page.waitForTimeout(180);
        }

        const panelData = harmonizeTeamResultWithRow(
            await extractTeamDataFromSidePanel(page, rank, selectedRaceName, expectedTeamName, fallbackManager),
            expectedTeamName,
            fallbackManager,
            fallbackPoints,
        );
        if (panelData) {
            await page.evaluate((targetY) => window.scrollTo(0, targetY), originalScrollY).catch(() => {});
            return panelData;
        }
    }

    await page.evaluate((targetY) => window.scrollTo(0, targetY), originalScrollY).catch(() => {});
    return null;
}

async function waitForTeamDataAfterClick(page, rank, selectedRaceName, expectedTeamName, fallbackManager, fallbackPoints, networkCollector, trustPanelSelection = false) {
    for (let attempt = 0; attempt < 12; attempt++) {
        const networkData = harmonizeTeamResultWithRow(extractTeamDataFromNetworkResponses(
            networkCollector ? networkCollector.getResponses() : [],
            rank,
            selectedRaceName,
            expectedTeamName,
            fallbackManager,
        ), expectedTeamName, fallbackManager, fallbackPoints);
        if (networkData) {
            return networkData;
        }

        const popup = await page.$('.si-popup__container');
        if (popup) {
            return harmonizeTeamResultWithRow(
                await extractTeamDataFromPopup(page, rank, selectedRaceName),
                expectedTeamName,
                fallbackManager,
                fallbackPoints,
            );
        }

        if (page.url().includes('/team/')) {
            await page.waitForSelector('.si-main__container, main', { timeout: 8000 }).catch(() => null);
            return harmonizeTeamResultWithRow(
                await extractTeamDataFromPage(page, rank, selectedRaceName),
                expectedTeamName,
                fallbackManager,
                fallbackPoints,
            );
        }

        let panelData = await extractTeamDataFromSidePanel(page, rank, selectedRaceName, expectedTeamName, fallbackManager);
        if (trustPanelSelection && panelData) {
            panelData = {
                ...panelData,
                detailTeamName: panelData.teamName,
                teamName: expectedTeamName || panelData.teamName,
                manager: panelData.manager || fallbackManager,
            };
        } else {
            panelData = harmonizeTeamResultWithRow(
                panelData,
                expectedTeamName,
                fallbackManager,
                fallbackPoints,
            );
        }
        if (panelData) {
            return panelData;
        }

        if (attempt === 3 || attempt === 7) {
            const sweptPanelData = await sweepPageForSidePanelData(
                page,
                rank,
                selectedRaceName,
                expectedTeamName,
                fallbackManager,
                fallbackPoints,
            );
            if (sweptPanelData) {
                return sweptPanelData;
            }
        }
        await page.waitForTimeout(500);
    }

    return null;
}

/**
 * Find clickable team rows on the league leaderboard.
 * League page may use clickable cards/rows/list items inside the leaderboard.
 * Avoid generic navigation buttons such as "Teams".
 */
async function findTeamRows(page) {
    const candidateSelectors = [
        '[class*="leaderboard"] [class*="row"]',
        '[class*="leaderboard"] [class*="card"]',
        '[class*="league"] [class*="row"]',
        '[class*="league"] [class*="card"]',
        '[class*="league"] li',
        '[class*="leaderboard"] li',
        'table tbody tr',
        '[role="row"]',
        '[class*="si-"] [class*="list-item"]',
        'main [role="button"]',
        'main button',
        'main li',
        'main article',
        'main div',
        '.si-main__container [role="button"]',
        '.si-main__container button',
        '.si-main__container li',
        '.si-main__container article',
        '.si-main__container div',
    ];

    let bestRows = [];
    let bestSelector = null;

    for (const selector of candidateSelectors) {
        try {
            const elements = await page.$$(selector);
            const filtered = [];

            for (const element of elements) {
                const metadata = await element.evaluate((node) => {
                    const text = (node.textContent || '').replace(/\s+/g, ' ').trim();
                    const lines = (node.innerText || '').split('\n').map((line) => line.trim()).filter(Boolean);
                    const rankSource = `${lines[0] || ''} ${text}`.trim();
                    const rankMatch = rankSource.match(/^[^\d]{0,8}(\d{1,3})\b/);
                    const numericMatches = [...text.matchAll(/\b(\d{1,4})\b/g)].map((match) => parseInt(match[1], 10));
                    const inferredPoints = numericMatches.length > 1
                        ? Math.max(...numericMatches.filter((value) => Number.isFinite(value)))
                        : null;
                    const clickableChild = node.querySelector('button, a, [role="button"]');
                    const navAncestor = node.closest('header, nav, footer, aside');
                    const rect = node.getBoundingClientRect();
                    const depth = (() => {
                        let current = node;
                        let count = 0;
                        while (current && current.parentElement) {
                            count += 1;
                            current = current.parentElement;
                        }
                        return count;
                    })();
                    const hasHeaderLabels = /position\s+name\s+pts\s+team/i.test(text);

                    return {
                        text,
                        lines,
                        rank: rankMatch ? parseInt(rankMatch[1], 10) : null,
                        points: inferredPoints,
                        hasClickableChild: !!clickableChild,
                        inNav: !!navAncestor,
                        visible: rect.width > 0 && rect.height > 0,
                        left: rect.left,
                        right: rect.right,
                        width: rect.width,
                        height: rect.height,
                        depth,
                        hasHeaderLabels,
                    };
                });

                const isLikelyRow = metadata.visible
                    && !metadata.inNav
                    && !!metadata.rank
                    && metadata.rank >= 1
                    && metadata.rank <= 100
                    && metadata.left < 20 + (await page.evaluate(() => window.innerWidth * 0.72))
                    && metadata.width > 260
                    && metadata.height >= 36
                    && metadata.height <= 180
                    && metadata.text.length > 8
                    && metadata.lines.length >= 2
                    && !metadata.hasHeaderLabels
                    && (metadata.points === null || metadata.points !== metadata.rank)
                    && !/^teams?$/i.test(metadata.text)
                    && !/^drivers?$/i.test(metadata.text)
                    && !/^constructors?$/i.test(metadata.text)
                    && !/cookie preferences/i.test(metadata.text);

                if (isLikelyRow) {
                    filtered.push({
                        element,
                        rank: metadata.rank,
                        points: metadata.points,
                        text: metadata.text,
                        teamName: metadata.lines.find((line) => {
                            const normalized = normalizeName(line);
                            return normalized
                                && normalized !== String(metadata.rank)
                                && !/^(position|name|pts|team)$/.test(normalized)
                                && !/^\d+$/.test(normalized);
                        }) || metadata.lines[1] || metadata.lines[0] || '',
                        manager: metadata.lines.find((line, index) => index > 0 && /[a-z]/i.test(line) && !/\d/.test(line) && normalizeName(line) !== normalizeName(metadata.lines[0])) || '',
                        depth: metadata.depth,
                        width: metadata.width,
                    });
                }
            }

            const deduped = [];
            const seenKeys = new Set();
            filtered
                .sort((a, b) => {
                    if (a.rank !== b.rank) return a.rank - b.rank;
                    if (a.teamName !== b.teamName) return a.teamName.localeCompare(b.teamName);
                    if (a.depth !== b.depth) return a.depth - b.depth;
                    return b.width - a.width;
                })
                .forEach((entry) => {
                    const dedupeKey = `${entry.rank}|${normalizeName(entry.teamName)}|${normalizeName(entry.manager)}`;
                    if (!seenKeys.has(dedupeKey)) {
                        seenKeys.add(dedupeKey);
                        deduped.push(entry);
                    }
                });

            if (deduped.length > 0) {
                console.log(`   🔎 Selector ${selector} matched ${deduped.length} leaderboard rows`);
                if (deduped.length > bestRows.length) {
                    bestRows = deduped;
                    bestSelector = selector;
                }
            }
        } catch (e) {}
    }

    if (bestRows.length > 0) {
        const rankCounts = new Map();
        for (const row of bestRows) {
            rankCounts.set(row.rank, (rankCounts.get(row.rank) || 0) + 1);
        }
        const duplicateRanks = [...rankCounts.entries()]
            .filter(([, count]) => count > 1)
            .map(([rank, count]) => `${rank}x${count}`);
        console.log(`   📋 Using selector ${bestSelector} with ${bestRows.length} leaderboard rows`);
        console.log(`   🧪 Sample rows: ${bestRows.slice(0, 8).map((row) => `#${row.rank} ${row.teamName}`).join(' | ')}`);
        if (duplicateRanks.length > 0) {
            console.log(`   🤝 Duplicate ranks detected: ${duplicateRanks.join(', ')}`);
        }
        return bestRows;
    }

    return [];
}

async function clickTeamRow(page, rowHandle) {
    const clickableChild = await rowHandle.$('button:not([disabled]), a[href], [role="button"]');
    if (clickableChild) {
        const childText = (await clickableChild.textContent())?.replace(/\s+/g, ' ').trim() || '';
        if (!/^teams?$/i.test(childText)) {
            await clickableChild.click();
            return;
        }
    }

    await rowHandle.click();
}

/**
 * Run the scraping logic (shared by both launch modes)
 */
async function runScraper(page) {
    const outputFile = getOutputFilePath();
    const results = {
        leagueUrl: CONFIG.LEAGUE_URL,
        targetRace: CONFIG.TARGET_RACE,
        scrapedAt: new Date().toISOString(),
        teams: [],
    };

    try {
        console.log('🏁 F1 Fantasy League Scraper');
        console.log(`📊 Target: ${CONFIG.LEAGUE_URL}`);
        if (CONFIG.TARGET_RACE) {
            console.log(`🏆 Race filter: ${CONFIG.TARGET_RACE}`);
        } else {
            console.log('🏆 Race filter: current page selection');
        }
        console.log('');

        await handleCookieConsent(page);

        // Wait for main content
        await page.waitForSelector('.si-main__container, main, [class*="leaderboard"], [class*="league"]', { timeout: 30000 }).catch(() => {});
        await page.waitForTimeout(CONFIG.DELAYS.PAGE_LOAD);

        if (CONFIG.TARGET_RACE) {
            console.log(`📅 Selecting race: ${CONFIG.TARGET_RACE}...`);
            await selectRace(page, CONFIG.TARGET_RACE);
        }

        const teamRows = await findTeamRows(page);

        if (teamRows.length === 0) {
            console.log('⚠️  No team rows found. The league page structure may have changed.');
            console.log('   Try inspecting the page and updating selectors in findTeamRows().');
            if (process.argv.includes('--debug')) {
                const html = await page.content();
                const debugDir = path.join(getOutputDir(), 'debug');
                const debugPath = path.join(debugDir, 'league_page_debug.html');
                await fsp.mkdir(debugDir, { recursive: true });
                await fsp.writeFile(debugPath, html, 'utf8');
                console.log(`   Debug: saved page HTML to ${debugPath}`);
            }
            console.log('   Saving empty results.');
        } else {
            const maxTeams = teamRows.length;
            console.log(`\n📋 Processing ${maxTeams} teams...\n`);

            for (let i = 0; i < maxTeams; i++) {
                let networkCollector = null;
                try {
                    const rowInfo = teamRows[i];
                    const row = rowInfo.element;
                    const text = rowInfo.text || (await row.textContent())?.trim() || '';
                    if (!text || text.length < 3) continue;

                    console.log(`   [${i + 1}/${maxTeams}] Clicking: ${text.substring(0, 50)}...`);
                    await row.scrollIntoViewIfNeeded().catch(() => {});
                    const beforePanelSignature = await getSidePanelSignature(page);
                    networkCollector = startNetworkResponseCollector(page);
                    await clickTeamRow(page, row);
                    await page.waitForTimeout(350);
                    const afterPanelSignature = await getSidePanelSignature(page);
                    const trustPanelSelection = !!afterPanelSignature && afterPanelSignature !== beforePanelSignature;

                    const rank = rowInfo.rank || (i + 1);
                    const teamData = await waitForTeamDataAfterClick(
                        page,
                        rank,
                        CONFIG.TARGET_RACE,
                        rowInfo.teamName,
                        rowInfo.manager,
                        rowInfo.points,
                        networkCollector,
                        trustPanelSelection,
                    );
                    const capturedResponses = networkCollector.getResponses();
                    networkCollector.stop();
                    networkCollector = null;
                    if (teamData) {
                        const turboDriverFromResponses = extractTurboDriverFromCapturedResponses(capturedResponses, teamData.drivers);
                        if (turboDriverFromResponses) {
                            applyTurboDriverToTeamResult(teamData, turboDriverFromResponses);
                        }
                        const chipInfoFromResponses = extractChipInfoFromCapturedResponses(capturedResponses, teamData.drivers);
                        if (chipInfoFromResponses.used.length > 0) {
                            applyChipInfoToTeamResult(teamData, chipInfoFromResponses);
                        }
                        const transferInfoFromResponses = extractTransferInfoFromCapturedResponses(capturedResponses, teamData.drivers);
                        if (
                            transferInfoFromResponses.made !== null
                            || transferInfoFromResponses.allowed !== null
                            || transferInfoFromResponses.remaining !== null
                            || transferInfoFromResponses.penaltyPerTransfer !== null
                        ) {
                            applyTransferInfoToTeamResult(teamData, transferInfoFromResponses);
                        }
                        await saveCapturedResponsesArtifact({
                            rank,
                            teamName: rowInfo.teamName,
                            manager: rowInfo.manager,
                        }, capturedResponses);
                        await saveNetworkDebugArtifact(teamData);
                        delete teamData.__networkDebug;
                        results.teams.push(teamData);
                        const pts = teamData.totalPoints ?? teamData.selectedRace?.totalPoints ?? 0;
                        const lineup = [...(teamData.drivers || []).map((d) => `${d.name} ${d.points}`), ...(teamData.constructors || []).map((c) => `${c.name} ${c.points}`)].join(', ');
                        console.log(`      ✅ #${rank} ${teamData.teamName} | ${pts} pts | ${lineup}`);

                        if (!page.url().includes('/team/')) {
                            await page.waitForTimeout(CONFIG.DELAYS.BETWEEN_TEAMS);
                            continue;
                        }
                    }

                    if (page.url().includes('/team/')) {
                        await page.goBack();
                        await page.waitForLoadState('load');
                    } else if (await page.$('.si-popup__container')) {
                        await closePopup(page);
                    } else {
                        console.log('      ⚠️  No team details found after clicking row');
                    }

                    await page.waitForTimeout(CONFIG.DELAYS.BETWEEN_TEAMS);
                } catch (err) {
                    if (networkCollector) {
                        networkCollector.stop();
                    }
                    console.log(`      ⚠️  Error: ${err.message}`);
                    await page.keyboard.press('Escape');
                    await page.waitForTimeout(500);
                }
            }
        }

        await fsp.mkdir(path.dirname(outputFile), { recursive: true });
        await fsp.writeFile(outputFile, JSON.stringify(results, null, 2), 'utf8');
        console.log(`\n💾 Saved to ${outputFile}`);
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
    if (CONFIG.CDP_URL) {
        const { browser, page, browserLabel, shouldClosePage } = await connectToExistingBrowser();
        console.log(`✅ Browser ready: ${browserLabel}`);
        console.log(`📊 Using already-open league page: ${page.url()}`);
        await handleCookieConsent(page);
        console.log(`✅ Current URL: ${page.url()}`);

        if (!page.url().includes('/leagues/') && !page.url().includes('leaderboard')) {
            console.log(`❌ Redirected to ${page.url()} instead of the league page.`);
            console.log('   Make sure the Chrome instance you attached to is already logged in.');
            console.log('   If needed, open the league page manually in that Chrome window first, then rerun the scraper.');
            if (shouldClosePage) {
                await page.close().catch(() => {});
            }
            return;
        }

        await runScraper(page);
        if (shouldClosePage) {
            await page.close().catch(() => {});
        }
        return;
    }

    if (CONFIG.USE_PERSISTENT_PROFILE) {
        const { context, browserLabel } = await launchPersistentContext();
        console.log(`✅ Browser ready: ${browserLabel}`);
        const existingPage = context.pages()[0] || await context.newPage();
        const page = await createPage(existingPage);

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
        console.log(`📊 Navigating to league: ${CONFIG.LEAGUE_URL}`);
        await page.goto(CONFIG.LEAGUE_URL, { waitUntil: 'load', timeout: 60000 });
        await handleCookieConsent(page);
        const currentUrl = page.url();

        if (!currentUrl.includes('/leagues/') && !currentUrl.includes('leaderboard')) {
            console.log(`❌ Redirected to ${currentUrl} – league URL requires login.`);
            console.log('   Make sure you are fully logged in (check for "My Team" or your name in the header).');
            console.log('   Press Enter to retry navigation...');
            await new Promise((resolve) => process.stdin.once('data', resolve));
            await page.goto(CONFIG.LEAGUE_URL, { waitUntil: 'load', timeout: 60000 });
            await handleCookieConsent(page);
        }

        console.log(`✅ Current URL: ${page.url()}`);
        await runScraper(page);
        await context.close();
        return;
    }

    const { browser, browserLabel } = await launchBrowser();
    console.log(`✅ Browser ready: ${browserLabel}`);
    const page = await createPage(await browser.newPage());

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

    console.log(`📊 Navigating to league: ${CONFIG.LEAGUE_URL}`);
    await page.goto(CONFIG.LEAGUE_URL, { waitUntil: 'load', timeout: 60000 });
    await handleCookieConsent(page);
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
const browserArg = getArgValue('--browser');
if (browserArg) {
    CONFIG.BROWSER = browserArg.toLowerCase();
}
const cdpUrlArg = getArgValue('--cdp-url');
if (cdpUrlArg) {
    CONFIG.CDP_URL = cdpUrlArg;
}
const leagueUrlArg = getArgValue('--league-url');
if (leagueUrlArg) {
    CONFIG.LEAGUE_URL = leagueUrlArg;
}
const raceArg = getArgValue('--race') || getArgValue('--view');
if (raceArg) {
    CONFIG.TARGET_RACE = raceArg;
}
const outputArg = getArgValue('--output');
if (outputArg) {
    CONFIG.OUTPUT_FILE = path.isAbsolute(outputArg) ? outputArg : path.resolve(process.cwd(), outputArg);
}
const outputDirArg = getArgValue('--output-dir');
if (outputDirArg) {
    CONFIG.OUTPUT_DIR = path.isAbsolute(outputDirArg) ? outputDirArg : path.resolve(process.cwd(), outputDirArg);
}

main().catch((e) => {
    console.error(e);
    process.exit(1);
});
