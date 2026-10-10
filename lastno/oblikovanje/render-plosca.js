// Okno Render (skupno spletnemu FreeCAD-u in Oblikovanju): nastavitve, napredek, slika ali video, zgodovina.
// Strežnik (kateri koli od obeh) ponuja: POST /render, GET /render/stanje?id=, GET /render/seznam,
// GET /render/slika?id=, POST /render/ustavi. Render teče v ločenem procesu Blenderja (Cycles na grafični kartici).
//
// Uporaba:  import { odpriRender } from '/oblikovanje/render-plosca.js';
//           odpriRender({ zeton: () => ZETON, kamera: () => ({...}), premiki: () => ({...}), razmerje: () => 1.6 });

const OSVETLITVE = [
  ['studio', 'Studio (tri luči)'], ['mehka', 'Mehka svetloba'], ['soncni', 'Sončni zahod'],
  ['mesto', 'Mesto'], ['gozd', 'Gozd'], ['notranjost', 'Notranjost'], ['noc', 'Noč'],
];
const OZADJA = [['svetlo', 'Svetel preliv'], ['belo', 'Belo'], ['temno', 'Temno'], ['prozorno', 'Prozorno (PNG)'], ['okolje', 'Okolje (slika okolja)']];
const KAKOVOSTI = [['osnutek', 'Osnutek (hitro)'], ['dobro', 'Dobro'], ['najboljse', 'Najboljše (počasi)']];
const VELIKOSTI = [[1280, '1280 px'], [1920, '1920 px (Full HD)'], [2560, '2560 px'], [3840, '3840 px (4K)']];
const VRSTE = [['slika', 'Slika'], ['vrtenje', 'Vrtenje 360° (video)']];

const SLOG = `
#renderOkno { position: fixed; inset: 0; z-index: 60; display: flex; align-items: center; justify-content: center;
  background: rgba(15, 23, 42, .38); backdrop-filter: blur(2px); font: 13px system-ui, "Segoe UI", sans-serif; color: #1f2937; }
#renderOkno.skrit { display: none; }
#renderOkno .okno { width: min(1180px, 96vw); height: min(780px, 92vh); background: #fff; border-radius: 14px; display: flex;
  flex-direction: column; box-shadow: 0 24px 60px rgba(15, 23, 42, .28); overflow: hidden; }
#renderOkno header { display: flex; align-items: center; gap: 10px; padding: 12px 16px; border-bottom: 1px solid #e5e7eb; }
#renderOkno header b { font-size: 15px; }
#renderOkno header small { color: #6b7280; }
#renderOkno header .zapri { margin-left: auto; border: 0; background: none; font-size: 22px; cursor: pointer; color: #6b7280; line-height: 1; }
#renderOkno .vsebina { flex: 1 1 auto; display: flex; min-height: 0; }
#renderOkno .nastavitve { width: 250px; flex: none; padding: 14px 16px; border-right: 1px solid #e5e7eb; overflow: auto; display: flex; flex-direction: column; gap: 12px; }
#renderOkno label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: #4b5563; }
#renderOkno select { height: 32px; border: 1px solid #d1d5db; border-radius: 8px; padding: 0 8px; font: inherit; color: #111827; background: #fff; }
#renderOkno .gumbi { display: flex; gap: 8px; margin-top: 4px; }
#renderOkno button.glavni { flex: 1; height: 36px; border: 0; border-radius: 9px; background: #2563eb; color: #fff; font-weight: 600; cursor: pointer; font: inherit; font-weight: 600; }
#renderOkno button.glavni:disabled { opacity: .5; cursor: default; }
#renderOkno button.drugi { height: 36px; padding: 0 12px; border: 1px solid #d1d5db; border-radius: 9px; background: #fff; cursor: pointer; font: inherit; }
#renderOkno .opomba { font-size: 11.5px; color: #6b7280; line-height: 1.45; }
#renderOkno .prikaz { flex: 1 1 auto; display: flex; flex-direction: column; min-width: 0; background:
  repeating-conic-gradient(#f3f4f6 0 25%, #fff 0 50%) 0 0 / 18px 18px; }
#renderOkno .slika { flex: 1 1 auto; display: flex; align-items: center; justify-content: center; min-height: 0; padding: 14px; position: relative; }
#renderOkno .slika img, #renderOkno .slika video { max-width: 100%; max-height: 100%; border-radius: 6px; box-shadow: 0 4px 18px rgba(0,0,0,.12); }
#renderOkno .prazno { color: #6b7280; text-align: center; line-height: 1.6; background: rgba(255,255,255,.85); padding: 14px 18px; border-radius: 10px; }
#renderOkno .napredek { position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%); width: min(380px, 80%);
  background: rgba(255,255,255,.95); border-radius: 12px; padding: 14px 16px; box-shadow: 0 6px 24px rgba(0,0,0,.14); }
#renderOkno .napredek .trak { height: 8px; background: #e5e7eb; border-radius: 4px; overflow: hidden; margin: 8px 0 6px; }
#renderOkno .napredek .trak div { height: 100%; background: #2563eb; width: 0; transition: width .4s; }
#renderOkno .napredek small { color: #6b7280; }
#renderOkno .noga { display: flex; align-items: center; gap: 10px; padding: 8px 14px; border-top: 1px solid #e5e7eb; background: #fff; min-height: 46px; }
#renderOkno .noga .pot { color: #6b7280; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
#renderOkno .noga a { color: #2563eb; font-weight: 600; text-decoration: none; white-space: nowrap; }
#renderOkno .zgodovina { display: flex; gap: 6px; padding: 8px 14px; border-top: 1px solid #e5e7eb; background: #fafafa; overflow-x: auto; min-height: 64px; }
#renderOkno .zgodovina button { flex: none; width: 84px; height: 52px; padding: 0; border: 2px solid transparent; border-radius: 6px;
  background: #e5e7eb center / cover no-repeat; cursor: pointer; font-size: 10px; color: #374151; }
#renderOkno .zgodovina button.izbran { border-color: #2563eb; }
`;

