/* ============================================================
   Network Compliance Checker - Dashboard JavaScript
   ============================================================ */

let auditData = null;
let pollInterval = null;

// ===== INITIALIZATION =====
document.addEventListener('DOMContentLoaded', () => {
    loadInventoryInfo();
    checkExistingAudit();
});

async function loadInventoryInfo() {
    try {
        const [invRes, tplRes] = await Promise.all([
            fetch('/api/inventory'),
            fetch('/api/template')
        ]);
        const inventory = await invRes.json();
        const template = await tplRes.json();

        const statsEl = document.getElementById('emptyStats');
        const regionCount = Object.keys(inventory.regions || {}).length;
        statsEl.innerHTML = `
            <span>🖥️ ${inventory.total_switches} Switches</span>
            <span>🌍 ${regionCount} Regions</span>
            <span>📋 ${template.total_rules} Compliance Rules</span>
            <span>📂 ${template.categories?.length || 0} Categories</span>
        `;
    } catch (e) {
        console.error('Failed to load inventory info:', e);
    }
}

async function checkExistingAudit() {
    try {
        const res = await fetch('/api/status');
        const status = await res.json();
        if (status.status === 'running') {
            startPolling();
        } else if (status.status === 'completed' && status.last_audit) {
            auditData = status.last_audit;
            renderDashboard(auditData);
        }
    } catch (e) {
        console.error('Failed to check status:', e);
    }
}

// ===== AUDIT CONTROL =====
async function runAudit() {
    const btn = document.getElementById('btnRunAudit');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Starting Audit...';

    try {
        const res = await fetch('/api/run-audit', { method: 'POST' });
        const data = await res.json();

        if (res.ok) {
            document.getElementById('emptyState').style.display = 'none';
            document.getElementById('progressContainer').style.display = 'block';
            startPolling();
        } else {
            alert(data.error || 'Failed to start audit');
            btn.disabled = false;
            btn.innerHTML = 'Run Compliance Audit';
        }
    } catch (e) {
        alert('Error starting audit: ' + e.message);
        btn.disabled = false;
        btn.innerHTML = 'Run Compliance Audit';
    }
}

function startPolling() {
    document.getElementById('emptyState').style.display = 'none';
    document.getElementById('progressContainer').style.display = 'block';

    const btn = document.getElementById('btnRunAudit');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Audit Running...';

    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(pollStatus, 1000);
}

async function pollStatus() {
    try {
        const res = await fetch('/api/status');
        const status = await res.json();

        // Update progress
        const pct = status.total > 0 ? Math.round(status.progress / status.total * 100) : 0;
        document.getElementById('progressFill').style.width = pct + '%';
        document.getElementById('progressCount').textContent = `${status.progress} / ${status.total}`;
        document.getElementById('progressLabel').textContent =
            status.status === 'running' ? 'Collecting & analyzing configurations...' : status.status;
        document.getElementById('progressDetail').textContent =
            status.current_switch ? `Current: ${status.current_switch}` : 'Processing...';

        if (status.status === 'completed') {
            clearInterval(pollInterval);
            pollInterval = null;

            // Fetch full results
            const resultsRes = await fetch('/api/audit-results');
            auditData = await resultsRes.json();
            renderDashboard(auditData);

            document.getElementById('progressContainer').style.display = 'none';
            const btn = document.getElementById('btnRunAudit');
            btn.disabled = false;
            btn.innerHTML = `
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                </svg>
                Re-Run Audit`;
        } else if (status.status === 'error') {
            clearInterval(pollInterval);
            pollInterval = null;
            document.getElementById('progressContainer').style.display = 'none';
            const btn = document.getElementById('btnRunAudit');
            btn.disabled = false;
            btn.innerHTML = 'Run Compliance Audit';
            alert('Audit failed: ' + (status.errors?.join(', ') || 'Unknown error'));
        }
    } catch (e) {
        console.error('Poll error:', e);
    }
}

