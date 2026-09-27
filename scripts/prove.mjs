// Prove Endow end to end on GenLayer Asimov.
//
//   AT=0x... PADV=<padv pw> PPUB=<ppub pw> node scripts/prove.mjs
//
// padv (the funder) opens a grant with fixed criteria and a reward; ppub (an applicant)
// submits three deliveries. One that misses the criteria is UNMET, an unreadable one is
// UNCLEAR, and the one that meets them is awarded the reward, closing the grant. A funder
// cannot apply to their own grant, and an awarded grant cannot be reviewed again.
import { Wallet } from 'ethers';
import { createClient, createAccount } from 'genlayer-js';
import { testnetAsimov } from 'genlayer-js/chains';
import fs from 'fs';
import os from 'os';
import path from 'path';
import url from 'url';

const AT = process.env.AT;
const PADV = process.env.PADV || '';
const PPUB = process.env.PPUB || '';
if (!AT || !PADV || !PPUB) { console.error('set AT, PADV and PPUB'); process.exit(1); }

const ROOT = path.join(path.dirname(url.fileURLToPath(import.meta.url)), '..');
const KS = path.join(os.homedir(), '.genlayer', 'keystores');
async function acct(file, pw) {
  const w = await Wallet.fromEncryptedJson(fs.readFileSync(path.join(KS, file), 'utf8'), pw);
  return { addr: w.address.toLowerCase(), client: createClient({ chain: testnetAsimov, account: createAccount(w.privateKey) }) };
}
const padv = await acct('padv.json', PADV);   // funder
const ppub = await acct('ppub.json', PPUB);    // applicant
const anybody = createClient({ chain: testnetAsimov });

const RAW = 'https://raw.githubusercontent.com/JspIIV/endow/master/docs/';
const TITLE = 'csv2json grant';
const CRIT = 'An open-source command-line tool that converts CSV to JSON, with a README documenting usage and an OSI-approved licence.';
const GOOD = RAW + 'delivery-good.txt';
const BAD = RAW + 'delivery-bad.txt';
const UNREADABLE = RAW + 'no-such-delivery-9f2c.txt';

