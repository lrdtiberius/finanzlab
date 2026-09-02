
// Credit archive extension (v0.13.5)
const _baseRenderCredits=renderCredits;
renderCredits=function(){
  const all=[...(state.credits||[]),...(state.archivedCredits||[])];
  const active=(state.credits||[]).filter(item=>!item.archived);
  const archived=(state.archivedCredits||[]).filter(item=>item.archived);
  const types=['consumer_credit','credit','borrowed'];
  const groups=types.map(type=>{const credits=active.filter(item=>item.credit_type===type);return {credit_type:type,count:credits.length,balance_cents:credits.reduce((sum,item)=>sum+Number(item.remaining_balance_cents||0),0)}});
  const filters=[['all','Alle'],...types.map(type=>[type,creditTypeLabels[type]]),['archive','Archiv']];
  let filtered,activeLabel;
  if(state.creditFilter==='archive'){filtered=archived;activeLabel='Archiv';}
  else {filtered=state.creditFilter==='all'?active:active.filter(item=>item.credit_type===state.creditFilter);activeLabel=state.creditFilter==='all'?'Alle Kredite':creditTypeLabels[state.creditFilter];}
  $('#credit-page-summary').innerHTML=groups.map(creditSummaryCard).join('');
  $('#credit-list-title').textContent=state.creditFilter==='archive'?'Archivierte Kredite':activeLabel;
  $('#credit-filter').innerHTML=filters.map(([value,label])=>{const count=value==='archive'?archived.length:value==='all'?active.length:groups.find(group=>group.credit_type===value).count,selected=state.creditFilter===value;return `<button class="credit-filter-button ${selected?'active':''}" type="button" data-credit-filter="${value}" aria-pressed="${selected}">${escapeHtml(label)} <span>${count}</span></button>`}).join('');
  $('#credit-list').innerHTML=filtered.length?filtered.map(item=>`<article class="credit-row ${item.archived?'inactive':''}" data-open-credit="${escapeHtml(item.id)}"><div><span class="credit-type-badge">${escapeHtml(creditTypeLabels[item.credit_type])}</span><h3>${escapeHtml(item.name)}</h3><small>Ausgang ${eur(item.opening_balance_cents)} · getilgt ${eur(item.paid_cents)}${item.archived?` · archiviert${item.archive_reason==='paid'?' (abbezahlt)':' (manuell)'}`:''}</small></div><strong>${eur(item.remaining_balance_cents)}</strong><small>${item.archived?'Saldo bei Archivierung':'offener Saldo'}</small><label class="account-choice" onclick="event.stopPropagation()"><input type="checkbox" data-credit-archive="${escapeHtml(item.id)}" ${item.archived?'checked':''}> Archiviert</label><button class="link-button" type="button" data-edit-credit="${escapeHtml(item.id)}">Bearbeiten</button></article>`).join(''):`<p class="empty">${state.creditFilter==='archive'?'Noch keine archivierten Kredite vorhanden.':state.creditFilter==='all'?'Noch kein aktiver Kredit angelegt.':`Keine aktiven Kredite der Art „${escapeHtml(activeLabel)}“ vorhanden.`}</p>`;
};

const _baseLoadAll=loadAll;
loadAll=async function(){
  const query=`household_id=${encodeURIComponent(state.currentId)}&as_of=${encodeURIComponent(state.asOf)}`,managementQuery=`household_id=${encodeURIComponent(state.currentId)}&as_of=${encodeURIComponent(today())}`;
  const [dashboard,incomes,expenses,transfers,credits,diagnostics]=await Promise.all([api(`/api/dashboard?${query}`),api(`/api/cash-flows?${managementQuery}&kind=income`),api(`/api/cash-flows?${managementQuery}&kind=expense`),api(`/api/transfers?household_id=${encodeURIComponent(state.currentId)}`),api(`/api/credits?household_id=${encodeURIComponent(state.currentId)}&as_of=${encodeURIComponent(today())}`),api(`/api/diagnostics?${query}`)]);
  state.dashboard=dashboard;state.incomes=incomes.items;state.expenses=expenses.items;state.transfers=transfers.items;state.credits=credits.items||[];state.archivedCredits=credits.archived_items||[];state.diagnostics=diagnostics;ensureSelections();renderAll();await loadPreview();
};

const _baseEnsureSelections=ensureSelections;
ensureSelections=function(){
  const ids=state.dashboard.household.accounts.map(account=>account.id),valid=new Set(ids);state.previewAccountIds=state.previewAccountIds.filter(id=>valid.has(id));if(!state.previewAccountIds.length)state.previewAccountIds=[...ids];
  const creditIds=(state.credits||[]).filter(item=>!item.archived).map(credit=>credit.id),validCredits=new Set(creditIds);state.previewCreditIds=state.previewCreditIds.filter(id=>validCredits.has(id));
};

renderCreditSelectors=function(){
  const target=$('#preview-credit-selectors');
  const credits=(state.credits||[]).filter(item=>!item.archived);
  target.innerHTML=credits.length?credits.map(credit=>`<label class="account-choice credit-choice"><input type="checkbox" data-preview-credit="${escapeHtml(credit.id)}" ${state.previewCreditIds.includes(credit.id)?'checked':''}> ${escapeHtml(credit.name)}</label>`).join(''):'<p class="empty">Keine aktiven Kredite vorhanden.</p>';
};

document.addEventListener('change',async event=>{
  const input=event.target.closest('[data-credit-archive]');
  if(!input)return;
  event.stopPropagation();
  try{
    await api(`/api/credits/${encodeURIComponent(input.dataset.creditArchive)}/archive`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({household_id:state.currentId,archived:input.checked})});
    toast(input.checked?'Kredit archiviert.':'Kredit reaktiviert.');
    await loadAll();
  }catch(error){input.checked=!input.checked;toast(error.message);}
});