// ===== RENDER DASHBOARD =====
function renderDashboard(data) {
    document.getElementById('emptyState').style.display = 'none';
    document.getElementById('summaryGrid').style.display = 'grid';
    document.getElementById('gaugeRow').style.display = 'grid';
    document.getElementById('categoryCard').style.display = 'block';
    document.getElementById('topRulesCard').style.display = 'block';
    document.getElementById('switchTableCard').style.display = 'block';
    document.getElementById('downloadGroup').style.display = 'flex';

    // Update timestamp
    document.getElementById('lastUpdated').textContent =
        'Last audit: ' + new Date(data.audit_timestamp).toLocaleString();

    // Summary cards
    document.getElementById('totalSwitches').textContent = data.total_switches;
    document.getElementById('compliantCount').textContent = data.compliant_switches;
    document.getElementById('partialCount').textContent = data.partially_compliant_switches;
    document.getElementById('nonCompliantCount').textContent = data.non_compliant_switches;
    document.getElementById('unreachableCount').textContent = data.unreachable_switches;

    // Gauge
    renderGauge(data.overall_compliance_pct);

    // Severity bars
    renderSeverityBars(data.summary_by_severity);

    // Region list
    renderRegions(data.summary_by_region);

    // Category grid
    renderCategories(data.summary_by_category);

    // Top rules
    renderTopRules(data.top_non_compliant_rules);

    // Switch table
    renderSwitchTable(data.switch_reports);
}

function renderGauge(pct) {
    const gaugeArc = document.getElementById('gaugeArc');
    const gaugeValue = document.getElementById('gaugeValue');

    // Arc length is ~251 (circumference of arc from 20,100 to 180,100 with r=80)
    const arcLength = 251;
    const fillLength = (pct / 100) * arcLength;

    gaugeArc.style.strokeDasharray = `${fillLength} ${arcLength}`;

    // Color based on compliance
    let color = '#DC2626'; // red
    if (pct >= 95) color = '#059669'; // green
    else if (pct >= 70) color = '#D97706'; // amber
    else if (pct >= 50) color = '#EA580C'; // orange

    gaugeArc.style.stroke = color;
    gaugeValue.textContent = pct + '%';
    gaugeValue.style.color = color;
}

function renderSeverityBars(severity) {
    const total = Object.values(severity).reduce((a, b) => a + b, 0) || 1;
    const max = Math.max(...Object.values(severity), 1);

    ['critical', 'high', 'medium', 'low'].forEach(sev => {
        const count = severity[sev] || 0;
        const pct = (count / max) * 100;
        document.getElementById(`sev${sev.charAt(0).toUpperCase() + sev.slice(1)}`).style.width = pct + '%';
        document.getElementById(`sev${sev.charAt(0).toUpperCase() + sev.slice(1)}Count`).textContent = count;
    });
}

function renderRegions(regions) {
    const container = document.getElementById('regionList');
    const regionFilter = document.getElementById('regionFilter');
    container.innerHTML = '';
    // Reset region filter
    regionFilter.innerHTML = '<option value="all">All Regions</option>';

    const sortedRegions = Object.entries(regions).sort((a, b) => a[0].localeCompare(b[0]));

    sortedRegions.forEach(([name, data]) => {
        const pct = data.avg_compliance;
        let color = '#DC2626';
        if (pct >= 95) color = '#059669';
        else if (pct >= 70) color = '#D97706';

        container.innerHTML += `
            <div class="region-item">
                <span class="name">${name}</span>
                <div class="bar-container">
                    <div class="bar-fill" style="width:${pct}%; background:${color}"></div>
                </div>
                <span class="pct" style="color:${color}">${pct}%</span>
            </div>`;

        regionFilter.innerHTML += `<option value="${name}">${name}</option>`;
    });
}

function renderCategories(categories) {
    const grid = document.getElementById('categoryGrid');
    grid.innerHTML = '';

    Object.entries(categories).sort((a, b) => a[0].localeCompare(b[0])).forEach(([name, data]) => {
        const pct = data.compliance_pct || 0;
        let color = '#DC2626';
        if (pct >= 95) color = '#059669';
        else if (pct >= 70) color = '#D97706';

        grid.innerHTML += `
            <div class="category-item">
                <div class="cat-header">
                    <span class="cat-name">${name}</span>
                    <span class="cat-pct" style="color:${color}">${pct}%</span>
                </div>
                <div class="cat-bar"><div class="cat-fill" style="width:${pct}%; background:${color}"></div></div>
                <div class="cat-stats">
                    ✓ ${data.compliant} compliant · ✗ ${data.non_compliant} non-compliant · — ${data.na} N/A
                </div>
            </div>`;
    });
}

