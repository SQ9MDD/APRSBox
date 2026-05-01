# GUI UI Style Guide Template

Ten dokument jest szablonem prywatnego stylu GUI dla kolejnych aplikacji. Bazuje na estetyce operacyjnej konsoli: gęsty, techniczny interfejs, szybki odczyt statusu, czytelne panele, tabele i formularze. Nie zakłada konkretnego frameworka. Przy użyciu w nowym projekcie dopasuj nazwy klas, ścieżki ikon i mechanizmy routingu do realnej architektury aplikacji.

## 0. Jak używać tego szablonu

- Traktuj dokument jako domyślny kierunek UI, nie jako zamknięty design system.
- Najpierw sprawdź istniejący kod projektu. Jeśli projekt ma już własne komponenty, tokeny lub helpery, używaj ich zamiast kopiować nazwy 1:1.
- Zachowuj filozofię, proporcje, hierarchię, spacing, semantykę kolorów i zachowanie responsywne.
- Nazwy klas w przykładach są rekomendowanym słownikiem startowym. W istniejącym projekcie można je zmapować na lokalne odpowiedniki.
- Elementy oznaczone jako `do decyzji` wymagają świadomego wyboru przy starcie nowej aplikacji.

## 1. Ogólna filozofia wyglądu

GUI ma być operacyjną konsolą roboczą: spokojną, gęstą, techniczną i nastawioną na skuteczne wykonanie zadań. Użytkownik ma szybko widzieć, co jest ważne, co wymaga reakcji i gdzie wykonać następną akcję.

Preferuj:

- kompaktowe widoki robocze zamiast marketingowych układów,
- lewy sidebar, lokalne nagłówki sekcji i panele jako podstawę struktury,
- tabele, listy i formularze jako główne powierzchnie pracy,
- małe i średnie rozmiary tekstu,
- ciemny motyw jako domyślny lub pełnoprawny pierwszy motyw,
- subtelne tła, ramki, cienie i focus ringi,
- jeden główny kolor akcentu oraz stałą semantykę statusów,
- krótkie, operacyjne opisy pomocnicze,
- ikony tylko tam, gdzie realnie przyspieszają rozpoznanie akcji.

Unikaj:

- dużych hero sekcji w aplikacjach narzędziowych,
- dekoracyjnych kart bez funkcji,
- przypadkowych kolorów,
- dużych pustych przestrzeni,
- mieszania kilku stylów komponentów w jednym ekranie.

## 2. Layout aplikacji

Domyślny shell aplikacji:

- `body` bez marginesu, pełna wysokość viewportu,
- `.app-shell` jako kontener całej aplikacji,
- `.sidebar` po lewej stronie,
- `.main-area` jako obszar roboczy,
- `.content` jako pionowy stack ekranów, paneli i sekcji.

Rekomendowany układ desktop:

```html
<body class="app-shell">
    <aside class="sidebar">...</aside>
    <div class="main-area">
        <main class="content">...</main>
    </div>
</body>
```

Rekomendowane proporcje:

- sidebar: `240px`-`260px`; domyślnie `248px`,
- padding głównej treści: ok. `0.9rem`,
- odstęp między panelami: ok. `0.9rem`,
- panele na całą dostępną szerokość, bez dekoracyjnego centrowania małych kart.

Podstawowy rytm strony:

- ekran składaj z kolejnych `section.panel`,
- wewnątrz panelu stosuj `.panel-body`,
- nagłówek sekcji buduj jako `.panel-header > .panel-header-copy`,
- opis pod tytułem dawaj jako `.section-lead`,
- większe widoki dziel siatkami: `.grid.two`, `.overview-grid`, `.detail-grid` lub lokalnymi odpowiednikami.

## 3. Sidebar

Sidebar jest główną nawigacją i miejscem podstawowego kontekstu aplikacji.

Zalecana struktura:

- `.brand` z ikoną/logo i nazwą aplikacji,
- opcjonalny krótki opis produktu lub środowiska,
- `.sidebar-user-panel` dla użytkownika, roli, przełącznika motywu i wylogowania,
- opcjonalny mały blok statusowy, np. zegar, środowisko, tenant, połączenie,
- `.nav-list` z `.nav-link`,
- `.nav-separator` do logicznego grupowania,
- `.sidebar-footer` z wersją, środowiskiem albo krótkim metadanym.

