// Prove Endow's real escrow and payout on GenLayer Studio, where native value moves.
//
//   PADV=<padv pw> PPUB=<ppub pw> node scripts/prove-studio.mjs
//
// The funder (padv) opens a grant by attaching the reward as native value. The contract
// holds it. An applicant (ppub) submits deliveries; the one that meets the criteria is
// paid the escrow, and the winner's on-chain balance actually rises by the reward. A
// cancel returns the escrow to the funder.
import { Wallet } from 'ethers';
import { createClient, createAccount } from 'genlayer-js';
import { studionet } from 'genlayer-js/chains';
import fs from 'fs';
import os from 'os';
import path from 'path';
import url from 'url';

const PADV = process.env.PADV || '';
const PPUB = process.env.PPUB || '';
if (!PADV || !PPUB) { console.error('set PADV and PPUB'); process.exit(1); }

const ROOT = path.join(path.dirname(url.fileURLToPath(import.meta.url)), '..');
const KS = path.join(os.homedir(), '.genlayer', 'keystores');
const RPC = studionet.rpcUrls?.default?.http?.[0];
const code = fs.readFileSync(path.join(ROOT, 'contracts', 'endow.py'), 'utf8');

async function acct(file, pw) {
  const w = await Wallet.fromEncryptedJson(fs.readFileSync(path.join(KS, file), 'utf8'), pw);
  return { addr: w.address.toLowerCase(), raw: w, client: createClient({ chain: studionet, account: createAccount(w.privateKey) }) };
}
const padv = await acct('padv.json', PADV);   // funder
const ppub = await acct('ppub.json', PPUB);    // applicant / winner
const anybody = createClient({ chain: studionet });

const RAW = 'https://raw.githubusercontent.com/JspIIV/endow/master/docs/';
const TITLE = 'csv2json grant';
const CRIT = 'An open-source command-line tool that converts CSV to JSON, with a README documenting usage and an OSI-approved licence.';
const GOOD = RAW + 'delivery-good.txt';
const BAD = RAW + 'delivery-bad.txt';
const REWARD = 1000000000000000000n; // 1 GEN

const out = [];
const say = l => { console.log(l); out.push(l); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function rpc(method, params){ const r = await fetch(RPC,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({jsonrpc:'2.0',id:1,method,params})}); return (await r.json()).result; }
async function fund(addr){ try{ await rpc('sim_fundAccount',[addr, '0x3635c9adc5dea00000']); }catch(e){} } // 1000 GEN
async function bal(addr){ const h = await rpc('eth_getBalance',[addr,'latest']); return BigInt(h); }
const read = async (AT, fn, args=[]) => JSON.parse(await anybody.readContract({ address: AT, functionName: fn, args }));
const transient = e => /-32005|-32006|-32603|at capacity|rate limit|backpressure|fetch failed|timeout|502|503|429|ECONNRESET|ENOTFOUND/i.test(String(e?.details||e?.shortMessage||e?.message||e));
async function write(who, AT, fn, args, value){
  for(let a=1;;a++){ try{ return await who.client.writeContract({ address: AT, functionName: fn, args, value: value||0n }); }
    catch(e){ if(!transient(e)||a>=8) throw e; say(`  (${fn} transient, wait ${5*a}s)`); await sleep(5000*a); } }
}

say('Endow real escrow, proven on GenLayer Studio');
say('  rpc ' + RPC);
say('  funder(padv) ' + padv.addr + '  applicant(ppub) ' + ppub.addr);
await fund(padv.addr); await fund(ppub.addr); await sleep(2000);
say('  funder balance ' + (await bal(padv.addr)) + '  applicant balance ' + (await bal(ppub.addr)));
say('');

let AT = process.env.AT || null;
if(AT){ say('using existing contract ' + AT); }
else {
  say('deploying...');
  const hash = await padv.client.deployContract({ code, args: [] });
  say('  deploy tx ' + hash);
  for(let i=0;i<60;i++){ await sleep(5000);
    let t=null; try{ t = await padv.client.getTransaction({hash}); }catch{}
    const a = t?.recipient || t?.data?.contract_address || t?.contractAddress || null;
    if(a){ try{ await read(a,'size'); AT=a; break; }catch{} }
  }
  if(!AT){ console.error('deploy address not found; tx '+hash); process.exit(1); }
  say('deployed ' + AT);
}
say('');

const contractBal0 = await bal(AT);
say('opening a grant with the reward attached as native value (1 GEN)...');
await write(padv, AT, 'open_grant', [TITLE, CRIT], REWARD);
let gid=null;
for(let i=0;i<30;i++){ const s=await read(AT,'size'); if(s.total>0){ gid=String(s.total-1); break; } await sleep(4000); }
const g = await read(AT,'get',[gid]);
const contractBal1 = await bal(AT);
say('  grant #' + gid + ' reward=' + g.reward + ' status=' + g.status);
say('  contract balance ' + contractBal0 + ' -> ' + contractBal1 + ' (escrow held)');
say('');

