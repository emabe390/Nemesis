// Fix unnamed characters in names.json and all character JSON files
// Usage: node backend/fix_unnamed.js

const fs = require('fs');
const path = require('path');

const DATA_DIR = 'docs/data';
const DB_PATH = process.env.NEMESIS_DB || 'backend/nemesis.db';
const ESI_NAMES_URL = 'https://esi.evetech.net/latest/universe/names/';

// Load names.json
const namesPath = path.join(DATA_DIR, 'names.json');
const names = JSON.parse(fs.readFileSync(namesPath, 'utf8'));

// Find all "Character {id}" entries
const unnamed = [];
for (const [name, id] of Object.entries(names)) {
  if (name.startsWith('Character ')) {
    const charId = parseInt(name.split(' ')[1]);
    if (!isNaN(charId)) {
      unnamed.push({ badName: name, id: charId });
    }
  }
}

console.log(`Found ${unnamed.length} unnamed characters`);
if (unnamed.length === 0) process.exit(0);

// Resolve via ESI in batches of 1000
async function resolveNames(ids) {
  const resolved = {};
  for (let i = 0; i < ids.length; i += 1000) {
    const batch = ids.slice(i, i + 1000);
    const batchNum = Math.floor(i / 1000) + 1;
    const totalBatches = Math.ceil(ids.length / 1000);
    console.log(`  ESI batch ${batchNum}/${totalBatches} (${batch.length} IDs)`);

    for (let attempt = 0; attempt < 5; attempt++) {
      try {
        const res = await fetch(ESI_NAMES_URL, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(batch),
        });
        if (res.status === 200) {
          const data = await res.json();
          for (const entry of data) {
            if (entry.name) resolved[entry.id] = entry.name;
          }
          break;
        } else if (res.status === 429) {
          const retryAfter = parseInt(res.headers.get('retry-after') || '2');
          console.log(`    Rate limited, waiting ${retryAfter}s...`);
          await sleep(retryAfter * 1000);
        } else if (res.status >= 500) {
          console.log(`    ESI error ${res.status}, retrying...`);
          await sleep(2000 * (attempt + 1));
        } else {
          console.log(`    ESI error ${res.status}: ${await res.text()}`);
          break;
        }
      } catch (e) {
        console.log(`    Error: ${e.message}`);
        await sleep(2000 * (attempt + 1));
      }
    }
    await sleep(100);
  }
  return resolved;
}

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