let okno = null, moznosti = null, tekoci = null, prikazan = null, casovnik = 0;

function nalozi(kljuc, privzeto) { try { return localStorage.getItem('render.' + kljuc) || privzeto; } catch (e) { return privzeto; } }
function shrani(kljuc, v) { try { localStorage.setItem('render.' + kljuc, v); } catch (e) { /* zasebno okno */ } }

function izbirnik(ime, naslov, moznostiSeznam, privzeto) {
  const l = document.createElement('label');
  l.textContent = naslov;
  const s = document.createElement('select');
  s.name = ime;
  for (const [v, t] of moznostiSeznam) { const o = document.createElement('option'); o.value = v; o.textContent = t; s.appendChild(o); }
  s.value = nalozi(ime, String(privzeto));
  if (s.selectedIndex < 0) s.value = String(privzeto);
  s.addEventListener('change', () => shrani(ime, s.value));
  l.appendChild(s);
  return l;
}

function zgradi() {
  const slog = document.createElement('style'); slog.textContent = SLOG; document.head.appendChild(slog);
  okno = document.createElement('div'); okno.id = 'renderOkno'; okno.className = 'skrit';
  okno.innerHTML = `<div class="okno" role="dialog" aria-label="Render">
    <header><b>Render</b><small>Blender Cycles · fotorealistično, na grafični kartici</small><button type="button" class="zapri" title="Zapri (Esc)">×</button></header>
    <div class="vsebina">
      <div class="nastavitve"></div>
      <div class="prikaz"><div class="slika"><div class="prazno">Nastavi osvetlitev in ozadje, nato <b>Render</b>.<br>Kamera je trenutni pogled.</div></div>
        <div class="noga"><span class="pot"></span></div>
        <div class="zgodovina" title="Renderji te seje"></div></div>
    </div></div>`;
  const nast = okno.querySelector('.nastavitve');
  nast.append(izbirnik('osvetlitev', 'Osvetlitev', OSVETLITVE, 'studio'), izbirnik('ozadje', 'Ozadje', OZADJA, 'svetlo'),
    izbirnik('kakovost', 'Kakovost', KAKOVOSTI, 'dobro'), izbirnik('sirina', 'Širina slike', VELIKOSTI, 1920),
    izbirnik('vrsta', 'Vrsta', VRSTE, 'slika'));
  const gumbi = document.createElement('div'); gumbi.className = 'gumbi';
  gumbi.innerHTML = '<button type="button" class="glavni">Render</button><button type="button" class="drugi" disabled>Ustavi</button>';
  const opomba = document.createElement('div'); opomba.className = 'opomba';
  opomba.textContent = 'Slika ima razmerje trenutnega pogleda. Osnutek je pol manjši in hitrejši. Video ima 120 sličic (4 s) v polovični velikosti. Končani renderji se shranijo tudi v mapo Renderji ob datoteki.';
  nast.append(gumbi, opomba);
  okno.querySelector('.zapri').addEventListener('click', zapri);
  okno.addEventListener('click', e => { if (e.target === okno) zapri(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !okno.classList.contains('skrit')) { e.stopPropagation(); zapri(); } }, true);
  gumbi.querySelector('.glavni').addEventListener('click', zazeni);
  gumbi.querySelector('.drugi').addEventListener('click', ustavi);
  document.body.appendChild(okno);
}

const vrednost = ime => okno.querySelector(`select[name="${ime}"]`).value;

