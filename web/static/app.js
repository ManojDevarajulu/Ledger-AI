document.addEventListener('DOMContentLoaded', () => {
    let filingsData = [];
    let selectedCase = null;
    let currentAblationMode = 'full';

    // DOM Elements
    const filingSelect = document.getElementById('filingSelect');
    const ablationSelect = document.getElementById('ablationSelect');
    const quickChips = document.getElementById('quickChips');
    const queryInput = document.getElementById('queryInput');
    const runQueryBtn = document.getElementById('runQueryBtn');

    // Tab Navigation Elements
    const tabResearch = document.getElementById('tabResearch');
    const tabBenchmark = document.getElementById('tabBenchmark');
    const researchView = document.getElementById('researchView');
    const benchmarkView = document.getElementById('benchmarkView');

    // Analysis Result Elements
    const statusBadge = document.getElementById('statusBadge');
    const queryStatusNotice = document.getElementById('queryStatusNotice');
    const heroMetricValue = document.getElementById('heroMetricValue');
    const synthesisText = document.getElementById('synthesisText');
    const traceFormula = document.getElementById('traceFormula');
    const citedCellsList = document.getElementById('citedCellsList');
    const retrievedChunkText = document.getElementById('retrievedChunkText');

    // SEC Table Elements
    const tableContainer = document.getElementById('tableContainer');
    const tableTitleTag = document.getElementById('tableTitleTag');
    const unitScaleTag = document.getElementById('unitScaleTag');

    // Benchmark Elements
    const benchmarkTableBody = document.getElementById('benchmarkTableBody');
    const runBenchmarkBtn = document.getElementById('runBenchmarkBtn');

    // 1. Tab Switching Logic
    tabResearch.addEventListener('click', () => {
        tabResearch.classList.add('active');
        tabResearch.setAttribute('aria-selected', 'true');
        tabBenchmark.classList.remove('active');
        tabBenchmark.setAttribute('aria-selected', 'false');

        researchView.classList.remove('hidden');
        benchmarkView.classList.add('hidden');
    });

    tabBenchmark.addEventListener('click', () => {
        tabBenchmark.classList.add('active');
        tabBenchmark.setAttribute('aria-selected', 'true');
        tabResearch.classList.remove('active');
        tabResearch.setAttribute('aria-selected', 'false');

        benchmarkView.classList.remove('hidden');
        researchView.classList.add('hidden');

        // Auto load benchmark if empty
        if (benchmarkTableBody && benchmarkTableBody.children.length <= 1) {
            fetchBenchmark();
        }
    });

    // 2. Pipeline Mode Change
    ablationSelect.addEventListener('change', (e) => {
        currentAblationMode = e.target.value;
        if (selectedCase) {
            executeQuery();
        }
    });

    // 3. Fetch Filings
    fetch('/api/filings')
        .then(res => res.json())
        .then(data => {
            filingsData = data.filings || [];
            renderFilingsDropdown();
            renderQuickChips();

            if (filingsData.length > 0) {
                filingSelect.value = filingsData[0].case_id;
                selectFiling(filingsData[0].case_id);
            }
        })
        .catch(err => {
            console.error("Failed to load filings:", err);
            filingSelect.innerHTML = '<option disabled>Failed to load filings</option>';
        });

    // Live SEC Ingest Elements
    const liveTickerInput = document.getElementById('liveTickerInput');
    const fetchLiveBtn = document.getElementById('fetchLiveBtn');

    // Live Fetch Handler
    if (fetchLiveBtn && liveTickerInput) {
        fetchLiveBtn.addEventListener('click', handleLiveFetch);
        liveTickerInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                handleLiveFetch();
            }
        });
    }

    function handleLiveFetch() {
        const ticker = liveTickerInput.value.trim().toUpperCase();
        if (!ticker) {
            liveTickerInput.focus();
            return;
        }

        const origHtml = fetchLiveBtn.innerHTML;
        fetchLiveBtn.disabled = true;
        fetchLiveBtn.innerHTML = '<span>Ingesting...</span>';
        queryStatusNotice.textContent = `Querying SEC EDGAR Submissions API for ${ticker} Form 10-K...`;

        fetch('/api/filing/live', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ticker: ticker })
        })
        .then(res => {
            if (!res.ok) {
                return res.json().then(errData => {
                    throw new Error(errData.detail || `SEC Error ${res.status}`);
                });
            }
            return res.json();
        })
        .then(data => {
            const existingIdx = filingsData.findIndex(f => f.case_id === data.case_id);
            if (existingIdx >= 0) {
                filingsData[existingIdx] = data.case;
            } else {
                filingsData.unshift(data.case);
            }

            renderFilingsDropdown();
            filingSelect.value = data.case_id;
            selectFiling(data.case_id, true);
            liveTickerInput.value = '';
            queryStatusNotice.textContent = `Audited live from SEC EDGAR (Accession: ${data.case.accession_number})`;
        })
        .catch(err => {
            console.error("Live fetch failed:", err);
            queryStatusNotice.textContent = `SEC EDGAR error: ${err.message}`;
            alert(`Unable to ingest ${ticker} from SEC EDGAR: ${err.message}`);
        })
        .finally(() => {
            fetchLiveBtn.disabled = false;
            fetchLiveBtn.innerHTML = origHtml;
        });
    }

    function renderFilingsDropdown() {
        filingSelect.innerHTML = '';
        filingsData.forEach(f => {
            const opt = document.createElement('option');
            opt.value = f.case_id;
            const liveBadge = f.is_live_edgar ? '[LIVE EDGAR] ' : '';
            opt.textContent = `${liveBadge}${f.company} (${f.ticker}) — ${f.fiscal_year} 10-K (${f.section})`;
            filingSelect.appendChild(opt);
        });

        filingSelect.addEventListener('change', (e) => {
            selectFiling(e.target.value);
        });
    }

    function renderQuickChips() {
        quickChips.innerHTML = '';
        const sampleIds = ['fb_msft_01', 'fb_nvda_01', 'fb_aapl_02', 'fb_refusal_01', 'fb_amzn_02'];
        const samples = filingsData.filter(f => sampleIds.includes(f.case_id));

        samples.forEach(s => {
            const chip = document.createElement('button');
            chip.className = 'pill-chip';
            chip.type = 'button';
            chip.textContent = s.is_refusal_case ? `${s.ticker}: Copilot Guidance` : `${s.ticker}: ${s.table_title.split(' ')[0]} Growth`;
            chip.addEventListener('click', () => {
                filingSelect.value = s.case_id;
                selectFiling(s.case_id, true);
            });
            quickChips.appendChild(chip);
        });
    }

    function selectFiling(caseId, autoExecute = true) {
        selectedCase = filingsData.find(f => f.case_id === caseId);
        if (!selectedCase) return;

        queryInput.value = selectedCase.question;
        tableTitleTag.textContent = selectedCase.table_title;

        if (autoExecute) {
            executeQuery();
        }
    }

    // 4. Query Execution
    runQueryBtn.addEventListener('click', executeQuery);
    queryInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            executeQuery();
        }
    });

    function executeQuery() {
        if (!selectedCase) return;

        runQueryBtn.disabled = true;
        heroMetricValue.textContent = 'Verifying...';
        queryStatusNotice.textContent = 'Retrieving table context and validating arithmetic AST...';

        const payload = {
            case_id: selectedCase.case_id,
            ablation_mode: currentAblationMode,
            custom_query: queryInput.value.trim()
        };

        fetch('/api/query', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
        .then(res => res.json())
        .then(data => {
            renderQueryResult(data);
        })
        .catch(err => {
            console.error("Query execution error:", err);
            heroMetricValue.textContent = 'Error';
            synthesisText.textContent = 'Unable to complete query execution.';
            statusBadge.className = 'status-pill status-refusal';
            statusBadge.textContent = 'ERROR';
        })
        .finally(() => {
            runQueryBtn.disabled = false;
        });
    }

    function renderQueryResult(data) {
        statusBadge.className = 'status-pill';

        if (data.status === 'VERIFIED') {
            statusBadge.classList.add('status-verified');
            statusBadge.textContent = 'VERIFIED';
            heroMetricValue.textContent = data.numeric_result || 'Verified';
            queryStatusNotice.textContent = 'Deterministic calculation matched grounded filing cells';
        } else if (data.status === 'REFUSAL') {
            statusBadge.classList.add('status-refusal');
            statusBadge.textContent = 'REFUSAL GUARD';
            heroMetricValue.textContent = 'REFUSED';
            queryStatusNotice.textContent = 'Refused to hallucinate undisclosed or forward-looking metric';
        } else {
            statusBadge.classList.add('status-unverified');
            statusBadge.textContent = 'UNVERIFIED';
            heroMetricValue.textContent = data.numeric_result || 'Unverified';
            queryStatusNotice.textContent = 'Heuristic answer without deterministic AST verification';
        }

        synthesisText.textContent = data.answer;
        tableTitleTag.textContent = data.table_title || 'Financial Statement';
        unitScaleTag.textContent = data.unit_scale || 'In millions USD';
        retrievedChunkText.textContent = data.retrieved_chunk || 'No context chunk returned.';

        // Formula
        if (data.formula) {
            traceFormula.textContent = data.formula;
        } else {
            traceFormula.textContent = data.status === 'REFUSAL' ? 'Halted by Calibrated Refusal Guard' : 'None (Ablation mode bypasses AST verifier)';
        }

        // Cited Cells Tags
        citedCellsList.innerHTML = '';
        if (data.cited_cells && data.cited_cells.length > 0) {
            data.cited_cells.forEach(c => {
                const tag = document.createElement('span');
                tag.className = 'cell-badge';
                const formattedVal = Number(c.val).toLocaleString();
                tag.textContent = `${c.row} (${c.col}): ${formattedVal}`;
                citedCellsList.appendChild(tag);
            });
        } else {
            citedCellsList.innerHTML = '<span class="ledger-runtime">No cell coordinates cited</span>';
        }

        // Table Render with Right-Aligned Financial Columns
        renderTable(data.table_markdown, data.cited_cells || []);
    }

    function renderTable(markdown, citedCells) {
        if (!markdown) {
            tableContainer.innerHTML = '<div class="empty-state">No statement data found.</div>';
            return;
        }

        const lines = markdown.trim().split('\n').filter(l => l.trim().length > 0);
        if (lines.length < 2) return;

        const table = document.createElement('table');
        table.className = 'rendered-table';

        // Parse Headers
        const thead = document.createElement('thead');
        const headerRow = document.createElement('tr');
        const headerCols = lines[0].split('|').map(c => c.trim()).filter(c => c.length > 0);

        headerCols.forEach(h => {
            const th = document.createElement('th');
            th.textContent = h;
            headerRow.appendChild(th);
        });
        thead.appendChild(headerRow);
        table.appendChild(thead);

        // Parse Data Rows
        const tbody = document.createElement('tbody');
        const dataLines = lines.slice(2);

        dataLines.forEach(line => {
            const cols = line.split('|').map(c => c.trim()).filter(c => c.length > 0);
            if (cols.length === 0) return;

            const tr = document.createElement('tr');
            const rowLabel = cols[0];

            cols.forEach((colVal, colIdx) => {
                const td = document.createElement('td');
                td.textContent = colVal;

                if (colIdx > 0) {
                    const colHeader = headerCols[colIdx];
                    const isCited = citedCells.some(c => {
                        const rowMatch = rowLabel.toLowerCase().includes(c.row.toLowerCase());
                        const colMatch = colHeader && c.col && (colHeader.toLowerCase().includes(c.col.toLowerCase()) || c.col.toLowerCase().includes(colHeader.toLowerCase()));
                        return rowMatch && colMatch;
                    });

                    if (isCited) {
                        td.classList.add('cited-cell-highlight');
                    }
                }

                tr.appendChild(td);
            });
            tbody.appendChild(tr);
        });

        table.appendChild(tbody);
        tableContainer.innerHTML = '';
        tableContainer.appendChild(table);
    }

    // 5. Benchmark Fetcher
    function fetchBenchmark() {
        if (!runBenchmarkBtn) return;
        runBenchmarkBtn.disabled = true;
        benchmarkTableBody.innerHTML = '<tr><td colspan="6" class="benchmark-loading">Running 4-way ablation benchmark over 20 test cases...</td></tr>';

        fetch('/api/benchmark')
            .then(res => res.json())
            .then(data => {
                renderBenchmarkTable(data.benchmark || []);
            })
            .catch(err => {
                console.error("Benchmark error:", err);
                benchmarkTableBody.innerHTML = '<tr><td colspan="6" class="benchmark-loading" style="color:var(--color-rose)">Failed to execute benchmark harness.</td></tr>';
            })
            .finally(() => {
                runBenchmarkBtn.disabled = false;
            });
    }

    function renderBenchmarkTable(results) {
        benchmarkTableBody.innerHTML = '';
        results.forEach(r => {
            const tr = document.createElement('tr');
            if (r.name.includes('Ledger')) {
                tr.classList.add('row-accent');
            }

            tr.innerHTML = `
                <td><strong>${r.name}</strong></td>
                <td>${r.recall_at_1}%</td>
                <td>${r.accuracy}%</td>
                <td>${r.math_error_rate}%</td>
                <td>${r.refusal_precision}%</td>
                <td>${r.duration_sec}s</td>
            `;
            benchmarkTableBody.appendChild(tr);
        });
    }

    if (runBenchmarkBtn) {
        runBenchmarkBtn.addEventListener('click', fetchBenchmark);
    }
});