function renderTopRules(rules) {
    const tbody = document.getElementById('topRulesBody');
    tbody.innerHTML = '';

    if (!rules || rules.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#94A3B8;padding:24px;">No non-compliant rules found 🎉</td></tr>';
        return;
    }

    rules.slice(0, 15).forEach(rule => {
        tbody.innerHTML += `
            <tr>
                <td><strong>${rule.rule_id}</strong></td>
                <td>${rule.description}</td>
                <td>${rule.category}</td>
                <td><span class="badge severity-${rule.severity}">${rule.severity.toUpperCase()}</span></td>
                <td style="text-align:center;font-weight:700;color:#DC2626;">${rule.count}</td>
            </tr>`;
    });
}

function renderSwitchTable(reports) {
    const tbody = document.getElementById('switchTableBody');
    tbody.innerHTML = '';

    reports.forEach(report => {
        const sev = report.severity_counts || {};
        const statusClass = report.overall_status;
        const statusLabel = report.overall_status.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
        const pct = report.compliance_percentage;

        let barColor = '#DC2626';
        if (pct >= 95) barColor = '#059669';
        else if (pct >= 70) barColor = '#D97706';

        tbody.innerHTML += `
            <tr data-name="${report.switch_name.toLowerCase()}"
                data-status="${report.overall_status}"
                data-region="${report.region}">
                <td><strong>${report.switch_name}</strong></td>
                <td style="font-family:monospace;font-size:12px;">${report.hostname}</td>
                <td>${report.region}</td>
                <td>${report.location}</td>
                <td><span class="badge ${statusClass}">${statusLabel}</span></td>
                <td>
                    <div class="compliance-bar">
                        <div class="bar"><div class="fill" style="width:${pct}%;background:${barColor}"></div></div>
                        <span class="pct" style="color:${barColor}">${pct}%</span>
                    </div>
                </td>
                <td style="text-align:center;color:${(sev.critical||0) > 0 ? '#DC2626' : '#94A3B8'};font-weight:600;">${sev.critical || 0}</td>
                <td style="text-align:center;color:${(sev.high||0) > 0 ? '#EA580C' : '#94A3B8'};font-weight:600;">${sev.high || 0}</td>
                <td style="text-align:center;color:${(sev.medium||0) > 0 ? '#D97706' : '#94A3B8'};font-weight:600;">${sev.medium || 0}</td>
                <td style="text-align:center;color:${(sev.low||0) > 0 ? '#2563EB' : '#94A3B8'};font-weight:600;">${sev.low || 0}</td>
                <td>
                    ${report.overall_status !== 'unreachable'
                        ? `<button class="btn btn-sm btn-outline" onclick="showSwitchDetail('${report.switch_name}')">Details</button>`
                        : '<span style="color:#94A3B8;font-size:12px;">N/A</span>'
                    }
                </td>
            </tr>`;
    });
}

// ===== FILTERS =====
function filterSwitchTable() {
    const search = document.getElementById('searchInput').value.toLowerCase();
    const statusFilter = document.getElementById('statusFilter').value;
    const regionFilter = document.getElementById('regionFilter').value;

    const rows = document.querySelectorAll('#switchTableBody tr');
    rows.forEach(row => {
        const name = row.dataset.name || '';
        const status = row.dataset.status || '';
        const region = row.dataset.region || '';

        const matchSearch = !search || name.includes(search);
        const matchStatus = statusFilter === 'all' || status === statusFilter;
        const matchRegion = regionFilter === 'all' || region === regionFilter;

        row.classList.toggle('hidden', !(matchSearch && matchStatus && matchRegion));
    });
}