Styl pozycji menu:

- pozycja ma ikonę i etykietę,
- aktywna pozycja ma delikatne tło akcentowe, wyraźniejszy tekst i subtelną ramkę,
- hover może minimalnie przesuwać element lub zmieniać tło,
- statusy w nawigacji, np. nieprzeczytane, używają koloru warning,
- disabled lub niedostępne pozycje są przygaszone, nieusuwane z layoutu bez powodu.

Rekomendacja implementacyjna:

- trzymaj definicję nawigacji w jednym miejscu,
- każda pozycja powinna mieć `key`, `label`, `href`, `icon`, opcjonalnie `roles` i `badge`,
- aktywną pozycję ustawiaj przez jawny klucz, nie przez zgadywanie z URL.

## 4. Topbar i nagłówki ekranów

Domyślny styl nie wymaga globalnego topbara. Preferowany wzorzec to lokalny nagłówek w panelu albo toolbar w danym widoku.

Używaj:

- `.panel-header` dla tytułu sekcji i akcji,
- `.toolbar-inline` dla lokalnych filtrów, przełączników i akcji narzędziowych,
- `.page-header` tylko jeśli ekran potrzebuje nagłówka ponad kilkoma panelami.

Przykład:

```html
<div class="panel-header">
    <div class="panel-header-copy">
        <h2>Users</h2>
        <p class="section-lead">Manage accounts, roles and access state.</p>
    </div>
    <div class="toolbar-actions">
        <button class="button button-secondary" type="button">Refresh</button>
        <button class="button" type="button">Create</button>
    </div>
</div>
```

Do decyzji przy nowej aplikacji:

- czy ma istnieć globalny topbar,
- czy sidebar na mobile ma pozostać blokiem u góry, czy przejść w drawer,
- czy tytuł aktualnej strony ma być globalny, czy lokalny w pierwszym panelu.

## 5. Kolory i semantyka kolorów

Projekt powinien mieć tokeny kolorów dla ciemnego i jasnego motywu. Tokeny mogą być CSS variables, theme objectem albo stałymi komponentów.

Minimalny zestaw tokenów:

```css
:root {
    --font-ui: "Space Grotesk", "Segoe UI", sans-serif;
    --font-mono: "SFMono-Regular", "SF Mono", "Consolas", monospace;
    --radius: 12px;
    --radius-md: 10px;
    --radius-sm: 8px;
    --sidebar-width: 248px;
    --control-height: 2.42rem;
    --icon-control-size: 1.88rem;
    --space-1: 0.3rem;
    --space-2: 0.47rem;
    --space-3: 0.66rem;
    --space-4: 0.89rem;
    --space-5: 1.13rem;
    --space-6: 1.45rem;
}

:root[data-theme="dark"] {
    --bg: #0f1311;
    --bg-layer: #141a17;
    --sidebar: rgba(16, 21, 18, 0.92);
    --panel: rgba(24, 31, 27, 0.96);
    --panel-alt: #1c2420;
    --panel-soft: #202923;
    --panel-emphasis: #253029;
    --border: #2f3d36;
    --text: #cdd6cf;
    --muted: #8d998f;
    --accent: #6dbd80;
    --accent-strong: #4e9f63;
    --accent-soft: rgba(109, 189, 128, 0.12);
    --focus-ring: rgba(109, 189, 128, 0.18);
    --danger: #c97a7a;
    --success: #8bcf9b;
    --warning: #d9b565;
}

:root[data-theme="light"] {
    --bg: #d9e0d7;
    --bg-layer: #eef2ed;
    --sidebar: rgba(228, 235, 229, 0.94);
    --panel: rgba(241, 245, 241, 0.98);
    --panel-alt: #e2e9e1;
    --panel-soft: #d8e0d8;
    --panel-emphasis: #d5ddd4;
    --border: #b9c5bb;
    --text: #27312a;
    --muted: #5f6c61;
    --accent: #2f7a45;
    --accent-strong: #215e34;
    --accent-soft: rgba(47, 122, 69, 0.1);
    --focus-ring: rgba(47, 122, 69, 0.16);
    --danger: #a95d5d;
    --success: #3b7a4d;
    --warning: #8f6b1d;
}
```

