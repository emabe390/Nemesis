const fs = require('fs');
const path = require('path');

const dataDir = './docs/data';

// Start with existing names.json
const namesPath = path.join(dataDir, 'names.json');
const names = JSON.parse(fs.readFileSync(namesPath, 'utf8'));

// Add names from all character files (id.json files)
const files = fs.readdirSync(dataDir).filter(f => /^\d+\.json$/.test(f));
console.log(`Scanning ${files.length} character files...`);

let added = 0;
for (const file of files) {
  const id = parseInt(file.replace('.json', ''), 10);
  try {
    const d = JSON.parse(fs.readFileSync(path.join(dataDir, file), 'utf8'));
    const name = d.character_name;
    if (name && !names[name]) {
      names[name] = id;
      added++;
    }
  } catch (e) {}
}

// Add names from reverse_nemesis.json (nemesis names and victim names)
const rev = JSON.parse(fs.readFileSync(path.join(dataDir, 'reverse_nemesis.json'), 'utf8'));
for (const [nemesisId, victims] of Object.entries(rev)) {
  // Try to find nemesis name from victim files' top_killers
  let nemesisName = null;
  for (const v of victims.slice(0, 30)) {
    try {
      const d = JSON.parse(fs.readFileSync(path.join(dataDir, v.id + '.json'), 'utf8'));
      const n = d.top_killers.find(k => k.id === parseInt(nemesisId));
      if (n && n.name && !n.name.startsWith('Character ')) {
        nemesisName = n.name;
        break;
      }
    } catch (e) {}
  }
  if (nemesisName && !names[nemesisName]) {
    names[nemesisName] = parseInt(nemesisId);
    added++;
  }

  // Add victim names too
  for (const v of victims) {
    if (v.name && !names[v.name]) {
      names[v.name] = v.id;
      added++;
    }
  }
}

// Add names from top_nemesis.json
const top = JSON.parse(fs.readFileSync(path.join(dataDir, 'top_nemesis.json'), 'utf8'));
for (const e of top) {
  if (e.name && !e.name.startsWith('Character ') && !names[e.name]) {
    names[e.name] = e.id;
    added++;
  }
}

fs.writeFileSync(namesPath, JSON.stringify(names, null, 2));
console.log(`Wrote ${namesPath}`);
console.log(`  Total entries: ${Object.keys(names).length}`);
console.log(`  Added: ${added}`);
