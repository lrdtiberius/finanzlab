const $=selector=>document.querySelector(selector);
const $$=selector=>[...document.querySelectorAll(selector)];
const state={households:[],currentId:null,asOf:null,dashboard:null,incomes:[],expenses:[],transfers:[],credits:[],energylab:null,incomeFilter:'active',expenseFilter:'active',dashboardExpenseCategory:'all',dashboardMonth:null,transferFilter:'active',creditFilter:'all',diagnostics:null,settingsLoadedFor:null,settingsLoading:false,preview:null,previewMonth:null,previewAccountIds:[],previewCreditIds:[],previewSelectedDay:null,editingFlowId:null,editingFlowKind:null,editingIncomeChangeId:null,editingEnergyFlowId:null,editingAccountId:null,editingAccountHistory:[],editingTransferId:null,editingCreditId:null,currentCreditId:null,categories:[],outlook:null,outlookBaseMonth:null,outlookRequest:0,outlookAccountIds:[],outlookSelectionFor:null,outlookLoadingKey:null};
const recurrenceLabels={weekly:'wöchentlich',monthly:'monatlich',quarterly:'vierteljährlich',semiannual:'halbjährlich',yearly:'jährlich',once:'einmalig'};
const categoryLabels={salary:'Gehalt',pension:'Rente',benefit:'Leistung',family:'Familie',other_income:'Sonstige Einnahme',housing:'Wohnen',energy:'Energie',insurance:'Versicherung',food:'Lebensmittel',mobility:'Mobilität',consumer_credit:'Konsumkredit',credit:'Kredit',borrowed:'Geliehen',mortgage:'Darlehen',interest:'Zinsen',leisure:'Freizeit',other_expense:'Sonstige Ausgabe',other:'Sonstiges'};
const creditTypeLabels={consumer_credit:'Konsumkredit',credit:'Kredit',borrowed:'Geliehen',mortgage:'Darlehen'};
const movementLabels={income:'Einnahme',expense:'Ausgabe',transfer_in:'Umbuchung +',transfer_out:'Umbuchung −'};
const incomeCategories=[['salary','Gehalt'],['pension','Rente'],['benefit','Leistung'],['family','Familie'],['other_income','Sonstige Einnahme']];
const expenseCategories=[['housing','Wohnen'],['energy','Energie'],['insurance','Versicherung'],['food','Lebensmittel'],['mobility','Mobilität'],['consumer_credit','Konsumkredit'],['credit','Kredit'],['borrowed','Geliehen'],['interest','Zinsen'],['leisure','Freizeit'],['other_expense','Sonstige Ausgabe']];
const creditCategories=new Set(['consumer_credit','credit','borrowed','mortgage']);