Semantyka:

- `accent`: podstawowa akcja, aktywna nawigacja, focus, wybór,
- `success`: OK, aktywne, zakończone powodzeniem,
- `warning`: wymaga uwagi, stan niepełny, nieznany, opóźniony,
- `danger`: błąd, disabled krytyczne, usuwanie, operacje destrukcyjne,
- `muted`: opis, metadane, mniej ważny tekst,
- lokalne kolory danych są dopuszczalne tylko dla stabilnych kategorii domenowych.

## 6. Typografia

Domyślna typografia jest kompaktowa.

Rekomendowane wartości:

- font UI: `"Space Grotesk", "Segoe UI", sans-serif`,
- font mono: `"SFMono-Regular", "SF Mono", "Consolas", monospace`,
- body: `12.75px`, `line-height: 1.42`,
- tytuł strony: `1.15rem`-`1.25rem`, `font-weight: 600`,
- tytuł panelu: `0.92rem`-`1rem`, `font-weight: 600`,
- label formularza: ok. `0.82rem`, kolor `muted`,
- opis pomocniczy: ok. `0.82rem`-`0.85rem`, kolor `muted`,
- tabela: `0.78rem`-`0.83rem`,
- badge/status: `0.7rem`-`0.76rem`.

Zasady:

- nie używaj hero-scale type wewnątrz paneli,
- większe liczby rezerwuj dla KPI i ekranów diagnostycznych,
- dane techniczne, logi, identyfikatory i payloady pokazuj fontem mono,
- długie wartości muszą mieć ellipsis albo kontrolowane zawijanie.

## 7. Spacing i rytm interfejsu

Używaj stałej skali spacingu:

- `--space-1: 0.3rem`,
- `--space-2: 0.47rem`,
- `--space-3: 0.66rem`,
- `--space-4: 0.89rem`,
- `--space-5: 1.13rem`,
- `--space-6: 1.45rem`.

Zasady:

- między panelami stosuj `--space-4`,
- wewnątrz panelu stosuj `--space-4`,
- w formularzach i zwartych grupach stosuj `--space-3`,
- w toolbarach stosuj `--space-2` albo `--space-3`,
- małe relacje etykieta-wartość mogą używać wartości poniżej `--space-1`,
- preferuj `gap` w grid/flex zamiast ręcznych marginesów.

## 8. Karty, panele i sekcje

Podstawowy panel:

- tło `panel`,
- ramka `border`,
- promień `radius`,
- subtelny cień albo wewnętrzny highlight,
- padding ok. `--space-4`,
- zawartość jako grid z `gap`.

Rekomendowane klasy:

- `.panel`: podstawowa obudowa sekcji,
- `.panel-body`: układ zawartości,
- `.panel-header`: tytuł i akcje,
- `.panel-header-copy`: tytuł i opis,
- `.metric-card`: mała karta KPI,
- `.detail-card`: karta szczegółów,
- `.status-card`: karta stanu,
- `.danger-zone-panel`: panel operacji destrukcyjnych.

Zasady:

- panel jest kontenerem logicznej sekcji, nie dekoracją,
- nie zagnieżdżaj dużych paneli w panelach,
- małe karty w panelu są dopuszczalne, gdy reprezentują powtarzalne elementy albo KPI,
- semantyczne karty mogą używać delikatnego tła statusowego lub border-left.

## 9. Formularze

Podstawowe układy:

- `.form-grid`: dwie kolumny na desktopie,
- `.form-stack`: jedna kolumna,
- `.form-actions`: przyciski formularza,
- `.field-inline-actions`: pole i akcja w jednym rzędzie,
- `.checkbox-row`: checkbox albo toggle z etykietą.

Kontrolki:

- wszystkie kontrolki mają ten sam font co UI,
- wysokość kontrolki ok. `2.42rem`,
- radius `--radius-sm`,
- tło `panel-alt`,
- ramka `border`,
- hover podbija tło i ramkę,
- focus używa ringa z koloru akcentu,
- disabled jest przygaszony i ma `cursor: not-allowed`,
- textarea ma sensowne `min-height` i `resize: vertical`.

Walidacja:

- błąd przy polu: `.field-validation-error`,
- błąd całego formularza: `.alert.alert-error` albo lokalny odpowiednik,
- sukces: `.alert.alert-success`,
- opis pola: krótki, spokojny, kolor `muted`,
- wymagane pola oznaczaj konsekwentnie, ale bez agresywnych czerwonych znaczników, dopóki nie ma błędu.

## 10. Tabele

Tabele są podstawowym widokiem danych.

Wzorzec:

```html
<div class="table-wrap">
    <table class="data-table compact-table">
        <thead>
            <tr>
                <th>Name</th>
                <th>Status</th>
                <th>Actions</th>
            </tr>
        </thead>
        <tbody>...</tbody>
    </table>
</div>
```

Zasady:

- zawsze owijaj tabele w `.table-wrap`,
- domyślnie stosuj kompaktowy wariant,
- nagłówki są krótkie i stabilne,
- komórki są jednowierszowe z ellipsis, jeśli dane mają stałą strukturę,
- komentarze, logi i payloady jawnie zawijaj przez `overflow-wrap: anywhere`,
- akcje w wierszu trzymaj po prawej stronie albo w ostatniej kolumnie,
- ikony akcji w tabeli muszą mieć `title` i `aria-label`,
- sortowanie powinno mieć widoczny stan aktywny i kierunek.

## 11. Przyciski

Typy:

- `.button`: primary, główna akcja,
- `.button-secondary`: akcja pomocnicza,
- `.button-danger`: operacja destrukcyjna,
- `.button-icon`: przycisk ikonowy poza tabelą,
- `.table-icon-button`: przycisk ikonowy w tabeli,
- `.link-button`: link stylowany jak neutralna akcja, jeśli projekt tego potrzebuje.

Zasady:

- primary używaj oszczędnie, zwykle jeden główny przycisk na formularz albo sekcję,
- secondary używaj do anulowania, przejścia, filtrowania i akcji pobocznych,
- danger wymaga jednoznacznej etykiety, często potwierdzenia i czerwonej semantyki,
- icon-only wymaga `aria-label` i `title`,
- disabled nie może wyglądać jak aktywny hover.

## 12. Ikony

Domyślnie używaj lokalnych SVG albo istniejącej biblioteki ikon projektu. Nie dodawaj nowej biblioteki tylko dla kilku ikon.

Zasady:

- ikony w sidebarze: ok. `16px`,
- ikony w przyciskach: ok. `0.9rem`,
- ikony statusowe mogą być w okrągłych/pillowych kontenerach,
- ikony dekoracyjne mają `alt=""`,
- ikony akcji mają dostępny opis przez przycisk,
- zachowuj jeden styl ikon w całej aplikacji.

Do decyzji:

- źródło ikon w nowym projekcie,
- czy ikony mają być filtrowane przez CSS, czy dostarczone w wariantach kolorystycznych,
- czy domenowe ikony bitmapowe wymagają `image-rendering: pixelated`.

## 13. Komunikaty, alerty i statusy

Alerty:

- `alert-error`: błąd lub operacja nieudana,
- `alert-success`: zapisano, wykonano, zakończono powodzeniem,
- `alert-warning`: działanie możliwe, ale ryzykowne albo niepełne,
- `alert-info`: neutralna informacja operacyjna.

Statusy inline:

- `.status-pill`: tekstowy status w tabelach i kartach,
- `.status-running` albo `.status-success`: OK/aktywny,
- `.status-stopped` albo `.status-danger`: błąd/wyłączony,
- `.status-unknown` albo `.status-warning`: nieznany/wymaga uwagi,
- `.notice`: krótka neutralna informacja.

Zasady:

- kolor statusu musi wynikać z semantyki, nie z preferencji wizualnej,
- alerty pisz krótko i konkretnie,
- nie mieszaj kilku typów alertów w jednym miejscu bez hierarchii.

## 14. Loading states

Typowe stany:

- mały spinner inline,
- busy button,
- skeleton tylko tam, gdzie ładowana jest znana struktura,
- modal postępu dla długiej operacji blokującej,
- empty/loading placeholder dla list i tabel.

Zasady:

- krótka akcja: busy button,
- pobieranie listy: loading row albo empty-like panel,
- długa operacja: modal z tytułem, opisem i ewentualnym logiem,
- loading nie może przesuwać layoutu bardziej niż konieczne,
- po błędzie pokaż alert i możliwość ponowienia, jeśli ma sens.

