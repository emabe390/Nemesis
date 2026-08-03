const DATA_URL = './data/';

function portraitUrl(charId, size = 64) {
    return `https://images.evetech.net/characters/${charId}/portrait?size=${size}`;
}

function charLink(name, charId, size = 64, showPortrait = true) {
    const img = showPortrait && charId ? `<img src="${portraitUrl(charId, size)}" class="char-portrait char-link" data-name="${name.replace(/"/g, '&quot;')}" alt="" loading="lazy">` : '';
    return img;
}

function corpLogoUrl(corpId, size = 24) {
    return `https://images.evetech.net/corporations/${corpId}/logo?size=${size}`;
}

function allianceLogoUrl(allianceId, size = 24) {
    return `https://images.evetech.net/alliances/${allianceId}/logo?size=${size}`;
}

function orgsHtml(entry) {
    const orgs = [];
    if (entry.corporation_id && entry.corporation_name) {
        orgs.push(`<a href="https://zkillboard.com/corporation/${entry.corporation_id}/" target="_blank" rel="noopener" class="org-link" title="${entry.corporation_name.replace(/"/g, '&quot;')}"><img src="${corpLogoUrl(entry.corporation_id, 32)}" class="org-logo" alt="" loading="lazy"></a>`);
    }
    if (entry.alliance_id && entry.alliance_name) {
        orgs.push(`<a href="https://zkillboard.com/alliance/${entry.alliance_id}/" target="_blank" rel="noopener" class="org-link" title="${entry.alliance_name.replace(/"/g, '&quot;')}"><img src="${allianceLogoUrl(entry.alliance_id, 32)}" class="org-logo" alt="" loading="lazy"></a>`);
    }
    return orgs.length ? `<div class="leader-orgs">${orgs.join('')}</div>` : '';
}

async function loadTopNemesis() {
    const res = await fetch(DATA_URL + 'top_nemesis.json');
    if (!res.ok) throw new Error('Failed to load leaderboard');
    return await res.json();
}

function renderLeaderboard(data) {
    const el = document.getElementById('leaderboard');
    el.innerHTML = '';

    const top10 = data.slice(0, 10);

    top10.forEach((entry, i) => {
        const row = document.createElement('div');
        const rankClass = i < 3 ? `top-${i + 1}` : '';
        row.className = `leaderboard-row ${rankClass}`;

        const rankLabel = i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : `#${i + 1}`;

        row.innerHTML = `
            <div class="rank-badge">${rankLabel}</div>
            <div class="leader-info">
                ${charLink(entry.name, entry.id, 64, true)}
                ${orgsHtml(entry)}
                <a href="./#${encodeURIComponent(entry.name)}" class="leader-name">${entry.name}</a>
            </div>
            <div class="leader-stats">
                <div class="stat-main">${entry.nemesis_count} nemesis</div>
                <div class="stat-sub">${entry.total_final_blows} total final blows</div>
            </div>
        `;
        el.appendChild(row);
    });

    document.getElementById('loading').classList.add('hidden');
    el.classList.remove('hidden');
}

async function init() {
    try {
        const data = await loadTopNemesis();
        renderLeaderboard(data);
    } catch (e) {
        document.getElementById('loading').classList.add('hidden');
        const err = document.getElementById('error');
        err.textContent = 'Error loading leaderboard. Try again later.';
        err.classList.remove('hidden');
        console.error(e);
    }
}

init();
