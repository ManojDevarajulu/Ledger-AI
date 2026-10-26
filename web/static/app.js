document.addEventListener('DOMContentLoaded', () => {
    let filingsData = [];
    let currentAblationMode = 'full';
    let selectedCase = null;

    // Elements
    const filingSelect = document.getElementById('filingSelect');
    const quickChips = document.getElementById('quickChips');
    const queryInput = document.getElementById('queryInput');
    const runQueryBtn = document.getElementById('runQueryBtn');
    const ablationPills = document.querySelectorAll('#ablationPills .pill');
    
    const statusBadge = document.getElementById('statusBadge');
    const heroMetricValue = document.getElementById('heroMetricValue');
    const synthesisText = document.getElementById('synthesisText');
    const traceFormula = document.getElementById('traceFormula');
    const citedCellsList = document.getElementById('citedCellsList');
    const retrievedChunkText = document.getElementById('retrievedChunkText');
    
    const tableContainer = document.getElementById('tableContainer');
    const tableTitleTag = document.getElementById('tableTitleTag');
    const unitScaleTag = document.getElementById('unitScaleTag');
    
    const benchmarkTableBody = document.getElementById('benchmarkTableBody');
    const runBenchmarkBtn = document.getElementById('runBenchmarkBtn');

    // 1. Initialize Ablation Mode Pills
    ablationPills.forEach(pill => {
        pill.addEventListener('click', () => {
            ablationPills.forEach(p => p.classList.remove('active'));
            pill.classList.add('active');
            currentAblationMode = pill.getAttribute('data-mode');
            if (selectedCase) {
                executeQuery();
            }
        });
    });

    // 2. Fetch Filings
    fetch('/api/filings')
        .then(res => res.json())
        .then(data => {
            filingsData = data.filings;
            renderFilingsDropdown();
            renderQuickChips();
            
            // Auto-select first filing
            if (filingsData.length > 0) {
                filingSelect.value = filingsData[0].case_id;
                selectFiling(filingsData[0].case_id);
            }
        })
        .catch(err => console.error("Error loading filings:", err));

    function renderFilingsDropdown() {
        filingSelect.innerHTML = '';
        filingsData.forEach(f => {
            const opt = document.createElement('option');
            opt.value = f.case_id;
            opt.textContent = `${f.company} (${f.ticker}) — ${f.fiscal_year} 10-K [${f.table_title}]`;
            filingSelect.appendChild(opt);
        });

        filingSelect.addEventListener('change', (e) => {
            selectFiling(e.target.value);
        });
    }

    function renderQuickChips() {
        quickChips.innerHTML = '';
        
        // Select 4 high-signal sample benchmarks
        const sampleIds = ['fb_msft_01', 'fb_nvda_01', 'fb_aapl_02', 'fb_refusal_01', 'fb_amzn_02'];
        const samples = filingsData.filter(f => sampleIds.includes(f.case_id));

        samples.forEach(s => {
            const chip = document.createElement('button');
            chip.className = 'chip-btn';
            const icon = s.is_refusal_case ? '⚠️' : '⚡';
            chip.textContent = `${icon} ${s.ticker}: ${s.table_title.split(' ')[0]}`;
            chip.addEventListener('click', () => {
                filingSelect.value = s.case_id;
                selectFiling(s.case_id, true);
            });
            quickChips.appendChild(chip);
        });
    }

    function selectFiling(caseId, autoExecute = false) {
        selectedCase = filingsData.find(f => f.case_id === caseId);
        if (!selectedCase) return;

        queryInput.value = selectedCase.question;
        tableTitleTag.textContent = selectedCase.table_title;

        if (autoExecute || selectedCase) {
            executeQuery();
        }
    }

    // 3. Execute Query
    runQueryBtn.addEventListener('click', () => {
        executeQuery();
    });

    queryInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            executeQuery();
        }
    });

    function executeQuery() {
        if (!selectedCase) return;

        runQueryBtn.disabled = true;
        heroMetricValue.textContent = 'Verifying...';

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
            console.error("Query error:", err);
            heroMetricValue.textContent = 'Error';
            synthesisText.textContent = 'Failed to execute query.';
        })
        .finally(() => {
            runQueryBtn.disabled = false;
        });
    }

    function renderQueryResult(data) {
        // Status Badge
        statusBadge.className = 'status-badge';
        if (data.status === 'VERIFIED') {
            statusBadge.classList.add('status-verified');
            statusBadge.textContent = 'DETERMINISTIC VERIFIED';
            heroMetricValue.textContent = data.numeric_result || 'Verified';
            heroMetricValue.style.color = 'var(--color-green)';
        } else if (data.status === 'REFUSAL') {
            statusBadge.classList.add('status-refusal');
            statusBadge.textContent = 'REFUSAL TRIGGERED';
            heroMetricValue.textContent = 'REFUSED';
            heroMetricValue.style.color = 'var(--color-red)';
        } else {
            statusBadge.classList.add('status-unverified');
            statusBadge.textContent = 'UNVERIFIED (HALLUCINATION RISK)';
            heroMetricValue.textContent = data.numeric_result || 'Unverified';
            heroMetricValue.style.color = 'var(--color-amber)';
        }

        // Synthesis & Tags
        synthesisText.textContent = data.answer;
        tableTitleTag.textContent = data.table_title || 'Table';
        unitScaleTag.textContent = data.unit_scale || 'USD in millions';
        retrievedChunkText.textContent = data.retrieved_chunk || 'No context returned.';

        // Math Trace Card
        if (data.formula) {
            traceFormula.textContent = data.formula;
        } else {
            traceFormula.textContent = data.status === 'REFUSAL' ? 'N/A (Refusal Guard halted calculation)' : 'N/A (No Formula in Naive mode)';
        }

        // Cited Cells Pills
        citedCellsList.innerHTML = '';
        if (data.cited_cells && data.cited_cells.length > 0) {
            data.cited_cells.forEach(c => {
                const pill = document.createElement('span');
                pill.className = 'cell-pill';
                pill.textContent = `${c.row} [${c.col}]: ${Number(c.val).toLocaleString()}`;
                citedCellsList.appendChild(pill);
            });
        } else {
            citedCellsList.innerHTML = '<span class="trace-val">None cited</span>';
        }

        // Render Table with Highlights
        renderTable(data.table_markdown, data.cited_cells || []);
    }

    function renderTable(markdown, citedCells) {
        if (!markdown) {
            tableContainer.innerHTML = '<div class="empty-table-state">No table data available.</div>';
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

        // Parse Body Rows
        const tbody = document.createElement('tbody');
        const dataLines = lines.slice(2); // Skip header and separator line

        dataLines.forEach(line => {
            const cols = line.split('|').map(c => c.trim()).filter(c => c.length > 0);
            if (cols.length === 0) return;

            const tr = document.createElement('tr');
            const rowLabel = cols[0];

            cols.forEach((colVal, colIdx) => {
                const td = document.createElement('td');
                td.textContent = colVal;

                // Check if this cell is in cited_cells
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

    // 4. Benchmark Runner
    function fetchBenchmark() {
        runBenchmarkBtn.disabled = true;
        benchmarkTableBody.innerHTML = '<tr><td colspan="6" class="loading-td">Running 4-way ablation benchmark on 20 FinanceBench cases...</td></tr>';

        fetch('/api/benchmark')
            .then(res => res.json())
            .then(data => {
                renderBenchmarkTable(data.benchmark);
            })
            .catch(err => {
                console.error("Benchmark error:", err);
                benchmarkTableBody.innerHTML = '<tr><td colspan="6" class="loading-td" style="color:var(--color-red)">Failed to load benchmark.</td></tr>';
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
                tr.classList.add('row-full-ledger');
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

    runBenchmarkBtn.addEventListener('click', fetchBenchmark);

    // Initial benchmark load
    fetchBenchmark();
});