## 15. Empty states

Pusty stan jest informacyjny, nie dekoracyjny.

Wzorzec:

- `.empty-state`,
- dashed border,
- tło `panel-alt`,
- krótki tekst,
- opcjonalna akcja secondary albo primary, jeśli użytkownik może coś zrobić.

Treść:

- powiedz, czego nie ma,
- jeśli istnieje następny krok, nazwij go,
- nie dodawaj długich instrukcji ani ilustracji w aplikacji operacyjnej.

## 16. Responsywność

Domyślne breakpointy:

- `1180px`: szerokie dashboardy przechodzą na jedną kolumnę,
- `980px`: shell może przejść w kolumnę, sidebar staje się górnym blokiem albo drawerem,
- `720px`: większość gridów przechodzi na jedną kolumnę,
- `640px`: inline actions przechodzą pod pola.

Zasady:

- każdy nowy grid musi mieć zachowanie mobilne,
- tabele przewijają się poziomo w `.table-wrap`,
- toolbary mogą się zawijać,
- formularze na mobile są jednokolumnowe,
- przyciski nie mogą mieć tekstu wychodzącego poza kontener,
- nie skaluj fontów liniowo z viewportem.

## 17. Konwencje nazewnicze

Rekomendacja:

- klasy CSS: kebab-case,
- komponenty/partial templates: rzeczownikowe nazwy domenowe,
- warianty: sufiksy semantyczne, np. `-success`, `-warning`, `-danger`, `-active`,
- stany JS: `is-active`, `is-open`, `is-loading`, `is-disabled`,
- data attributes: `data-*` dla hooków JS, nie dla stylu podstawowego.

Unikaj:

- nazw zależnych od koloru, np. `green-card`, jeśli znaczenie to `success`,
- mieszania kilku konwencji w jednym ekranie,
- nazw klas opisujących jednorazowe położenie zamiast funkcji.

## 18. Czego unikać

- Nie dodawaj nowych frameworków CSS bez potrzeby.
- Nie twórz landing page jako pierwszego widoku aplikacji narzędziowej.
- Nie dodawaj globalnego topbara, jeśli lokalne nagłówki wystarczą.
- Nie używaj losowych kolorów poza stabilnymi kategoriami danych.
- Nie usuwaj przewijania poziomego z tabel.
- Nie zwiększaj drastycznie rozmiaru tekstu.
- Nie zastępuj istniejących komponentów lokalnymi duplikatami.
- Nie zmieniaj semantyki statusów między ekranami.
- Nie ukrywaj operacji destrukcyjnych jako neutralnych akcji.
- Nie zostawiaj stanów pustych, loading ani błędów bez obsługi.

## 19. Checklista dla nowych ekranów

- Czy ekran używa głównego shell layoutu aplikacji?
- Czy aktywna nawigacja jest ustawiana jawnie?
- Czy pierwszy panel jasno mówi, czego dotyczy widok?
- Czy nagłówek ma tytuł, opcjonalny opis i akcje w przewidywalnym miejscu?
- Czy formularze używają wspólnego układu i kontrolek?
- Czy tabele są w `.table-wrap` i mają stabilne kolumny?
- Czy akcje używają właściwego typu przycisku?
- Czy statusy mają poprawną semantykę kolorów?
- Czy empty, loading, success i error states są obsłużone?
- Czy widok działa przy `980px`, `720px` i `640px`?
- Czy ikony mają poprawną dostępność?
- Czy teksty są gotowe na lokalizację, jeśli projekt jej używa?

## 20. Checklista code review GUI

- Czy zmiana nie modyfikuje globalnych tokenów bez potrzeby?
- Czy nowe klasy nie duplikują istniejących wzorców?
- Czy spacing używa ustalonej skali?
- Czy kolory pochodzą z tokenów albo mają domenowe uzasadnienie?
- Czy tabela ma przewijanie poziome i sensowne szerokości?
- Czy długie wartości mają ellipsis albo kontrolowane zawijanie?
- Czy formularz ma czytelne labelki, disabled states i focus states?
- Czy operacje destrukcyjne są wizualnie danger i mają potwierdzenie, jeśli dotyczy?
- Czy mobile nie powoduje nakładania tekstów, toolbarów ani akcji?
- Czy role i uprawnienia nie pokazują niespójnych akcji?
- Czy ciemny i jasny motyw są spójne?
- Czy zmiana nie wprowadza martwych klas ani nieużywanych komponentów?

