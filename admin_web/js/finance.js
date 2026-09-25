// ProsArtisan Back-Office — Module Finance : tableau de bord, journal filtrable, remboursements, rapports.
// Script classique (non module) : partage la portée globale avec les autres
// fichiers de admin_web/js/, chargés dans l'ordre par index.html.

// =========================================================================
// 5. MODULE FINANCE (Dashboard, journal filtrable, remboursements, rapports)
// =========================================================================

const financeState = {
    limit: 20,
    offset: 0,
    total: 0,
};

function buildFinanceQuery(extra = {}) {
    const params = new URLSearchParams();
    const statut = document.getElementById('fin-filter-statut')?.value;
    const operateur = document.getElementById('fin-filter-operateur')?.value;
    const q = document.getElementById('fin-filter-q')?.value.trim();
    const dateFrom = document.getElementById('fin-filter-date-from')?.value;
    const dateTo = document.getElementById('fin-filter-date-to')?.value;

    if (statut) params.set('statut', statut);
    if (operateur) params.set('operateur', operateur);
    if (q) params.set('q', q);
    if (dateFrom) params.set('date_from', `${dateFrom}T00:00:00`);
    if (dateTo) params.set('date_to', `${dateTo}T23:59:59`);
    Object.entries(extra).forEach(([k, v]) => params.set(k, v));
    return params;
}

async function loadFinanceTab() {
    await Promise.all([
        loadFinanceOverview(),
        loadFinanceReport(),
        loadFinanceTransactions(),
    ]);
}

async function loadFinanceOverview() {
    try {
        const res = await adminFetch('/api/admin/finance/overview');
        if (!res.ok) return;
        const kpis = await res.json();
        const fmt = (n) => `${(n || 0).toLocaleString()} F`;
        document.getElementById('fin-kpi-revenu-total').textContent = fmt(kpis.revenu_total);
        document.getElementById('fin-kpi-revenu-30j').textContent = fmt(kpis.revenu_30j);
        document.getElementById('fin-kpi-taux-succes').textContent = `${kpis.taux_succes_pct}%`;
        document.getElementById('fin-kpi-rembourse').textContent = fmt(kpis.revenu_rembourse_total);

        const parOperateurEl = document.getElementById('fin-par-operateur');
        if (parOperateurEl) {
            const entries = Object.entries(kpis.par_operateur || {});
            parOperateurEl.innerHTML = entries.length === 0
                ? '<p class="text-muted small mb-0">Aucune donnée.</p>'
                : entries.map(([op, montant]) => `
                    <div class="d-flex justify-content-between border-bottom py-1">
                        <span>${op}</span>
                        <strong>${montant.toLocaleString()} F</strong>
                    </div>
                `).join('');
        }
    } catch (err) {
        console.error('Erreur chargement KPIs finance:', err);
    }
}

async function loadFinanceReport() {
    try {
        const period = document.getElementById('fin-report-period')?.value || 'day';
        const res = await adminFetch(`/api/admin/finance/reports?period=${period}`);
        if (!res.ok) return;
        const data = await res.json();
        const tbody = document.getElementById('fin-report-tbody');
        if (!tbody) return;
        const entries = data.entries || [];
        tbody.innerHTML = entries.length === 0
            ? '<tr><td colspan="3" class="text-center text-muted py-3">Aucune donnée.</td></tr>'
            : entries.slice().reverse().map(e => `
                <tr>
                    <td>${e.periode}</td>
                    <td>${e.nb_transactions}</td>
                    <td>${e.revenu.toLocaleString()} F</td>
                </tr>
            `).join('');
    } catch (err) {
        console.error('Erreur chargement rapport finance:', err);
    }
}