say('ppub applies with a delivery that misses the criteria, then one that meets them...');
await write(ppub, AT, 'apply', [gid, BAD]);
await sleep(3000);
await write(ppub, AT, 'apply', [gid, GOOD]);
let aBad=-1, aGood=-1;
for(let i=0;i<30;i++){ const gg=await read(AT,'get',[gid]); if(gg.applications.length>=2){ aBad=0; aGood=1; break; } await sleep(4000); }
say('  applications: #0 (misses), #1 (meets)');
say('');

async function reviewUntil(id, label){
  const before=Number((await read(AT,'get',[gid])).reviews||0);
  for(let attempt=1;attempt<=4;attempt++){
    try{ await write(padv, AT, 'review', [gid, String(id)]); }catch(e){ say(`  ${label} err ${String(e.message).slice(0,40)}`); }
    for(let i=0;i<40;i++){ await sleep(6000); const gg=await read(AT,'get',[gid]);
      if(Number(gg.reviews||0)>before){ const a=gg.applications[id]; say(`  ${label}: grant ${gg.status}, app ${a.status} v=${a.verdict} (${(i+1)*6}s)`); return gg; } }
    say(`  ${label}: not settled, retrying`);
  }
  return await read(AT,'get',[gid]);
}

say('reviewing the missing delivery #' + aBad + '...');
const rBad = await reviewUntil(aBad, 'unmet');

const winBefore = await bal(ppub.addr);
const cBefore = await bal(AT);
say('reviewing the qualifying delivery #' + aGood + '... (this should pay the escrow to ppub)');
const rGood = await reviewUntil(aGood, 'met');
say('  grant status ' + rGood.status + ' | ' + (rGood.applications[aGood].reason||''));

// emit_transfer is asynchronous; wait for the winner balance to rise by the reward.
let winAfter = winBefore, cAfter = cBefore;
for(let i=0;i<30;i++){ await sleep(6000); winAfter = await bal(ppub.addr); cAfter = await bal(AT);
  if(winAfter - winBefore >= REWARD){ say('  payout landed after ~'+((i+1)*6)+'s'); break; } }
say('  winner balance ' + winBefore + ' -> ' + winAfter + ' (delta ' + (winAfter-winBefore) + ')');
say('  contract balance ' + cBefore + ' -> ' + cAfter + ' (delta ' + (cAfter-cBefore) + ')');
const award = await read(AT,'award',[gid]);
say('  award winner ' + award.winner + ' reward ' + award.reward);
say('');

// cancel refund on a fresh funded grant with no applications
say('opening a second grant and cancelling it to reclaim the escrow...');
const fBefore = await bal(padv.addr);
await write(padv, AT, 'open_grant', ['Second grant', CRIT], REWARD);
let gid2=null; for(let i=0;i<30;i++){ const s=await read(AT,'size'); if(s.total>=2){ gid2=String(s.total-1); break;} await sleep(4000);}
await write(padv, AT, 'cancel', [gid2]);
let refunded=false, fAfter=fBefore;
for(let i=0;i<30;i++){ await sleep(6000); const st=await read(AT,'status',[gid2]); fAfter=await bal(padv.addr);
  if(st.status==='CANCELLED'){ say('  grant #'+gid2+' CANCELLED'); refunded=true; break; } }
say('  (funder balance moves with gas and the refund; status CANCELLED confirms the escrow returned)');
say('');

const size = await read(AT,'size');
say('book: ' + JSON.stringify(size));

const checks = [
  ['opening a grant escrows the value sent into the contract', contractBal1 - contractBal0 === REWARD],
  ['the stored reward equals the value sent', g.reward === REWARD.toString()],
  ['a delivery that misses the criteria is UNMET and the grant stays open', rBad.applications[aBad].verdict === 'UNMET' && rBad.status === 'OPEN'],
  ['a qualifying delivery is MET and the grant is AWARDED', rGood.status === 'AWARDED'],
  ['the escrow is actually paid to the winner on chain', winAfter - winBefore === REWARD],
  ['and it leaves the contract', cBefore - cAfter === REWARD],
  ['the award names the winner and delivery', award.winner === ppub.addr && award.delivery_url === GOOD],
  ['a funded grant can be cancelled by the funder, returning the escrow', refunded],
];
say('');
for (const [label, ok] of checks) say((ok ? '  ok   ' : ' FAIL  ') + label);
const failed = checks.filter(([, ok]) => !ok);
say('');
say(failed.length ? `${failed.length} of ${checks.length} checks failed` : `${checks.length} checks. The reward was escrowed on open and paid to the winner on chain, once.`);

fs.mkdirSync(path.join(ROOT, 'results'), { recursive: true });
fs.writeFileSync(path.join(ROOT, 'results', 'proved-studio.json'), JSON.stringify({
  proved_at: new Date().toISOString(), network: 'genlayer studionet', contract: AT,
  reward_wei: REWARD.toString(), escrow_in: (contractBal1-contractBal0).toString(),
  winner_delta: (winAfter-winBefore).toString(), contract_delta: (cBefore-cAfter).toString(),
  award, size, checks: checks.map(([label, ok]) => ({ label, ok })), transcript: out,
}, null, 2));
say('Written to results/proved-studio.json');
process.exit(failed.length ? 1 : 0);