## 21. Minimalny szablon strony

Ten przykład jest neutralny technologicznie. Zamień składnię templatingu, routing i tłumaczenia na mechanizmy projektu.

```html
<section class="panel">
    <div class="panel-body">
        <div class="panel-header">
            <div class="panel-header-copy">
                <h2>Records</h2>
                <p class="section-lead">Manage records, status and operational actions.</p>
            </div>
            <div class="toolbar-actions">
                <button type="button" class="button button-secondary">Refresh</button>
                <button type="button" class="button">Create</button>
            </div>
        </div>

        <div class="alert alert-success" hidden>Saved successfully.</div>

        <div class="table-wrap">
            <table class="data-table compact-table">
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Status</th>
                        <th>Updated</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td>Primary record</td>
                        <td><span class="status-pill status-running">Active</span></td>
                        <td><span class="muted">2026-04-25 12:00</span></td>
                        <td>
                            <div class="table-actions">
                                <button type="button" class="table-icon-button" title="Edit" aria-label="Edit Primary record">
                                    <img src="/static/icons/edit.svg" alt="">
                                </button>
                                <button type="button" class="table-icon-button table-icon-button-danger" title="Delete" aria-label="Delete Primary record">
                                    <img src="/static/icons/delete.svg" alt="">
                                </button>
                            </div>
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>

        <div class="empty-state muted" hidden>No records yet.</div>
    </div>
</section>
```

## 22. Minimalny szablon formularza

```html
<section class="panel">
    <div class="panel-body">
        <div class="panel-header">
            <div class="panel-header-copy">
                <h2>Edit Record</h2>
                <p class="section-lead">Update the core fields and save changes.</p>
            </div>
        </div>

        <form method="post" class="form-grid">
            <label>
                <span>Name</span>
                <input type="text" name="name" required>
            </label>

            <label>
                <span>Type</span>
                <select name="type" required>
                    <option value="">Select type</option>
                </select>
            </label>

            <label class="full">
                <span>Description</span>
                <textarea name="description"></textarea>
            </label>

            <label class="checkbox-row">
                <input type="checkbox" name="enabled" value="1">
                <span>Enabled</span>
            </label>

            <div class="form-actions">
                <button type="submit" class="button">Save Changes</button>
                <a href="/records" class="button button-secondary">Cancel</a>
            </div>
        </form>
    </div>
</section>
```

## 23. Minimalny CSS startowy

Ten fragment jest punktem startowym dla nowej aplikacji, jeśli nie ma jeszcze własnego UI. W istniejącym projekcie najpierw mapuj na obecne tokeny.