async function loadFinanceTransactions() {
    try {
        const params = buildFinanceQuery({
            limit: financeState.limit,
            offset: financeState.offset,
        });
        const res = await adminFetch(`/api/admin/finance/transactions?${params.toString()}`);
        const tbody = document.getElementById('payments-table-body');
        if (!res.ok) {
            if (res.status === 403 && tbody) {
                tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted py-3">Votre rôle ne donne pas accès au module Finance.</td></tr>';
            }
            return;
        }
        const data = await res.json();
        financeState.total = data.total || 0;
        if (!tbody) return;

        tbody.innerHTML = data.transactions.length === 0
            ? '<tr><td colspan="7" class="text-center text-muted py-3">Aucune transaction ne correspond à ces filtres.</td></tr>'
            : data.transactions.map(t => {
                const badgeClass = {
                    ACCEPTED: 'badge bg-success-subtle text-success',
                    SUCCESS: 'badge bg-success-subtle text-success',
                    PAID: 'badge bg-success-subtle text-success',
                    PENDING: 'badge bg-warning-subtle text-warning',
                    FAILED: 'badge bg-danger-subtle text-danger',
                    REFUNDED: 'badge bg-secondary-subtle text-secondary',
                }[t.statut_paiement] || 'badge bg-light text-dark';
                const canRefund = ['ACCEPTED', 'SUCCESS', 'PAID'].includes(t.statut_paiement);
                const canAdjust = t.statut_paiement !== 'REFUNDED';

                return `
                    <tr>
                        <td><code>${t.reference_externe || '—'}</code></td>
                        <td>${t.artisan}</td>
                        <td><strong>${t.montant.toLocaleString()} ${t.devise}</strong></td>
                        <td>${t.operateur}</td>
                        <td><span class="${badgeClass}">${t.statut_paiement}</span></td>
                        <td>${new Date(t.created_at).toLocaleString()}</td>
                        <td>
                            ${canRefund ? `<button type="button" class="btn btn-sm btn-outline-warning" onclick='openFinanceActionModal(${JSON.stringify(t.id)}, "refund")' title="Rembourser" aria-label="Rembourser cette transaction"><i class="iconoir-undo"></i></button>` : ''}
                            ${canAdjust ? `<button type="button" class="btn btn-sm btn-outline-secondary" onclick='openFinanceActionModal(${JSON.stringify(t.id)}, "adjust")' title="Corriger le statut" aria-label="Corriger le statut de cette transaction"><i class="iconoir-edit-pencil"></i></button>` : ''}
                        </td>
                    </tr>
                `;
            }).join('');

        const info = document.getElementById('fin-pagination-info');
        if (info) {
            const start = financeState.total === 0 ? 0 : financeState.offset + 1;
            const end = Math.min(financeState.offset + financeState.limit, financeState.total);
            info.textContent = `${start}–${end} sur ${financeState.total}`;
        }
    } catch (err) {
        console.error('Erreur chargement transactions finance:', err);
    }
}

function handleFinanceFilterChange() {
    financeState.offset = 0;
    loadFinanceTransactions();
}

function resetFinanceFilters() {
    ['fin-filter-q', 'fin-filter-date-from', 'fin-filter-date-to'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
    });
    ['fin-filter-statut', 'fin-filter-operateur'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
    });
    handleFinanceFilterChange();
}

function changeFinancePage(delta) {
    const nextOffset = financeState.offset + delta * financeState.limit;
    if (nextOffset < 0 || nextOffset >= financeState.total) return;
    financeState.offset = nextOffset;
    loadFinanceTransactions();
}

async function exportFinanceTransactions() {
    try {
        const params = buildFinanceQuery();
        const res = await adminFetch(`/api/admin/finance/transactions/export?${params.toString()}`);
        if (!res.ok) {
            alert("Échec de l'export.");
            return;
        }
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `transactions_prosartisan_${new Date().toISOString().slice(0, 10)}.csv`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
    } catch (err) {
        alert("Erreur réseau lors de l'export.");
    }
}

// --- Modale remboursement / correction de statut ---
let financeActionModalInstance = null;

function openFinanceActionModal(txnId, type) {
    document.getElementById('fin-action-txn-id').value = txnId;
    document.getElementById('fin-action-type').value = type;
    document.getElementById('fin-action-reason').value = '';
    document.getElementById('fin-action-feedback').textContent = '';
    document.getElementById('fin-action-status-group').classList.toggle('d-none', type !== 'adjust');
    document.getElementById('modal-finance-action-title').textContent =
        type === 'refund' ? 'Rembourser la transaction' : 'Corriger le statut';

    if (!financeActionModalInstance) {
        financeActionModalInstance = new bootstrap.Modal(document.getElementById('modal-finance-action'));
    }
    financeActionModalInstance.show();
}

function closeFinanceActionModal() {
    if (financeActionModalInstance) financeActionModalInstance.hide();
}

async function submitFinanceAction() {
    const txnId = document.getElementById('fin-action-txn-id').value;
    const type = document.getElementById('fin-action-type').value;
    const reason = document.getElementById('fin-action-reason').value.trim();
    const feedback = document.getElementById('fin-action-feedback');

    if (!reason) {
        feedback.className = 'mt-2 small text-danger';
        feedback.textContent = 'Le motif est obligatoire (tracé dans le journal d\'audit).';
        return;
    }

    try {
        let res;
        if (type === 'refund') {
            res = await adminFetch(`/api/admin/finance/transactions/${txnId}/refund`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ reason }),
            });
        } else {
            const newStatus = document.getElementById('fin-action-new-status').value;
            res = await adminFetch(`/api/admin/finance/transactions/${txnId}/adjust-status`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ new_status: newStatus, reason }),
            });
        }

        const data = await res.json().catch(() => ({}));
        if (res.ok) {
            closeFinanceActionModal();
            await loadFinanceTab();
        } else {
            feedback.className = 'mt-2 small text-danger';
            feedback.textContent = data.detail || 'Échec de l\'action.';
        }
    } catch (err) {
        feedback.className = 'mt-2 small text-danger';
        feedback.textContent = 'Erreur réseau.';
    }
}
