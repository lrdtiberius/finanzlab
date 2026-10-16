// Lightweight frontend regression of the actual credit plan event handlers.
const fs=require('fs');
const vm=require('vm');
const assert=require('assert');
const app=fs.readFileSync(require('path').join(__dirname,'../app/static/app.js'),'utf8');
const a=app.indexOf(';(()=>{const marker="finanzlab-1.6.12-credit-plan-helper";');
const end='else bindCreditPlanHelper1612();\n})();';
const b=app.indexOf(end,a);
assert(a!==-1&&b!==-1,'Credit plan helper missing');
const script=app.slice(a,b+end.length);
function input(val=''){
  return {value:String(val),dataset:{},checked:false,_listeners:{},addEventListener(ev,fn){(this._listeners[ev]??=[]).push(fn)},fire(ev){for(const fn of this._listeners[ev]??[])fn({type:ev})}};
}
function check(kind,initial,APR=0,product=0,financing=0){
  const e={credit_type:input(kind),plan_change_from:input('2026-10-16'),product_price:input(product),financing_price:input(financing),installment_surcharge:input('0'),opening_balance:input('2700.00'),plan_amount:input('337.50'),plan_count:input('8'),balloon_payment:input('0'),automatic_interest:input(''),interest_rate:input(String(APR))};
  e.automatic_interest.checked=true;
  const form={dataset:{},elements:e};
  const pending=[];
  const credit={id:'current',as_of:'2026-10-16',remaining_balance_cents:initial,opening_balance_cents:270000,payments:[]};
  const globals={
    document:{querySelector:x=>x==='#credit-form'?form:null,readyState:'complete',addEventListener(){}},
    state:{editingCreditId:'current',editingCreditSnapshot:credit},
    creditById:id=>credit,
    today:()=> '2026-10-16',
    creditPlanBalanceAt:()=>initial,
    euroCents:s=>Math.round(Number(String(s||'0').replace(',','.'))*100)||0,
    updateCreditPlanCheck:()=>{},
    setTimeout:(fn,t)=>{if(t===0)pending.push(fn)},
  };
  vm.runInNewContext(script,globals);
  function flush(){while(pending.length)pending.shift()()}
  e.plan_count.value='4';e.plan_count.fire('input');flush();
  const suggestedRate=Number(e.plan_amount.value);
  e.plan_amount.value='337.50';e.plan_amount.fire('input');flush();
  return {rate:suggestedRate,count:Number(e.plan_count.value)};
}
const borrowed=check('borrowed',131900,0);
assert.deepEqual(borrowed,{rate:329.75,count:4});
const credit=check('credit',131900,6);
assert(credit.rate>329.75,`credit rate ignores interest: ${credit.rate}`);
assert.equal(credit.count,4);
const consumer=check('consumer_credit',131900,0,2700,2700);
assert.deepEqual(consumer,{rate:329.75,count:4});
const consumerWithApr=check('consumer_credit',131900,6,0,0);
assert(consumerWithApr.rate>329.75);
assert.equal(consumerWithApr.count,4);
const newLoan=check('borrowed',270000,0);
assert.deepEqual(newLoan,{rate:675,count:8}); // Fresh plan remains based on original amount, except editing uses remaining.
console.log('JS plan regression OK:', {borrowed,credit,consumer,consumerWithApr,newLoan});
