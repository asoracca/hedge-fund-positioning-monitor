import fs from 'node:fs';
import assert from 'node:assert/strict';
import vm from 'node:vm';
const d=JSON.parse(fs.readFileSync(new URL('./assets/research.json',import.meta.url)));
assert.equal(d.manifest.kind,'synthetic');
assert.equal(Object.keys(d.research).length,6);
for(const [date,s] of Object.entries(d.snapshots)){
  assert(s.holdings.length>0);
  for(const row of s.holdings)assert(row.filing_date.slice(0,10)<=date);
}
for(const r of Object.values(d.research)){
  for(const f of r.folds)if(f.latest_filing)assert(f.latest_filing<f.test_start);
  for(const x of r.daily)assert(Math.abs(x.net_return-((1+x.gross_return)*(1-x.traded_notional*15/10000)-1))<1e-8);
}
const source=fs.readFileSync(new URL('./app.js',import.meta.url),'utf8');
new vm.Script(source);
// Execute the browser's actual metric function against Python reference values.
const fn=source.slice(source.indexOf('function computeMetrics('),source.indexOf('\nfunction research('));
const context=vm.createContext({sum:a=>a.reduce((s,x)=>s+x,0)});
vm.runInContext(fn,context);
for(const r of Object.values(d.research)){
  const m=context.computeMetrics(r.daily.map(x=>x.net_return));
  assert(Math.abs(m.total-r.metrics.total_return)<1e-7);
  assert(Math.abs(m.vol-r.metrics.volatility)<1e-7);
  assert(Math.abs(m.sharpe-r.metrics.sharpe)<1e-7);
  assert(Math.abs(m.dd-r.metrics.max_drawdown)<1e-7);
}
assert(Math.abs(context.computeMetrics([-.2,.1]).dd+.2)<1e-12);
for(const file of ['index.html','style.css','app.js','assets/plotly.min.js'])assert(fs.existsSync(new URL(file,import.meta.url)));
console.log('Verified disclosure boundaries, all six backtest presets, browser financial metrics, and static assets.');
