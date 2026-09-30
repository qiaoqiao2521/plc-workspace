import test from 'node:test';import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';
const data=JSON.parse(readFileSync(new URL('../data/traces.json',import.meta.url),'utf8'));
const frames=id=>data.scenarios.find(s=>s.id===id).frames;
test('zero threshold clears accumulated timer and restored threshold starts fresh',()=>{const f=frames('zero');assert.equal(f[3].outputs.timer,3);assert.equal(f[4].outputs.timer,0);assert.equal(f[6].outputs.phase,1);assert.equal(f[6].outputs.timer,1);assert.equal(f[7].outputs.error,1);});
test('held reset does not clear aborted after stop release',()=>{const f=frames('reset');assert.equal(f[3].outputs.command_aborted,1);assert.equal(f[5].outputs.command_aborted,0);});
test('completion wins on deadline and held start does not restart',()=>{assert.equal(frames('deadline')[2].outputs.phase,2);assert.equal(frames('deadline')[2].outputs.error,0);assert.equal(frames('held')[3].outputs.phase,0);assert.equal(frames('held')[5].outputs.phase,1);});
test('disable clears current fault but new enable clears diagnostic history',()=>{const f=frames('timeout');assert.equal(f[5].outputs.error,1);assert.equal(f[6].outputs.error,0);assert.equal(f[6].outputs.timeout_diagnostic,1);assert.equal(f[7].outputs.timeout_diagnostic,0);});
test('all displayed energized actions are revoked on error',()=>{for(const s of data.scenarios)for(const f of s.frames)if(f.outputs.error)for(const k of ['belt_forward','q1','q2','done','command_busy'])assert.equal(f.outputs[k],0,`${s.id}/${f.scan}/${k}`);});
