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

async function loadNames() {
    if (indexCache) return indexCache;
    try {
        const res = await fetch(DATA_URL + 'names.json');
        if (!res.ok) throw new Error('No names index');
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
    const names = await loadNames();

    // Exact match
    if (names[name]) {
        return { slug: slugify(name), id: names[name] };
    }

    // Case-insensitive
    const lower = name.toLowerCase();
    for (const [k, id] of Object.entries(names)) {
        if (k.toLowerCase() === lower) {
            return { slug: slugify(k), id };
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

function portraitUrl(charId, size = 64) {
    return `https://images.evetech.net/characters/${charId}/portrait?size=${size}`;
}

function charLink(name, charId, size = 64) {
    const img = charId ? `<img src="${portraitUrl(charId, size)}" class="char-portrait char-link" data-name="${name.replace(/"/g, '&quot;')}" alt="" loading="lazy">` : '';
    return `${img}<a href="javascript:void(0)" class="char-link" data-name="${name.replace(/"/g, '&quot;')}">${name}</a>`;
}

function zkillLink(charId, label) {
    return `<a href="https://zkillboard.com/character/${charId}/" target="_blank" rel="noopener" class="zkill-link">${label}</a>`;
}

function corpLogoUrl(corpId, size = 32) {
    return `https://images.evetech.net/corporations/${corpId}/logo?size=${size}`;
}

function allianceLogoUrl(allianceId, size = 32) {
    return `https://images.evetech.net/alliances/${allianceId}/logo?size=${size}`;
}

function corpLink(name, corpId, size = 32) {
    if (!corpId || !name) return '';
    const img = `<img src="${corpLogoUrl(corpId, size)}" class="corp-logo" alt="" loading="lazy">`;
    return `<a href="https://zkillboard.com/corporation/${corpId}/" target="_blank" rel="noopener" class="corp-link" title="${name.replace(/"/g, '&quot;')}">${img}<span>${name}</span></a>`;
}

function allianceLink(name, allianceId, size = 32) {
    if (!allianceId || !name) return '';
    const img = `<img src="${allianceLogoUrl(allianceId, size)}" class="alliance-logo" alt="" loading="lazy">`;
    return `<a href="https://zkillboard.com/alliance/${allianceId}/" target="_blank" rel="noopener" class="alliance-link" title="${name.replace(/"/g, '&quot;')}">${img}<span>${name}</span></a>`;
}

function entityHeader(name, charId, corpId, corpName, allianceId, allianceName, portraitSize = 64) {
    let html = charLink(name, charId, portraitSize);
    const orgs = [];
    if (corpId && corpName) orgs.push(corpLink(corpName, corpId));
    if (allianceId && allianceName) orgs.push(allianceLink(allianceName, allianceId));
    if (orgs.length) {
        html += `<div class="entity-orgs">${orgs.join('')}</div>`;
    }
    return html;
}

function nemesisEntityHeader(name, charId, corpId, corpName, allianceId, allianceName, portraitSize = 128) {
    let html = charLink(name, charId, portraitSize);
    const orgs = [];
    if (corpId && corpName) orgs.push(corpLink(corpName, corpId));
    if (allianceId && allianceName) orgs.push(allianceLink(allianceName, allianceId));
    if (orgs.length) {
        html += `<div class="entity-orgs">${orgs.join('')}</div>`;
    }
    return html;
}

function renderResult(data) {
    document.getElementById('victimName').innerHTML = charLink(data.character_name, data.character_id, 64) + zkillLink(data.character_id, 'zKill');
    const victimOrgs = document.getElementById('victimOrgs');
    const orgs = [];
    if (data.corporation_id && data.corporation_name) orgs.push(corpLink(data.corporation_name, data.corporation_id));
    if (data.alliance_id && data.alliance_name) orgs.push(allianceLink(data.alliance_name, data.alliance_id));
    victimOrgs.innerHTML = orgs.join('');
    victimOrgs.style.display = orgs.length ? 'flex' : 'none';
    document.getElementById('totalLosses').textContent = data.total_losses;

    // Handle characters with no nemesis (0 losses)
    if (data.nemesis && data.nemesis.id) {
        const nemOrgs = [];
        if (data.nemesis.corporation_id && data.nemesis.corporation_name) nemOrgs.push(corpLink(data.nemesis.corporation_name, data.nemesis.corporation_id));
        if (data.nemesis.alliance_id && data.nemesis.alliance_name) nemOrgs.push(allianceLink(data.nemesis.alliance_name, data.nemesis.alliance_id));
        document.getElementById('nemesisName').innerHTML = charLink(data.nemesis.name, data.nemesis.id, 128) +
            (nemOrgs.length ? `<div class="entity-orgs">${nemOrgs.join('')}</div>` : '') +
            zkillLink(data.nemesis.id, 'zKill');
        document.getElementById('nemesisKills').textContent = data.nemesis.final_blows;
    } else {
        document.getElementById('nemesisName').innerHTML = '<span style="color:var(--text-dim)">No recorded losses</span>';
        document.getElementById('nemesisKills').textContent = '0';
    }
    document.getElementById('nemesisFinalBlows').textContent = 'final blows';

    // Top killers
    const killersEl = document.getElementById('topKillers');
    killersEl.innerHTML = '';
    if (data.top_killers && data.top_killers.length > 0) {
        data.top_killers.forEach((k, i) => {
            const row = document.createElement('div');
            row.className = 'killer-row' + (i === 0 ? ' nemesis' : '');
            row.innerHTML = `
                <div class="killer-info">
                    <div class="killer-rank">${i + 1}</div>
                    <div class="killer-name">${charLink(k.name, k.id, 64)}</div>
                </div>
                <div class="killer-count">${k.final_blows} final blows</div>
            `;
            killersEl.appendChild(row);
        });
    } else {
        killersEl.innerHTML = '<div class="killer-row"><div class="killer-name" style="color:var(--text-dim)">No losses recorded in tracking period.</div></div>';
    }

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
                <div class="killer-name">${charLink(entry.name, entry.id, 64)}</div>
            </div>
            <div class="killer-count">${entry.kill_count} final blows on them</div>
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

async function doSearch(pushState = true) {
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
            if (pushState) {
                history.pushState(null, '', '#' + encodeURIComponent(data.character_name));
            }
        } else {
            // Character not directly tracked — check if they appear in reverse index
            const charId = await resolveCharacterId(name);
            if (charId) {
                // Show reverse-only view
                document.getElementById('victimName').textContent = name;
                document.getElementById('totalLosses').textContent = '?';
                document.getElementById('nemesisName').textContent = 'Not tracked';
                document.getElementById('nemesisKills').textContent = '?';
                document.getElementById('nemesisFinalBlows').textContent = 'final blows';
                document.getElementById('topKillers').innerHTML = '<div class="killer-row"><div class="killer-name" style="color:var(--text-dim)">Character not in tracked database.</div></div>';
                document.getElementById('result').classList.remove('hidden');
                await renderReverseNemesis(charId);
                if (pushState) {
                    history.pushState(null, '', '#' + encodeURIComponent(name));
                }
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

function handleHash() {
    const hash = location.hash.slice(1);
    if (!hash) return;
    const name = decodeURIComponent(hash);
    document.getElementById('searchInput').value = name;
    doSearch(false);
}

async function loadMeta() {
    try {
        const res = await fetch(DATA_URL + 'meta.json');
        if (!res.ok) return null;
        return await res.json();
    } catch (e) {
        return null;
    }
}

function fmtDateRange(from, to) {
    if (!from || !to) return '';
    const d1 = new Date(from + 'T00:00:00');
    const d2 = new Date(to + 'T00:00:00');
    const opts = { day: 'numeric', month: 'long', year: 'numeric' };
    return d1.toLocaleDateString('en-GB', opts) + ' to ' + d2.toLocaleDateString('en-GB', opts);
}

async function loadDbStats() {
    const index = await loadNames();
    const count = Object.keys(index).length;
    document.getElementById('trackedCount').textContent = count;

    const meta = await loadMeta();
    if (meta) {
        document.getElementById('dateRange').textContent = fmtDateRange(meta.date_from, meta.date_to);
    } else {
        document.getElementById('dateRange').textContent = '';
    }
}

let suggestionIndex = -1;
let suggestionNames = [];

function showSuggestions(matches) {
    const box = document.getElementById('suggestions');
    if (!matches.length) {
        box.classList.add('hidden');
        return;
    }
    suggestionNames = matches.map(m => m.name);
    suggestionIndex = -1;
    box.innerHTML = matches.map((m, i) => `
        <div class="suggestion-item" data-index="${i}" data-name="${m.name.replace(/"/g, '&quot;')}">
            <img src="${portraitUrl(m.id, 32)}" alt="">
            <span>${m.name}</span>
        </div>
    `).join('');
    box.classList.remove('hidden');
}

function hideSuggestions() {
    document.getElementById('suggestions').classList.add('hidden');
    suggestionIndex = -1;
}

function updateActiveSuggestion() {
    const items = document.querySelectorAll('.suggestion-item');
    items.forEach((el, i) => {
        el.classList.toggle('active', i === suggestionIndex);
    });
}

function selectSuggestion(name) {
    document.getElementById('searchInput').value = name;
    hideSuggestions();
    doSearch();
}

let debounceTimer;
document.getElementById('searchInput').addEventListener('input', e => {
    clearTimeout(debounceTimer);
    const query = e.target.value.trim();
    if (!query || query.length < 2) {
        hideSuggestions();
        return;
    }
    debounceTimer = setTimeout(async () => {
        const names = await loadNames();
        const lower = query.toLowerCase();
        const matches = [];
        for (const [name, id] of Object.entries(names)) {
            if (name.toLowerCase().includes(lower)) {
                matches.push({ name, id });
                if (matches.length >= 10) break;
            }
        }
        showSuggestions(matches);
    }, 150);
});

document.getElementById('searchInput').addEventListener('keydown', e => {
    const items = document.querySelectorAll('.suggestion-item');
    if (e.key === 'ArrowDown') {
        e.preventDefault();
        suggestionIndex = Math.min(suggestionIndex + 1, items.length - 1);
        updateActiveSuggestion();
    } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        suggestionIndex = Math.max(suggestionIndex - 1, -1);
        updateActiveSuggestion();
    } else if (e.key === 'Enter') {
        if (suggestionIndex >= 0 && suggestionNames[suggestionIndex]) {
            e.preventDefault();
            selectSuggestion(suggestionNames[suggestionIndex]);
        } else {
            doSearch();
        }
    } else if (e.key === 'Escape') {
        hideSuggestions();
    }
});

document.getElementById('suggestions').addEventListener('click', e => {
    const item = e.target.closest('.suggestion-item');
    if (item) {
        selectSuggestion(item.dataset.name);
    }
});

document.addEventListener('click', e => {
    if (!e.target.closest('.search-wrap')) {
        hideSuggestions();
    }
});

document.getElementById('searchBtn').addEventListener('click', doSearch);

// Delegate clicks on character links to search
document.addEventListener('click', e => {
    const link = e.target.closest('.char-link');
    if (!link) return;
    e.preventDefault();
    document.getElementById('searchInput').value = link.dataset.name;
    doSearch();
});

// Handle browser back/forward
window.addEventListener('popstate', () => {
    handleHash();
});

// Handle initial hash on load
loadDbStats().then(() => {
    handleHash();
});
