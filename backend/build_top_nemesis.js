const fs = require('fs');
const path = require('path');

const dataDir = process.argv[2];
if (!dataDir) {
    console.error('Usage: node build_top_nemesis.js <data_dir>');
    process.exit(1);
}

const reversePath = path.join(dataDir, 'reverse_nemesis.json');
const namesPath = path.join(dataDir, 'names.json');
const outPath = path.join(dataDir, 'top_nemesis.json');

console.log(`Reading ${reversePath}...`);
const reverse = JSON.parse(fs.readFileSync(reversePath, 'utf8'));
console.log(`  ${Object.keys(reverse).length} nemesis entries`);

let idToName = {};
if (fs.existsSync(namesPath)) {
    const names = JSON.parse(fs.readFileSync(namesPath, 'utf8'));
    for (const [name, id] of Object.entries(names)) {
        idToName[String(id)] = name;
    }
}

const topNemesis = [];
for (const [nemesisId, victims] of Object.entries(reverse)) {
    victims.sort((a, b) => b.kill_count - a.kill_count);

    let name = idToName[nemesisId];
    if (!name) {
        const fp = path.join(dataDir, `${nemesisId}.json`);
        if (fs.existsSync(fp)) {
            try {
                const d = JSON.parse(fs.readFileSync(fp, 'utf8'));
                name = d.character_name;
            } catch (e) {}
        }
    }
    if (!name) name = `Character ${nemesisId}`;

    topNemesis.push({
        id: parseInt(nemesisId, 10),
        name,
        nemesis_count: victims.length,
        total_final_blows: victims.reduce((sum, v) => sum + v.kill_count, 0),
        top_victim: victims[0] || null,
    });
}

topNemesis.sort((a, b) => b.nemesis_count - a.nemesis_count);

fs.writeFileSync(outPath, JSON.stringify(topNemesis, null, 2));

console.log(`Wrote ${outPath}`);
console.log(`  Total entries: ${topNemesis.length}`);
for (let i = 0; i < Math.min(10, topNemesis.length); i++) {
    const e = topNemesis[i];
    console.log(`  #${i + 1}: ${e.name} — ${e.nemesis_count} nemesis, ${e.total_final_blows} final blows`);
}