(async () => {
  const ids = unnamed.map(u => u.id);
  const resolved = await resolveNames(ids);
  console.log(`Resolved ${Object.keys(resolved).length}/${unnamed.length} names`);

  // Build rename map: oldName -> newName
  const renameMap = {};
  const idToNewName = {};
  for (const u of unnamed) {
    const newName = resolved[u.id];
    if (newName) {
      renameMap[u.badName] = newName;
      idToNewName[u.id] = newName;
    }
  }

  if (Object.keys(renameMap).length === 0) {
    console.log('No names resolved, exiting');
    process.exit(0);
  }

  // Update names.json
  for (const [oldName, newName] of Object.entries(renameMap)) {
    const id = names[oldName];
    delete names[oldName];
    names[newName] = id;
  }
  fs.writeFileSync(namesPath, JSON.stringify(names, null, 2));
  console.log('Updated names.json');

  // Update all character JSON files
  const files = fs.readdirSync(DATA_DIR).filter(f => f.endsWith('.json') && f !== 'names.json');
  let updatedFiles = 0;
  for (const file of files) {
    const filePath = path.join(DATA_DIR, file);
    const data = JSON.parse(fs.readFileSync(filePath, 'utf8'));
    let changed = false;

    // Update character_name
    if (renameMap[data.character_name]) {
      data.character_name = renameMap[data.character_name];
      changed = true;
    }

    // Update nemesis name
    if (data.nemesis && renameMap[data.nemesis.name]) {
      data.nemesis.name = renameMap[data.nemesis.name];
      changed = true;
    }

    // Update top_killers names
    if (data.top_killers) {
      for (const k of data.top_killers) {
        if (renameMap[k.name]) {
          k.name = renameMap[k.name];
          changed = true;
        }
      }
    }

    if (changed) {
      fs.writeFileSync(filePath, JSON.stringify(data, null, 2));
      updatedFiles++;
    }
  }
  console.log(`Updated ${updatedFiles} character files`);

  // Update index.json if it exists
  const indexPath = path.join(DATA_DIR, 'index.json');
  if (fs.existsSync(indexPath)) {
    const index = JSON.parse(fs.readFileSync(indexPath, 'utf8'));
    let changed = false;
    for (const [oldName, newName] of Object.entries(renameMap)) {
      if (index[oldName]) {
        const entry = index[oldName];
        delete index[oldName];
        index[newName] = entry;
        changed = true;
      }
    }
    if (changed) {
      fs.writeFileSync(indexPath, JSON.stringify(index, null, 2));
      console.log('Updated index.json');
    }
  }

  // Update reverse_nemesis.json if it exists
  const revPath = path.join(DATA_DIR, 'reverse_nemesis.json');
  if (fs.existsSync(revPath)) {
    const rev = JSON.parse(fs.readFileSync(revPath, 'utf8'));
    let changed = false;
    for (const [nemesisId, victims] of Object.entries(rev)) {
      for (const v of victims) {
        if (idToNewName[v.id]) {
          v.name = idToNewName[v.id];
          changed = true;
        }
      }
    }
    if (changed) {
      fs.writeFileSync(revPath, JSON.stringify(rev, null, 2));
      console.log('Updated reverse_nemesis.json');
    }
  }

  // Update top_nemesis.json if it exists
  const topPath = path.join(DATA_DIR, 'top_nemesis.json');
  if (fs.existsSync(topPath)) {
    const top = JSON.parse(fs.readFileSync(topPath, 'utf8'));
    let changed = false;
    for (const entry of top) {
      if (idToNewName[entry.id]) {
        entry.name = idToNewName[entry.id];
        changed = true;
      }
      if (entry.top_victim && idToNewName[entry.top_victim.id]) {
        entry.top_victim.name = idToNewName[entry.top_victim.id];
        changed = true;
      }
    }
    if (changed) {
      fs.writeFileSync(topPath, JSON.stringify(top, null, 2));
      console.log('Updated top_nemesis.json');
    }
  }

  // Update SQLite DB if it exists
  const dbPath = path.join('..', DB_PATH);
  const dbPathDirect = DB_PATH;
  let sqlite3;
  try {
    sqlite3 = require('better-sqlite3');
  } catch (e) {
    try {
      sqlite3 = require('sqlite3');
    } catch (e2) {
      // neither available
    }
  }

  if (sqlite3 && (fs.existsSync(dbPath) || fs.existsSync(dbPathDirect))) {
    const actualDbPath = fs.existsSync(dbPath) ? dbPath : dbPathDirect;
    console.log(`Updating database at ${actualDbPath}...`);

    let db;
    if (sqlite3.Database) {
      // sqlite3 (async)
      db = new sqlite3.Database(actualDbPath);
      const run = (sql, params) => new Promise((res, rej) => {
        db.run(sql, params, function(err) { err ? rej(err) : res(this) });
      });

      for (const [id, newName] of Object.entries(idToNewName)) {
        await run('UPDATE kills SET victim_name = ? WHERE victim_char_id = ?', [newName, id]);
        await run('UPDATE kills SET final_blow_name = ? WHERE final_blow_char_id = ?', [newName, id]);
      }
      db.close();
    } else {
      // better-sqlite3 (sync)
      db = sqlite3(actualDbPath);
      const updateVictim = db.prepare('UPDATE kills SET victim_name = ? WHERE victim_char_id = ?');
      const updateKiller = db.prepare('UPDATE kills SET final_blow_name = ? WHERE final_blow_char_id = ?');
      const updateTransaction = db.transaction((entries) => {
        for (const [id, newName] of entries) {
          updateVictim.run(newName, id);
          updateKiller.run(newName, id);
        }
      });
      updateTransaction(Object.entries(idToNewName));
      db.close();
    }
    console.log(`Updated DB for ${Object.keys(idToNewName).length} characters`);
  } else {
    console.log('SQLite DB not found or sqlite3/better-sqlite3 not installed, skipping DB update');
  }

  console.log('Done!');
})();
