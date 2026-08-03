const DATA_URL = './data/';
const PAGE_SIZE = 10;

let allData = [];

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

function getPageFromHash() {
    const hash = location.hash.slice(1);
    // Hash format: "page3" or just "3"
    const match = hash.match(/^(?:page)?(\d+)$/);
    if (!match) return 1;
    const page = parseInt(match[1], 10);
    return isNaN(page) || page < 1 ? 1 : page;
}

function setPageHash(page) {
    history.replaceState(null, '', '#page' + page);
}

function renderLeaderboard(data, page) {
    const el = document.getElementById('leaderboard');
    el.innerHTML = '';

    const start = (page - 1) * PAGE_SIZE;
    const pageData = data.slice(start, start + PAGE_SIZE);

    pageData.forEach((entry, i) => {
        const globalRank = start + i + 1;
        const row = document.createElement('div');
        const rankClass = globalRank <= 3 ? `top-${globalRank}` : '';
        row.className = `leaderboard-row ${rankClass}`;

        const rankLabel = globalRank === 1 ? '🥇' : globalRank === 2 ? '🥈' : globalRank === 3 ? '🥉' : `#${globalRank}`;

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

    // Pagination
    const totalPages = Math.ceil(data.length / PAGE_SIZE);
    const pagination = document.createElement('div');
    pagination.className = 'pagination';

    let pagHtml = '';
    if (page > 1) {
        pagHtml += `<button class="pag-btn" data-page="${page - 1}">← Previous</button>`;
    } else {
        pagHtml += `<button class="pag-btn" disabled>← Previous</button>`;
    }

    pagHtml += `<span class="pag-info">Page ${page} / ${totalPages}</span>`;

    if (page < totalPages) {
        pagHtml += `<button class="pag-btn" data-page="${page + 1}">Next →</button>`;
    } else {
        pagHtml += `<button class="pag-btn" disabled>Next →</button>`;
    }

    pagination.innerHTML = pagHtml;
    el.appendChild(pagination);

    // Bind pagination clicks
    pagination.querySelectorAll('.pag-btn:not([disabled])').forEach(btn => {
        btn.addEventListener('click', () => {
            const newPage = parseInt(btn.dataset.page, 10);
            setPageHash(newPage);
            renderLeaderboard(allData, newPage);
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
    });

    document.getElementById('loading').classList.add('hidden');
    el.classList.remove('hidden');
}

async function init() {
    try {
        const res = await fetch(DATA_URL + 'top_nemesis.json');
        if (!res.ok) throw new Error('Failed to load leaderboard');
        allData = await res.json();

        const page = getPageFromHash();
        renderLeaderboard(allData, page);
    } catch (e) {
        document.getElementById('loading').classList.add('hidden');
        const err = document.getElementById('error');
        err.textContent = 'Error loading leaderboard. Try again later.';
        err.classList.remove('hidden');
        console.error(e);
    }
}

// Handle browser back/forward
window.addEventListener('popstate', () => {
    if (allData.length) {
        const page = getPageFromHash();
        renderLeaderboard(allData, page);
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
});

init();
