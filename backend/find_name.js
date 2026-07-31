const fs = require('fs');
const names = JSON.parse(fs.readFileSync('./docs/data/names.json', 'utf8'));
const rev = JSON.parse(fs.readFileSync('./docs/data/reverse_nemesis.json', 'utf8'));
const entry = rev['3019609'];

// Check if any victim file has the nemesis name cached
for (const v of entry.slice(0, 50)) {
  try {
    const d = JSON.parse(fs.readFileSync(`./docs/data/${v.id}.json`, 'utf8'));
    const n = d.top_killers.find(k => k.id === 3019609);
    if (n && n.name && !n.name.startsWith('Character ')) {
      console.log('Found name in victim file:', n.name);
      process.exit(0);
    }
  } catch(e) {}
}

// Check names.json
const found = Object.entries(names).find(([k, v]) => v === 3019609);
console.log('In names.json:', found ? found[0] : 'no');

// Check index.json
const idx = JSON.parse(fs.readFileSync('./docs/data/index.json', 'utf8'));
for (const [name, data] of Object.entries(idx)) {
  if (data.id === 3019609) {
    console.log('In index.json:', name);
    break;
  }
}