const escapeHtml=value=>String(value??'').replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
const eur=cents=>new Intl.NumberFormat('de-DE',{style:'currency',currency:'EUR'}).format((Number(cents)||0)/100);
const moneyOrMissing=cents=>cents==null?'Nicht hinterlegt':eur(cents);
const euroCents=value=>Math.round((Number.parseFloat(String(value).replace(',','.'))||0)*100);
function today(){const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`}
function monthNow(){return today().slice(0,7)}
function monthEndDate(value){const [y,m]=String(value||monthNow()).split('-').map(Number),last=new Date(y,m,0).getDate();return `${y}-${String(m).padStart(2,'0')}-${String(last).padStart(2,'0')}`}
function dateLabel(value){if(!value)return 'nicht hinterlegt';const [y,m,d]=String(value).split('-');return d?`${d}.${m}.${y}`:String(value)}
function monthLabel(value){if(!value)return '';const [y,m]=value.split('-').map(Number);return new Intl.DateTimeFormat('de-DE',{month:'long',year:'numeric'}).format(new Date(y,m-1,1))}
function weekdayLabel(value){const [y,m,d]=value.split('-').map(Number);return new Intl.DateTimeFormat('de-DE',{weekday:'long'}).format(new Date(y,m-1,d))}
function shiftDay(value,count){const [y,m,d]=value.split('-').map(Number),next=new Date(y,m-1,d+count);return `${next.getFullYear()}-${String(next.getMonth()+1).padStart(2,'0')}-${String(next.getDate()).padStart(2,'0')}`}
function shiftMonth(value,count){const [y,m]=value.split('-').map(Number),next=new Date(y,m-1+count,1);return `${next.getFullYear()}-${String(next.getMonth()+1).padStart(2,'0')}`}
function addMonthsToDate(value,count){if(!value||!count)return '';const [y,m,d]=value.split('-').map(Number),monthIndex=m-1+Number(count),year=y+Math.floor(monthIndex/12),month=((monthIndex%12)+12)%12;const lastDay=new Date(year,month+1,0).getDate();return `${year}-${String(month+1).padStart(2,'0')}-${String(Math.min(d,lastDay)).padStart(2,'0')}`}
function durationBetweenDates(start,end){if(!start||!end)return '';const [sy,sm]=start.split('-').map(Number),[ey,em]=end.split('-').map(Number),months=(ey-sy)*12+em-sm;return months>0&&addMonthsToDate(start,months)===end?String(months):''}
function expectedTransferEnd(start,recurrence,count){const total=Number(count);if(!start||!Number.isInteger(total)||total<1)return '';if(recurrence==='once')return total===1?start:'';const interval={monthly:1,quarterly:3,semiannual:6,yearly:12}[recurrence];return interval?addMonthsToDate(start,(total-1)*interval):''}
function transferLimitError(form){const end=form.end_date.value,count=form.occurrence_count.value;if(!count)return '';if(form.recurrence.value==='once'&&Number(count)!==1)return 'Eine einmalige Umbuchung kann nur eine Ausführung haben.';if(!end)return '';const expected=expectedTransferEnd(form.due_date.value,form.recurrence.value,count);return expected&&end!==expected?`Enddatum und Anzahl passen nicht zusammen. Bei ${count} Ausführungen ist das Enddatum ${dateLabel(expected)}.`:''}
function ownerName(item){if(item.owner_scope==='joint')return 'Gemeinsam';return state.dashboard?.household.persons.find(person=>person.id===item.owner_person_id)?.display_name||'Haushalt'}
function accountById(id){return state.dashboard?.household.accounts.find(account=>account.id===id)}
function accountName(id){return accountById(id)?.name||'Kein Konto'}
function creditById(id){return state.credits.find(credit=>credit.id===id)}
function creditName(id){return creditById(id)?.name||'Kein Kredit'}
function slotForOwner(item){if(item?.owner_scope==='joint')return 'joint';return state.dashboard.household.persons.find(person=>person.id===item?.owner_person_id)?.slot||'A'}
function isArchived(item){const archiveDate=item?.end_date||(item?.recurrence==='once'?item?.due_date:null);return item?.lifecycle_status==='ended'||Boolean(archiveDate&&archiveDate<today())}
async function api(url,options={}){const response=await fetch(url,options),data=await response.json().catch(()=>({error:'Ungültige Serverantwort.'}));if(!response.ok)throw new Error(data.error||'Anfrage fehlgeschlagen.');return data}
function toast(message){const element=$('#toast');element.textContent=message;element.hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>element.hidden=true,3800)}
// finanzlab-2.1-dashboard-startup

function startupLoader(show,message='FinanzLab lädt …'){
  let el=$('#startup-loader');

  if(!el){
    el=document.createElement('div');
    el.id='startup-loader';
    el.innerHTML=
      '<div class="startup-loader-card">'+
      '<strong></strong>'+
      '<small>Aktuelle Daten werden geladen.</small>'+
      '</div>';
    document.body.appendChild(el);
  }

  el.querySelector('strong').textContent=message;
  el.hidden=!show;
}

const STARTUP_CACHE_PREFIX='finanzlab-ui-cache-v1:';
const OUTLOOK_ACCOUNT_SELECTION_PREFIX='finanzlab-outlook-accounts-v1:';

function startupCacheKey(){
  return state.currentId
    ? `${STARTUP_CACHE_PREFIX}${state.currentId}`
    : null;
}

function outlookSelectionKey(){
  return state.currentId
    ? `${OUTLOOK_ACCOUNT_SELECTION_PREFIX}${state.currentId}`
    : null;
}

function liquidDashboardAccounts(){
  return (state.dashboard?.household?.accounts||[]).filter(
    account=>account.kind!=='credit_line'
  );
}

function ensureOutlookAccountSelection(){
  const accounts=liquidDashboardAccounts();
  const validIds=accounts.map(account=>account.id);
  const valid=new Set(validIds);

  if(state.outlookSelectionFor!==state.currentId){
    let saved=[];
    try{
      const value=JSON.parse(
        window.localStorage.getItem(outlookSelectionKey())||'[]'
      );
      if(Array.isArray(value))saved=value;
    }catch(error){
      saved=[];
    }
    const savedSet=new Set(saved.filter(id=>valid.has(id)));
    state.outlookAccountIds=validIds.filter(id=>savedSet.has(id));
    state.outlookSelectionFor=state.currentId;
    if(state.outlookAccountIds.length){
      saveOutlookAccountSelection();
    }
  }else{
    const selectedSet=new Set(
      state.outlookAccountIds.filter(id=>valid.has(id))
    );
    state.outlookAccountIds=validIds.filter(id=>selectedSet.has(id));
  }

  if(!state.outlookAccountIds.length&&validIds.length){
    state.outlookAccountIds=[...validIds];
    saveOutlookAccountSelection();
  }
}

function saveOutlookAccountSelection(){
  const key=outlookSelectionKey();
  if(!key)return;
  try{
    window.localStorage.setItem(key,JSON.stringify(state.outlookAccountIds));
  }catch(error){
    // Die Prognose funktioniert auch ohne verfügbaren Browser-Speicher.
  }
}

function saveStartupCache(){
  const key=startupCacheKey();

  if(!key||!state.dashboard)return;

  try{
    window.localStorage.setItem(key,JSON.stringify({
      savedAt:Date.now(),
      dashboardMonth:state.dashboardMonth,
      dashboard:state.dashboard,
      incomes:state.incomes,
      expenses:state.expenses,
      transfers:state.transfers,
      credits:state.credits,
      categories:state.categories,
      outlook:state.outlook,
      outlookBaseMonth:state.outlookBaseMonth,
      outlookAccountIds:state.outlookAccountIds
    }));
  }catch(error){
    // Komfortfunktion: Cachefehler dürfen FinanzLab nicht blockieren.
  }
}

function restoreStartupCache(){
  const key=startupCacheKey();

  if(!key)return false;

  try{
    const cached=JSON.parse(window.localStorage.getItem(key)||'null');

    if(!cached?.dashboard?.household)return false;

    // FinanzLab startete bisher immer im aktuellen Monat.
    // Einen alten, manuell gewählten Prognosemonat übernehmen wir
    // deshalb nicht beim Kaltstart.
    const currentMonth=state.dashboardMonth||monthNow();
    const cachedMonth=
      cached.dashboard.month ||
      String(cached.dashboard.as_of||'').slice(0,7);

    if(cachedMonth!==currentMonth)return false;

    state.dashboardMonth=currentMonth;
    state.dashboard=cached.dashboard;
    state.incomes=Array.isArray(cached.incomes)?cached.incomes:[];
    state.expenses=Array.isArray(cached.expenses)?cached.expenses:[];
    state.transfers=Array.isArray(cached.transfers)?cached.transfers:[];
    state.credits=Array.isArray(cached.credits)?cached.credits:[];
    state.categories=Array.isArray(cached.categories)?cached.categories:[];
    syncCategoryState();
    ensureSelections();

    const cachedAccountIds=Array.isArray(cached.outlookAccountIds)
      ? cached.outlookAccountIds
      : [];
    const sameSelection=
      cachedAccountIds.length===state.outlookAccountIds.length &&
      cachedAccountIds.every(
        (id,index)=>id===state.outlookAccountIds[index]
      );
    const accountAwareCache=(cached.outlook?.items||[]).every(
      item=>Array.isArray(item.accounts)
    );

    state.outlook=sameSelection&&accountAwareCache
      ? (cached.outlook||null)
      : null;
    state.outlookBaseMonth=state.outlook
      ? (cached.outlookBaseMonth||null)
      : null;

    return true;
  }catch(error){
    return false;
  }
}

async function boot(){
  startupLoader(true);

  state.asOf=today();
  state.dashboardMonth=monthNow();
  state.previewMonth=monthNow();

  state.households=(await api('/api/households')).items;
  state.currentId=state.households[0]?.id||null;

  if(!state.currentId){
    startupLoader(false);
    $('#app').hidden=false;
    renderHouseholdSelect();
    openSetup(true);
    return;
  }

  renderHouseholdSelect();

  const requested=location.hash.replace('#','');
  const validRequested=[
    'dashboard','preview','accounts','income',
    'expenses','credits','transfers','settings'
  ].includes(requested)
    ? requested
    : 'dashboard';

  const restored=restoreStartupCache();

  if(restored){
    $('#app').hidden=false;
    renderAll();
    showView(validRequested);
    startupLoader(false);
  }

  try{
    await loadAll();

    $('#app').hidden=false;

    if(!restored){
      showView(validRequested);
    }

    startupLoader(false);
  }catch(error){
    startupLoader(false);
    $('#app').hidden=false;

    if(!restored)throw error;

    toast(
      `Aktualisierung fehlgeschlagen – letzter Stand wird angezeigt: `+
      error.message
    );
  }
}

function syncCategoryState(){for(const item of state.categories||[]){categoryLabels[item.key]=item.name}for(const target of [incomeCategories,expenseCategories])target.splice(0,target.length);for(const item of (state.categories||[]).filter(item=>item.active)){(item.kind==='income'?incomeCategories:expenseCategories).push([item.key,item.name])}}
async function loadAll(){
  const householdId=state.currentId;
  const dashboardAsOf=monthEndDate(
    state.dashboardMonth||monthNow()
  );

  const dashboardQuery=
    `household_id=${encodeURIComponent(householdId)}`+
    `&as_of=${encodeURIComponent(dashboardAsOf)}`;

  const managementQuery=
    `household_id=${encodeURIComponent(householdId)}`+
    `&as_of=${encodeURIComponent(today())}`;

  state.settingsLoadedFor=null;

  const [
    dashboard,
    incomes,
    expenses,
    transfers,
    credits,
    categories
  ]=await Promise.all([
    api(`/api/dashboard?${dashboardQuery}`),
    api(`/api/cash-flows?${managementQuery}&kind=income`),
    api(`/api/cash-flows?${managementQuery}&kind=expense`),
    api(`/api/transfers?household_id=${encodeURIComponent(householdId)}`),
    api(
      `/api/credits?household_id=${encodeURIComponent(householdId)}`+
      `&as_of=${encodeURIComponent(today())}`
    ),
    api(`/api/categories?household_id=${encodeURIComponent(householdId)}`)
  ]);

  if(householdId!==state.currentId)return;

  state.dashboard=dashboard;
  state.incomes=incomes.items;
  state.expenses=expenses.items;
  state.transfers=transfers.items;
  state.credits=credits.items;
  state.categories=categories.items||[];

  syncCategoryState();
  ensureSelections();
  renderAll();
  saveStartupCache();

  // Die 6-Monats-Prognose wird bewusst erst nach dem normalen
  // Dashboard nachgeladen, damit sie den Kaltstart nicht ausbremst.
  loadDashboardOutlook(state.dashboardMonth).catch(error=>{
    const target=$('#dashboard-outlook-list');
    if(target){
      target.innerHTML=
        `<p class="empty">Vorschau konnte nicht geladen werden: `+
        `${escapeHtml(error.message)}</p>`;
    }
  });

  if(location.hash==='#settings'){
    loadSettingsSupplemental().catch(error=>
      toast(
        `Einstellungen konnten nicht vollständig geladen werden: `+
        error.message
      )
    );
  }
}

function ensureSelections(){const ids=state.dashboard.household.accounts.map(account=>account.id),valid=new Set(ids);state.previewAccountIds=state.previewAccountIds.filter(id=>valid.has(id));if(!state.previewAccountIds.length)state.previewAccountIds=[...ids];const creditIds=state.credits.filter(credit=>credit.credit_type!=='mortgage').map(credit=>credit.id),validCredits=new Set(creditIds);state.previewCreditIds=state.previewCreditIds.filter(id=>validCredits.has(id));ensureOutlookAccountSelection()}
function updateDashboardMonthControl(){const input=$('#dashboard-month'),label=$('#dashboard-month-label');if(input)input.value=state.dashboardMonth||monthNow();if(label)label.textContent=monthLabel(state.dashboardMonth||monthNow())}
function renderAll(){renderHouseholdSelect();renderDashboard();renderManage();renderIncomes();renderExpenses();renderCredits();renderTransfers();renderSettings();updateDashboardMonthControl();$('#preview-month-label').textContent=monthLabel(state.previewMonth);$('#current-household-name').textContent=state.dashboard.household.name}

function renderHouseholdSelect(){const select=$('#household-select');select.innerHTML=state.households.map(h=>`<option value="${escapeHtml(h.id)}" ${h.id===state.currentId?'selected':''}>${escapeHtml(h.name)}</option>`).join('');const current=state.households.find(h=>h.id===state.currentId);$('#current-household-name').textContent=current?.name||'Noch keiner';$('#delete-household').disabled=!current}
function warningHtml(warnings){return (warnings||[]).map(item=>`<div class="overdraft-warning">${item.kind==='credit_line'?'Kreditrahmen':'Disporahmen'} bei <b>${escapeHtml(item.name)}</b> um ${eur(item.overage_cents)} überschritten.</div>`).join('')}
function accountRow(account,editable=false){const projected=account.projected_balance_cents??account.balance_cents,changed=projected!=null&&account.balance_cents!=null&&projected!==account.balance_cents,isLine=account.kind==='credit_line',limit=Number(account.overdraft_limit_cents||0),used=isLine&&projected!=null?Math.max(0,-Number(projected)):0,available=isLine?Math.max(0,limit-used):0,badge=isLine?'<span class="credit-line-badge">Rahmenkredit</span>':(account.is_default?'<span class="default-badge">Standardkonto</span>':''),warning=account.overdraft_exceeded?`<span class="warning-badge">${isLine?'Rahmen':'Dispo'} überschritten</span>`:'';return `<article class="account-row ${account.overdraft_exceeded?'overdraft-card':''} ${isLine?'credit-line-row':''}"><div><div class="account-meta"><h3>${escapeHtml(account.name)}</h3>${badge}${warning}</div><small>Stand ${dateLabel(account.anchor_date)} · ${account.bookings_applied?'Tagesbuchungen enthalten':'Tagesbuchungen werden berechnet'}</small></div><strong class="${projected<0?'amount-negative':''}">${moneyOrMissing(projected)}</strong><small>${changed?`Gespeichert ${eur(account.balance_cents)} · `:''}${isLine?`Rahmen ${eur(limit)} · verfügbar ${eur(available)}`:(limit>0?`Dispo ${eur(limit)}`:'Kein Dispo')}</small>${editable?`<div class="row-actions"><button class="link-button" type="button" data-edit-account="${escapeHtml(account.id)}">Bearbeiten &amp; Stand erfassen</button></div>`:''}</article>`}
function mortgageDashboardCard(credit){
  const rate=Number(credit.payment_plan?.amount_cents||0);

  const interest=
    Number.parseFloat(
      String(credit.interest_rate??'0').replace(',','.')
    )||0;

  const repayment=
    Number.parseFloat(
      String(credit.repayment_rate??'0').replace(',','.')
    )||0;

  const special=
    Number.parseFloat(
      String(credit.special_repayment_percent??'0').replace(',','.')
    )||0;

  return `
    <article class="financing-card mortgage-financing-card">
      <div>
        <span>Darlehen</span>
        <h3>${escapeHtml(credit.name)}</h3>
        <small>
          ${
            credit.fixed_interest_until
              ? `Zinsbindung bis ${dateLabel(credit.fixed_interest_until)}`
              : 'Keine Zinsbindung hinterlegt'
          }
        </small>
      </div>

      <strong>${eur(credit.remaining_balance_cents)} Restschuld</strong>

      <div class="financing-facts">
        <span>
          Rate
          <b>${rate?eur(rate):'–'}</b>
        </span>

        <span>
          Sollzins
          <b>${
            interest.toLocaleString(
              'de-DE',
              {minimumFractionDigits:2,maximumFractionDigits:2}
            )
          } %</b>
        </span>

        <span>
          Tilgung
          <b>${
            repayment.toLocaleString(
              'de-DE',
              {minimumFractionDigits:2,maximumFractionDigits:2}
            )
          } %</b>
        </span>

        <span>
          Sondertilgung
          <b>${
            special.toLocaleString(
              'de-DE',
              {minimumFractionDigits:2,maximumFractionDigits:2}
            )
          } % p. a.</b>
        </span>
      </div>
    </article>`;
}

function renderLiquidityOutlook(){
  const target=$('#dashboard-outlook-list');

  if(!target)return;

  ensureOutlookAccountSelection();

  const availableAccounts=liquidDashboardAccounts();
  const selector=$('#dashboard-outlook-selectors');

  if(selector){
    selector.innerHTML=availableAccounts.length
      ? availableAccounts.map(account=>{
          const checked=state.outlookAccountIds.includes(account.id);
          const lastSelected=checked&&state.outlookAccountIds.length===1;
          return `<label class="account-choice outlook-account-choice">`+
            `<input type="checkbox" `+
            `data-outlook-account="${escapeHtml(account.id)}" `+
            `${checked?'checked':''} ${lastSelected?'disabled':''}> `+
            `${escapeHtml(account.name)}</label>`;
        }).join('')
      : '<p class="empty">Noch kein normales Bankkonto vorhanden.</p>';
  }

  if(!availableAccounts.length){
    target.innerHTML=
      '<p class="empty">Lege zuerst ein normales Bankkonto an.</p>';
    return;
  }

  const items=
    state.outlookBaseMonth===state.dashboardMonth
      ? (state.outlook?.items||[])
      : [];

  target.innerHTML=items.length
    ? (state.outlook?.accounts||[]).map(account=>`
        <section class="liquidity-account-group"
                 data-outlook-account-group="${escapeHtml(account.id)}">
          <div class="liquidity-account-heading">
            <div>
              <span>Bankkonto</span>
              <h3>${escapeHtml(account.name)}</h3>
            </div>
            <small>Rahmenkredit ausgeschlossen</small>
          </div>
          <div class="liquidity-outlook-grid">
            ${items.map(item=>{
              const values=(item.accounts||[]).find(
                entry=>entry.account_id===account.id
              )||{};
              const mid=values.mid_balance_cents;
              const end=values.end_balance_cents;
              return `
                <article class="liquidity-outlook-card">
                  <h4>${escapeHtml(monthLabel(item.month))}</h4>
                  <div>
                    <span>Monatsmitte · ${dateLabel(item.mid_date).slice(0,5)}.</span>
                    <strong class="${mid!=null&&Number(mid)<0?'amount-negative':''}">
                      ${moneyOrMissing(mid)}
                    </strong>
                  </div>
                  <div>
                    <span>Monatsende · ${dateLabel(item.end_date).slice(0,5)}.</span>
                    <strong class="${end!=null&&Number(end)<0?'amount-negative':''}">
                      ${moneyOrMissing(end)}
                    </strong>
                  </div>
                </article>`;
            }).join('')}
          </div>
        </section>
      `).join('')
    : '<p class="empty">Vorschau wird berechnet …</p>';
}

async function loadDashboardOutlook(
  baseMonth=state.dashboardMonth
){
  if(!state.currentId)return;

  ensureOutlookAccountSelection();
  if(!state.outlookAccountIds.length){
    renderLiquidityOutlook();
    return;
  }

  const requested=baseMonth||monthNow();
  const loadingKey=
    `${state.currentId}:${requested}:`+
    state.outlookAccountIds.join(',');

  if(state.outlookLoadingKey===loadingKey)return;

  state.outlookLoadingKey=loadingKey;
  const requestId=++state.outlookRequest;
  const selectedSignature=state.outlookAccountIds.join(',');

  state.outlookBaseMonth=requested;
  renderLiquidityOutlook();

  const query=new URLSearchParams({
    household_id:state.currentId,
    base_month:requested,
    months:'6'
  });

  state.outlookAccountIds.forEach(
    accountId=>query.append('account_id',accountId)
  );

  try{
    const outlook=await api(
      `/api/dashboard/outlook?${query.toString()}`
    );

    if(
      requestId!==state.outlookRequest ||
      requested!==state.dashboardMonth ||
      selectedSignature!==state.outlookAccountIds.join(',')
    )return;

    state.outlook=outlook;
    state.outlookBaseMonth=requested;

    renderLiquidityOutlook();
    saveStartupCache();
  }finally{
    if(state.outlookLoadingKey===loadingKey){
      state.outlookLoadingKey=null;
    }
  }
}

function renderDashboard(){
  const m=state.dashboard.metrics;

  const accounts=
    state.dashboard.household.accounts.filter(
      account=>account.kind!=='credit_line'
    );

  const creditLines=state.dashboard.credit_lines||[];

  const mortgages=
    state.credits.filter(
      credit=>
        credit.credit_type==='mortgage' &&
        !credit.archived
    );

  const creditSummary=
    state.dashboard.credit_summary||{groups:[]};

  const breakdowns=state.dashboard.breakdowns||{};

  $('#dashboard-balance').textContent=eur(m.balance_cents);

  $('#dashboard-balance').classList.toggle(
    'amount-negative',
    m.balance_cents<0
  );

  $('#dashboard-balance-note').textContent=
    accounts.length
      ? `Monatsende ${dateLabel(state.dashboard.as_of)} · `+
        `Finanzierungen separat`
      : 'Noch kein Bankkonto hinterlegt';

  $('#dashboard-income').textContent=eur(m.income_cents);
  $('#dashboard-expenses').textContent=eur(m.expenses_cents);

  $('#dashboard-operating-surplus').textContent=
    eur(m.operating_surplus_cents??m.surplus_cents);

  $('#dashboard-liquidity-delta').textContent=
    eur(m.liquidity_delta_cents);

  $('#dashboard-liquidity-delta').classList.toggle(
    'amount-negative',
    Number(m.liquidity_delta_cents)<0
  );

  $('#dashboard-as-of').textContent=
    monthLabel(
      state.dashboard.month ||
      state.dashboard.as_of.slice(0,7)
    );

  $('#dashboard-credit-as-of').textContent=
    `Stand ${dateLabel(creditSummary.as_of)}`;

  $('#dashboard-credit-summary').innerHTML=
    (creditSummary.groups||[])
      .map(group=>creditSummaryCard(group))
      .join('');

  $('#dashboard-warnings').innerHTML=
    warningHtml(state.dashboard.overdraft_warnings);

  $('#dashboard-account-list').innerHTML=
    accounts.length
      ? accounts.map(account=>accountRow(account)).join('')
      : '<p class="empty">Noch kein normales Bankkonto angelegt.</p>';

  const financingPanel=$('#dashboard-financing-panel');
  const financingList=$('#dashboard-financing-list');

  const financingCards=[
    ...creditLines.map(
      account=>creditLineDashboardCard(account)
    ),
    ...mortgages.map(
      credit=>mortgageDashboardCard(credit)
    )
  ];

  if(financingPanel){
    financingPanel.hidden=!financingCards.length;
  }

  if(financingList){
    financingList.innerHTML=financingCards.join('');
  }

  renderLiquidityOutlook();

  const renderedAccountIds=(state.outlook?.accounts||[]).map(
    account=>account.id
  );
  const outlookMatches=
    state.outlookBaseMonth===state.dashboardMonth &&
    renderedAccountIds.length===state.outlookAccountIds.length &&
    renderedAccountIds.every(
      (id,index)=>id===state.outlookAccountIds[index]
    );

  if(!outlookMatches&&state.outlookAccountIds.length){
    loadDashboardOutlook(state.dashboardMonth).catch(error=>{
      const target=$('#dashboard-outlook-list');
      if(target){
        target.innerHTML=
          `<p class="empty">Vorschau konnte nicht geladen werden: `+
          `${escapeHtml(error.message)}</p>`;
      }
    });
  }

  $('#dashboard-breakdowns').innerHTML=
    categoryBreakdownCard(
      'Einnahmen nach Kategorie',
      breakdowns.income_categories,
      'income'
    )+
    categoryBreakdownCard(
      'Ausgaben nach Kategorie',
      breakdowns.expense_categories,
      'expense'
    );
}

function creditLineDashboardCard(account){const limit=Number(account.credit_limit_cents??account.overdraft_limit_cents??0),used=Number(account.credit_used_cents??Math.max(0,-Number(account.projected_balance_cents||0))),available=Number(account.credit_available_cents??Math.max(0,limit-used)),percent=limit>0?Math.min(100,used/limit*100):0,linked=accountById(account.linked_account_id);return `<article class="credit-line-card"><div><span>Rahmenkredit</span><h3>${escapeHtml(account.name)}</h3><small>Verrechnung nur über ${escapeHtml(linked?.name||'verknüpftes Girokonto')}</small></div><strong>${eur(used)} genutzt</strong><div class="credit-line-meter"><i style="width:${percent}%"></i></div><small>${eur(available)} von ${eur(limit)} verfügbar</small></article>`}
function creditSummaryCard(group){return `<article class="summary-card"><span>${escapeHtml(creditTypeLabels[group.credit_type]||group.credit_type)} · ${group.count}</span><b>${eur(group.balance_cents)}</b><small>offener Gesamtsaldo</small></article>`}
function categoryBreakdownCard(title,items,kind){const values=[...(items||[])].sort((a,b)=>b.amount_cents-a.amount_cents),max=Math.max(...values.map(item=>item.amount_cents),1),sum=values.reduce((total,item)=>total+Number(item.amount_cents||0),0);return `<article class="breakdown-card"><h3>${title}</h3><div class="filtered-expense-total"><small>Monatssumme</small><strong>${eur(sum)}</strong></div><div class="bar-list">${values.length?values.map(item=>`<div class="bar-row"><span>${escapeHtml(categoryLabels[item.category]||'Sonstiges')}</span><b>${eur(item.amount_cents)}</b><div class="bar ${kind}"><i style="width:${Math.max(4,item.amount_cents/max*100)}%"></i></div></div>`).join(''):'<p class="empty">Keine Werte</p>'}</div></article>`}

function flowRow(item){const account=accountName(item.account_id),kind=item.kind==='income'?'income':'expense',linkedCredit=creditById(item.credit_id),end=item.end_date?` · ${item.credit_id?'Vertragliches Ende':'endet'} ${dateLabel(item.end_date)}`:'',expected=item.credit_id&&linkedCredit?.expected_repayment_date?` · Voraussichtlich getilgt ${dateLabel(linkedCredit.expected_repayment_date)}`:'',credit=item.credit_id?` · ${escapeHtml(creditName(item.credit_id))}`:'',managed=item.managed_by==='energylab',future=kind==='income'&&item.next_version?` · ab ${dateLabel(item.next_version.version_from)}: ${eur(item.next_version.amount_cents)}`:'',changeButton=kind==='income'&&item.recurrence!=='once'?`<button class="link-button" type="button" data-income-change="${escapeHtml(item.id)}">Betrag ändern</button>`:'',action=managed?`<div class="row-actions"><span class="badge">EnergyLab</span><button class="link-button" type="button" data-energy-account-flow="${escapeHtml(item.id)}">Konto &amp; Zahlungstag</button></div>`:`<div class="row-actions">${changeButton}<button class="link-button" type="button" data-edit-flow-kind="${kind}" data-edit-flow="${escapeHtml(item.id)}">Bearbeiten</button></div>`;return `<article class="flow-row ${item.configured_active?'':'inactive'}"><span><b>${escapeHtml(item.name)}</b><small>${escapeHtml(categoryLabels[item.category]||'Sonstiges')} · ${dateLabel(item.due_date)} · ${recurrenceLabels[item.recurrence]||item.recurrence}${end}${expected} · ${escapeHtml(account)}${credit}${state.dashboard.household.mode==='couple'?` · ${escapeHtml(ownerName(item))}`:''}${managed?' · automatisch aus EnergyLab':''}${future}</small></span><strong class="${kind==='expense'?'amount-negative':''}">${kind==='expense'?'− ':'+ '}${eur(item.amount_cents)}</strong>${action}</article>`}
function lifecycleFilter(filter,activeCount,archiveCount,attribute){return `<button class="credit-filter-button ${filter==='active'?'active':''}" type="button" data-${attribute}="active" aria-pressed="${filter==='active'}">Aktiv <span>${activeCount}</span></button><button class="credit-filter-button ${filter==='archive'?'active':''}" type="button" data-${attribute}="archive" aria-pressed="${filter==='archive'}">Archiv <span>${archiveCount}</span></button>`}
function renderManage(){const accounts=state.dashboard.household.accounts;$('#manage-account-list').innerHTML=accounts.length?accounts.map(account=>accountRow(account,true)).join(''):'<p class="empty">Lege dein erstes Konto an.</p>'}
function renderIncomes(){const active=state.incomes.filter(item=>!isArchived(item)),archive=state.incomes.filter(isArchived),visible=state.incomeFilter==='archive'?archive:active;$('#income-list-title').textContent=state.incomeFilter==='archive'?'Archivierte Einnahmen':'Aktive Einnahmen';$('#income-filter').innerHTML=lifecycleFilter(state.incomeFilter,active.length,archive.length,'income-filter');$('#income-list').innerHTML=visible.length?visible.map(flowRow).join(''):`<p class="empty">${state.incomeFilter==='archive'?'Noch keine archivierte Einnahme vorhanden.':'Noch keine aktive Einnahme angelegt.'}</p>`;$('#income-position-total').textContent=`+ ${eur(state.incomes.reduce((sum,item)=>sum+Number(item.amount_cents||0),0))}`}
function renderExpenses(){const standalone=state.expenses.filter(item=>!(item.credit_id&&item.recurrence==="monthly")),active=standalone.filter(item=>!isArchived(item)),archive=standalone.filter(isArchived),visible=state.expenseFilter==='archive'?archive:active;$('#expense-list-title').textContent=state.expenseFilter==='archive'?'Archivierte Ausgaben':'Aktive Ausgaben';$('#expense-filter').innerHTML=lifecycleFilter(state.expenseFilter,active.length,archive.length,'expense-filter');$('#expense-list').innerHTML=visible.length?visible.map(flowRow).join(''):`<p class="empty">${state.expenseFilter==='archive'?'Noch keine archivierte Ausgabe vorhanden.':'Noch keine aktive Ausgabe angelegt.'}</p>`;$('#expense-position-total').textContent=`− ${eur(state.expenses.reduce((sum,item)=>sum+Number(item.amount_cents||0),0))}`}
function renderCredits(){const types=['consumer_credit','credit','borrowed','mortgage'],groups=types.map(type=>{const credits=state.credits.filter(item=>item.credit_type===type);return {credit_type:type,count:credits.length,balance_cents:credits.reduce((sum,item)=>sum+Number(item.remaining_balance_cents||0),0)}}),filters=[['all','Alle'],...types.map(type=>[type,creditTypeLabels[type]])],filtered=state.creditFilter==='all'?state.credits:state.credits.filter(item=>item.credit_type===state.creditFilter),activeLabel=state.creditFilter==='all'?'Alle Kredite':creditTypeLabels[state.creditFilter];$('#credit-page-summary').innerHTML=groups.map(creditSummaryCard).join('');$('#credit-list-title').textContent=activeLabel;$('#credit-filter').innerHTML=filters.map(([value,label])=>{const count=value==='all'?state.credits.length:groups.find(group=>group.credit_type===value).count,active=state.creditFilter===value;return `<button class="credit-filter-button ${active?'active':''}" type="button" data-credit-filter="${value}" aria-pressed="${active}">${escapeHtml(label)} <span>${count}</span></button>`}).join('');$('#credit-list').innerHTML=filtered.length?filtered.map(item=>`<article class="credit-row" data-open-credit="${escapeHtml(item.id)}"><div><span class="credit-type-badge">${escapeHtml(creditTypeLabels[item.credit_type])}</span><h3>${escapeHtml(item.name)}</h3><small>Ausgang ${eur(item.opening_balance_cents)} · getilgt ${eur(item.paid_cents)}</small></div><strong>${eur(item.remaining_balance_cents)}</strong><small>offener Saldo</small><button class="link-button" type="button" data-edit-credit="${escapeHtml(item.id)}">Bearbeiten</button></article>`).join(''):state.credits.length?`<p class="empty">Keine Kredite der Art „${escapeHtml(activeLabel)}“ vorhanden.</p>`:'<p class="empty">Noch kein Kredit angelegt.</p>'}
function renderTransfers(){const active=state.transfers.filter(item=>!isArchived(item)),archive=state.transfers.filter(isArchived),visible=state.transferFilter==='archive'?archive:active;$('#transfer-list-title').textContent=state.transferFilter==='archive'?'Archivierte Umbuchungen':'Aktive Umbuchungen';$('#transfer-filter').innerHTML=lifecycleFilter(state.transferFilter,active.length,archive.length,'transfer-filter');$('#transfer-list').innerHTML=visible.length?visible.map(item=>{const end=item.end_date?` · Ende ${dateLabel(item.end_date)}`:'',count=item.occurrence_count?` · ${item.occurrence_count} Ausführung${Number(item.occurrence_count)===1?'':'en'}`:'';return `<article class="flow-row ${item.active?'':'inactive'}"><span><b>${escapeHtml(item.name)}</b><small>${dateLabel(item.due_date)} · ${recurrenceLabels[item.recurrence]}${end}${count} · ${escapeHtml(item.source_account_name)} → ${escapeHtml(item.target_account_name)}</small></span><strong>${eur(item.amount_cents)}</strong><button class="link-button" type="button" data-edit-transfer="${escapeHtml(item.id)}">Bearbeiten</button></article>`}).join(''):`<p class="empty">${state.transferFilter==='archive'?'Noch keine archivierte Umbuchung vorhanden.':'Noch keine aktive Umbuchung angelegt.'}</p>`}
function renderSettings(){const persons=state.dashboard.household.persons;$('#person-list').innerHTML=persons.map(person=>`<article class="person-row"><span class="avatar">${escapeHtml(person.display_name.slice(0,1).toUpperCase())}</span><span><b>${escapeHtml(person.display_name)}</b><small>Person ${escapeHtml(person.slot)}</small></span></article>`).join('');const categoryList=$('#category-settings-list');if(categoryList)categoryList.innerHTML=(state.categories||[]).map(item=>`<article class="person-row ${item.active?'':'inactive'}"><span><b>${escapeHtml(item.name)}</b><small>${item.kind==='income'?'Einnahme':'Ausgabe'} · ${item.is_system?'System-Art':'Eigene Art'}${item.active?'':' · deaktiviert'}</small></span>${item.is_system?'':`<span class="row-actions"><button class="link-button" type="button" data-edit-category="${escapeHtml(item.id)}">Bearbeiten</button><button class="link-button" type="button" data-delete-category="${escapeHtml(item.id)}">Löschen</button></span>`}</article>`).join('');const integration=state.energylab||{},form=$('#energylab-form');form.elements.base_url.value=integration.base_url||'http://energylab:8090';form.elements.enabled.checked=Boolean(integration.enabled);$('#energylab-account').innerHTML='<option value="">Kein Konto zugeordnet</option>'+state.dashboard.household.accounts.map(account=>`<option value="${escapeHtml(account.id)}" ${account.id===integration.account_id?'selected':''}>${escapeHtml(account.name)}</option>`).join('');const status=$('#energylab-status');status.hidden=!integration.last_message;status.className=`notice ${integration.last_status==='error'?'error':''}`;status.textContent=integration.last_message?`${integration.last_status==='ok'?'Zuletzt erfolgreich':'Letzter Versuch fehlgeschlagen'}: ${integration.last_message}`:'';$('#energylab-sync').disabled=state.settingsLoading||!integration.enabled;const diagnostics=state.diagnostics;if(!diagnostics||state.settingsLoadedFor!==state.currentId){$('#diagnostics-as-of').textContent=state.settingsLoading?'wird geladen …':'bei Bedarf';$('#diagnostics-summary').innerHTML='';$('#diagnostics-list').innerHTML='<div class="notice">Datenprüfung wird nur beim Öffnen der Einstellungen geladen. Dadurch bleibt das Dashboard schneller.</div>';return}$('#diagnostics-as-of').textContent=dateLabel(diagnostics.as_of);const s=diagnostics.summary;$('#diagnostics-summary').innerHTML=summaryCard('Betroffene Positionen',s.item_count)+summaryCard('Nicht berücksichtigt',s.not_considered_count)+summaryCard('Fehler',s.error,'negative')+summaryCard('Warnungen',s.warning);$('#diagnostics-list').innerHTML=diagnostics.items.length?diagnostics.items.map(item=>{const managed=flowById(item.kind,item.id)?.managed_by==='energylab';return `<article class="diagnostic-row"><i class="severity ${item.issues.some(issue=>issue.severity==='error')?'error':'warning'}"></i><div><b>${escapeHtml(item.name)}</b><small>${item.kind==='income'?'Einnahme':'Ausgabe'} · ${eur(item.amount_cents)}</small><ul>${item.issues.map(issue=>`<li>${escapeHtml(issue.message)}</li>`).join('')}</ul></div>${managed?'<span class="badge">EnergyLab</span>':`<button class="link-button" type="button" data-edit-flow-kind="${item.kind}" data-edit-flow="${escapeHtml(item.id)}">Bearbeiten</button>`}</article>`}).join(''):'<div class="notice">Alle Einnahmen und Ausgaben können berücksichtigt werden.</div>'}
async function loadSettingsSupplemental(force=false){if(!state.currentId||!state.dashboard)return;if(!force&&state.settingsLoadedFor===state.currentId)return;if(state.settingsLoading)return;const householdId=state.currentId;state.settingsLoading=true;renderSettings();const managementQuery=`household_id=${encodeURIComponent(householdId)}&as_of=${encodeURIComponent(today())}`;try{const [diagnostics,energylab]=await Promise.all([api(`/api/diagnostics?${managementQuery}`),api(`/api/integrations/energylab?household_id=${encodeURIComponent(householdId)}`)]);if(householdId!==state.currentId)return;state.diagnostics=diagnostics;state.energylab=energylab;state.settingsLoadedFor=householdId}finally{state.settingsLoading=false;if(householdId===state.currentId)renderSettings()}}
function summaryCard(label,value,style=''){const countLabels=new Set(['Betroffene Positionen','Nicht berücksichtigt','Fehler','Warnungen','Ausgewählte Konten','Bewegungen','Buchungen']);const display=typeof value==='number'&&!countLabels.has(label)?eur(value):value;return `<article class="summary-card ${style}"><span>${escapeHtml(label)}</span><b class="${style==='negative'?'amount-negative':''}">${escapeHtml(display)}</b></article>`}

function renderAccountSelectors(target,selectedIds,mode){const accounts=state.dashboard.household.accounts;target.innerHTML=accounts.length?accounts.map(account=>`<label class="account-choice"><input type="checkbox" data-${mode}-account="${escapeHtml(account.id)}" ${selectedIds.includes(account.id)?'checked':''}> ${escapeHtml(account.name)}</label>`).join(''):'<p class="empty">Noch keine Konten vorhanden.</p>'}
function renderCreditSelectors(){const target=$('#preview-credit-selectors');target.innerHTML=state.credits.some(credit=>credit.credit_type!=='mortgage')?state.credits.filter(credit=>credit.credit_type!=='mortgage').map(credit=>`<label class="account-choice credit-choice"><input type="checkbox" data-preview-credit="${escapeHtml(credit.id)}" ${state.previewCreditIds.includes(credit.id)?'checked':''}> ${escapeHtml(credit.name)}</label>`).join(''):'<p class="empty">Noch keine Kredite vorhanden.</p>'}
function movementRow(item){const negative=Number(item.amount_cents)<0,skipped=item.skip_reason==='credit_repaid',residual=Number(item.final_residual_added_cents||0),adjusted=Boolean(item.credit_adjusted)&&!skipped,override=item.amount_overridden?` · Plan ${eur(item.planned_amount_cents)}, tatsächlich ${eur(Math.abs(item.amount_cents))}`:'',status=skipped?' · entfällt – Kredit bereits getilgt':residual>0?` · Restbetrag ${eur(residual)} in Schlussrate enthalten`:adjusted?` · Schlussrate von ${eur(item.planned_amount_cents)} auf ${eur(Math.abs(item.amount_cents))} begrenzt`:item.completed?' · erledigt – nicht eingerechnet':(item.applied_to_projection===false?' · bereits im Kontostand enthalten':'');const amountEdit=item.kind==='expense'&&item.origin==='planned'?`<button class="link-button movement-amount-button" type="button" data-movement-amount="${escapeHtml(item.completion_key)}" data-current-cents="${Math.abs(Number(item.amount_cents))}" data-planned-cents="${Number(item.planned_amount_cents)}">Betrag ändern</button>`:'',completion=item.completion_allowed?`<label class="movement-completion"><input type="checkbox" data-movement-completion="${escapeHtml(item.completion_key)}" ${item.completed?'checked':''}> Vorgang erledigt</label>`:'';return `<article class="movement-row ${item.completed?'completed':''} ${skipped?'skipped':''}"><span class="movement-kind ${escapeHtml(item.kind)}">${escapeHtml(movementLabels[item.kind]||'Buchung')}</span><span><b>${escapeHtml(item.label)}</b><small>${dateLabel(item.date)} · ${escapeHtml(accountName(item.account_id))}${override}${status}</small></span><strong class="${negative?'amount-negative':''}">${skipped?'0,00 €':`${negative?'− ':'+ '}${eur(Math.abs(item.amount_cents))}`}</strong><div class="movement-actions">${amountEdit}${completion}</div></article>`}
async function loadPreview(){if(!state.currentId)return;state.preview=await api('/api/preview/monthly',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({household_id:state.currentId,month:state.previewMonth,account_ids:state.previewAccountIds,credit_ids:state.previewCreditIds})});renderPreview()}
function creditPaymentRow(item){const skipped=item.skip_reason==='credit_repaid',increase=item.source==='manual'&&Number(item.amount_cents)<0,residual=Number(item.final_residual_added_cents||0),adjusted=Boolean(item.adjusted)&&!skipped,parts=item.automatic_calculation?[`Rate ${eur(item.account_amount_cents)}`,`Zins ${eur(item.interest_cents)}`,`Tilgung ${eur(item.effective_reduction_cents)}`,`Rest ${eur(item.remaining_after_cents)}`]:[],status=skipped?' · entfällt – Kredit bereits getilgt':increase?' · Kreditaufstockung':residual>0?` · Restbetrag ${eur(residual)} zugeschlagen`:adjusted?` · auf Restschuld begrenzt (geplant ${eur(item.planned_amount_cents)})`:item.future?' · geplant':'',amount=skipped?'0,00 €':increase?`+ ${eur(Math.abs(item.amount_cents))}`:`− ${eur(item.amount_cents)}`;return `<article class="credit-payment-row ${item.future?'future':''} ${skipped?'skipped':''} ${increase?'increase':''}"><span><b>${escapeHtml(item.label)}</b><small>${dateLabel(item.date)} · ${item.source==='expense'?'aus Ausgabe':'manuell'}${status}${parts.length?`<br>${parts.join(' · ')}`:''}</small></span><strong>${amount}</strong>${item.source==='manual'?`<button class="link-button" type="button" data-delete-credit-payment="${escapeHtml(item.id)}">Löschen</button>`:'<span></span>'}</article>`}
function renderPreview(){renderAccountSelectors($('#preview-account-selectors'),state.previewAccountIds,'preview');renderCreditSelectors();const result=state.preview,t=result.totals,ct=result.credit_totals||{opening_balance_cents:0,closing_balance_cents:0,reduction_cents:0};$('#preview-month-label').textContent=monthLabel(result.month);$('#preview-summary').innerHTML=summaryCard('Konten am Monatsanfang',t.opening_balance_cents)+summaryCard('Einnahmen',t.income_cents)+summaryCard('Ausgaben',t.expense_cents)+summaryCard('Konten am Monatsende',t.closing_balance_cents,t.closing_balance_cents<0?'negative':'');$('#preview-credit-summary').innerHTML=state.previewCreditIds.length?summaryCard('Kredite am Monatsanfang',ct.opening_balance_cents)+summaryCard('Simulierte Tilgung',ct.reduction_cents)+summaryCard('Kredite am Monatsende',ct.closing_balance_cents):'';$('#preview-warnings').innerHTML=warningHtml(result.overdraft_warnings);$('#preview-range').textContent=`${dateLabel(result.from)} – ${dateLabel(result.through)}`;const days=result.days||[];if(!result.accounts.length&&!result.credits.length){$('#preview-day-list').innerHTML='<p class="empty">Wähle mindestens ein Konto oder einen Kredit.</p>';updatePreviewDayNavigation();return}$('#preview-day-list').innerHTML=days.map(day=>{const open=state.previewSelectedDay===day.date,balances=(day.balances||[]).map(account=>`<span class="day-balance ${account.overdraft_exceeded?'warning':''}"><small>${escapeHtml(account.name)}</small><b class="${Number(account.projected_balance_cents)<0?'amount-negative':''}">${moneyOrMissing(account.projected_balance_cents)}</b></span>`).join(''),credits=(day.credits||[]).map(credit=>`<span class="day-balance credit-balance"><small>${escapeHtml(credit.name)} · Kredit</small><b>${eur(credit.remaining_balance_cents)}</b>${credit.reduction_cents?`<em>− ${eur(credit.reduction_cents)} Tilgung</em>`:''}</span>`).join('');const warning=day.overdraft_warning_count?'<div class="day-warning">Disporahmen an diesem Tag überschritten.</div>':'',creditMovements=(day.credits||[]).flatMap(credit=>credit.payments||[]);return `<details class="day-entry ${day.overdraft_warning_count?'has-warning':''}" data-preview-day-entry="${escapeHtml(day.date)}" ${open?'open':''}><summary data-preview-day="${escapeHtml(day.date)}"><span class="day-date"><b>${escapeHtml(weekdayLabel(day.date))}</b><small>${dateLabel(day.date)}</small></span><span class="day-balances">${balances}${credits}</span><span class="day-total"><small>Konten gesamt</small><b class="${day.total_balance_cents<0?'amount-negative':''}">${eur(day.total_balance_cents)}</b><em class="${day.delta_cents<0?'amount-negative':''}">${day.delta_cents===0?'keine Kontobewegung':`${day.delta_cents>0?'+ ':''}${eur(day.delta_cents)}`}</em></span></summary><div class="day-detail">${warning}<div class="movement-list">${day.movements.length?day.movements.map(movementRow).join(''):'<p class="empty">An diesem Tag sind keine Kontobewegungen fällig.</p>'}${creditMovements.length?`<div class="credit-movement-separator"><p class="eyebrow">KREDITVERÄNDERUNGEN · NICHT IN DER KONTENSUMME</p>${creditMovements.map(creditPaymentRow).join('')}</div>`:''}</div></div></details>`}).join('');updatePreviewDayNavigation()}
function updatePreviewDayNavigation(){const navigation=$('#preview-day-navigation');navigation.hidden=!state.previewSelectedDay;$('#preview-selected-day-label').textContent=state.previewSelectedDay?`${weekdayLabel(state.previewSelectedDay)}, ${dateLabel(state.previewSelectedDay)}`:''}
function selectPreviewDay(value,scroll=true){state.previewSelectedDay=value;$$('[data-preview-day-entry]').forEach(entry=>entry.open=entry.dataset.previewDayEntry===value);updatePreviewDayNavigation();if(scroll)$(`[data-preview-day-entry="${value}"]`)?.scrollIntoView({behavior:'smooth',block:'center'})}
function movePreviewDay(count){const start=state.previewSelectedDay||(state.previewMonth===monthNow()?today():`${state.previewMonth}-01`),next=shiftDay(start,count);if(next.slice(0,7)!==state.previewMonth){state.previewMonth=next.slice(0,7);state.previewSelectedDay=next;loadPreview()}else selectPreviewDay(next)}

function showView(name){$$('.view').forEach(view=>view.hidden=view.id!==`${name}-view`);$$('.nav-item').forEach(button=>button.classList.toggle('active',button.dataset.view===name));location.hash=name;if(name==='preview'&&state.currentId&&state.dashboard)loadPreview().catch(error=>toast(`Vorschau konnte nicht geladen werden: ${error.message}`));if(name==='settings'&&state.currentId&&state.dashboard)loadSettingsSupplemental().catch(error=>toast(`Einstellungen konnten nicht vollständig geladen werden: ${error.message}`))}
$$('[data-view]').forEach(button=>button.addEventListener('click',()=>showView(button.dataset.view)));
$$('[data-show-view]').forEach(link=>link.addEventListener('click',event=>{event.preventDefault();showView(link.dataset.showView)}));
let dashboardMonthRequest=0;
async function loadDashboardMonth(value){
  if(!state.currentId)return;

  const requested=
    value ||
    state.dashboardMonth ||
    monthNow();

  const requestId=++dashboardMonthRequest;

  const previous=
    state.dashboard?.month ||
    state.dashboardMonth ||
    monthNow();

  state.dashboardMonth=requested;
  state.outlook=null;
  state.outlookBaseMonth=requested;

  updateDashboardMonthControl();
  renderLiquidityOutlook();

  const control=$('.dashboard-month-control');

  if(control){
    control.setAttribute('aria-busy','true');
  }

  try{
    const dashboardAsOf=monthEndDate(requested);

    const query=
      `household_id=${encodeURIComponent(state.currentId)}`+
      `&as_of=${encodeURIComponent(dashboardAsOf)}`;

    const dashboard=await api(
      `/api/dashboard?${query}`
    );

    if(requestId!==dashboardMonthRequest)return;

    const returned=
      dashboard.month ||
      String(dashboard.as_of||'').slice(0,7);

    if(returned!==requested){
      throw new Error(
        `Server lieferte ${monthLabel(returned)} `+
        `statt ${monthLabel(requested)}.`
      );
    }

    state.dashboard=dashboard;
    state.dashboardMonth=requested;

    renderDashboard();
    renderManage();
    renderSettings();
    updateDashboardMonthControl();

    $('#current-household-name').textContent=
      state.dashboard.household.name;

    saveStartupCache();

    loadDashboardOutlook(requested).catch(error=>{
      const target=$('#dashboard-outlook-list');

      if(target){
        target.innerHTML=
          `<p class="empty">Vorschau konnte nicht geladen werden: `+
          `${escapeHtml(error.message)}</p>`;
      }
    });

  }catch(err){
    if(requestId!==dashboardMonthRequest)return;

    state.dashboardMonth=previous;
    updateDashboardMonthControl();

    toast(
      `Monat konnte nicht geladen werden: ${err.message}`
    );
  }finally{
    if(
      requestId===dashboardMonthRequest &&
      control
    ){
      control.removeAttribute('aria-busy');
    }
  }
}

function changeDashboardMonth(count){return loadDashboardMonth(shiftMonth(state.dashboardMonth||monthNow(),count))}
$('#dashboard-prev').addEventListener('click',()=>changeDashboardMonth(-1));
$('#dashboard-next').addEventListener('click',()=>changeDashboardMonth(1));
$('#dashboard-current').addEventListener('click',()=>loadDashboardMonth(monthNow()));
let dashboardMonthInputTimer=null;
function onDashboardMonthInput(event){const value=event.target.value;if(!value)return;state.dashboardMonth=value;updateDashboardMonthControl();clearTimeout(dashboardMonthInputTimer);dashboardMonthInputTimer=setTimeout(()=>loadDashboardMonth(value),120)}
$('#dashboard-month').addEventListener('input',onDashboardMonthInput);
$('#dashboard-month').addEventListener('change',event=>{clearTimeout(dashboardMonthInputTimer);if(event.target.value)loadDashboardMonth(event.target.value)});
$('#dashboard-month').addEventListener('blur',event=>{clearTimeout(dashboardMonthInputTimer);const value=event.target.value;if(value&&value!==state.dashboard?.month)loadDashboardMonth(value)});
function changePreviewMonth(count){state.previewMonth=shiftMonth(state.previewMonth,count);state.previewSelectedDay=null;loadPreview()}
$('#preview-minus').addEventListener('click',()=>changePreviewMonth(-1));$('#preview-plus').addEventListener('click',()=>changePreviewMonth(1));$('#preview-plus-two').addEventListener('click',()=>changePreviewMonth(2));$('#preview-current').addEventListener('click',()=>{state.previewMonth=monthNow();state.previewSelectedDay=null;loadPreview()});$('#preview-day-prev').addEventListener('click',()=>movePreviewDay(-1));$('#preview-day-next').addEventListener('click',()=>movePreviewDay(1));
$('#preview-day-list').addEventListener('click',event=>{const summary=event.target.closest('[data-preview-day]');if(!summary)return;const details=summary.closest('details'),value=summary.dataset.previewDay;setTimeout(()=>{if(details.open)selectPreviewDay(value,false);else if(state.previewSelectedDay===value){state.previewSelectedDay=null;updatePreviewDayNavigation()}$$('[data-preview-day-entry]').forEach(entry=>{if(entry!==details)entry.open=false})},0)});
$('#preview-day-list').addEventListener('change',async event=>{const input=event.target.closest('[data-movement-completion]');if(!input)return;const completed=input.checked;input.disabled=true;try{await api('/api/movement-completion',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({household_id:state.currentId,occurrence_key:input.dataset.movementCompletion,completed})});await loadAll();toast(completed?'Vorgang wurde als erledigt gespeichert.':'Vorgang wird wieder in der Vorschau berücksichtigt.')}catch(err){input.checked=!completed;input.disabled=false;toast(err.message)}});
$('#preview-day-list').addEventListener('click',async event=>{const button=event.target.closest('[data-movement-amount]');if(!button)return;event.preventDefault();event.stopPropagation();const current=(Number(button.dataset.currentCents)/100).toFixed(2),planned=Number(button.dataset.plannedCents),value=prompt('Tatsächlichen Betrag nur für diesen Termin eingeben. Leer lassen, um wieder den Planbetrag zu verwenden:',current);if(value===null)return;const normalized=value.trim().replace(',','.');if(normalized!==''&&(!Number.isFinite(Number(normalized))||Number(normalized)<0)){toast('Bitte einen gültigen, nicht negativen Betrag eingeben.');return}button.disabled=true;try{await api('/api/movement-amount',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({household_id:state.currentId,occurrence_key:button.dataset.movementAmount,amount_cents:normalized===''?null:euroCents(normalized)})});await loadAll();toast(normalized===''?'Für den Termin gilt wieder der Planbetrag.':`Tatsächlicher Betrag gespeichert; der Planbetrag ${eur(planned)} bleibt für künftige Termine bestehen.`)}catch(err){button.disabled=false;toast(err.message)}});
$('#dashboard-outlook-selectors').addEventListener('change',event=>{
  const input=event.target.closest('[data-outlook-account]');
  if(!input)return;

  const accountId=input.dataset.outlookAccount;
  const next=input.checked
    ? [...state.outlookAccountIds,accountId]
    : state.outlookAccountIds.filter(id=>id!==accountId);

  if(!next.length){
    input.checked=true;
    toast('Mindestens ein Bankkonto muss ausgewählt bleiben.');
    return;
  }

  const nextSet=new Set(next);
  state.outlookAccountIds=liquidDashboardAccounts()
    .map(account=>account.id)
    .filter(id=>nextSet.has(id));
  saveOutlookAccountSelection();
  state.outlook=null;
  state.outlookBaseMonth=state.dashboardMonth;
  renderLiquidityOutlook();
  loadDashboardOutlook(state.dashboardMonth).catch(error=>{
    const target=$('#dashboard-outlook-list');
    if(target){
      target.innerHTML=
        `<p class="empty">Vorschau konnte nicht geladen werden: `+
        `${escapeHtml(error.message)}</p>`;
    }
  });
});
$('#preview-account-selectors').addEventListener('change',event=>{const input=event.target.closest('[data-preview-account]');if(!input)return;const id=input.dataset.previewAccount;state.previewAccountIds=input.checked?[...state.previewAccountIds,id]:state.previewAccountIds.filter(value=>value!==id);loadPreview()});
$('#preview-credit-selectors').addEventListener('change',event=>{const input=event.target.closest('[data-preview-credit]');if(!input)return;const id=input.dataset.previewCredit;state.previewCreditIds=input.checked?[...state.previewCreditIds,id]:state.previewCreditIds.filter(value=>value!==id);loadPreview()});

function openSetup(firstRun=false){const form=$('#setup-form');form.reset();form.elements.anchor_date.value=today();$('#person-b-field').hidden=true;$('#setup-error').hidden=true;$('#close-setup').hidden=firstRun;$('#setup-dialog').showModal()}
$('#new-household').addEventListener('click',()=>openSetup(false));
$('#setup-form').addEventListener('change',event=>{if(event.target.name==='mode'){const couple=event.target.value==='couple';$('#person-b-field').hidden=!couple;event.currentTarget.elements.person_b.required=couple}});
$('#setup-form').addEventListener('submit',async event=>{event.preventDefault();const form=event.currentTarget.elements,error=$('#setup-error'),button=event.submitter;error.hidden=true;button.disabled=true;const payload={name:form.name.value,mode:form.mode.value,person_a:form.person_a.value,person_b:form.person_b.value,account:form.account_name.value?{name:form.account_name.value,owner:'A',balance_cents:euroCents(form.balance.value),anchor_date:form.anchor_date.value,overdraft_limit_cents:euroCents(form.overdraft_limit.value),bookings_applied:form.bookings_applied.checked}:null};try{const household=await api('/api/households',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});state.households=(await api('/api/households')).items;state.currentId=household.id;state.previewAccountIds=[];state.previewCreditIds=[];$('#setup-dialog').close();await loadAll();showView('dashboard');toast('Haushalt wurde angelegt.')}catch(err){error.textContent=err.message;error.hidden=false}finally{button.disabled=false}});

function updateAccountBookingsHint(){const form=$('#account-form').elements,date=dateLabel(form.anchor_date.value),checked=form.bookings_applied.checked,hint=$('#account-bookings-hint');hint.textContent=checked?`Aktiv: Fällige Zahlungen am ${date} werden nicht erneut berechnet.`:`Nicht aktiv: Fällige Zahlungen am ${date} werden zum eingegebenen Kontostand hinzugerechnet oder davon abgezogen.`;hint.classList.toggle('active',checked)}
function applyAccountEntryForDate(){if(!state.editingAccountId){updateAccountBookingsHint();return}const form=$('#account-form').elements,entry=state.editingAccountHistory.find(item=>item.anchor_date===form.anchor_date.value);if(entry){form.balance.value=(Number(entry.balance_cents)/100).toFixed(2);form.bookings_applied.checked=Boolean(entry.bookings_applied)}else if(form.anchor_date.value===state.asOf){const account=accountById(state.editingAccountId);form.balance.value=account?.projected_balance_cents==null?'0.00':(Number(account.projected_balance_cents)/100).toFixed(2);form.bookings_applied.checked=false}updateAccountBookingsHint()}
function configureAccountKindFields(){const form=$('#account-form').elements,isLine=form.is_credit_line.checked,linkedField=$('#account-linked-field'),limitLabel=$('#account-limit-label'),defaultField=$('#account-default-field');linkedField.hidden=!isLine;form.linked_account_id.disabled=!isLine;limitLabel.firstChild.textContent=isLine?'Kreditlimit':'Disporahmen';defaultField.hidden=isLine;form.is_default.disabled=isLine;if(isLine)form.is_default.checked=false}
async function openAccount(account=null){const form=$('#account-form');form.reset();state.editingAccountId=account?.id||null;state.editingAccountHistory=[];const h=state.dashboard.household;$('#account-owner').innerHTML=h.persons.map(person=>`<option value="${escapeHtml(person.slot)}">${escapeHtml(person.display_name)}</option>`).join('')+(h.mode==='couple'?'<option value="joint">Gemeinsam</option>':'');form.elements.anchor_date.value=state.asOf||today();form.elements.balance.value='0.00';form.elements.overdraft_limit.value=(Number(account?.overdraft_limit_cents||0)/100).toFixed(2);form.elements.is_default.checked=Boolean(account?.is_default);form.elements.is_credit_line.checked=account?.kind==='credit_line';form.elements.bookings_applied.checked=false;const linkedOptions=h.accounts.filter(item=>item.id!==account?.id&&item.kind!=='credit_line').map(item=>`<option value="${escapeHtml(item.id)}">${escapeHtml(item.name)}${item.is_default?' · Standard':''}</option>`).join('');form.elements.linked_account_id.innerHTML=`<option value="">Bitte auswählen</option>${linkedOptions}`;form.elements.linked_account_id.value=account?.linked_account_id||'';if(account){form.elements.name.value=account.name;form.elements.owner.value=slotForOwner(account)}else{form.elements.owner.value='A'}$('#account-dialog-eyebrow').textContent=account?'KONTO UND HISTORIE':'KONTO ANLEGEN';$('#account-dialog-title').textContent=account?'Konto bearbeiten':'Konto anlegen';$('#account-submit').textContent=account?'Änderungen und Kontostand speichern':'Konto anlegen';$('#delete-account').hidden=!account;$('#account-error').hidden=true;const history=$('#account-history');history.hidden=!account;if(account){state.editingAccountHistory=(await api(`/api/accounts/${encodeURIComponent(account.id)}/balances?household_id=${encodeURIComponent(state.currentId)}`)).items;history.innerHTML=`<h3>Kontostand-Historie</h3>${state.editingAccountHistory.map(item=>`<article class="history-row"><span><b>${dateLabel(item.anchor_date)}</b><small>${item.bookings_applied?'Tagesbuchungen bereits enthalten':'Tagesbuchungen werden ab diesem Stand berechnet'} · ${item.source==='statement'?'historischer Altbestand':'manuell'}</small></span><strong class="${item.balance_cents<0?'amount-negative':''}">${eur(item.balance_cents)}</strong>${item.source==='manual'?`<button class="link-button" type="button" data-delete-balance="${escapeHtml(item.id)}">Löschen</button>`:''}</article>`).join('')}`;}configureAccountKindFields();applyAccountEntryForDate();if(!$('#account-dialog').open)$('#account-dialog').showModal()}
$('#new-account').addEventListener('click',()=>openAccount());$('#manage-account-list').addEventListener('click',event=>{const button=event.target.closest('[data-edit-account]');if(button){const account=accountById(button.dataset.editAccount);if(account)openAccount(account)}});
$('#account-form [name="bookings_applied"]').addEventListener('change',updateAccountBookingsHint);$('#account-form [name="anchor_date"]').addEventListener('change',applyAccountEntryForDate);$('#account-form [name="is_credit_line"]').addEventListener('change',configureAccountKindFields);
$('#account-form').addEventListener('submit',async event=>{event.preventDefault();const form=event.currentTarget.elements,error=$('#account-error'),button=event.submitter;button.disabled=true;error.hidden=true;const payload={household_id:state.currentId,name:form.name.value,owner:form.owner.value,balance_cents:euroCents(form.balance.value),anchor_date:form.anchor_date.value,bookings_applied:form.bookings_applied.checked,kind:form.is_credit_line.checked?'credit_line':'checking',linked_account_id:form.is_credit_line.checked?form.linked_account_id.value:null,overdraft_limit_cents:euroCents(form.overdraft_limit.value),is_default:form.is_credit_line.checked?false:form.is_default.checked};try{const editedAccountId=state.editingAccountId,saved=await api(editedAccountId?`/api/accounts/${encodeURIComponent(editedAccountId)}`:'/api/accounts',{method:editedAccountId?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}),savedAccount=saved.accounts?.find(account=>editedAccountId?account.id===editedAccountId:account.name===payload.name);if(!savedAccount||savedAccount.anchor_date!==payload.anchor_date||Number(savedAccount.balance_cents)!==payload.balance_cents||Boolean(savedAccount.bookings_applied)!==payload.bookings_applied)throw new Error('Der gespeicherte Kontostand konnte nicht bestätigt werden. Bitte erneut versuchen.');state.asOf=payload.anchor_date;$('#account-dialog').close();state.editingAccountId=null;state.editingAccountHistory=[];await loadAll();toast(`${payload.kind==='credit_line'?'Rahmenkredit':'Kontostand'} am ${dateLabel(payload.anchor_date)} wurde gespeichert.`)}catch(err){error.textContent=err.message;error.hidden=false}finally{button.disabled=false}});
$('#delete-account').addEventListener('click',async()=>{const account=accountById(state.editingAccountId);if(!account)return;const message=`Konto „${account.name}“ wirklich löschen?\n\nDie Kontostand-Historie und alle Umbuchungen dieses Kontos werden gelöscht. Einnahmen und Ausgaben bleiben erhalten, verlieren aber ihre Kontozuordnung.`;if(!confirm(message))return;const button=$('#delete-account'),error=$('#account-error');button.disabled=true;error.hidden=true;try{const result=await api(`/api/accounts/${encodeURIComponent(account.id)}?household_id=${encodeURIComponent(state.currentId)}`,{method:'DELETE'});state.previewAccountIds=state.previewAccountIds.filter(id=>id!==account.id);$('#account-dialog').close();state.editingAccountId=null;state.editingAccountHistory=[];await loadAll();toast(`Konto wurde gelöscht. ${result.unassigned_cash_flow_count} Position(en) sind jetzt ohne Konto.`)}catch(err){error.textContent=err.message;error.hidden=false}finally{button.disabled=false}});
$('#account-history').addEventListener('click',async event=>{const button=event.target.closest('[data-delete-balance]');if(!button||!state.editingAccountId)return;if(!confirm('Diesen historischen Kontostand wirklich löschen?'))return;try{await api(`/api/accounts/${encodeURIComponent(state.editingAccountId)}/balances/${encodeURIComponent(button.dataset.deleteBalance)}?household_id=${encodeURIComponent(state.currentId)}`,{method:'DELETE'});const account=accountById(state.editingAccountId);await loadAll();await openAccount(accountById(account.id));toast('Kontostand wurde aus der Historie entfernt.')}catch(err){toast(err.message)}});

function flowById(kind,id){return (kind==='income'?state.incomes:state.expenses).find(item=>item.id===id)}
function configureFlowRecurrences(kind){const select=$('#cash-flow-form').elements.recurrence,weekly=select.querySelector('option[value="weekly"]'),expense=kind==='expense';weekly.hidden=!expense;weekly.disabled=!expense;if(!expense&&select.value==='weekly')select.value='monthly'}
function configureFlowEndFields(kind){const expense=kind==='expense';$('#cash-flow-end-date-field').hidden=!expense;$('#cash-flow-duration-field').hidden=!expense;const form=$('#cash-flow-form').elements;form.end_date.disabled=!expense;form.duration_months.disabled=!expense}
function configureFlowCreditFields(){const form=$('#cash-flow-form').elements,isCredit=state.editingFlowKind==='expense'&&creditCategories.has(form.category.value),field=$('#cash-flow-credit-fields'),current=form.credit_id.value;field.hidden=!isCredit;form.credit_id.disabled=!isCredit;if(!isCredit){form.credit_id.value='';return}const matches=state.credits.filter(credit=>credit.credit_type===form.category.value);$('#cash-flow-credit').innerHTML=matches.length?matches.map(credit=>`<option value="${escapeHtml(credit.id)}">${escapeHtml(credit.name)} · offen ${eur(credit.remaining_balance_cents)}</option>`).join(''):'<option value="">Zuerst passenden Kredit anlegen</option>';form.credit_id.value=matches.some(credit=>credit.id===current)?current:(matches[0]?.id||'')}
function syncFlowEndFromDuration(){const form=$('#cash-flow-form').elements,duration=Number(form.duration_months.value);if(state.editingFlowKind==='expense'&&form.due_date.value&&Number.isInteger(duration)&&duration>0)form.end_date.value=expectedTransferEnd(form.due_date.value,form.recurrence.value,duration)}
function syncFlowDurationFromEnd(){const form=$('#cash-flow-form').elements;if(state.editingFlowKind!=='expense')return;const months=durationBetweenDates(form.due_date.value,form.end_date.value),step={monthly:1,quarterly:3,semiannual:6,yearly:12}[form.recurrence.value];form.duration_months.value=step&&months!==''&&Number(months)%step===0?String(Number(months)/step+1):''}
function openFlow(kind,item=null){
  state.editingFlowKind=kind;state.editingFlowId=item?.id||null;
  const form=$('#cash-flow-form');form.reset();configureFlowRecurrences(kind);configureFlowEndFields(kind);
  const h=state.dashboard.household,categories=kind==='income'?incomeCategories:expenseCategories;
  $('#cash-flow-category').innerHTML=categories.map(([value,label])=>`<option value="${value}">${label}</option>`).join('');
  $('#cash-flow-owner').innerHTML=h.persons.map(person=>`<option value="${escapeHtml(person.slot)}">${escapeHtml(person.display_name)}</option>`).join('')+(h.mode==='couple'?'<option value="joint">Gemeinsam</option>':'');
  $('#cash-flow-owner-field').hidden=h.mode==='single';
  const defaultAccount=h.accounts.find(account=>account.is_default);
  $('#cash-flow-account').innerHTML='<option value="">Kein Konto zugeordnet</option>'+h.accounts.filter(account=>account.kind!=='credit_line').map(account=>`<option value="${escapeHtml(account.id)}">${escapeHtml(account.name)}${account.is_default?' · Standard':''}</option>`).join('');
  form.elements.owner.value='A';form.elements.account_id.value=defaultAccount?.id||'';form.elements.due_date.value=state.asOf;form.elements.recurrence.value='once';form.elements.active.checked=true;
  if(item){form.elements.name.value=item.name;form.elements.category.value=item.category;form.elements.owner.value=slotForOwner(item);form.elements.amount.value=(Number(item.amount_cents)/100).toFixed(2);form.elements.recurrence.value=item.recurrence;form.elements.due_date.value=item.due_date;form.elements.end_date.value=item.end_date||'';form.elements.duration_months.value=item.duration_months||'';form.elements.account_id.value=item.account_id||'';form.elements.credit_id.value=item.credit_id||'';form.elements.active.checked=Boolean(item.configured_active)}
  configureFlowCreditFields();if(item?.credit_id){form.elements.credit_id.value=item.credit_id;configureFlowCreditFields()}
  $('#cash-flow-dialog-eyebrow').textContent=item?(kind==='income'?'EINNAHME BEARBEITEN':'AUSGABE BEARBEITEN'):(kind==='income'?'NEUE EINNAHME':'NEUE AUSGABE');
  $('#cash-flow-dialog-title').textContent=item?'Position bearbeiten':(kind==='income'?'Einnahme anlegen':'Ausgabe anlegen');$('#delete-cash-flow').hidden=!item;$('#cash-flow-error').hidden=true;$('#cash-flow-dialog').showModal()
}
$('#new-income').addEventListener('click',()=>{state.incomeFilter='active';openFlow('income')});$('#new-expense').addEventListener('click',()=>{state.expenseFilter='active';openFlow('expense')});$('#dashboard-new-income').addEventListener('click',()=>{state.incomeFilter='active';openFlow('income')});$('#dashboard-new-expense').addEventListener('click',()=>{state.expenseFilter='active';openFlow('expense')});
$('#cash-flow-form').elements.duration_months.addEventListener('input',syncFlowEndFromDuration);$('#cash-flow-form').elements.due_date.addEventListener('change',()=>{if($('#cash-flow-form').elements.duration_months.value)syncFlowEndFromDuration();else syncFlowDurationFromEnd()});$('#cash-flow-form').elements.end_date.addEventListener('change',syncFlowDurationFromEnd);$('#cash-flow-form').elements.category.addEventListener('change',configureFlowCreditFields);$('#cash-flow-form').elements.credit_id.addEventListener('change',configureFlowCreditFields);
function openEnergyAccount(item){state.editingEnergyFlowId=item.id;$('#energylab-account-flow-name').textContent=`${item.name} · ${eur(item.amount_cents)} ${recurrenceLabels[item.recurrence]||item.recurrence}`;const form=$('#energylab-account-form');$('#energylab-flow-account').innerHTML=state.dashboard.household.accounts.map(account=>`<option value="${escapeHtml(account.id)}" ${account.id===item.account_id?'selected':''}>${escapeHtml(account.name)}</option>`).join('');form.elements.payment_day.value=item.payment_day||Number(String(item.due_date||'1').slice(-2));$('#energylab-account-error').hidden=true;$('#energylab-account-dialog').showModal()}
function openIncomeChange(item){state.editingIncomeChangeId=item.id;const form=$('#income-change-form');form.reset();$('#income-change-name').textContent=item.name;$('#income-change-current').textContent=`Aktuell ${eur(item.amount_cents)} · ${recurrenceLabels[item.recurrence]||item.recurrence}`;form.elements.effective_from.min=item.versions?.[0]?.version_from||'';form.elements.effective_from.value=today();$('#income-change-error').hidden=true;$('#income-change-dialog').showModal()}
function flowClick(event){const incomeChange=event.target.closest('[data-income-change]');if(incomeChange){const item=flowById('income',incomeChange.dataset.incomeChange);if(item)openIncomeChange(item);return}const accountButton=event.target.closest('[data-energy-account-flow]');if(accountButton){const item=flowById('expense',accountButton.dataset.energyAccountFlow);if(item)openEnergyAccount(item);return}const button=event.target.closest('[data-edit-flow]');if(!button)return;const kind=button.dataset.editFlowKind,item=flowById(kind,button.dataset.editFlow);if(item)openFlow(kind,item)}
$('#income-list').addEventListener('click',flowClick);$('#expense-list').addEventListener('click',flowClick);$('#diagnostics-list').addEventListener('click',flowClick);
$('#income-filter').addEventListener('click',event=>{const button=event.target.closest('[data-income-filter]');if(!button)return;state.incomeFilter=button.dataset.incomeFilter;renderIncomes()});
$('#expense-filter').addEventListener('click',event=>{const button=event.target.closest('[data-expense-filter]');if(!button)return;state.expenseFilter=button.dataset.expenseFilter;renderExpenses()});
$('#cash-flow-form').addEventListener('submit',async event=>{event.preventDefault();const form=event.currentTarget.elements,error=$('#cash-flow-error'),button=event.submitter,isCredit=state.editingFlowKind==='expense'&&creditCategories.has(form.category.value),existing=flowById(state.editingFlowKind,state.editingFlowId);button.disabled=true;error.hidden=true;const payload={household_id:state.currentId,kind:state.editingFlowKind,name:form.name.value,category:form.category.value,amount_cents:euroCents(form.amount.value),recurrence:form.recurrence.value,due_date:form.due_date.value,end_date:state.editingFlowKind==='expense'?form.end_date.value:'',duration_months:state.editingFlowKind==='expense'?form.duration_months.value:'',account_id:form.account_id.value,credit_id:isCredit?form.credit_id.value:'',credit_reduction_cents:isCredit&&existing?.credit_id===form.credit_id.value?existing.credit_reduction_cents:'',owner:form.owner.value,active:form.active.checked};try{await api(state.editingFlowId?`/api/cash-flows/${encodeURIComponent(state.editingFlowId)}`:'/api/cash-flows',{method:state.editingFlowId?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const archiveDate=payload.end_date||(payload.recurrence==='once'?payload.due_date:'');if(state.editingFlowKind==='expense')state.expenseFilter=archiveDate&&archiveDate<today()?'archive':'active';else state.incomeFilter=archiveDate&&archiveDate<today()?'archive':'active';$('#cash-flow-dialog').close();state.editingFlowId=null;await loadAll();toast('Position wurde gespeichert.')}catch(err){error.textContent=err.message;error.hidden=false}finally{button.disabled=false}});
$('#delete-cash-flow').addEventListener('click',async()=>{const item=flowById(state.editingFlowKind,state.editingFlowId);if(!item||!confirm(`„${item.name}“ wirklich löschen?`))return;try{await api(`/api/cash-flows/${encodeURIComponent(item.id)}?household_id=${encodeURIComponent(state.currentId)}`,{method:'DELETE'});$('#cash-flow-dialog').close();state.editingFlowId=null;await loadAll();toast('Position wurde gelöscht.')}catch(err){toast(err.message)}});
$('#income-change-form').addEventListener('submit',async event=>{event.preventDefault();const item=flowById('income',state.editingIncomeChangeId),form=event.currentTarget.elements,error=$('#income-change-error'),button=event.submitter;if(!item)return;error.hidden=true;button.disabled=true;const payload={household_id:state.currentId,kind:'income',name:item.name,category:item.category,amount_cents:euroCents(form.amount.value),recurrence:item.recurrence,due_date:item.due_date,effective_from:form.effective_from.value,account_id:item.account_id||'',owner:slotForOwner(item),active:Boolean(item.configured_active)};try{await api(`/api/cash-flows/${encodeURIComponent(item.id)}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});$('#income-change-dialog').close();state.editingIncomeChangeId=null;await loadAll();toast(`Neuer Betrag gilt ab ${dateLabel(payload.effective_from)}.`)}catch(err){error.textContent=err.message;error.hidden=false}finally{button.disabled=false}});
$('#energylab-account-form').addEventListener('submit',async event=>{event.preventDefault();const form=event.currentTarget.elements,error=$('#energylab-account-error'),button=event.submitter;error.hidden=true;button.disabled=true;try{await api(`/api/integrations/energylab/flows/${encodeURIComponent(state.editingEnergyFlowId)}/account`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({household_id:state.currentId,account_id:form.account_id.value,payment_day:form.payment_day.value})});$('#energylab-account-dialog').close();state.editingEnergyFlowId=null;await loadAll();toast('Konto und Zahlungstag wurden gespeichert.')}catch(err){error.textContent=err.message;error.hidden=false}finally{button.disabled=false}});

