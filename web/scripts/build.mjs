import {mkdir,copyFile,readFile,rm} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {createHash} from 'node:crypto';
const root=fileURLToPath(new URL('../',import.meta.url));
const traces=JSON.parse(await readFile(path.join(root,'data/traces.json'),'utf8'));
for(const [relative,hash] of Object.entries(traces.source_hashes)){
 const actual=createHash('sha256').update(await readFile(path.join(root,'..',relative))).digest('hex');
 if(actual!==hash)throw new Error(`Stale trace: ${relative}. Regenerate with export-traces.py.`);
}
const formal=JSON.parse(await readFile(path.join(root,'../docs/verification/plc-semantics-v0.3/formal-result.json'),'utf8'));
const actual=createHash('sha256').update(await readFile(path.join(root,'../projects/FB_MainSequence/03_checks/plcverif/FB_MainSequence_PLCverif.scl'))).digest('hex');
if(formal.source_sha256!==actual||traces.formal_source_sha256!==actual)throw new Error('Stale formal evidence');
await rm(path.join(root,'dist'),{recursive:true,force:true});await mkdir(path.join(root,'dist/data'),{recursive:true});
for(const f of ['index.html','style.css','app.js','favicon.svg','data/traces.json'])await copyFile(path.join(root,f),path.join(root,'dist',f));
console.log('Built static site in web/dist (5 assets, no server functions).');