const out = [];
const say = l => { console.log(l); out.push(l); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const transient = e => /-32005|-32006|-32029|-32603|at capacity|rate limit|gas rate|reverted.*consensus|consensus.*reverted|backpressure|fetch failed|timeout|502|503|429|ECONNRESET|ENOTFOUND|EAI_AGAIN|getaddrinfo|resource not found/i
  .test(String(e?.details || e?.shortMessage || e?.message || e) + ' ' + String(e?.cause?.cause?.code || e?.cause?.code || ''));

async function read(fn, args = []) {
  for (let a = 1; ; a++) {
    try { return JSON.parse(await anybody.readContract({ address: AT, functionName: fn, args })); }
    catch (e) { if (!transient(e) || a >= 14) throw e; await sleep(5000 * a); }
  }
}
async function write(who, fn, args) {
  for (let a = 1; ; a++) {
    try { return await who.client.writeContract({ address: AT, functionName: fn, args, value: 0n }); }
    catch (e) { if (!transient(e) || a >= 14) throw e; say(`  (${fn} transient, wait ${8 * a}s)`); await sleep(8000 * a); }
  }
}
async function openGrant(reward) {
  const n = (await read('size')).total;
  for (let attempt = 1; attempt <= 3; attempt++) {
    await write(padv, 'open_grant', [TITLE, CRIT, String(reward)]);
    for (let i = 0; i < 30; i++) { const s = await read('size'); if (s.total > n) return String(s.total - 1); await sleep(5000); }
  }
  throw new Error('grant not opened');
}
async function applyDelivery(gid, url) {
  const n = (await read('get', [gid])).applications.length;
  for (let attempt = 1; attempt <= 3; attempt++) {
    await write(ppub, 'apply', [gid, url]);
    for (let i = 0; i < 24; i++) { const g = await read('get', [gid]); if (g.applications.length > n) return n; await sleep(5000); }
  }
  throw new Error('application not made');
}
async function reviewUntil(who, gid, idx, label) {
  const before = Number((await read('get', [gid])).reviews || 0);
  for (let attempt = 1; attempt <= 4; attempt++) {
    try { await write(who, 'review', [gid, String(idx)]); } catch (e) { say(`  ${label} err ${String(e.message).slice(0, 50)}`); }
    for (let i = 0; i < 36; i++) {
      await sleep(15000);
      const g = await read('get', [gid]);
      if (Number(g.reviews || 0) > before) { const a = g.applications[idx];
        say(`  ${label}: grant ${g.status}, app ${a.status} v=${a.verdict} (${(i + 1) * 15}s)`); return g; }
    }
    say(`  ${label}: not settled after poll, retrying`);
  }
  return await read('get', [gid]);
}

say('Endow, proven on GenLayer Asimov');
say('  contract ' + AT);
say('  funder(padv) ' + padv.addr + '  applicant(ppub) ' + ppub.addr);
say('');

const baseWin = (await read('balance', [ppub.addr])).balance;
const baseSize = await read('size');

const gid = await openGrant(500);
say('padv opened grant #' + gid + ' (reward 500) with criteria fixed up front');

say('checking the funder cannot apply to their own grant...');
const appsBefore = (await read('get', [gid])).applications.length;
try { await write(padv, 'apply', [gid, GOOD]); } catch (e) { say('  apply err ' + String(e.message).slice(0, 40)); }
await sleep(6000);
const appsAfterSelf = (await read('get', [gid])).applications.length;
say('  applications ' + appsBefore + ' -> ' + appsAfterSelf + ' (a funder self-application is refused)');

const aBad = await applyDelivery(gid, BAD);
say('ppub applied #' + aBad + ' (a delivery that misses the criteria)');
const aUnread = await applyDelivery(gid, UNREADABLE);
say('ppub applied #' + aUnread + ' (an unreadable delivery)');
const aGood = await applyDelivery(gid, GOOD);
say('ppub applied #' + aGood + ' (a delivery that meets the criteria)');
say('');

say('reviewing the missing delivery #' + aBad + '...');
const rBad = await reviewUntil(padv, gid, aBad, 'unmet');
say('reviewing the unreadable delivery #' + aUnread + '...');
const rUn = await reviewUntil(padv, gid, aUnread, 'unclear');
say('reviewing the qualifying delivery #' + aGood + '...');
const rGood = await reviewUntil(padv, gid, aGood, 'met');
say('  grant status: ' + rGood.status + ' | ' + (rGood.applications[aGood].reason || ''));
say('');

say('trying to review again after the award...');
let reReview = { ok: null };
try { await write(padv, 'review', [gid, String(aBad)]); } catch {}
await sleep(6000);
const afterAward = await read('get', [gid]);
say('  grant status after a further review attempt: ' + afterAward.status);

const win = (await read('balance', [ppub.addr])).balance;
const award = await read('award', [gid]);
const size = await read('size');
say('applicant balance ' + baseWin + ' -> ' + win + ' (reward won)');
say('award: winner ' + award.winner.slice(0, 10) + '… delivery ' + award.delivery_url);
say('book: ' + JSON.stringify(size));

const checks = [
  ['a delivery that misses the criteria is UNMET and the grant stays open',
    rBad.applications[aBad].verdict === 'UNMET' && rBad.status === 'OPEN'],
  ['an unreadable delivery is UNCLEAR and the grant stays open',
    rUn.applications[aUnread].verdict === 'UNCLEAR' && rUn.status === 'OPEN'],
  ['the qualifying delivery is MET and the grant is AWARDED', rGood.status === 'AWARDED'],
  ['the reward is credited to the applicant', win - baseWin === 500],
  ['the award names the winner and their delivery', award.winner === ppub.addr && award.delivery_url === GOOD],
  ['a funder cannot apply to their own grant', appsAfterSelf === appsBefore],
  ['an awarded grant cannot be reviewed or awarded again', afterAward.status === 'AWARDED' && Number(afterAward.reviews) === 3],
  ['this run adds one awarded grant and its reward to the book',
    size.awarded - baseSize.awarded === 1 && size.awarded_units - baseSize.awarded_units === 500],
];
say('');
for (const [label, ok] of checks) say((ok ? '  ok   ' : ' FAIL  ') + label);
const failed = checks.filter(([, ok]) => !ok);
say('');
say(failed.length ? `${failed.length} of ${checks.length} checks failed` : `${checks.length} checks. The delivery met the published criteria, and the first that did was paid.`);

fs.mkdirSync(path.join(ROOT, 'results'), { recursive: true });
fs.writeFileSync(path.join(ROOT, 'results', 'proved.json'), JSON.stringify({
  proved_at: new Date().toISOString(), network: 'genlayer testnet asimov', contract: AT,
  unmet: rBad.applications[aBad], unclear: rUn.applications[aUnread], awarded: rGood, award,
  applicant_balance: win, size, checks: checks.map(([label, ok]) => ({ label, ok })), transcript: out,
}, null, 2));
say('Written to results/proved.json');
process.exit(failed.length ? 1 : 0);