function selectCreditFormTab(name){$$('[data-credit-form-tab]').forEach(button=>button.classList.toggle('active',button.dataset.creditFormTab===name));$$('[data-credit-form-panel]').forEach(panel=>panel.hidden=panel.dataset.creditFormPanel!==name)}
function inferInstallmentApr(principal,payment,count,balloon=0){if(!(principal>0&&payment>0&&Number.isInteger(count)&&count>0&&balloon>=0&&balloon<=principal))return null;const total=payment*count+balloon;if(total<principal)return null;if(total===principal)return 0;const presentValue=monthly=>{let discount=1,value=0;for(let index=0;index<count;index++){discount*=1+monthly;value+=payment/discount}return value+balloon/discount};let low=0,high=.01;while(presentValue(high)>principal&&high<10)high*=2;if(presentValue(high)>principal)return null;for(let index=0;index<96;index++){const middle=(low+high)/2;if(presentValue(middle)>principal)low=middle;else high=middle}return (low+high)/2*1200}
function creditPlanBalanceAt(credit,effectiveFrom){if(!credit)return 0;const fallback=Number(credit.remaining_balance_cents??credit.opening_balance_cents??0),asOf=String(credit.as_of||state.asOf||today());if(!effectiveFrom||effectiveFrom<=asOf)return fallback;let balance=fallback;const projected=(credit.payments||[]).filter(item=>{const day=String(item.date||'');return day>asOf&&day<effectiveFrom&&!item.skipped&&Number.isFinite(Number(item.remaining_after_cents))}).sort((a,b)=>String(a.date).localeCompare(String(b.date)));for(const item of projected)balance=Number(item.remaining_after_cents);return balance}
function updateCreditPlanCheck(){const form=$('#credit-form').elements,count=Number(form.plan_count.value),first=form.plan_first_due.value,rate=euroCents(form.plan_amount.value||0),formOpening=euroCents(form.opening_balance.value||0),currentCredit=creditById(state.editingCreditId),creditType=form.credit_type.value,effectiveFrom=form.plan_change_from?.value||state.asOf||today(),planningBalance=currentCredit&&creditType!=='mortgage'?creditPlanBalanceAt(currentCredit,effectiveFrom):formOpening,opening=Number(planningBalance??formOpening??0),contractPrincipal=currentCredit&&creditType!=='mortgage'?opening:(euroCents(form.product_price?.value||0)||formOpening||0),financing=creditType==='consumer_credit'?euroCents(form.financing_price?.value||0):0,isConsumerFinancing=creditType==='consumer_credit'&&financing>0&&contractPrincipal>0,balloon=euroCents(form.balloon_payment.value||0),enteredRate=String(form.interest_rate.value||'').replace(',','.'),automatic=form.automatic_interest.checked,storedApr=currentCredit?.calculated_interest_rate!=null?Number(currentCredit.calculated_interest_rate):null,inferred=automatic&&!enteredRate?(Number.isFinite(storedApr)?storedApr:inferInstallmentApr(contractPrincipal,rate,count,balloon)):null,apr=enteredRate?Number(enteredRate):Number(inferred||0),target=$('#credit-plan-check'),interestHint=$('#credit-interest-hint');form.interest_rate.placeholder=inferred!=null?Number(inferred).toFixed(4):'';form.interest_rate.dataset.calculated=inferred!=null?String(inferred):'';if(interestHint)interestHint.textContent=inferred!=null?`${currentCredit&&Number.isFinite(storedApr)?'Berechneter Zinssatz':'Vorschlag aus Zahlungsplan'}: ${Number(inferred).toLocaleString('de-DE',{minimumFractionDigits:2,maximumFractionDigits:4})} % p. a.`:enteredRate?'Manuell eingetragener Zinssatz.':'Noch nicht aus den Zahlungsdaten berechenbar.';let suggested=0,suggestionBalance=opening;while(suggestionBalance>balloon&&suggested<1200&&rate>0){if(isConsumerFinancing){suggestionBalance=Math.max(balloon,suggestionBalance-rate);suggested++;continue}const interest=automatic?Math.round(suggestionBalance*apr/1200):0,principal=Math.max(0,rate-interest);if(principal<=0){suggested=0;break}suggestionBalance=Math.max(balloon,suggestionBalance-principal);suggested++}form.plan_count.placeholder=suggested?String(suggested):'';if(!first||!Number.isInteger(count)||count<1){target.className='notice wide suggestion';target.textContent=suggested?`Vorschlag: ${suggested} monatliche Zahlungen${balloon?` bis zur vertraglichen Restschuld von ${eur(balloon)}`:''}.`:'Startdatum und Rate festlegen.';return}const scheduledTotal=rate*count+balloon,comparisonBalance=isConsumerFinancing?opening:0,roundingDifference=comparisonBalance?scheduledTotal-comparisonBalance:0,roundingTolerance=1000;if(comparisonBalance&&Math.abs(roundingDifference)>roundingTolerance){target.className='notice wide error';target.textContent=`Die geplanten Zahlungen ergeben ${eur(scheduledTotal)}, der zum Änderungszeitpunkt offene Finanzierungssaldo beträgt ${eur(comparisonBalance)}. Bitte Rate, Anzahl oder Reststand prüfen.`;return}const end=addMonthsToDate(first,count-1);let remaining=opening;for(let index=0;index<count&&remaining>balloon;index++){if(isConsumerFinancing){remaining=Math.max(balloon,remaining-rate)}else{const interest=automatic?Math.round(remaining*apr/1200):0;remaining=Math.max(balloon,remaining-Math.max(0,rate-interest))}}const shortfall=Math.max(0,remaining-balloon),finalAdjustment=shortfall>0&&shortfall<=1000?shortfall:0,roundingNote=comparisonBalance&&roundingDifference?` Rundungsdifferenz: ${eur(Math.abs(roundingDifference))} (toleriert).`:'';target.className=`notice wide${shortfall>0&&!finalAdjustment?' error':' suggestion'}`;target.textContent=finalAdjustment?`${count} Monatsraten bis ${dateLabel(end)}. Die letzte Rate wird automatisch um ${eur(finalAdjustment)} auf ${eur(rate+finalAdjustment)} angepasst; danach beträgt die vertragliche Restschuld ${eur(balloon)}.`:shortfall>0?`${count} Zahlungen reichen ab dem Reststand von ${eur(opening)} voraussichtlich nicht: Ziel-Restschuld um ${eur(shortfall)} verfehlt. Vorschlag: ${suggested||'–'} Zahlungen.`:`${count} Monatsraten bis ${dateLabel(end)} · gerechnet ab Reststand ${eur(opening)} · danach vertragliche Restschuld ${eur(balloon)}.${roundingNote}${suggested&&suggested<count?` Rechnerisch genügen voraussichtlich ${suggested}.`:''}`}
function configureCreditTypeFields(){const form=$('#credit-form').elements,isMortgage=form.credit_type.value==='mortgage';$('#mortgage-fields').hidden=!isMortgage;for(const input of $('#mortgage-fields').querySelectorAll('input'))input.disabled=!isMortgage;$('#credit-opening-label-text').textContent=isMortgage?'Aktuelle Restschuld':'Anfangssaldo';form.automatic_interest.checked=isMortgage?true:form.automatic_interest.checked;form.automatic_interest.disabled=isMortgage;if(isMortgage&&form.fixed_interest_until.value&&form.plan_first_due.value){const start=form.plan_first_due.value.slice(0,7),end=form.fixed_interest_until.value.slice(0,7);const [sy,sm]=start.split('-').map(Number),[ey,em]=end.split('-').map(Number),count=(ey-sy)*12+(em-sm)+1;if(count>0)form.plan_count.value=String(count)}if(isMortgage&&window.syncMortgagePlanV200)window.syncMortgagePlanV200()}
function mortgagePayload(form){return form.credit_type.value==='mortgage'?{original_principal_cents:euroCents(form.original_principal.value),balance_as_of:form.balance_as_of.value,effective_interest_rate:form.effective_interest_rate.value,repayment_rate:form.repayment_rate.value,fixed_interest_until:form.fixed_interest_until.value,special_repayment_percent:form.special_repayment_percent.value}:{};}
function openCredit(item=null){state.editingCreditId=item?.id||null;const form=$('#credit-form');form.reset(),plan=item?.payment_plan||null,accounts=state.dashboard.household.accounts.filter(account=>account.kind!=='credit_line'),defaultAccount=accounts.find(account=>account.is_default)||accounts[0];form.elements.credit_type.value=item?.credit_type||'consumer_credit';form.elements.opening_balance.value=item?(Number(item.opening_balance_cents)/100).toFixed(2):'';form.elements.original_principal.value=item?.original_principal_cents?(Number(item.original_principal_cents)/100).toFixed(2):'';form.elements.balance_as_of.value=item?.balance_as_of||today();form.elements.effective_interest_rate.value=item?.effective_interest_rate??'';form.elements.repayment_rate.value=item?.repayment_rate??'';form.elements.fixed_interest_until.value=item?.fixed_interest_until||'';form.elements.special_repayment_percent.value=item?.special_repayment_percent??'';form.elements.interest_rate.value=item?.interest_rate??'';form.elements.automatic_interest.checked=item?Boolean(item.automatic_interest):true;form.elements.name.value=item?.name||'';form.elements.note.value=item?.note||'';form.elements.archived.checked=Boolean(item?.archived);form.elements.balloon_payment.value=(Number(item?.balloon_payment_cents||0)/100).toFixed(2);form.elements.plan_account.innerHTML=accounts.map(account=>`<option value="${escapeHtml(account.id)}">${escapeHtml(account.name)}</option>`).join('');form.elements.plan_account.value=plan?.account_id||defaultAccount?.id||'';form.elements.plan_amount.value=plan?(Number(plan.amount_cents)/100).toFixed(2):'';form.elements.plan_first_due.value=plan?.due_date||today();form.elements.plan_count.value=plan?.occurrence_count||'';form.elements.plan_change_from.value=today();$('#credit-plan-change-field').hidden=!item;$('#credit-edit-payment-list').innerHTML=item?(item.payments.length?item.payments.map(creditPaymentRow).join(''):'<p class="empty">Noch keine Tilgungen vorhanden.</p>'):'<p class="empty">Die Tilgungshistorie steht nach dem Anlegen des Kredits zur Verfügung.</p>';const editPaymentForm=$('#credit-edit-payment-form');editPaymentForm.querySelector('[name="payment_date"]').value=today();editPaymentForm.querySelector('[name="amount"]').value='';$('#credit-edit-payment-error').hidden=true;$('#credit-archive-field').hidden=!item;$('#credit-dialog-title').textContent=item?'Kredit bearbeiten':'Kredit anlegen';$('#delete-credit').hidden=!item;$('#credit-error').hidden=true;selectCreditFormTab('data');configureCreditTypeFields();updateCreditPlanCheck();$('#credit-dialog').showModal()}
async function openCreditDetail(creditId){const credit=await api(`/api/credits/${encodeURIComponent(creditId)}?household_id=${encodeURIComponent(state.currentId)}&as_of=${encodeURIComponent(today())}`);state.currentCreditId=credit.id;$('#credit-detail-type').textContent=creditTypeLabels[credit.credit_type]||'KREDIT';$('#credit-detail-title').textContent=credit.name;$('#credit-detail-summary').innerHTML=(credit.credit_type==='mortgage'?summaryCard('Ursprüngliche Summe',credit.original_principal_cents)+summaryCard('Restschuld',credit.remaining_balance_cents)+summaryCard('Sollzins',`${credit.interest_rate||'–'} %`)+summaryCard('Tilgung',`${credit.repayment_rate||'–'} %`)+summaryCard('Zinsbindung',dateLabel(credit.fixed_interest_until))+summaryCard('Sondertilgung/Jahr',`${credit.special_repayment_percent||'0'} % · ${eur(credit.special_repayment_limit_cents||0)}`):summaryCard('Anfangssaldo',credit.opening_balance_cents)+summaryCard('Bisher getilgt',credit.paid_cents)+summaryCard('Offener Saldo',credit.remaining_balance_cents))+(credit.contractual_end_date?summaryCard('Vertragliches Ende',dateLabel(credit.contractual_end_date)):'')+(credit.expected_repayment_date?summaryCard('Voraussichtlich getilgt',dateLabel(credit.expected_repayment_date)):'');$('#credit-payment-list').innerHTML=credit.payments.length?credit.payments.map(creditPaymentRow).join(''):'<p class="empty">Noch keine Tilgungen vorhanden.</p>';const form=$('#credit-payment-form');form.reset();form.elements.payment_date.value=today();$('#credit-payment-error').hidden=true;if(!$('#credit-detail-dialog').open)$('#credit-detail-dialog').showModal()}
$('#new-credit').addEventListener('click',()=>openCredit());
$('[data-credit-form-tab="data"]').closest('.credit-tabs').addEventListener('click',event=>{const button=event.target.closest('[data-credit-form-tab]');if(button)selectCreditFormTab(button.dataset.creditFormTab)});
['plan_amount','plan_first_due','plan_count','opening_balance','balloon_payment','interest_rate','automatic_interest','plan_change_from'].forEach(name=>$('#credit-form').elements[name].addEventListener('input',updateCreditPlanCheck));
$('#credit-form').elements.credit_type.addEventListener('change',()=>{configureCreditTypeFields();updateCreditPlanCheck()});['fixed_interest_until','plan_first_due'].forEach(name=>$('#credit-form').elements[name].addEventListener('change',configureCreditTypeFields));
$('#credit-filter').addEventListener('click',event=>{const button=event.target.closest('[data-credit-filter]');if(!button)return;state.creditFilter=button.dataset.creditFilter;renderCredits()});
$('#credit-list').addEventListener('click',event=>{const edit=event.target.closest('[data-edit-credit]');if(edit){const item=creditById(edit.dataset.editCredit);if(item)openCredit(item);return}const row=event.target.closest('[data-open-credit]');if(row){const item=creditById(row.dataset.openCredit);if(item)openCredit(item)}});
$('#credit-edit-payment-submit').addEventListener('click',async event=>{const creditId=state.editingCreditId;if(!creditId)return;const area=$('#credit-edit-payment-form'),dateInput=area.querySelector('[name="payment_date"]'),amountInput=area.querySelector('[name="amount"]'),error=$('#credit-edit-payment-error'),button=event.currentTarget;if(!dateInput.value||!amountInput.value){error.textContent='Bitte Datum und Betrag angeben.';error.hidden=false;return}const amount=euroCents(amountInput.value);error.hidden=true;button.disabled=true;const payload={household_id:state.currentId,payment_date:dateInput.value,amount_cents:amount,note:''};try{await api(`/api/credits/${encodeURIComponent(creditId)}/payments`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});await loadAll();const updated=creditById(creditId);$('#credit-edit-payment-list').innerHTML=updated&&updated.payments.length?updated.payments.map(creditPaymentRow).join(''):'<p class="empty">Noch keine Tilgungen vorhanden.</p>';amountInput.value='';dateInput.value=today();toast(amount<0?'Kreditaufstockung wurde gespeichert.':'Tilgung wurde gespeichert.')}catch(err){error.textContent=err.message;error.hidden=false}finally{button.disabled=false}});
$('#credit-form').addEventListener('submit',async event=>{if(window.finanzLabCreditSubmitV15)return;event.preventDefault();const form=event.currentTarget.elements,error=$('#credit-error'),button=event.submitter,creditId=state.editingCreditId,current=creditById(creditId),plan={amount_cents:euroCents(form.plan_amount.value),first_due_date:form.plan_first_due.value,occurrence_count:form.plan_count.value,account_id:form.plan_account.value,owner:'A',flow_id:current?.payment_plan?.flow_id,effective_from:form.plan_change_from.value||today()};if(!form.name.value||!form.opening_balance.value){error.textContent="Bitte die Kreditdaten vollständig ausfüllen.";error.hidden=false;selectCreditFormTab("data");return}if(!form.plan_amount.value||!form.plan_first_due.value||!form.plan_count.value||!form.plan_account.value){error.textContent="Bitte die Zahlungsdaten vollständig ausfüllen.";error.hidden=false;selectCreditFormTab("plan");return}error.hidden=true;button.disabled=true;const payload={household_id:state.currentId,name:form.name.value,credit_type:form.credit_type.value,opening_balance_cents:euroCents(form.opening_balance.value),interest_rate:form.interest_rate.value,automatic_interest:form.automatic_interest.checked,note:form.note?.value||'',balloon_payment_cents:euroCents(form.balloon_payment.value||0),payment_plan:plan,...mortgagePayload(form)};try{await api(creditId?`/api/credits/${encodeURIComponent(creditId)}`:'/api/credits',{method:creditId?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});if(creditId){const flowPayload={household_id:state.currentId,kind:'expense',name:payload.name,category:payload.credit_type,amount_cents:plan.amount_cents,recurrence:'monthly',due_date:plan.first_due_date,duration_months:plan.occurrence_count,account_id:plan.account_id,credit_id:creditId,credit_reduction_cents:current?.payment_plan?'':'',owner:'A',active:true,effective_from:form.plan_change_from.value||today()};await api(current?.payment_plan?.flow_id?`/api/cash-flows/${encodeURIComponent(current.payment_plan.flow_id)}`:'/api/cash-flows',{method:current?.payment_plan?.flow_id?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(flowPayload)});await api(`/api/credits/${encodeURIComponent(creditId)}/archive`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({household_id:state.currentId,archived:form.archived.checked})})}state.creditFilter=creditId&&form.archived.checked?'archive':payload.credit_type;$('#credit-dialog').close();state.editingCreditId=null;await loadAll();toast(creditId&&form.archived.checked?'Kredit wurde gespeichert und archiviert.':'Kredit und Zahlungsplan wurden gespeichert.')}catch(err){error.textContent=err.message;error.hidden=false}finally{button.disabled=false}});
$('#delete-credit').addEventListener('click',async()=>{const item=creditById(state.editingCreditId);if(!item||!confirm(`„${item.name}“ mit seiner Zahlungshistorie wirklich löschen? Verknüpfte Ausgaben bleiben als normale Ausgaben erhalten.`))return;try{await api(`/api/credits/${encodeURIComponent(item.id)}?household_id=${encodeURIComponent(state.currentId)}`,{method:'DELETE'});$('#credit-dialog').close();state.editingCreditId=null;state.previewCreditIds=state.previewCreditIds.filter(id=>id!==item.id);await loadAll();toast('Kredit wurde gelöscht.')}catch(err){toast(err.message)}});
$('#credit-payment-form').addEventListener('submit',async event=>{event.preventDefault();if(!state.currentCreditId)return;const form=event.currentTarget.elements,error=$('#credit-payment-error'),button=event.submitter,amount=euroCents(form.amount.value);error.hidden=true;button.disabled=true;const payload={household_id:state.currentId,payment_date:form.payment_date.value,amount_cents:amount,note:form.note?.value||''};try{await api(`/api/credits/${encodeURIComponent(state.currentCreditId)}/payments`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});await loadAll();await openCreditDetail(state.currentCreditId);toast(amount<0?'Kreditaufstockung wurde gespeichert.':'Tilgung wurde gespeichert.')}catch(err){error.textContent=err.message;error.hidden=false}finally{button.disabled=false}});
$('#credit-payment-list').addEventListener('click',async event=>{const button=event.target.closest('[data-delete-credit-payment]');if(!button||!state.currentCreditId)return;if(!confirm('Diese manuelle Tilgung oder Kreditaufstockung wirklich löschen?'))return;try{await api(`/api/credits/${encodeURIComponent(state.currentCreditId)}/payments/${encodeURIComponent(button.dataset.deleteCreditPayment)}?household_id=${encodeURIComponent(state.currentId)}`,{method:'DELETE'});await loadAll();await openCreditDetail(state.currentCreditId);toast('Tilgung wurde gelöscht.')}catch(err){toast(err.message)}});