// ===== SWITCH DETAIL MODAL =====
async function showSwitchDetail(switchName) {
    const modal = document.getElementById('modalOverlay');
    const title = document.getElementById('modalTitle');
    const body = document.getElementById('modalBody');

    title.textContent = switchName;
    body.innerHTML = '<p style="text-align:center;padding:40px;color:#94A3B8;">Loading...</p>';
    modal.style.display = 'flex';

    try {
        const res = await fetch(`/api/switch-report/${encodeURIComponent(switchName)}`);
        const report = await res.json();

        let html = `
            <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:20px;">
                <div style="background:#F8FAFC;padding:12px;border-radius:8px;">
                    <div style="font-size:11px;color:#64748B;">Compliance</div>
                    <div style="font-size:24px;font-weight:800;">${report.compliance_percentage}%</div>
                </div>
                <div style="background:#F8FAFC;padding:12px;border-radius:8px;">
                    <div style="font-size:11px;color:#64748B;">Compliant Rules</div>
                    <div style="font-size:24px;font-weight:800;color:#059669;">${report.compliant_count}</div>
                </div>
                <div style="background:#F8FAFC;padding:12px;border-radius:8px;">
                    <div style="font-size:11px;color:#64748B;">Non-Compliant Rules</div>
                    <div style="font-size:24px;font-weight:800;color:#DC2626;">${report.non_compliant_count}</div>
                </div>
            </div>`;

        // Category tabs
        html += '<div style="margin-bottom:12px;font-size:13px;color:#64748B;">';
        html += `<strong>Hostname:</strong> ${report.hostname} | `;
        html += `<strong>Region:</strong> ${report.region} | `;
        html += `<strong>Location:</strong> ${report.location} | `;
        html += `<strong>Device:</strong> ${report.device_type}`;
        html += '</div>';

        // Show non-compliant first, then compliant
        const nonCompliant = report.all_findings.filter(f => f.status === 'non_compliant');
        const compliant = report.all_findings.filter(f => f.status === 'compliant');
        const na = report.all_findings.filter(f => f.status === 'na');

        if (nonCompliant.length > 0) {
            html += '<h4 style="color:#DC2626;margin:16px 0 8px;">❌ Non-Compliant Findings (' + nonCompliant.length + ')</h4>';
            html += '<div class="finding-list">';
            nonCompliant.forEach(f => {
                html += `
                    <div class="finding-item non_compliant">
                        <div class="finding-header">
                            <span class="finding-id">${f.rule_id}</span>
                            <span class="badge severity-${f.severity}">${f.severity.toUpperCase()}</span>
                        </div>
                        <div class="finding-desc">${f.description}</div>
                        <div class="finding-detail">${f.detail}</div>
                        ${f.remediation ? `<div class="finding-remediation">🔧 ${f.remediation}</div>` : ''}
                    </div>`;
            });
            html += '</div>';
        }

        if (compliant.length > 0) {
            html += '<details style="margin-top:16px;">';
            html += '<summary style="cursor:pointer;font-weight:600;color:#059669;margin-bottom:8px;">✅ Compliant Rules (' + compliant.length + ')</summary>';
            html += '<div class="finding-list">';
            compliant.forEach(f => {
                html += `
                    <div class="finding-item compliant">
                        <div class="finding-header">
                            <span class="finding-id">${f.rule_id}</span>
                            <span class="badge severity-${f.severity}">${f.severity.toUpperCase()}</span>
                        </div>
                        <div class="finding-desc">${f.description}</div>
                    </div>`;
            });
            html += '</div></details>';
        }

        if (na.length > 0) {
            html += '<details style="margin-top:16px;">';
            html += '<summary style="cursor:pointer;font-weight:600;color:#64748B;margin-bottom:8px;">— N/A Rules (' + na.length + ')</summary>';
            html += '<div class="finding-list">';
            na.forEach(f => {
                html += `
                    <div class="finding-item na">
                        <div class="finding-header">
                            <span class="finding-id">${f.rule_id}</span>
                        </div>
                        <div class="finding-desc">${f.description}</div>
                        <div class="finding-detail">${f.detail}</div>
                    </div>`;
            });
            html += '</div></details>';
        }

        body.innerHTML = html;

    } catch (e) {
        body.innerHTML = `<p style="color:#DC2626;text-align:center;padding:40px;">Error loading details: ${e.message}</p>`;
    }
}

function closeModal() {
    document.getElementById('modalOverlay').style.display = 'none';
}

// Close modal on Escape
document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeModal();
});

// ===== DOWNLOAD =====
function downloadReport(type) {
    window.location.href = `/api/download/${type}`;
}