```css
* {
    box-sizing: border-box;
}

html,
body {
    min-height: 100%;
}

body {
    margin: 0;
    font-family: var(--font-ui);
    font-size: 12.75px;
    line-height: 1.42;
    background: linear-gradient(180deg, var(--bg) 0%, var(--bg-layer) 100%);
    color: var(--text);
}

.app-shell {
    display: flex;
    min-height: 100vh;
}

.sidebar {
    width: var(--sidebar-width);
    background: var(--sidebar);
    border-right: 1px solid var(--border);
    padding: var(--space-5);
}

.main-area {
    flex: 1;
    min-width: 0;
}

.content {
    padding: var(--space-4);
    display: grid;
    gap: var(--space-4);
}

.panel {
    padding: var(--space-4);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--panel);
}

.panel-body,
.form-stack {
    display: grid;
    gap: var(--space-4);
}

.panel-header,
.toolbar-inline {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--space-4);
    flex-wrap: wrap;
}

.panel-header-copy {
    display: grid;
    gap: var(--space-1);
    min-width: 0;
}

.panel-header h2,
.panel-header p {
    margin: 0;
}

.section-lead,
.muted {
    color: var(--muted);
}

.form-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-3);
}

.form-grid .full,
.form-actions,
.alert,
.table-wrap {
    grid-column: 1 / -1;
}

label {
    display: grid;
    gap: 0.34rem;
    color: var(--muted);
    font-size: 0.82rem;
}

input,
textarea,
select,
button {
    font: inherit;
}

input,
textarea,
select {
    width: 100%;
    min-height: var(--control-height);
    padding: 0.58rem 0.72rem;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border);
    background: var(--panel-alt);
    color: var(--text);
}

input:hover,
textarea:hover,
select:hover {
    border-color: var(--accent);
    background: var(--panel-emphasis);
}

input:focus,
textarea:focus,
select:focus {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--focus-ring);
}

input:disabled,
textarea:disabled,
select:disabled {
    cursor: not-allowed;
    opacity: 0.68;
}

.checkbox-row {
    display: flex;
    flex-direction: row;
    align-items: center;
    gap: 0.5rem;
    color: var(--text);
}

.checkbox-row input {
    width: auto;
    min-height: auto;
    margin: 0;
    accent-color: var(--accent);
}

.button,
.button-secondary {
    min-height: var(--control-height);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.4rem;
    border-radius: var(--radius-sm);
    cursor: pointer;
    text-decoration: none;
}

.button {
    border: 0;
    background: linear-gradient(180deg, var(--accent), var(--accent-strong));
    color: #0f1712;
    font-weight: 600;
}

.button-secondary {
    border: 1px solid var(--border);
    background: var(--panel-alt);
    color: var(--text);
}

.button-danger {
    border-color: rgba(201, 122, 122, 0.35);
    color: var(--danger);
}

.button:focus-visible,
.button-secondary:focus-visible,
.table-icon-button:focus-visible {
    outline: none;
    box-shadow: 0 0 0 3px var(--focus-ring);
}

.button:disabled,
.button-secondary:disabled,
.table-icon-button:disabled {
    cursor: not-allowed;
    opacity: 0.58;
}

.form-actions,
.toolbar-actions,
.table-actions {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    flex-wrap: wrap;
}

.table-wrap {
    overflow-x: auto;
    width: 100%;
    border-radius: var(--radius-sm);
}

.table-icon-button {
    width: var(--icon-control-size);
    min-width: var(--icon-control-size);
    height: var(--icon-control-size);
    min-height: var(--icon-control-size);
    padding: 0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border);
    background: var(--panel-soft);
    cursor: pointer;
}

.table-icon-button img {
    width: 0.9rem;
    height: 0.9rem;
}

.table-icon-button-danger {
    border-color: rgba(201, 122, 122, 0.35);
    background: rgba(201, 122, 122, 0.08);
}

.alert {
    padding: 0.65rem 0.78rem;
    border-radius: var(--radius-sm);
    background: rgba(201, 122, 122, 0.1);
    border: 1px solid rgba(201, 122, 122, 0.24);
    color: var(--danger);
    overflow-wrap: anywhere;
}

.alert-success {
    background: rgba(107, 170, 121, 0.1);
    border-color: rgba(107, 170, 121, 0.22);
    color: var(--success);
}

.alert-warning {
    background: rgba(205, 178, 110, 0.12);
    border-color: rgba(205, 178, 110, 0.28);
    color: var(--warning);
}

.data-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.83rem;
}

.data-table th,
.data-table td {
    padding: 0.52rem 0.58rem;
    border-bottom: 1px solid var(--border);
    text-align: left;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.compact-table {
    font-size: 0.78rem;
}

.status-pill {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 6.4rem;
    padding: 0.24rem 0.52rem;
    border-radius: 999px;
    border: 1px solid var(--border);
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}

.status-running {
    background: rgba(107, 170, 121, 0.14);
    color: var(--success);
}

.status-stopped {
    background: rgba(201, 122, 122, 0.14);
    color: var(--danger);
}

.status-unknown {
    background: rgba(205, 178, 110, 0.14);
    color: var(--warning);
}

.empty-state {
    padding: var(--space-4);
    border: 1px dashed var(--border);
    border-radius: var(--radius-sm);
    background: var(--panel-alt);
}

@media (max-width: 980px) {
    .app-shell {
        flex-direction: column;
    }

    .sidebar {
        width: auto;
        border-right: 0;
        border-bottom: 1px solid var(--border);
    }
}

@media (max-width: 720px) {
    .form-grid {
        grid-template-columns: 1fr;
    }

    .panel-header,
    .toolbar-inline {
        flex-direction: column;
        align-items: stretch;
    }
}
```
