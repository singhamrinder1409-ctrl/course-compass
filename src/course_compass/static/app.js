'use strict';
const $ = id => document.getElementById(id);
const make = (tag, text, className) => { const el = document.createElement(tag); if (text !== undefined) el.textContent = text; if (className) el.className = className; return el; };
let ready = false;
function showStatus(message, error = false) { $('empty-state').hidden = true; $('response').hidden = false; $('status').textContent = message; $('status').className = error ? 'error' : ''; }
function modeNote() { if ($('mode').value === 'examples') { $('mode-note').textContent = 'Saved examples are authored demonstrations, not live AI output. No paid API calls.'; return; } $('mode-note').textContent = $('mode').value === 'model' ? (ready ? 'AI answers use the retrieved excerpts. Always check citations against the official source.' : 'AI answers need server-side API credentials. Source excerpts are available now.') : 'Source excerpts work without an API key. Inspect the evidence and its original context.'; }
async function loadConfig() {
  try {
    const response = await fetch('/api/config'); if (!response.ok) throw new Error('Unable to load the course collection.');
    const config = await response.json(); ready = config.model_ready; $('edition').textContent = config.edition; $('course-list').replaceChildren();
    for (const course of config.courses) { const item = make('li'); item.append(make('strong', course.code.replace(/([A-Z]+)(\d)/, '$1 $2')), make('span', course.title)); $('course-list').append(item); }
    const suggestions = document.querySelector('.suggestions'); suggestions.replaceChildren();
    for (const question of config.examples) { const button = make('button', question); button.type = 'button'; button.addEventListener('click', () => { $('question').value = question; $('question').focus(); }); suggestions.append(button); }
    modeNote();
  } catch (error) { showStatus(error.message, true); }
}
function render(result) {
  $('result-title').textContent = result.mode === 'examples' && result.status === 'answer' ? 'Saved example · no live generation' : result.status === 'answer' ? 'An answer, with evidence' : result.status === 'evidence' ? 'From the calendar' : result.status === 'clarify' ? 'A little more detail' : result.status === 'abstain' ? 'Outside this collection' : 'Unable to generate an answer';
  $('result-meta').textContent = `${result.calendar_edition} · ${Math.round(result.latency_ms)} ms`;
  const message = result.message || 'Each statement below includes a source. Check the passages for the full context.';
  showStatus(message, result.status === 'error');
  const numbers = new Map(result.citations.map((c, i) => [c.id, i + 1]));
  for (const claim of result.claims) {
    const paragraph = make('p', claim.text, 'claim');
    for (const ref of claim.evidence) { const link = make('a', `[${numbers.get(ref.section_id)}]`, 'citation-ref'); link.href = `#source-${numbers.get(ref.section_id)}`; link.addEventListener('click', () => { $(`source-${numbers.get(ref.section_id)}`).open = true; }); paragraph.append(link); }
    $('claims').append(paragraph);
  }
  for (const citation of result.citations) {
    const details = make('details', undefined, 'source'); const number = numbers.get(citation.id); details.id = `source-${number}`; details.open = (result.status === 'evidence' || result.mode === 'examples') && number === 1;
    const summary = make('summary'); summary.append(make('strong', `[${number}] ${citation.course_code} `), make('span', ` / ${citation.label}`));
    const body = make('div', undefined, 'source-body'); body.append(make('pre', citation.text, 'excerpt'));
    for (const flag of citation.quality_flags) body.append(make('p', flag, 'source-note'));
    const link = make('a', 'Open official calendar ↗');
    const url = new URL(citation.source_url); if (url.protocol === 'https:' && url.hostname === 'www.uvic.ca') { link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer'; body.append(link); }
    details.append(summary, body); $('sources').append(details);
  }
}
$('ask-form').addEventListener('submit', async event => {
  event.preventDefault(); const question = $('question').value.trim(); if (!question) { $('question').focus(); return; }
  $('submit').disabled = true; $('result').setAttribute('aria-busy', 'true'); $('claims').replaceChildren(); $('sources').replaceChildren(); $('result-meta').textContent = ''; $('result-title').textContent = 'Finding the evidence…'; showStatus('Searching the course calendar…');
  const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), 55000);
  try {
    const response = await fetch('/api/ask', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question, mode: $('mode').value }), signal: controller.signal });
    const data = await response.json(); if (!data.status) throw new Error(data.error || 'The request failed. Please try again.'); render(data);
  } catch (error) { $('result-title').textContent = 'Something interrupted the search'; showStatus(error.name === 'AbortError' ? 'The request timed out. Try again or choose source excerpts.' : error.message, true); }
  finally { clearTimeout(timer); $('submit').disabled = false; $('result').setAttribute('aria-busy', 'false'); }
});
for (const button of document.querySelectorAll('[data-question]')) button.addEventListener('click', () => { $('question').value = button.dataset.question; $('question').focus(); });
$('mode').addEventListener('change', modeNote);
$('evaluation-toggle').addEventListener('click', async () => {
  const panel = $('evaluation-details'); panel.hidden = !panel.hidden; $('evaluation-toggle').setAttribute('aria-expanded', String(!panel.hidden)); if (panel.hidden) return;
  panel.replaceChildren(make('p', 'Loading evaluation…'));
  try {
    const response = await fetch('/api/evaluation'); if (!response.ok) throw new Error('Unable to load evaluation.'); const data = await response.json(); panel.replaceChildren();
    if (!data.available) { panel.append(make('p', 'No evaluation report yet.')); return; }
    const report = data.report; panel.append(make('p', `${report.question_count} frozen questions · ${report.answerable_count} answerable`));
    for (const method of report.retrieval) { const row = make('div', undefined, 'metric'); row.append(make('span', method.name), make('strong', `${Math.round(method.all_evidence_hit_rate * 100)}% at k=${report.k}`)); panel.append(row); }
    panel.append(make('p', 'Percentages measure whether all labeled evidence appears in the retrieved passages. They do not measure answer accuracy.'));
    panel.append(make('p', `Local unsupported-question checks: ${report.behavior.abstain.correct_status}/${report.behavior.abstain.count} abstained. Other cases returned excerpts; they were not generated answers.`));
    panel.append(make('p', `Ambiguous questions: ${report.behavior.clarify.correct_status}/${report.behavior.clarify.count} requested clarification.`));
    panel.append(make('p', report.model_evaluation.note)); panel.append(make('p', 'Small six-course sample. No search settings were tuned after this test set was frozen.'));
  } catch (error) { panel.replaceChildren(make('p', error.message)); }
});
loadConfig();
