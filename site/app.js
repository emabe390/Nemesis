const DATA_URL = './data/';
const ESI_IMG = 'https://images.evetech.net/characters/';

let indexCache = null;
let reverseCache = null;

async function loadReverseIndex() {
    if (reverseCache) return reverseCache;
    try {
        const res = await fetch(DATA_URL + 'reverse_nemesis.json');
        if (!res.ok) throw new Error('No reverse index');
        reverseCache = await res.json();
        return reverseCache;
    } catch (e) {
        return {};
    }
}

async function loadIndex() {
    if (indexCache) return indexCache;
    try {
        const res = await fetch(DATA_URL + 'index.json');
        if (!res.ok) throw new Error('No index');
        indexCache = await res.json();
        return indexCache;
    } catch (e) {
        return {};
    }
}

function slugify(name) {
    return name.toLowerCase().replace(/[\s-]+/g, '_').replace(/[^a-z0-9_]/g, '');
}

async function lookupCharacter(name) {
    const index = await loadIndex();

    // Exact match
    if (index[name]) {
        return { slug: slugify(name), ...index[name] };
    }

    // Case-insensitive
    const lower = name.toLowerCase();
    for (const [k, v] of Object.entries(index)) {
        if (k.toLowerCase() === lower) {
            return { slug: slugify(k), ...v };
        }
    }

    return null;
}

async function fetchCharacterData(name) {
    const match = await lookupCharacter(name);
    if (!match) return null;

    const res = await fetch(DATA_URL + `${match.id}.json`);
    if (!res.ok) {
        // fallback to slug
        const res2 = await fetch(DATA_URL + `${match.slug}.json`);
        if (!res2.ok) return null;
        return await res2.json();
    }
    return await res.json();
}

function fmtIsk(value) {
    if (!value) return '0 ISK';
    if (value >= 1e9) return (value / 1e9).toFixed(2) + 'B ISK';
    if (value >= 1e6) return (value / 1e6).toFixed(1) + 'M ISK';
    if (value >= 1e3) return (value / 1e3).toFixed(1) + 'K ISK';
    return value.toFixed(0) + ' ISK';
}

function fmtDate(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function renderResult(data) {
    document.getElementById('victimName').textContent = data.character_name;
    document.getElementById('totalLosses').textContent = data.total_losses;
    document.getElementById('nemesisName').textContent = data.nemesis.name;
    document.getElementById('nemesisKills').textContent = data.nemesis.kill_count;
    document.getElementById('nemesisFinalBlows').textContent = data.nemesis.final_blows;

    // Top killers
    const killersEl = document.getElementById('topKillers');
    killersEl.innerHTML = '';
    data.top_killers.forEach((k, i) => {
        const row = document.createElement('div');
        row.className = 'killer-row' + (i === 0 ? ' nemesis' : '');
        row.innerHTML = `
            <div class="killer-info">
                <div class="killer-rank">${i + 1}</div>
                <div class="killer-name">${k.name}</div>
            </div>
            <div class="killer-count">${k.kill_count} kills</div>
        `;
        killersEl.appendChild(row);
    });

    // Recent losses
    const lossesEl = document.getElementById('recentLosses');
    lossesEl.innerHTML = '';
    data.recent_losses.forEach(loss => {
        const row = document.createElement('div');
        row.className = 'loss-row';
        row.innerHTML = `
            <div>
                <span class="loss-ship">${loss.ship_name || 'Unknown Ship'}</span>
                <span class="loss-killer"> — ${loss.killer_name || 'Unknown'}</span>
            </div>
            <div>
                <span class="loss-value">${fmtIsk(loss.loss_value)}</span>
                <span class="loss-time">${fmtDate(loss.killmail_time)}</span>
            </div>
        `;
        lossesEl.appendChild(row);
    });

    document.getElementById('result').classList.remove('hidden');
    document.getElementById('notIndexed').classList.add('hidden');
}

async function renderReverseNemesis(charId) {
    const reverse = await loadReverseIndex();
    const revEl = document.getElementById('reverseNemesis');
    revEl.innerHTML = '';

    const entries = reverse[charId];
    if (!entries || entries.length === 0) {
        revEl.innerHTML = '<div class="killer-row"><div class="killer-name" style="color:var(--text-dim)">No tracked characters consider you their nemesis.</div></div>';
        return;
    }

    entries.forEach((entry, i) => {
        const row = document.createElement('div');
        row.className = 'killer-row';
        row.innerHTML = `
            <div class="killer-info">
                <div class="killer-rank">${i + 1}</div>
                <div class="killer-name">${entry.name}</div>
            </div>
            <div class="killer-count">${entry.kill_count} kills on them</div>
        `;
        revEl.appendChild(row);
    });
}

async function resolveCharacterId(name) {
    // Try to find in index first
    const match = await lookupCharacter(name);
    if (match) return match.id;

    // Fallback: search ESI directly (requires CORS proxy or backend)
    // For static site, we can't call ESI directly due to CORS.
    // So we just return null and show "not tracked".
    return null;
}

async function doSearch() {
    const input = document.getElementById('searchInput');
    const name = input.value.trim();
    if (!name) return;

    document.getElementById('result').classList.add('hidden');
    document.getElementById('notIndexed').classList.add('hidden');
    document.getElementById('error').classList.add('hidden');
    document.getElementById('loading').classList.remove('hidden');

    try {
        const data = await fetchCharacterData(name);
        document.getElementById('loading').classList.add('hidden');

        if (data) {
            renderResult(data);
            await renderReverseNemesis(data.character_id);
        } else {
            // Character not directly tracked — check if they appear in reverse index
            const charId = await resolveCharacterId(name);
            if (charId) {
                // Show reverse-only view
                document.getElementById('victimName').textContent = name;
                document.getElementById('totalLosses').textContent = '?';
                document.getElementById('nemesisName').textContent = 'Not tracked';
                document.getElementById('nemesisKills').textContent = '?';
                document.getElementById('nemesisFinalBlows').textContent = '?';
                document.getElementById('topKillers').innerHTML = '<div class="killer-row"><div class="killer-name" style="color:var(--text-dim)">Character not in tracked database.</div></div>';
                document.getElementById('recentLosses').innerHTML = '';
                document.getElementById('result').classList.remove('hidden');
                await renderReverseNemesis(charId);
            } else {
                document.getElementById('notIndexed').classList.remove('hidden');
            }
        }
    } catch (e) {
        document.getElementById('loading').classList.add('hidden');
        const err = document.getElementById('error');
        err.textContent = 'Error loading data. Try again later.';
        err.classList.remove('hidden');
        console.error(e);
    }
}

async function loadDbStats() {
    const index = await loadIndex();
    const count = Object.keys(index).length;
    document.getElementById('trackedCount').textContent = count;
}

document.getElementById('searchBtn').addEventListener('click', doSearch);
document.getElementById('searchInput').addEventListener('keydown', e => {
    if (e.key === 'Enter') doSearch();
});

loadDbStats();