function syncTransferCreditLine(){const form=$('#transfer-form').elements,source=accountById(form.source_account_id.value),target=accountById(form.target_account_id.value),hint=$('#transfer-credit-line-hint');if(source?.kind==='credit_line'&&source.linked_account_id){form.target_account_id.value=source.linked_account_id;form.recurrence.value='once';form.recurrence.disabled=true;form.end_date.value='';form.end_date.disabled=true;form.occurrence_count.value='1';form.occurrence_count.disabled=true;const limit=Number(source.overdraft_limit_cents||0),balance=Number(source.projected_balance_cents??source.balance_cents??0),available=Math.max(0,limit-Math.max(0,-balance));hint.textContent=`Auszahlung aus ${source.name}: beliebig viele einzelne Auszahlungen sind möglich. Laut aktueller Prognose sind etwa ${eur(available)} Rahmen verfügbar; das Limit wird für jede Auszahlung serverseitig zum Fälligkeitstag geprüft.`;hint.hidden=false;return}form.recurrence.disabled=false;form.end_date.disabled=false;form.occurrence_count.disabled=false;if(target?.kind==='credit_line'&&target.linked_account_id){form.source_account_id.value=target.linked_account_id;hint.textContent=`Tilgung auf ${target.name}: Umbuchungen sind nur vom verknüpften Konto ${accountName(target.linked_account_id)} möglich.`;hint.hidden=false;return}hint.hidden=true;hint.textContent=''}
function openTransfer(item=null){const accounts=state.dashboard.household.accounts;if(accounts.length<2){toast('Für eine Umbuchung werden mindestens zwei Konten benötigt.');showView('accounts');return}state.editingTransferId=item?.id||null;const form=$('#transfer-form');form.reset();const options=accounts.map(account=>`<option value="${escapeHtml(account.id)}">${escapeHtml(account.name)}${account.kind==='credit_line'?' · Rahmenkredit':''}</option>`).join('');$('#transfer-source').innerHTML=options;$('#transfer-target').innerHTML=options;const defaultAccount=accounts.find(account=>account.is_default)||accounts.find(account=>account.kind!=='credit_line')||accounts[0];form.elements.source_account_id.value=item?.source_account_id||defaultAccount.id;form.elements.target_account_id.value=item?.target_account_id||accounts.find(account=>account.id!==form.elements.source_account_id.value).id;form.elements.name.value=item?.name||'Umbuchung';form.elements.amount.value=item?(Number(item.amount_cents)/100).toFixed(2):'';form.elements.due_date.value=item?.due_date||state.asOf;form.elements.recurrence.value=item?.recurrence||'once';form.elements.end_date.value=item?.end_date||'';form.elements.occurrence_count.value=item?.occurrence_count||'';form.elements.active.checked=item?Boolean(item.active):true;$('#transfer-dialog-title').textContent=item?'Umbuchung bearbeiten':'Umbuchung anlegen';$('#delete-transfer').hidden=!item;$('#transfer-error').hidden=true;syncTransferCreditLine();$('#transfer-dialog').showModal()}
$('#transfer-source').addEventListener('change',syncTransferCreditLine);$('#transfer-target').addEventListener('change',syncTransferCreditLine);