async function post(pot, telo) {
  const r = await fetch(pot, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Zeton': moznosti.zeton() }, body: JSON.stringify(telo || {}) });
  const d = await r.json().catch(() => ({}));
  if (!r.ok && !d.sporocilo) d.sporocilo = 'Strežnik je vrnil ' + r.status;
  return d;
}

async function zazeni() {
  const razmerje = Math.max(0.2, Math.min(5, (moznosti.razmerje && moznosti.razmerje()) || 1.6));
  const sirina = Number(vrednost('sirina'));
  const telo = {
    kamera: moznosti.kamera ? moznosti.kamera() : null,
    premiki: moznosti.premiki ? moznosti.premiki() : null,
    osvetlitev: vrednost('osvetlitev'), ozadje: vrednost('ozadje'), kakovost: vrednost('kakovost'),
    sirina, visina: Math.round(sirina / razmerje), vrtenje: vrednost('vrsta') === 'vrtenje' ? 120 : 0,
  };
  okno.querySelector('.glavni').disabled = true;
  const d = await post('/render', telo).catch(e => ({ sporocilo: e.message }));
  if (!d.id) { okno.querySelector('.glavni').disabled = false; pokaziNapako(d.sporocilo || 'Render se ni začel.'); return; }
  tekoci = d.id;
  okno.querySelector('.drugi').disabled = false;
  spremljaj();
}

async function ustavi() { if (tekoci) await post('/render/ustavi', { id: tekoci }).catch(() => {}); }

function pokaziNapako(besedilo) {
  const s = okno.querySelector('.slika');
  s.innerHTML = '<div class="prazno" style="color:#b91c1c"></div>';
  s.firstChild.textContent = besedilo;
}

async function spremljaj() {
  clearTimeout(casovnik);
  if (!tekoci) return;
  let s;
  try { s = await (await fetch('/render/stanje?id=' + encodeURIComponent(tekoci), { cache: 'no-store' })).json(); }
  catch (e) { casovnik = setTimeout(spremljaj, 1500); return; }
  if (s.stanje === 'caka' || s.stanje === 'tece') {
    const pl = okno.querySelector('.slika');
    let n = pl.querySelector('.napredek');
    if (!n) { n = document.createElement('div'); n.className = 'napredek'; n.innerHTML = '<b></b><div class="trak"><div></div></div><small></small>'; pl.appendChild(n); }
    n.querySelector('b').textContent = s.stanje === 'caka' ? 'Čaka v vrsti' : (s.sporocilo || 'Rišem …');
    n.querySelector('.trak div').style.width = Math.round((s.napredek || 0) * 100) + '%';
    n.querySelector('small').textContent = s.sirina + ' × ' + s.visina + ' px · ' + s.vzorci + ' vzorcev · ' + (s.cas || 0).toFixed(0) + ' s' + (s.naprava ? ' · ' + s.naprava : '');
    casovnik = setTimeout(spremljaj, 700);
    return;
  }
  tekoci = null;
  okno.querySelector('.glavni').disabled = false;
  okno.querySelector('.drugi').disabled = true;
  if (s.stanje === 'koncano') pokazi(s); else pokaziNapako((s.stanje === 'ustavljeno' ? 'Ustavljeno. ' : 'Render ni uspel: ') + (s.sporocilo || ''));
  osveziZgodovino();
}

function pokazi(s) {
  prikazan = s.id;
  const url = '/render/slika?id=' + encodeURIComponent(s.id);
  const pl = okno.querySelector('.slika');
  pl.innerHTML = s.video ? `<video src="${url}" controls autoplay loop muted playsinline></video>` : `<img src="${url}" alt="Render">`;
  const noga = okno.querySelector('.noga');
  noga.innerHTML = '<span class="pot"></span>';
  noga.querySelector('.pot').textContent = (s.shranjeno ? 'Shranjeno: ' + s.shranjeno : 'Shranjeno v začasno mapo renderjev')
    + ' · ' + s.sirina + ' × ' + s.visina + ' px, ' + (s.cas || 0).toFixed(1) + ' s';
  const a = document.createElement('a'); a.href = url; a.download = (s.ime || 'render') + (s.video ? '.mp4' : '.png'); a.textContent = 'Prenesi';
  noga.appendChild(a);
  for (const b of okno.querySelectorAll('.zgodovina button')) b.classList.toggle('izbran', b.dataset.id === s.id);
}

async function osveziZgodovino() {
  let seznam = [];
  try { seznam = await (await fetch('/render/seznam', { cache: 'no-store' })).json(); } catch (e) { return; }
  const z = okno.querySelector('.zgodovina'); z.innerHTML = '';
  for (const s of seznam.filter(x => x.stanje === 'koncano')) {
    const b = document.createElement('button'); b.type = 'button'; b.dataset.id = s.id;
    b.title = (s.ime || '') + ' · ' + s.sirina + ' × ' + s.visina + (s.video ? ' · video' : '');
    if (s.video) b.textContent = '▶ video'; else b.style.backgroundImage = `url("/render/slika?id=${encodeURIComponent(s.id)}")`;
    b.classList.toggle('izbran', s.id === prikazan);
    b.addEventListener('click', () => pokazi(s));
    z.appendChild(b);
  }
  const tece = seznam.find(x => x.stanje === 'tece' || x.stanje === 'caka');
  if (tece && !tekoci) { tekoci = tece.id; okno.querySelector('.glavni').disabled = true; okno.querySelector('.drugi').disabled = false; spremljaj(); }
}

export function odpriRender(m) {
  moznosti = m;
  if (!okno) zgradi();
  okno.classList.remove('skrit');
  osveziZgodovino();
}

export function zapri() { if (okno) okno.classList.add('skrit'); }