$('#new-transfer').addEventListener('click',()=>openTransfer());


$('#transfer-filter').addEventListener('click',event=>{
    const button=event.target.closest('[data-transfer-filter]');
    if(!button)return;
    state.transferFilter=button.dataset.transferFilter;
    renderTransfers();
});


$('#transfer-list').addEventListener('click',event=>{
    const button=event.target.closest('[data-edit-transfer]');
    if(!button)return;

    const item=state.transfers.find(
        entry=>entry.id===button.dataset.editTransfer
    );

    if(item)openTransfer(item);
});

$('#transfer-form').addEventListener('submit',async event=>{event.preventDefault();const form=event.currentTarget.elements,error=$('#transfer-error'),button=event.submitter,limitError=transferLimitError(form);error.hidden=true;if(limitError){error.textContent=limitError;error.hidden=false;form.end_date.focus();return}button.disabled=true;const payload={household_id:state.currentId,name:form.name.value,source_account_id:form.source_account_id.value,target_account_id:form.target_account_id.value,amount_cents:euroCents(form.amount.value),due_date:form.due_date.value,recurrence:form.recurrence.value,end_date:form.end_date.value,occurrence_count:form.occurrence_count.value,active:form.active.checked};try{await api(state.editingTransferId?`/api/transfers/${encodeURIComponent(state.editingTransferId)}`:'/api/transfers',{method:state.editingTransferId?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const archiveDate=payload.end_date||(payload.recurrence==='once'?payload.due_date:'');state.transferFilter=archiveDate&&archiveDate<today()?'archive':'active';$('#transfer-dialog').close();state.editingTransferId=null;await loadAll();toast('Umbuchung wurde gespeichert.')}catch(err){error.textContent=err.message;error.hidden=false}finally{button.disabled=false}});
$('#delete-transfer').addEventListener('click',async()=>{const item=state.transfers.find(entry=>entry.id===state.editingTransferId);if(!item||!confirm(`„${item.name}“ wirklich löschen?`))return;try{await api(`/api/transfers/${encodeURIComponent(item.id)}?household_id=${encodeURIComponent(state.currentId)}`,{method:'DELETE'});$('#transfer-dialog').close();state.editingTransferId=null;await loadAll();toast('Umbuchung wurde gelöscht.')}catch(err){toast(err.message)}});

$('#category-form')?.addEventListener('submit',async event=>{event.preventDefault();const form=event.currentTarget.elements,error=$('#category-error'),button=event.submitter;error.hidden=true;button.disabled=true;try{await api('/api/categories',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({household_id:state.currentId,kind:form.kind.value,name:form.name.value})});form.name.value='';await loadAll();toast('Art wurde hinzugefügt.')}catch(err){error.textContent=err.message;error.hidden=false}finally{button.disabled=false}});
$('#category-settings-list')?.addEventListener('click',async event=>{const edit=event.target.closest('[data-edit-category]'),del=event.target.closest('[data-delete-category]'),id=edit?.dataset.editCategory||del?.dataset.deleteCategory;if(!id)return;const item=state.categories.find(entry=>entry.id===id);if(!item)return;if(edit){const name=prompt('Bezeichnung der Art:',item.name);if(name===null)return;const active=confirm('OK = aktiv lassen/aktivieren. Abbrechen = deaktivieren.');try{await api(`/api/categories/${encodeURIComponent(id)}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({household_id:state.currentId,name,active})});await loadAll();toast('Art wurde gespeichert.')}catch(err){toast(err.message)}}else if(del&&confirm(`Eigene Art „${item.name}“ wirklich löschen?`)){try{await api(`/api/categories/${encodeURIComponent(id)}?household_id=${encodeURIComponent(state.currentId)}`,{method:'DELETE'});await loadAll();toast('Art wurde gelöscht.')}catch(err){toast(err.message)}}});
$('#household-select').addEventListener('change',async event=>{state.currentId=event.target.value;state.previewAccountIds=[];state.previewCreditIds=[];state.outlookAccountIds=[];state.outlookSelectionFor=null;state.outlook=null;state.outlookBaseMonth=null;state.incomeFilter='active';state.expenseFilter='active';state.transferFilter='active';state.creditFilter='all';state.diagnostics=null;state.energylab=null;state.settingsLoadedFor=null;await loadAll()});
$('#delete-household').addEventListener('click',async()=>{const current=state.households.find(h=>h.id===state.currentId);if(!current||!confirm(`Haushalt „${current.name}“ einschließlich aller Daten endgültig löschen?`))return;try{await api(`/api/households/${encodeURIComponent(current.id)}`,{method:'DELETE'});state.households=(await api('/api/households')).items;state.currentId=state.households[0]?.id||null;if(state.currentId)await loadAll();else openSetup(true);toast('Haushalt wurde gelöscht.')}catch(err){toast(err.message)}});

$('#energylab-form').addEventListener('submit',async event=>{event.preventDefault();const form=event.currentTarget.elements,button=event.submitter,status=$('#energylab-status');button.disabled=true;status.hidden=true;try{state.energylab=await api('/api/integrations/energylab',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({household_id:state.currentId,base_url:form.base_url.value,account_id:form.account_id.value,callback_token:form.callback_token.value,enabled:form.enabled.checked})});renderSettings();toast('EnergyLab-Verbindung wurde gespeichert.')}catch(err){status.textContent=err.message;status.className='notice error';status.hidden=false}finally{button.disabled=false}});
$('#energylab-sync').addEventListener('click',async event=>{const button=event.currentTarget,status=$('#energylab-status');button.disabled=true;button.textContent='Wird synchronisiert …';status.hidden=true;try{const result=await api('/api/integrations/energylab/sync',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({household_id:state.currentId})});await loadAll();toast(result.message)}catch(err){status.textContent=err.message;status.className='notice error';status.hidden=false}finally{button.disabled=false;button.textContent='Jetzt synchronisieren'}});

$('#open-excel-export').addEventListener('click',()=>{const form=$('#excel-export-form');form.elements.from_month.value=monthNow();form.elements.through_month.value=shiftMonth(monthNow(),11);$('#excel-export-error').hidden=true;$('#excel-export-dialog').showModal()});
$('#excel-export-form').addEventListener('submit',async event=>{event.preventDefault();const form=event.currentTarget.elements,error=$('#excel-export-error'),button=event.submitter;error.hidden=true;button.disabled=true;button.textContent='Excel wird erstellt …';try{const query=new URLSearchParams({household_id:state.currentId,from_month:form.from_month.value,through_month:form.through_month.value});const response=await fetch(`/api/export.xlsx?${query}`);if(!response.ok){const data=await response.json().catch(()=>({}));throw new Error(data.error||'Der Excel-Export konnte nicht erstellt werden.')}const blob=await response.blob(),disposition=response.headers.get('Content-Disposition')||'',match=disposition.match(/filename="([^"]+)"/),filename=match?.[1]||`Haushaltsplaner-${form.from_month.value}-bis-${form.through_month.value}.xlsx`,url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=filename;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);$('#excel-export-dialog').close();toast('Die Excel-Arbeitsmappe wurde erstellt.')}catch(err){error.textContent=err.message;error.hidden=false}finally{button.disabled=false;button.textContent='Excel herunterladen'}});
$$('[data-close]').forEach(button=>button.addEventListener('click',()=>document.getElementById(button.dataset.close).close()));
boot().catch(error=>{$('#app').hidden=false;toast(`Die Anwendung konnte nicht gestartet werden: ${error.message}`)});

;(()=>{const marker="finanzlab-1.6.3-opening-default";
function bindOpeningDefaultFromFinancing(){
  const form=document.querySelector('#credit-form');
  if(!form||form.dataset.openingDefaultBound)return;
  form.dataset.openingDefaultBound='1';

  const els=form.elements;
  const opening=els.opening_balance;
  if(!opening)return;

  opening.addEventListener('input',()=>{opening.dataset.manual='1';});

  const apply=()=>{
    const type=els.credit_type&&els.credit_type.value;
    const financing=typeof euroCents==='function'?euroCents(els.financing_price&&els.financing_price.value||0):0;
    if(type!=='consumer_credit'||!financing||state.editingCreditId)return;
    if(!opening.value||opening.dataset.autoFromFinancing==='1'){
      opening.value=(financing/100).toFixed(2);
      opening.dataset.autoFromFinancing='1';
      try{updateCreditPlanCheck();}catch(e){}
    }
  };

  ['credit_type','financing_price','product_price','installment_surcharge'].forEach(name=>{
    const el=els[name];
    if(!el)return;
    el.addEventListener('input',()=>setTimeout(apply,0));
    el.addEventListener('change',()=>setTimeout(apply,0));
  });

  setTimeout(apply,0);
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bindOpeningDefaultFromFinancing);
else bindOpeningDefaultFromFinancing();
})();

/* finanzlab-1.6.5-form-opening-check */





;(()=>{const marker="finanzlab-1.6.12-credit-plan-helper";
function bindCreditPlanHelper1612(){
  const form=document.querySelector('#credit-form');
  if(!form||form.dataset.creditPlanHelper1612)return;
  form.dataset.creditPlanHelper1612='1';

  const els=form.elements;
  const product=els.product_price;
  const financing=els.financing_price;
  const surcharge=els.installment_surcharge;
  const opening=els.opening_balance;
  const planAmount=els.plan_amount;
  const planCount=els.plan_count;
  const balloon=els.balloon_payment;

  if(!product||!financing||!opening||!planAmount||!planCount)return;

  const cents=value=>typeof euroCents==='function'
    ? euroCents(value||0)
    : (Math.round(Number(String(value||'0').replace(',','.'))*100)||0);

  const money=c=>((c||0)/100).toFixed(2);
  const isConsumer=()=>els.credit_type&&els.credit_type.value==='consumer_credit';
  const isMortgage=()=>els.credit_type&&els.credit_type.value==='mortgage';

  const setOpeningByScript=(valueCents)=>{
    opening.dataset.settingFromScript='1';
    try{
      opening.value=valueCents ? money(valueCents) : '';
    }finally{
      setTimeout(()=>{opening.dataset.settingFromScript='';},0);
    }
  };

  opening.addEventListener('input',()=>{
    if(opening.dataset.settingFromScript==='1')return;
    opening.dataset.manual='1';
    opening.dataset.autoFromFinancing='0';
    opening.dataset.manualCents=String(cents(opening.value));
  },true);

  const syncCreditData=(source)=>{
    if(!isConsumer())return;

    const productCents=cents(product.value);
    let financingCents=cents(financing.value);
    const surchargeCents=surcharge?cents(surcharge.value):0;

    if(source==='surcharge'&&productCents>0){
      financingCents=productCents+surchargeCents;
      financing.value=money(financingCents);
    }

    if(financingCents>0&&productCents>0&&surcharge){
      surcharge.value=money(Math.max(0,financingCents-productCents));
    }

    // Produktpreis allein setzt den Anfangssaldo nicht.
    if(financingCents<=0){
      if(opening.dataset.manual!=='1' || cents(opening.value)<=100){
        setOpeningByScript(0);
        opening.dataset.autoFromFinancing='0';
      }
      return;
    }

    // Manuell gesetzter Anfangssaldo gewinnt immer.
    if(opening.dataset.manual==='1'){
      const manualCents=Number(opening.dataset.manualCents||0);
      if(Number.isFinite(manualCents)&&manualCents>=0){
        setOpeningByScript(manualCents);
        opening.dataset.autoFromFinancing='0';
      }
      return;
    }

    setOpeningByScript(financingCents);
    opening.dataset.autoFromFinancing='1';
  };

  const planBase=()=>{
    const openingCents=cents(opening.value);
    const financingCents=cents(financing.value);
    const base=openingCents||financingCents||0;
    const balloonCents=balloon?cents(balloon.value):0;
    return Math.max(0,base-balloonCents);
  };

  const recalcPlanFromRate=()=>{
    if(isMortgage())return;
    const base=planBase();
    const rate=cents(planAmount.value);
    if(base<=0||rate<=0)return;

    const count=Math.max(1,Math.ceil(base/rate));
    planCount.value=String(count);

    try{if(typeof updateCreditPlanCheck==='function')updateCreditPlanCheck();}catch(e){}
  };

  const recalcPlanFromCount=()=>{
    if(isMortgage())return;
    const base=planBase();
    const count=Number(planCount.value||0);
    if(base<=0||!Number.isFinite(count)||count<1)return;

    const rate=Math.ceil(base/count);
    planAmount.value=money(rate);

    try{if(typeof updateCreditPlanCheck==='function')updateCreditPlanCheck();}catch(e){}
  };

  const settle=source=>{
    syncCreditData(source);
    try{if(typeof updateCreditPlanCheck==='function')updateCreditPlanCheck();}catch(e){}
  };

  const later=source=>{
    setTimeout(()=>settle(source),0);
    setTimeout(()=>settle(source),40);
    setTimeout(()=>settle(source),120);
  };

  ['input','change'].forEach(ev=>{
    product.addEventListener(ev,()=>later('product'));
    financing.addEventListener(ev,()=>later('financing'));

    if(surcharge){
      surcharge.addEventListener(ev,()=>later('surcharge'));
    }

    planAmount.addEventListener(ev,()=>setTimeout(recalcPlanFromRate,0));
    planCount.addEventListener(ev,()=>setTimeout(recalcPlanFromCount,0));

    if(balloon){
      balloon.addEventListener(ev,()=>{
        if(isMortgage())return;
        if(cents(planAmount.value)>0)setTimeout(recalcPlanFromRate,0);
        else if(Number(planCount.value||0)>0)setTimeout(recalcPlanFromCount,0);
      });
    }
  });

  if(els.credit_type){
    els.credit_type.addEventListener('change',()=>later('type'));
  }

  document.addEventListener('click',event=>{
    if(event.target&&event.target.matches('[data-credit-form-tab]'))later('tab');
  });
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bindCreditPlanHelper1612);
else bindCreditPlanHelper1612();
})();

;(()=>{const marker="finanzlab-1.6.13-save-validation-fix";
function hideLegacyFinancingError1613(){
  const legacy='Monatsrate, Zahlungsanzahl und Schlussrate passen nicht zum Finanzierungspreis.';
  const replacement='Hinweis: Finanzierungspreis und Zahlungsplan werden getrennt behandelt.';

  const clean=()=>{
    document.querySelectorAll('*').forEach(el=>{
      if(el.childElementCount)return;
      if((el.textContent||'').trim()===legacy){
        el.textContent=replacement;
        el.classList.remove('error');
        el.classList.add('suggestion');
        el.style.display='none';
      }
    });
  };

  const observer=new MutationObserver(()=>clean());
  observer.observe(document.body,{childList:true,subtree:true,characterData:true});
  clean();
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',hideLegacyFinancingError1613);
else hideLegacyFinancingError1613();
})();


/* finanzlab-2.0.0-mortgage-plan-fix */
;(()=>{
  function bindMortgagePlanV200(){
    const form=document.querySelector('#credit-form');
    if(!form||form.dataset.mortgagePlanV200)return;
    form.dataset.mortgagePlanV200='1';
    const e=form.elements;
    const isMortgage=()=>e.credit_type?.value==='mortgage';
    const cents=value=>typeof euroCents==='function'?euroCents(value||0):(Math.round(Number(String(value||'0').replace(',','.'))*100)||0);
    const money=value=>((Number(value)||0)/100).toFixed(2);
    const pct=value=>Number(String(value||'').replace(',','.'));
    const countMonths=()=>{
      if(!e.plan_first_due.value||!e.fixed_interest_until.value)return 0;
      const [sy,sm]=e.plan_first_due.value.slice(0,7).split('-').map(Number);
      const [ey,em]=e.fixed_interest_until.value.slice(0,7).split('-').map(Number);
      const count=(ey-sy)*12+(em-sm)+1;
      return Number.isFinite(count)&&count>0?count:0;
    };
    const autoRate=()=>{
      const principal=cents(e.original_principal.value),interest=pct(e.interest_rate.value),repayment=pct(e.repayment_rate.value);
      if(!(principal>0&&Number.isFinite(interest)&&interest>=0&&Number.isFinite(repayment)&&repayment>0))return 0;
      return Math.round(principal*(interest+repayment)/1200);
    };
    const forecast=(opening,rate,interest,count)=>{
      let remaining=opening;
      for(let i=0;i<count&&remaining>0;i++){
        const interestPart=Math.round(remaining*interest/1200);
        const principalPart=rate-interestPart;
        if(principalPart<=0)break;
        remaining=Math.max(0,remaining-principalPart);
      }
      return remaining;
    };
    const setLabel=(input,text,hint)=>{
      const label=input?.closest('label'); if(!label)return;
      const node=[...label.childNodes].find(n=>n.nodeType===Node.TEXT_NODE&&n.textContent.trim());
      if(node)node.textContent=text;
      const h=label.querySelector('.hint'); if(h&&hint!=null)h.textContent=hint;
    };
    let reset=document.querySelector('#mortgage-rate-reset');
    if(!reset){
      reset=document.createElement('button'); reset.type='button'; reset.id='mortgage-rate-reset'; reset.className='link-button';
      reset.textContent='Aus Tilgung neu berechnen'; e.plan_amount.insertAdjacentElement('afterend',reset);
      reset.addEventListener('click',()=>{e.plan_amount.dataset.mortgageManual='0';sync(true)});
    }
    function sync(forceRate=false){
      if(!isMortgage()){
        e.plan_count.readOnly=false; e.balloon_payment.readOnly=false; reset.hidden=true;
        setLabel(e.plan_count,'Anzahl Zahlungen','');
        setLabel(e.balloon_payment,'Vertragliche Restschuld','z. B. Schlussrate beim Fahrzeug');
        return;
      }
      e.plan_count.readOnly=true; e.balloon_payment.readOnly=true; reset.hidden=false;
      setLabel(e.plan_count,'Raten bis Ende Zinsbindung','automatisch');
      setLabel(e.balloon_payment,'Voraussichtliche Restschuld bei Zinsbindungsende','automatisch berechnet');
      const calculated=autoRate();
      if(calculated>0&&(forceRate||e.plan_amount.dataset.mortgageManual!=='1')){
        e.plan_amount.dataset.settingMortgageRate='1'; e.plan_amount.value=money(calculated); e.plan_amount.dataset.settingMortgageRate='';
      }
      const count=countMonths(); if(count>0)e.plan_count.value=String(count);
      const opening=cents(e.opening_balance.value),rate=cents(e.plan_amount.value),interest=pct(e.interest_rate.value);
      const remaining=(count>0&&opening>0&&rate>0&&Number.isFinite(interest)&&interest>=0)?forecast(opening,rate,interest,count):0;
      e.balloon_payment.value=money(remaining);
      const box=document.querySelector('#credit-plan-check');
      if(box){
        box.className='notice wide suggestion';
        if(!count)box.textContent='Erste Rate und Ende der Zinsbindung festlegen.';
        else if(!rate)box.textContent='Ursprüngliche Darlehenssumme, Sollzins und Tilgungssatz festlegen; daraus wird die Monatsrate automatisch berechnet.';
        else{
          const manual=e.plan_amount.dataset.mortgageManual==='1',auto=autoRate();
          const note=manual&&auto>0?` · Rate manuell; automatisch wären ${eur(auto)}`:' · Rate aus Sollzins + Tilgung berechnet';
          box.textContent=`${count} Raten bis ${dateLabel(e.fixed_interest_until.value)} · voraussichtliche Restschuld ${eur(remaining)}${note}.`;
        }
      }
    }
    window.syncMortgagePlanV200=sync;
    e.plan_amount.addEventListener('input',()=>{if(isMortgage()&&e.plan_amount.dataset.settingMortgageRate!=='1'){e.plan_amount.dataset.mortgageManual='1';setTimeout(()=>sync(false),0)}},true);
    ['original_principal','opening_balance','interest_rate','repayment_rate','fixed_interest_until','plan_first_due'].forEach(name=>{
      e[name]?.addEventListener('input',()=>setTimeout(()=>sync(false),0));
      e[name]?.addEventListener('change',()=>setTimeout(()=>sync(false),0));
    });
    e.credit_type?.addEventListener('change',()=>setTimeout(()=>sync(false),0));
    document.addEventListener('click',ev=>{if(ev.target?.matches('[data-credit-form-tab]'))setTimeout(()=>sync(false),0)});
    sync(false);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bindMortgagePlanV200); else bindMortgagePlanV200();
})();
