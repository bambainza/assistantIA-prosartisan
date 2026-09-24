// State Variables
let selectedUserIdForGrant = null;
let grantModal = null;

// Encoder toute donnée non fiable avant son insertion dans une chaîne HTML.
function escapeHtml(value) {
    return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
}

// Unified Admin Fetch Wrapper
async function adminFetch(url, options = {}) {
    options.headers = options.headers || {};
    options.credentials = 'same-origin';

    const res = await fetch(url, options);
    if (res.status === 401 || res.status === 403) {
        logoutAdmin();
        throw new Error('Session expired or unauthorized');
    }
    return res;
}

window.logoutAdmin = async function() {
    localStorage.removeItem('prosartisan_admin_token');
    await fetch('/api/auth/session/logout', {
        method: 'POST',
        credentials: 'same-origin'
    }).catch(() => {});
    document.getElementById('login-container').classList.remove('d-none');
    window.location.reload();
};

document.addEventListener('DOMContentLoaded', () => {
    const year = document.getElementById('copyright-year');
    if (year) year.textContent = String(new Date().getFullYear());
    if (window.location.search.includes('logout=1')) {
        fetch('/api/auth/session/logout', { method: 'POST', credentials: 'same-origin' }).catch(() => {});
        window.history.replaceState({}, document.title, window.location.pathname);
    }

    initTabs();
    initLoginForm();
    initUploadForm();
    loadPromptInspector();

    // Check if already authenticated
    adminFetch('/api/auth/me').then(() => {
        document.getElementById('login-container').classList.add('d-none');
        refreshDashboard();
    }).catch(() => {
        document.getElementById('login-container').classList.remove('d-none');
    });
});

// Login Form handler
function initLoginForm() {
    const form = document.getElementById('admin-login-form');
    if (!form) return;

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = (document.getElementById('admin-email').value || '').trim();
        const password = (document.getElementById('admin-password').value || '').trim();
        const totpGroup = document.getElementById('admin-totp-group');
        const totpCode = (document.getElementById('admin-totp').value || '').trim();
        const errMsg = document.getElementById('login-error-msg');
        const submitBtn = document.getElementById('btn-login-submit');

        submitBtn.disabled = true;
        submitBtn.textContent = 'Connexion...';
        errMsg.classList.add('d-none');

        try {
            const payload = { email, password };
            if (totpCode) payload.totp_code = totpCode;

            const res = await fetch('/api/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (res.status === 200) {
                const data = await res.json();
                if (data.user && data.user.is_admin) {
                    localStorage.removeItem('prosartisan_admin_token');
                    document.getElementById('login-container').classList.add('d-none');
                    refreshDashboard();
                } else {
                    errMsg.textContent = 'Accès interdit : privilèges administrateur requis.';
                    errMsg.classList.remove('d-none');
                }
            } else {
                const errData = await res.json().catch(() => ({}));
                const detail = errData.detail || 'Identifiants incorrects.';
                // Le backend renvoie ce message précis quand le compte a la 2FA
                // active : on révèle alors le champ code au lieu d'afficher un
                // simple échec, pour ne pas forcer l'admin à ressaisir email/mdp.
                if (detail.includes('authentification à deux facteurs')) {
                    totpGroup.classList.remove('d-none');
                    document.getElementById('admin-totp').focus();
                    errMsg.textContent = totpCode
                        ? 'Code invalide, veuillez réessayer.'
                        : 'Entrez le code de votre application d\'authentification.';
                    errMsg.classList.remove('d-none');
                } else {
                    errMsg.textContent = detail;
                    errMsg.classList.remove('d-none');
                }
            }
        } catch (err) {
            errMsg.textContent = 'Impossible de contacter le serveur d\'authentification.';
            errMsg.classList.remove('d-none');
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Se connecter';
        }
    });
}

// Tab Navigation — implémente le pattern WAI-ARIA Tabs (role=tab/tabpanel,
// aria-selected, tabindex "roving" + navigation flèches) sur le menu latéral
// existant, sans changer son apparence visuelle.
function initTabs() {
    const navItems = Array.from(document.querySelectorAll('.nav-menu-item'));
    const tabPages = document.querySelectorAll('.tab-page');
    const pageTitle = document.getElementById('page-title');
    const pageTitleH1 = document.getElementById('page-title-h1');

    function activateTab(item, { focusTab = false } = {}) {
        navItems.forEach(n => {
            n.classList.remove('active');
            n.setAttribute('aria-selected', 'false');
            n.setAttribute('tabindex', '-1');
        });
        tabPages.forEach(p => p.classList.remove('active'));

        item.classList.add('active');
        item.setAttribute('aria-selected', 'true');
        item.setAttribute('tabindex', '0');
        if (focusTab) item.focus();

        const targetTab = item.getAttribute('data-tab');
        const targetEl = document.getElementById(targetTab);
        if (targetEl) targetEl.classList.add('active');

        const label = item.querySelector('span') ? item.querySelector('span').textContent : '';
        if (label) {
            pageTitle.textContent = label;
            if (pageTitleH1) pageTitleH1.textContent = label;
            document.title = `${label} — ProsArtisan IA — Console d'Administration`;
        }

        if (targetTab === 'tab-packages') {
            loadPackagesTab();
        }
        if (targetTab === 'tab-security') {
            loadSecurityTab();
        }
        if (targetTab === 'tab-actualites') {
            loadActualitesTab();
        }
        if (targetTab === 'tab-payments') {
            loadFinanceTab();
        }
        if (targetTab === 'tab-parametres') {
            loadParametresTab();
        }
        if (targetTab === 'tab-quotes') {
            loadQuotesAndCalculatorsTab();
        }
    }

    navItems.forEach((item, index) => {
        item.addEventListener('click', () => activateTab(item));

        // Navigation clavier flèches Haut/Bas + Home/End entre les onglets,
        // conforme au pattern APG Tabs (activation automatique au focus).
        item.addEventListener('keydown', (e) => {
            let targetIndex = null;
            if (e.key === 'ArrowDown' || e.key === 'ArrowRight') {
                targetIndex = (index + 1) % navItems.length;
            } else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') {
                targetIndex = (index - 1 + navItems.length) % navItems.length;
            } else if (e.key === 'Home') {
                targetIndex = 0;
            } else if (e.key === 'End') {
                targetIndex = navItems.length - 1;
            }
            if (targetIndex !== null) {
                e.preventDefault();
                activateTab(navItems[targetIndex], { focusTab: true });
            }
        });
    });
}

// Refresh Dashboard & Data
async function refreshDashboard() {
    const token = localStorage.getItem('prosartisan_admin_token');
    if (!token) return;

    await fetchOverview();
    await fetchArtisans();
    await fetchDocuments();
    await loadFinanceTab();
    await loadPackagesTab();
    await fetchLogs();
}

// 1. Fetch Overview (KPIs & Top Métiers)
async function fetchOverview() {
    try {
        const res = await adminFetch('/api/admin/overview');
        const data = await res.json();

        document.getElementById('kpi-artisans').textContent = data.kpis.total_artisans.toLocaleString();
        document.getElementById('kpi-dau').textContent = data.kpis.artisans_actifs_dau.toLocaleString();
        document.getElementById('kpi-ca').textContent = data.kpis.chiffre_affaires_mfa.toLocaleString() + ' F';
        document.getElementById('kpi-questions').textContent = data.kpis.total_questions_rag.toLocaleString();

        const barChartList = document.getElementById('top-metiers-list');
        barChartList.innerHTML = '';
        
        if (data.metiers_top && data.metiers_top.length > 0) {
            const maxReq = Math.max(...data.metiers_top.map(m => m.requetes)) || 1;
            data.metiers_top.forEach(m => {
                const pct = (m.requetes / maxReq) * 100;
                barChartList.innerHTML += `
                    <div class="bar-item mb-3">
                        <div class="bar-info d-flex justify-content-between mb-1" style="font-size: 13px;">
                            <span>${escapeHtml(m.nom)}</span>
                            <span><strong>${m.requetes.toLocaleString()}</strong> req</span>
                        </div>
                        <div class="progress" style="height: 8px;">
                            <div class="progress-bar bg-primary" role="progressbar" style="width: ${pct}%;" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100"></div>
                        </div>
                    </div>
                `;
            });
        }
    } catch (err) {
        console.error('Erreur chargement overview:', err);
    }
}

// 2. Fetch Artisans Table
async function fetchArtisans() {
    try {
        const res = await adminFetch('/api/admin/users');
        const data = await res.json();
        const tbody = document.getElementById('artisans-table-body');
        tbody.innerHTML = '';

        data.users.forEach(u => {
            const badgeClass = u.type_abonnement === 'pass_mois' ? 'badge bg-success-subtle text-success' :
                               (u.type_abonnement === 'pass_24h' ? 'badge bg-warning-subtle text-warning' : 'badge bg-danger-subtle text-danger');
            
            const reqLabel = u.questions_restantes > 9000 ? 'Illimité (Pro)' : `${u.questions_restantes} gratuites`;

            tbody.innerHTML += `
                <tr>
                    <td><strong>${escapeHtml(u.nom)}</strong></td>
                    <td>${escapeHtml(u.telephone)}</td>
                    <td>${escapeHtml(u.metier)}</td>
                    <td><span class="${badgeClass}">${u.type_abonnement.toUpperCase()}</span></td>
                    <td>${reqLabel}</td>
                    <td>
                        <button class="btn btn-sm btn-outline-primary" data-user-id="${escapeHtml(u.id)}" data-user-name="${escapeHtml(u.nom)}" onclick="openGrantModal(this.dataset.userId, this.dataset.userName)">
                            <i class="iconoir-plus-circle me-1"></i> Prolonger Pass
                        </button>
                    </td>
                </tr>
            `;
        });
    } catch (err) {
        console.error('Erreur chargement artisans:', err);
    }
}

// Modal Grant Pass
function openGrantModal(userId, userName) {
    selectedUserIdForGrant = userId;
    document.getElementById('modal-user-info').textContent = `Artisan : ${userName} (ID: ${userId})`;
    if (!grantModal) {
        grantModal = new bootstrap.Modal(document.getElementById('modal-grant'));
    }
    grantModal.show();
}

function closeModal() {
    if (grantModal) {
        grantModal.hide();
    }
}

async function submitGrantPass() {
    if (!selectedUserIdForGrant) return;
    const typePass = document.getElementById('select-type-pass').value;

    try {
        const res = await adminFetch(`/api/admin/users/${selectedUserIdForGrant}/grant-pass?type_pass=${typePass}`, {
            method: 'POST'
        });
        const data = await res.json();
        alert(data.message);
        closeModal();
        await fetchArtisans();
    } catch (err) {
        alert('Erreur lors de l attribution du Pass');
    }
}

// 3. Fetch Documents Qdrant
async function fetchDocuments() {
    try {
        const res = await adminFetch('/api/admin/documents');
        const data = await res.json();
        const docList = document.getElementById('documents-list');
        docList.innerHTML = '';

        data.documents.forEach(d => {
            const isActive = d.is_active !== false;
            docList.innerHTML += `
                <div class="card mb-3 shadow-none border ${isActive ? '' : 'bg-light opacity-75'}">
                    <div class="card-body p-3">
                        <div class="d-flex justify-content-between align-items-center mb-2">
                            <span class="fw-semibold text-truncate" style="max-width: 60%;"><i class="iconoir-paste-clipboard me-1 text-primary"></i> ${d.filename}</span>
                            <div class="d-flex gap-2 align-items-center">
                                <span class="badge ${isActive ? 'bg-success-subtle text-success' : 'bg-warning-subtle text-warning'}">
                                    ${isActive ? '● Visible Chat' : '○ Masqué Chat'}
                                </span>
                                <span class="badge bg-secondary-subtle text-secondary">${d.metier}</span>
                            </div>
                        </div>
                        <p class="text-muted mb-3" style="font-size: 11px;">
                            ${d.chunks_count} chunks vectoriels • Ingéré le ${d.date_ingestion}
                        </p>
                        <div class="d-flex gap-2">
                            <button class="btn btn-sm ${isActive ? 'btn-outline-warning' : 'btn-outline-success'}" onclick="toggleDocStatus('${d.filename}')">
                                <i class="${isActive ? 'iconoir-eye-closed' : 'iconoir-eye'} me-1"></i> ${isActive ? 'Désactiver pour le Chat' : 'Activer pour le Chat'}
                            </button>
                            <button class="btn btn-sm btn-outline-danger" onclick="deleteDoc('${d.filename}')">
                                <i class="iconoir-trash me-1"></i> Supprimer de Qdrant
                            </button>
                        </div>
                    </div>
                </div>
            `;
        });
    } catch (err) {
        console.error('Erreur chargement documents:', err);
    }
}

async function toggleDocStatus(docName) {
    try {
        const res = await adminFetch(`/api/admin/documents/${encodeURIComponent(docName)}/toggle`, { method: 'PATCH' });
        if (res.ok) {
            const data = await res.json();
            alert(data.message);
            await fetchDocuments();
        } else {
            alert('Erreur lors du basculement du statut du document.');
        }
    } catch (err) {
        alert('Erreur réseau lors du basculement.');
    }
}

async function deleteDoc(docId) {
    if (!confirm('Voulez-vous vraiment supprimer ce document de Qdrant ?')) return;
    try {
        const res = await adminFetch(`/api/admin/documents/${docId}`, { method: 'DELETE' });
        const data = await res.json();
        alert(data.message);
        await fetchDocuments();
    } catch (err) {
        alert('Erreur lors de la suppression');
    }
}

// 4. Upload PDF Form Handler
function initUploadForm() {
    const form = document.getElementById('upload-form');
    if (!form) return;
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const fileInput = document.getElementById('pdf-file-input');
        if (!fileInput.files.length) return alert('Veuillez sélectionner un fichier PDF');

        const formData = new FormData();
        formData.append('file', fileInput.files[0]);
        formData.append('metier_id', document.getElementById('metier_id').value);
        formData.append('type_document', document.getElementById('type_document').value);

        const btn = document.getElementById('btn-submit-upload');
        btn.textContent = '⏳ Ingestion vectorielle en cours...';
        btn.disabled = true;

        try {
            const res = await adminFetch('/api/admin/upload-pdf', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();
            alert(data.message);
            fileInput.value = '';
            await fetchDocuments();
        } catch (err) {
            alert('Échec de l ingestion');
        } finally {
            btn.textContent = '🚀 Lancer l\'ingestion vectorielle (Qdrant)';
            btn.disabled = false;
        }
    });
}

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

// 6. RAG Simulator
async function sendSimulatedChat() {
    const qInput = document.getElementById('chat-input-q');
    const imgInput = document.getElementById('chat-input-img');
    const q = qInput.value.trim();
    if (!q) return;

    const messages = document.getElementById('chat-messages');
    messages.innerHTML += `<div class="msg user">${escapeHtml(q)} ${imgInput.value ? '📷 [Photo jointe]' : ''}</div>`;

    qInput.value = '';

    try {
        // Envoi public
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question: q,
                metier_id: 1,
                image_url: imgInput.value || null
            })
        });
        const data = await res.json();
        messages.innerHTML += `<div class="msg assistant">${escapeHtml(data.reponse).replace(/\n/g, '<br>')}</div>`;
        messages.scrollTop = messages.scrollHeight;
    } catch (err) {
        messages.innerHTML += `<div class="msg assistant text-danger">Erreur de génération RAG</div>`;
    }
}

// Load Prompt Template Inspector
function loadPromptInspector() {
    const promptText = `
=== PROMPT SYSTÈME PROSARTISAN (MULTILINGUE & RAG) ===
Tu es l'Assistant Expert de ProsArtisan (maçons, électriciens, plombiers, menuisiers...).
1. FIDÉLITÉ AU CONTEXTE <CONTEXTE>{context}</CONTEXTE>
2. ZÉRO HALLUCINATION : Ne rien inventer.
3. COMPRÉHENSION MULTILINGUE : Français, Nouchi (argot de chantier), Dioula, Baoulé, Bété.
4. SÉCURITÉ & FORMATAGE : Étapes numérotées, dosages précis.
    `;
    const promptBlock = document.getElementById('prompt-code-block');
    if (promptBlock) {
        promptBlock.textContent = promptText;
    }
}

// Fetch System Logs
async function fetchLogs() {
    try {
        const res = await adminFetch('/api/admin/logs');
        const data = await res.json();
        const logsConsole = document.getElementById('logs-console');
        if (logsConsole) {
            logsConsole.innerHTML = data.logs.map(
                l => `[${escapeHtml(l.timestamp)}] [${escapeHtml(l.level)}] ${escapeHtml(l.event)}`
            ).join('<br>');
        }
    } catch (err) {
        console.error('Erreur chargement logs:', err);
    }
}

// =========================================================================
// 7. MODULE GESTION DES PACKAGES & ABONNEMENTS
// =========================================================================

let allPackagesCache = [];
let allSubscriptionsCache = [];
let assignPackageModalInstance = null;
let packageEditModalInstance = null;

async function loadPackagesTab() {
    try {
        const [statsRes, pkgsRes, subsRes] = await Promise.all([
            adminFetch('/api/admin/subscriptions/stats'),
            adminFetch('/api/admin/packages?active_only=false'),
            adminFetch('/api/admin/subscriptions')
        ]);

        if (statsRes.ok) {
            const stats = await statsRes.json();
            const elActive = document.getElementById('kpi-pkg-active');
            const elMrr = document.getElementById('kpi-pkg-mrr');
            const elExpiring = document.getElementById('kpi-pkg-expiring');
            const elTotal = document.getElementById('kpi-pkg-total');

            if (elActive) elActive.textContent = (stats.abonnements_actifs || 0).toLocaleString();
            if (elMrr) elMrr.textContent = (stats.chiffre_affaires_mrr_estime || 0).toLocaleString() + ' F';
            if (elExpiring) elExpiring.textContent = (stats.echeances_dans_7_jours || 0).toLocaleString();
            if (elTotal) elTotal.textContent = (stats.total_souscriptions || 0).toLocaleString();
        }

        if (pkgsRes.ok) {
            const pkgsData = await pkgsRes.json();
            allPackagesCache = pkgsData.packages || [];
            renderPackagesList(allPackagesCache);
            updatePackageFilterOptions(allPackagesCache);
        }

        if (subsRes.ok) {
            const subsData = await subsRes.json();
            allSubscriptionsCache = subsData.subscriptions || [];
            handleSubscriptionFilter();
        }
    } catch (err) {
        console.error('Erreur chargement onglet packages:', err);
    }
}

function updatePackageFilterOptions(packages) {
    const filterSelect = document.getElementById('sub-filter-package');
    if (!filterSelect) return;
    const currentVal = filterSelect.value;
    filterSelect.innerHTML = '<option value="ALL">Toutes les formules</option>';
    packages.forEach(p => {
        filterSelect.innerHTML += `<option value="${escapeHtml(p.code)}">${escapeHtml(p.nom)} (${escapeHtml(p.code)})</option>`;
    });
    if (currentVal) filterSelect.value = currentVal;
}

function renderPackagesList(packages) {
    const grid = document.getElementById('packages-cards-grid');
    if (!grid) return;
    grid.innerHTML = '';

    if (!packages || packages.length === 0) {
        grid.innerHTML = '<div class="col-12 text-center text-muted py-4">Aucune formule configurée</div>';
        return;
    }

    packages.forEach(pkg => {
        const isActive = (pkg.est_actif !== undefined) ? Boolean(pkg.est_actif) : (pkg.is_active !== undefined ? Boolean(pkg.is_active) : true);
        const features = Array.isArray(pkg.fonctionnalites) ? pkg.fonctionnalites : (Array.isArray(pkg.features) ? pkg.features : []);
        const featuresHtml = features.map(f => `<li><i class="iconoir-check text-success me-1"></i>${escapeHtml(f)}</li>`).join('');
        
        let durationBadge = '';
        if (pkg.duree_jours) {
            durationBadge = `<span class="badge bg-light text-dark me-1"><i class="iconoir-calendar me-1"></i>${pkg.duree_jours} jours</span>`;
        }
        if (pkg.quota_requetes) {
            durationBadge += `<span class="badge bg-light text-dark"><i class="iconoir-chat-bubble-check me-1"></i>${pkg.quota_requetes} req.</span>`;
        }

        const safeNom = encodeURIComponent(pkg.nom || '');

        grid.innerHTML += `
            <div class="col-md-6 col-xl-4 mb-3">
                <div class="card package-card h-100 ${isActive ? '' : 'package-card-inactive'}">
                    <div class="card-body d-flex flex-column">
                        <div class="d-flex justify-content-between align-items-start mb-2">
                            <div>
                                <span class="badge ${isActive ? 'bg-success-subtle text-success' : 'badge-sub-expired text-danger'} mb-1">
                                    ${isActive ? '● En vente (Actif)' : '○ Désactivé (Inactif)'}
                                </span>
                                <h5 class="card-title mb-0 text-truncate" title="${escapeHtml(pkg.nom)}">${escapeHtml(pkg.nom)}</h5>
                                <small class="text-muted font-monospace">${escapeHtml(pkg.code)}</small>
                            </div>
                            <div class="dropdown">
                                <button class="btn btn-sm btn-light border-0" type="button" data-bs-toggle="dropdown" aria-expanded="false">
                                    <i class="iconoir-more-vert"></i>
                                </button>
                                <ul class="dropdown-menu dropdown-menu-end shadow-sm">
                                    <li><a class="dropdown-item" href="javascript:void(0)" onclick="openEditPackageModal('${pkg.id}')"><i class="iconoir-edit me-2 text-primary"></i>Modifier la formule</a></li>
                                    <li><a class="dropdown-item" href="javascript:void(0)" onclick="togglePackageActive('${pkg.id}', ${!isActive})"><i class="${isActive ? 'iconoir-eye-closed text-warning' : 'iconoir-eye text-success'} me-2"></i>${isActive ? 'Désactiver de la vente' : 'Réactiver la formule'}</a></li>
                                    <li><hr class="dropdown-divider"></li>
                                    <li><a class="dropdown-item text-danger" href="javascript:void(0)" onclick="deletePackagePrompt('${pkg.id}', decodeURIComponent('${safeNom}'))"><i class="iconoir-trash me-2"></i>Supprimer définitivement</a></li>
                                </ul>
                            </div>
                        </div>
                        <div class="my-2">
                            <span class="package-price-val">${pkg.prix.toLocaleString()}</span>
                            <span class="package-period"> F CFA</span>
                        </div>
                        <div class="mb-2">
                            ${durationBadge}
                        </div>
                        <p class="text-muted small flex-grow-0 mb-3">${escapeHtml(pkg.description || 'Aucune description')}</p>
                        <ul class="package-features-list flex-grow-1">
                            ${featuresHtml || '<li class="text-muted fst-italic">Accès standard à la plateforme</li>'}
                        </ul>
                        <div class="mt-3 pt-2 border-top d-flex gap-2">
                            <button class="btn btn-sm btn-outline-primary flex-fill" onclick="openEditPackageModal('${pkg.id}')" title="Modifier cette offre">
                                <i class="iconoir-edit me-1"></i> Modifier
                            </button>
                            ${isActive ? `
                                <button class="btn btn-sm btn-outline-warning" onclick="togglePackageActive('${pkg.id}', false)" title="Désactiver (retirer de la vente)">
                                    <i class="iconoir-eye-closed me-1"></i> Désactiver
                                </button>
                            ` : `
                                <button class="btn btn-sm btn-outline-success" onclick="togglePackageActive('${pkg.id}', true)" title="Réactiver la mise en vente">
                                    <i class="iconoir-eye me-1"></i> Réactiver
                                </button>
                            `}
                            <button class="btn btn-sm btn-outline-danger" onclick="deletePackagePrompt('${pkg.id}', decodeURIComponent('${safeNom}'))" title="Supprimer définitivement cette formule" aria-label="Supprimer définitivement cette formule">
                                <i class="iconoir-trash"></i>
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
    });
}

function handleSubscriptionFilter() {
    const searchVal = (document.getElementById('sub-search-input')?.value || '').toLowerCase().trim();
    const pkgVal = document.getElementById('sub-filter-package')?.value || 'ALL';
    const statusVal = document.getElementById('sub-filter-status')?.value || 'ALL';

    const filtered = allSubscriptionsCache.filter(sub => {
        if (searchVal) {
            const nom = (sub.artisan_nom || '').toLowerCase();
            const tel = (sub.artisan_telephone || '').toLowerCase();
            const email = (sub.artisan_email || '').toLowerCase();
            if (!nom.includes(searchVal) && !tel.includes(searchVal) && !email.includes(searchVal)) {
                return false;
            }
        }
        if (pkgVal !== 'ALL' && sub.package_code !== pkgVal) {
            return false;
        }
        if (statusVal === 'ACTIVE' && (!sub.est_actif || sub.statut !== 'actif')) {
            return false;
        }
        if (statusVal === 'EXPIRED' && (sub.est_actif || sub.statut === 'actif')) {
            return false;
        }
        return true;
    });

    renderSubscriptionsTable(filtered);
}

function renderSubscriptionsTable(subs) {
    const tbody = document.getElementById('subscriptions-table-body');
    if (!tbody) return;
    tbody.innerHTML = '';

    if (!subs || subs.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" class="text-center text-muted py-4">Aucune souscription trouvée</td></tr>';
        return;
    }

    subs.forEach(s => {
        let badgeStatus = '';
        if (s.statut === 'actif') {
            if (s.jours_restants !== null && s.jours_restants <= 7 && s.jours_restants >= 0) {
                badgeStatus = '<span class="badge-sub-expiring">Expire sous peu</span>';
            } else {
                badgeStatus = '<span class="badge-sub-active">Actif</span>';
            }
        } else if (s.statut === 'resilie') {
            badgeStatus = '<span class="badge bg-danger-subtle text-danger">Résilié</span>';
        } else {
            badgeStatus = '<span class="badge-sub-expired">Expiré</span>';
        }

        let daysBadge = '';
        if (s.jours_restants === null) {
            daysBadge = '<span class="badge bg-info-subtle text-info">Illimité</span>';
        } else if (s.jours_restants <= 0) {
            daysBadge = '<span class="badge bg-secondary-subtle text-secondary">Échu</span>';
        } else if (s.jours_restants <= 7) {
            daysBadge = `<span class="badge bg-warning-subtle text-warning fw-bold">${s.jours_restants} j restants</span>`;
        } else {
            daysBadge = `<span class="badge bg-success-subtle text-success">${s.jours_restants} jours</span>`;
        }

        const quotasText = s.requetes_restantes !== null ? `${s.requetes_restantes} req.` : 'Illimité';
        const dateDebut = s.date_debut ? new Date(s.date_debut).toLocaleDateString() : '-';
        const dateFin = s.date_fin ? new Date(s.date_fin).toLocaleDateString() : 'Indéfinie';

        tbody.innerHTML += `
            <tr>
                <td>
                    <div class="d-flex align-items-center">
                        <div class="avatar-sm bg-primary-subtle text-primary rounded-circle d-flex align-items-center justify-content-center me-2 fw-bold" style="width:32px; height:32px;">
                            ${escapeHtml((s.artisan_nom || 'A')[0].toUpperCase())}
                        </div>
                        <div>
                            <strong>${escapeHtml(s.artisan_nom || 'Artisan #' + s.user_id)}</strong>
                            <div class="text-muted small">${escapeHtml(s.artisan_email || '')}</div>
                        </div>
                    </div>
                </td>
                <td><small>${escapeHtml(s.artisan_telephone || '-')}</small></td>
                <td><span class="badge bg-light text-dark">${escapeHtml(s.artisan_metier || 'BTP')}</span></td>
                <td>
                    <strong>${escapeHtml(s.package_nom)}</strong>
                    <div class="text-muted font-monospace small">${escapeHtml(s.package_code)}</div>
                </td>
                <td><small>${dateDebut}</small></td>
                <td>
                    <div>${daysBadge}</div>
                    <small class="text-muted">Échéance: ${dateFin}</small>
                </td>
                <td><small class="fw-semibold">${quotasText}</small></td>
                <td>${badgeStatus}</td>
                <td class="text-end">
                    <div class="btn-group">
                        <button class="btn btn-sm btn-outline-primary" title="Prolonger de 30 jours" onclick="quickExtendSubscription('${s.id}', 30)">
                            +30j
                        </button>
                        ${s.statut === 'actif' ? `
                            <button class="btn btn-sm btn-outline-danger" title="Résilier" aria-label="Résilier l'abonnement" onclick="cancelSubscription('${s.id}')">
                                <i class="iconoir-xmark"></i>
                            </button>
                        ` : ''}
                    </div>
                </td>
            </tr>
        `;
    });
}

// Quick Extend Subscription
async function quickExtendSubscription(subId, days = 30) {
    if (!confirm(`Voulez-vous vraiment prolonger cette souscription de ${days} jours ?`)) return;
    try {
        const res = await adminFetch(`/api/admin/subscriptions/${subId}/extend`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ jours_supplementaires: days })
        });
        if (res.ok) {
            const data = await res.json();
            alert(data.message || 'Souscription prolongée avec succès');
            await loadPackagesTab();
            await fetchArtisans();
        } else {
            const err = await res.json().catch(() => ({}));
            alert(err.detail || 'Erreur lors de la prolongation');
        }
    } catch (e) {
        alert('Erreur réseau');
    }
}

// Cancel Subscription
async function cancelSubscription(subId) {
    if (!confirm('Confirmez-vous la résiliation de cette souscription ?')) return;
    try {
        const res = await adminFetch(`/api/admin/subscriptions/${subId}/cancel`, {
            method: 'POST'
        });
        if (res.ok) {
            const data = await res.json();
            alert(data.message || 'Souscription résiliée avec succès');
            await loadPackagesTab();
            await fetchArtisans();
        } else {
            const err = await res.json().catch(() => ({}));
            alert(err.detail || 'Erreur lors de la résiliation');
        }
    } catch (e) {
        alert('Erreur réseau');
    }
}

// Toggle / Activate / Deactivate Package
async function togglePackageActive(packageId, targetState = null) {
    try {
        let url = `/api/admin/packages/${packageId}/toggle`;
        if (targetState !== null && targetState !== undefined) {
            url += `?active=${targetState}`;
        }
        const res = await adminFetch(url, {
            method: 'PATCH'
        });
        if (res.ok) {
            const data = await res.json();
            alert(data.message || 'Statut de la formule mis à jour.');
            await loadPackagesTab();
        } else {
            const err = await res.json().catch(() => ({}));
            alert(err.detail || 'Erreur lors du changement de statut');
        }
    } catch (e) {
        alert('Erreur réseau lors de l\'activation/désactivation');
    }
}

// Delete Package with Confirmation & Safeguards
async function deletePackagePrompt(packageId, packageName) {
    const confirmMsg = `Êtes-vous certain de vouloir supprimer définitivement la formule :\n"${packageName}" ?\n\nAttention : cette action retirera le package du catalogue commercial.`;
    if (!confirm(confirmMsg)) return;

    try {
        const res = await adminFetch(`/api/admin/packages/${packageId}`, {
            method: 'DELETE'
        });

        if (res.ok) {
            const data = await res.json();
            alert(data.message || `Package "${packageName}" supprimé avec succès.`);
            await loadPackagesTab();
        } else {
            const err = await res.json().catch(() => ({}));
            const detail = err.detail || 'Erreur lors de la suppression';
            
            // Si le blocage est dû à des abonnements actifs, offrir l'option de forcer
            if (detail.includes('actif(s)')) {
                const forceConfirm = `${detail}\n\nSouhaitez-vous forcer la suppression malgré tout (cela supprimera également l'historique associé) ?`;
                if (confirm(forceConfirm)) {
                    await deletePackageForce(packageId, packageName);
                }
            } else {
                alert(detail);
            }
        }
    } catch (e) {
        alert('Erreur réseau lors de la suppression du package');
    }
}

async function deletePackageForce(packageId, packageName) {
    try {
        const res = await adminFetch(`/api/admin/packages/${packageId}?force=true`, {
            method: 'DELETE'
        });
        if (res.ok) {
            const data = await res.json();
            alert(data.message || `Package "${packageName}" supprimé avec succès.`);
            await loadPackagesTab();
        } else {
            const err = await res.json().catch(() => ({}));
            alert(err.detail || 'Erreur lors du forçage de la suppression');
        }
    } catch (e) {
        alert('Erreur réseau');
    }
}

// Modal Assign Package
async function openAssignPackageModal() {
    const userSelect = document.getElementById('assign-user-select');
    const pkgSelect = document.getElementById('assign-package-select');
    const durationInput = document.getElementById('assign-duration-days');
    const autoRenewCheck = document.getElementById('assign-auto-renew');

    if (durationInput) durationInput.value = '';
    if (autoRenewCheck) autoRenewCheck.checked = false;

    // Load users
    try {
        const res = await adminFetch('/api/admin/users');
        if (res.ok) {
            const data = await res.json();
            if (userSelect) {
                userSelect.innerHTML = '<option value="">-- Sélectionner un artisan --</option>';
                (data.users || []).forEach(u => {
                    userSelect.innerHTML += `<option value="${escapeHtml(u.id)}">${escapeHtml(u.nom)} (${escapeHtml(u.telephone || u.email || 'Sans contact')}) - ${escapeHtml(u.metier || 'Métier')}</option>`;
                });
            }
        }
    } catch (e) {
        console.error('Erreur chargement utilisateurs:', e);
    }

    // Populate packages
    if (pkgSelect) {
        pkgSelect.innerHTML = '<option value="">-- Sélectionner une formule --</option>';
        allPackagesCache.forEach(p => {
            const isAct = (p.est_actif !== undefined) ? Boolean(p.est_actif) : (p.is_active !== undefined ? Boolean(p.is_active) : true);
            const actifLabel = isAct ? '' : ' (inactif)';
            pkgSelect.innerHTML += `<option value="${escapeHtml(p.code)}">${escapeHtml(p.nom)} - ${p.prix.toLocaleString()} F CFA${actifLabel}</option>`;
        });
    }

    if (!assignPackageModalInstance) {
        const el = document.getElementById('modal-assign-package');
        if (el) assignPackageModalInstance = new bootstrap.Modal(el);
    }
    if (assignPackageModalInstance) assignPackageModalInstance.show();
}

function closeAssignPackageModal() {
    if (assignPackageModalInstance) {
        assignPackageModalInstance.hide();
    }
}

async function submitAssignPackage() {
    const userId = document.getElementById('assign-user-select')?.value;
    const pkgCode = document.getElementById('assign-package-select')?.value;
    const durationDays = document.getElementById('assign-duration-days')?.value;
    const autoRenew = document.getElementById('assign-auto-renew')?.checked || false;

    if (!userId) {
        alert('Veuillez sélectionner un artisan');
        return;
    }
    if (!pkgCode) {
        alert('Veuillez sélectionner une formule');
        return;
    }

    const payload = {
        user_id: parseInt(userId, 10),
        package_code: pkgCode,
        renouvellement_auto: autoRenew
    };
    if (durationDays) {
        payload.duree_jours = parseInt(durationDays, 10);
    }

    try {
        const res = await adminFetch('/api/admin/subscriptions/assign', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (res.ok) {
            const data = await res.json();
            alert(data.message || 'Package attribué avec succès');
            closeAssignPackageModal();
            await loadPackagesTab();
            await fetchArtisans();
        } else {
            const err = await res.json().catch(() => ({}));
            alert(err.detail || 'Erreur lors de l\'attribution');
        }
    } catch (e) {
        alert('Erreur réseau');
    }
}

// Modal Edit / Create Package
function openCreatePackageModal() {
    const titleEl = document.getElementById('modal-package-edit-title');
    if (titleEl) titleEl.innerHTML = '<i class="iconoir-box-iso me-2 text-primary"></i>Créer une nouvelle Formule';
    document.getElementById('package-edit-id').value = '';
    const codeInput = document.getElementById('package-edit-code');
    codeInput.value = '';
    codeInput.disabled = false;
    document.getElementById('package-edit-name').value = '';
    document.getElementById('package-edit-price').value = '0';
    document.getElementById('package-edit-type').value = 'pass_temporel';
    document.getElementById('package-edit-duration').value = '30';
    document.getElementById('package-edit-quota').value = '';
    document.getElementById('package-edit-active').checked = true;
    document.getElementById('package-edit-description').value = '';
    document.getElementById('package-edit-features').value = '';

    if (!packageEditModalInstance) {
        const el = document.getElementById('modal-package-edit');
        if (el) packageEditModalInstance = new bootstrap.Modal(el);
    }
    if (packageEditModalInstance) packageEditModalInstance.show();
}

function openEditPackageModal(pkgId) {
    const pkg = allPackagesCache.find(p => String(p.id) === String(pkgId));
    if (!pkg) return;

    const titleEl = document.getElementById('modal-package-edit-title');
    if (titleEl) titleEl.innerHTML = `<i class="iconoir-edit me-2 text-primary"></i>Modifier : ${pkg.nom}`;
    document.getElementById('package-edit-id').value = pkg.id;
    const codeInput = document.getElementById('package-edit-code');
    codeInput.value = pkg.code;
    codeInput.disabled = true;
    document.getElementById('package-edit-name').value = pkg.nom;
    document.getElementById('package-edit-price').value = pkg.prix;
    document.getElementById('package-edit-type').value = pkg.type_package;
    document.getElementById('package-edit-duration').value = pkg.duree_jours || '';
    document.getElementById('package-edit-quota').value = pkg.quota_requetes || '';
    const isActive = (pkg.est_actif !== undefined) ? Boolean(pkg.est_actif) : (pkg.is_active !== undefined ? Boolean(pkg.is_active) : true);
    document.getElementById('package-edit-active').checked = isActive;
    document.getElementById('package-edit-description').value = pkg.description || '';
    
    const features = Array.isArray(pkg.fonctionnalites) ? pkg.fonctionnalites : (Array.isArray(pkg.features) ? pkg.features : []);
    document.getElementById('package-edit-features').value = features.join('\n');

    if (!packageEditModalInstance) {
        const el = document.getElementById('modal-package-edit');
        if (el) packageEditModalInstance = new bootstrap.Modal(el);
    }
    if (packageEditModalInstance) packageEditModalInstance.show();
}

function closePackageEditModal() {
    if (packageEditModalInstance) {
        packageEditModalInstance.hide();
    }
}

async function submitPackageForm() {
    const pkgId = document.getElementById('package-edit-id').value;
    const code = (document.getElementById('package-edit-code').value || '').trim().toLowerCase();
    const nom = (document.getElementById('package-edit-name').value || '').trim();
    const prix = parseFloat(document.getElementById('package-edit-price').value) || 0;
    const typePkg = document.getElementById('package-edit-type').value;
    const dureeJours = document.getElementById('package-edit-duration').value ? parseInt(document.getElementById('package-edit-duration').value, 10) : null;
    const quota = document.getElementById('package-edit-quota').value ? parseInt(document.getElementById('package-edit-quota').value, 10) : null;
    const isActive = document.getElementById('package-edit-active').checked;
    const desc = document.getElementById('package-edit-description').value.trim();
    const featuresRaw = document.getElementById('package-edit-features').value;
    const features = featuresRaw.split('\n').map(l => l.trim()).filter(l => l.length > 0);

    if (!code) {
        alert('Le code du package est obligatoire');
        return;
    }
    if (!nom) {
        alert('Le nom du package est obligatoire');
        return;
    }

    try {
        if (pkgId) {
            const payload = {
                nom,
                prix,
                type_package: typePkg,
                duree_jours: dureeJours,
                quota_requetes: quota,
                description: desc,
                fonctionnalites: features,
                features: features,
                est_actif: isActive,
                is_active: isActive
            };
            const res = await adminFetch(`/api/admin/packages/${pkgId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (res.ok) {
                alert('Package mis à jour avec succès');
                closePackageEditModal();
                await loadPackagesTab();
            } else {
                const err = await res.json().catch(() => ({}));
                alert(err.detail || 'Erreur lors de la mise à jour');
            }
        } else {
            const payload = {
                code,
                nom,
                prix,
                type_package: typePkg,
                duree_jours: dureeJours,
                quota_requetes: quota,
                description: desc,
                fonctionnalites: features,
                features: features,
                est_actif: isActive,
                is_active: isActive
            };
            const res = await adminFetch('/api/admin/packages', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (res.ok) {
                alert('Package créé avec succès');
                closePackageEditModal();
                await loadPackagesTab();
            } else {
                const err = await res.json().catch(() => ({}));
                alert(err.detail || 'Erreur lors de la création');
            }
        }
    } catch (e) {
        alert('Erreur réseau');
    }
}

// =========================================================================
// 8. MODULE RBAC (RÔLES) & JOURNAL D'AUDIT
// =========================================================================

let allRolesCache = [];
let allPermissionsCache = [];

async function loadSecurityTab() {
    try {
        const [rolesRes, permsRes, auditRes, statsRes] = await Promise.all([
            adminFetch('/api/admin/roles'),
            adminFetch('/api/admin/permissions'),
            adminFetch('/api/admin/audit-logs?limit=100'),
            adminFetch('/api/admin/security-stats'),
        ]);

        if (statsRes.ok) {
            const stats = await statsRes.json();
            const setKpi = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = (val || 0).toLocaleString(); };
            setKpi('sec-kpi-actions-24h', stats.actions_admin_dernieres_24h);
            setKpi('sec-kpi-login-failed', stats.tentatives_connexion_echouees_30j);
            setKpi('sec-kpi-webhooks-rejected', stats.webhooks_rejetes_30j);
            setKpi('sec-kpi-tokens-revoked', stats.tokens_revoques_30j);
        }

        if (permsRes.ok) {
            allPermissionsCache = await permsRes.json();
        }

        if (rolesRes.ok) {
            allRolesCache = await rolesRes.json();
            renderRolesList(allRolesCache);
            populateRoleAssignSelect(allRolesCache);
        } else if (rolesRes.status === 403) {
            const rolesList = document.getElementById('roles-list');
            if (rolesList) {
                rolesList.innerHTML = '<p class="text-muted mb-0">Votre rôle ne donne pas accès à la gestion des rôles.</p>';
            }
        }

        if (auditRes.ok) {
            const logs = await auditRes.json();
            renderAuditLog(logs);
        } else if (auditRes.status === 403) {
            const tbody = document.getElementById('audit-log-tbody');
            if (tbody) {
                tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted py-3">Votre rôle ne donne pas accès au journal d\'audit.</td></tr>';
            }
        }

        await loadMyAccountSecurity();
    } catch (err) {
        console.error('Erreur chargement onglet sécurité:', err);
    }
}

function renderRolesList(roles) {
    const container = document.getElementById('roles-list');
    if (!container) return;

    if (!roles || roles.length === 0) {
        container.innerHTML = '<p class="text-muted mb-0">Aucun rôle configuré.</p>';
        return;
    }

    container.innerHTML = roles.map(role => `
        <div class="d-flex justify-content-between align-items-center border-bottom py-2">
            <div>
                <span class="fw-semibold">${escapeHtml(role.label)}</span>
                <br><small class="text-muted font-monospace">${escapeHtml(role.code)}</small>
            </div>
            <div class="d-flex align-items-center gap-2">
                <span class="badge bg-primary-subtle text-primary">${role.permissions.length} permission(s)</span>
                <button type="button" class="btn btn-sm btn-outline-secondary" onclick='openEditRolePermissionsModal(${JSON.stringify(role.code)})'>
                    <i class="iconoir-settings"></i>
                </button>
            </div>
        </div>
    `).join('');
}

// =========================================================================
// MODAL RÔLE : CRÉATION + ÉDITION DES PERMISSIONS
// =========================================================================

let roleModalInstance = null;
let roleModalMode = 'create'; // 'create' | 'edit'

function renderPermissionChecklist(checkedCodes) {
    const container = document.getElementById('role-modal-permissions-list');
    if (!container) return;
    const checkedSet = new Set(checkedCodes || []);

    if (!allPermissionsCache || allPermissionsCache.length === 0) {
        container.innerHTML = '<p class="text-muted small mb-0">Aucune permission disponible.</p>';
        return;
    }

    container.innerHTML = allPermissionsCache.map(perm => `
        <div class="form-check">
            <input class="form-check-input" type="checkbox" value="${escapeHtml(perm.code)}" id="perm-check-${escapeHtml(perm.code)}" ${checkedSet.has(perm.code) ? 'checked' : ''}>
            <label class="form-check-label small" for="perm-check-${escapeHtml(perm.code)}">
                <span class="font-monospace">${escapeHtml(perm.code)}</span>
                ${perm.description ? `<br><span class="text-muted">${escapeHtml(perm.description)}</span>` : ''}
            </label>
        </div>
    `).join('');
}

function openCreateRoleModal() {
    roleModalMode = 'create';
    document.getElementById('modal-role-permissions-title').textContent = 'Créer un rôle';
    document.getElementById('role-modal-id').value = '';
    document.getElementById('role-modal-code').value = '';
    document.getElementById('role-modal-code').disabled = false;
    document.getElementById('role-modal-label').value = '';
    document.getElementById('role-modal-label').disabled = false;
    document.getElementById('role-modal-feedback').textContent = '';
    renderPermissionChecklist([]);

    if (!roleModalInstance) {
        roleModalInstance = new bootstrap.Modal(document.getElementById('modal-role-permissions'));
    }
    roleModalInstance.show();
}

function openEditRolePermissionsModal(roleCode) {
    const role = allRolesCache.find(r => r.code === roleCode);
    if (!role) return;

    roleModalMode = 'edit';
    document.getElementById('modal-role-permissions-title').textContent = `Permissions — ${role.label}`;
    document.getElementById('role-modal-id').value = role.id;
    document.getElementById('role-modal-code').value = role.code;
    document.getElementById('role-modal-code').disabled = true;
    document.getElementById('role-modal-label').value = role.label;
    document.getElementById('role-modal-label').disabled = true;
    document.getElementById('role-modal-feedback').textContent = '';
    renderPermissionChecklist(role.permissions.map(p => p.code));

    if (!roleModalInstance) {
        roleModalInstance = new bootstrap.Modal(document.getElementById('modal-role-permissions'));
    }
    roleModalInstance.show();
}

function closeRoleModal() {
    if (roleModalInstance) roleModalInstance.hide();
}

function getCheckedPermissionCodes() {
    return Array.from(document.querySelectorAll('#role-modal-permissions-list input[type="checkbox"]:checked'))
        .map(el => el.value);
}

async function submitRoleModal() {
    const feedback = document.getElementById('role-modal-feedback');
    const permissionCodes = getCheckedPermissionCodes();

    try {
        let res;
        if (roleModalMode === 'create') {
            const code = (document.getElementById('role-modal-code').value || '').trim();
            const label = (document.getElementById('role-modal-label').value || '').trim();
            if (!code || !label) {
                feedback.className = 'mt-2 small text-danger';
                feedback.textContent = 'Le code et le nom affiché sont obligatoires.';
                return;
            }
            res = await adminFetch('/api/admin/roles', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code, label, permission_codes: permissionCodes }),
            });
        } else {
            const roleId = document.getElementById('role-modal-id').value;
            res = await adminFetch(`/api/admin/roles/${roleId}/permissions`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ permission_codes: permissionCodes }),
            });
        }

        const data = await res.json().catch(() => ({}));
        if (res.ok) {
            closeRoleModal();
            await loadSecurityTab();
        } else {
            feedback.className = 'mt-2 small text-danger';
            feedback.textContent = data.detail || 'Échec de l\'enregistrement du rôle.';
        }
    } catch (err) {
        feedback.className = 'mt-2 small text-danger';
        feedback.textContent = 'Erreur réseau lors de l\'enregistrement.';
    }
}

function populateRoleAssignSelect(roles) {
    const select = document.getElementById('role-assign-select');
    if (!select) return;
    const placeholder = '<option value="">-- Retirer le rôle (accès complet hérité) --</option>';
    select.innerHTML = placeholder + roles.map(r => `<option value="${r.code}">${r.label} (${r.code})</option>`).join('');
}

async function submitAssignRole() {
    const userIdInput = document.getElementById('role-assign-user-id');
    const select = document.getElementById('role-assign-select');
    const feedback = document.getElementById('role-assign-feedback');
    const userId = (userIdInput.value || '').trim();
    const roleCode = select.value || null;

    if (!userId) {
        feedback.className = 'mt-2 small text-danger';
        feedback.textContent = "Renseignez l'ID (UUID) de l'administrateur cible.";
        return;
    }

    try {
        const res = await adminFetch(`/api/admin/users/${userId}/role`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ role_code: roleCode }),
        });
        const data = await res.json().catch(() => ({}));
        if (res.ok) {
            feedback.className = 'mt-2 small text-success';
            feedback.textContent = data.message || 'Rôle mis à jour avec succès.';
            await loadSecurityTab();
        } else {
            feedback.className = 'mt-2 small text-danger';
            feedback.textContent = data.detail || "Échec de l'assignation du rôle.";
        }
    } catch (err) {
        feedback.className = 'mt-2 small text-danger';
        feedback.textContent = 'Erreur réseau lors de l\'assignation.';
    }
}

// =========================================================================
// SÉCURITÉ DE MON COMPTE — 2FA (TOTP)
// =========================================================================

async function loadMyAccountSecurity() {
    const badge = document.getElementById('totp-status-badge');
    const enableSection = document.getElementById('totp-enable-section');
    const disableSection = document.getElementById('totp-disable-section');
    if (!badge || !enableSection || !disableSection) return;

    try {
        const res = await adminFetch('/api/auth/me');
        if (!res.ok) return;
        const me = await res.json();

        if (me.totp_enabled) {
            badge.innerHTML = '<span class="badge bg-success-subtle text-success"><i class="iconoir-check-circle me-1"></i>2FA activée</span>';
            enableSection.classList.add('d-none');
            disableSection.classList.remove('d-none');
        } else {
            badge.innerHTML = '<span class="badge bg-warning-subtle text-warning"><i class="iconoir-warning-triangle me-1"></i>2FA désactivée</span>';
            enableSection.classList.remove('d-none');
            disableSection.classList.add('d-none');
            document.getElementById('totp-setup-block').classList.add('d-none');
        }
    } catch (err) {
        console.error('Erreur chargement statut 2FA:', err);
    }
}

async function startTotpSetup() {
    const feedback = document.getElementById('totp-feedback');
    feedback.textContent = '';
    try {
        const res = await adminFetch('/api/auth/totp/setup', { method: 'POST' });
        const data = await res.json().catch(() => ({}));
        if (res.ok) {
            document.getElementById('totp-secret-display').textContent = data.secret;
            document.getElementById('totp-setup-block').classList.remove('d-none');
            document.getElementById('totp-enable-code').focus();
        } else {
            feedback.className = 'mt-2 small text-danger';
            feedback.textContent = data.detail || 'Impossible de générer le secret TOTP.';
        }
    } catch (err) {
        feedback.className = 'mt-2 small text-danger';
        feedback.textContent = 'Erreur réseau.';
    }
}

async function confirmTotpEnable() {
    const feedback = document.getElementById('totp-feedback');
    const code = (document.getElementById('totp-enable-code').value || '').trim();
    if (!code) {
        feedback.className = 'mt-2 small text-danger';
        feedback.textContent = 'Entrez le code à 6 chiffres affiché par votre application.';
        return;
    }
    try {
        const res = await adminFetch('/api/auth/totp/enable', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code }),
        });
        if (res.ok) {
            feedback.className = 'mt-2 small text-success';
            feedback.textContent = '2FA activée avec succès.';
            document.getElementById('totp-enable-code').value = '';
            await loadMyAccountSecurity();
        } else {
            const data = await res.json().catch(() => ({}));
            feedback.className = 'mt-2 small text-danger';
            feedback.textContent = data.detail || 'Code invalide.';
        }
    } catch (err) {
        feedback.className = 'mt-2 small text-danger';
        feedback.textContent = 'Erreur réseau.';
    }
}

async function confirmTotpDisable() {
    const feedback = document.getElementById('totp-feedback');
    const code = (document.getElementById('totp-disable-code').value || '').trim();
    if (!code) {
        feedback.className = 'mt-2 small text-danger';
        feedback.textContent = 'Entrez un code valide pour confirmer la désactivation.';
        return;
    }
    try {
        const res = await adminFetch('/api/auth/totp/disable', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code }),
        });
        if (res.ok) {
            feedback.className = 'mt-2 small text-success';
            feedback.textContent = '2FA désactivée.';
            document.getElementById('totp-disable-code').value = '';
            await loadMyAccountSecurity();
        } else {
            const data = await res.json().catch(() => ({}));
            feedback.className = 'mt-2 small text-danger';
            feedback.textContent = data.detail || 'Code invalide.';
        }
    } catch (err) {
        feedback.className = 'mt-2 small text-danger';
        feedback.textContent = 'Erreur réseau.';
    }
}

function renderAuditLog(logs) {
    const tbody = document.getElementById('audit-log-tbody');
    if (!tbody) return;

    if (!logs || logs.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted py-3">Aucune action enregistrée pour le moment.</td></tr>';
        return;
    }

    tbody.innerHTML = logs.map(entry => {
        const date = entry.created_at ? new Date(entry.created_at).toLocaleString('fr-FR') : '—';
        const actor = entry.actor_id ? entry.actor_id.slice(0, 8) + '…' : 'système';
        const resource = entry.resource_type + (entry.resource_id ? ` (${entry.resource_id.slice(0, 8)}…)` : '');
        return `
            <tr>
                <td class="text-muted small">${date}</td>
                <td class="font-monospace small" title="${escapeHtml(entry.actor_id || '')}">${escapeHtml(actor)}</td>
                <td><span class="badge bg-light text-dark">${escapeHtml(entry.action)}</span></td>
                <td class="text-muted small">${escapeHtml(resource)}</td>
            </tr>
        `;
    }).join('');
}

// =========================================================================
// 9. MODULE ACTUALITÉS & CENTRE DE NOTIFICATIONS
// =========================================================================

let actualitesStatusFilter = '';
let metiersCache = null;
let actuCategoriesCache = null;

// Peuple les <select> "Métier ciblé" (actualités + notifications) et
// "Catégorie" à partir des données de référence réelles (module Paramètres)
// plutôt que de faire saisir un ID numérique ou figer une liste en dur.
async function populateMetierSelects() {
    if (!metiersCache) {
        try {
            const res = await adminFetch('/api/admin/metiers');
            if (res.ok) {
                const data = await res.json();
                metiersCache = data.metiers || [];
                const optionsHtml = '<option value="">Tous les métiers</option>' + metiersCache.map(m =>
                    `<option value="${m.id}">${escapeHtml(m.nom)}${m.is_active ? '' : ' (désactivé)'}</option>`
                ).join('');
                ['actu-metier', 'notif-metier'].forEach(id => {
                    const sel = document.getElementById(id);
                    if (sel) sel.innerHTML = optionsHtml;
                });
            }
        } catch (err) {
            console.error('Erreur chargement de la liste des métiers:', err);
        }
    }

    if (!actuCategoriesCache) {
        try {
            const res = await adminFetch('/api/admin/actualites/categories');
            if (res.ok) {
                const data = await res.json();
                actuCategoriesCache = data.categories || [];
                const sel = document.getElementById('actu-category');
                if (sel && actuCategoriesCache.length > 0) {
                    sel.innerHTML = actuCategoriesCache.map(c =>
                        `<option value="${escapeHtml(c.code)}">${escapeHtml(c.label)}</option>`
                    ).join('');
                }
            }
        } catch (err) {
            console.error('Erreur chargement des catégories d\'actualité:', err);
        }
    }
}

function metierLabelFor(metierId) {
    if (!metierId) return 'Tous métiers';
    const m = metiersCache && metiersCache.find(x => x.id === metierId);
    return m ? m.nom : `Métier #${metierId}`;
}

function categorieLabelFor(code) {
    const c = actuCategoriesCache && actuCategoriesCache.find(x => x.code === code);
    if (c) return c.label;
    return CATEGORY_LABELS[code] || code;
}

async function loadActualitesTab() {
    try {
        const params = actualitesStatusFilter ? `?statut=${actualitesStatusFilter}` : '';
        await populateMetierSelects();
        const [actuRes, suggestRes] = await Promise.all([
            adminFetch(`/api/admin/actualites${params}`),
            adminFetch('/api/admin/actualites/suggestions'),
        ]);

        if (actuRes.ok) {
            const actualites = await actuRes.json();
            renderActualitesList(actualites);
        } else if (actuRes.status === 403) {
            const list = document.getElementById('actualites-list');
            if (list) list.innerHTML = '<p class="text-muted mb-0">Votre rôle ne donne pas accès aux actualités.</p>';
        }

        if (suggestRes.ok) {
            const data = await suggestRes.json();
            const container = document.getElementById('actualites-suggestions');
            if (container) {
                const suggestions = data.suggestions || [];
                container.innerHTML = suggestions.length === 0
                    ? '<em>Aucune suggestion pour le moment.</em>'
                    : suggestions.map(s => `<div>Conversation ${s.conversation_id.slice(0, 8)}… — ${s.feedbacks_negatifs} retour(s) négatif(s)</div>`).join('');
            }
        }

        await loadBroadcastHistory();
    } catch (err) {
        console.error('Erreur chargement onglet actualités:', err);
    }
}

function filterActualitesByStatus(statut, btnEl) {
    actualitesStatusFilter = statut;
    document.querySelectorAll('#actu-status-filter .nav-link').forEach(el => el.classList.remove('active'));
    if (btnEl) btnEl.classList.add('active');
    loadActualitesTab();
}

const STATUT_BADGES = {
    brouillon: '<span class="badge bg-secondary-subtle text-secondary">Brouillon</span>',
    programme: '<span class="badge bg-info-subtle text-info">Programmée</span>',
    publie: '<span class="badge bg-success-subtle text-success">Publiée</span>',
    archive: '<span class="badge bg-dark-subtle text-dark">Archivée</span>',
};

// Repli statique tant que `actuCategoriesCache` (module Paramètres) n'est pas
// encore chargé — les codes historiques restent lisibles même hors ligne.
const CATEGORY_LABELS = {
    annonce: 'Annonce',
    maintenance: 'Maintenance',
    conseil: 'Conseil',
    promotion: 'Promotion',
};

function renderActualitesList(actualites) {
    const container = document.getElementById('actualites-list');
    if (!container) return;

    if (!actualites || actualites.length === 0) {
        container.innerHTML = '<p class="text-muted mb-0">Aucune actualité pour ce filtre.</p>';
        return;
    }

    container.innerHTML = actualites.map(a => {
        const badge = STATUT_BADGES[a.statut] || '';
        const categoryLabel = categorieLabelFor(a.category);
        const metierLabel = metierLabelFor(a.metier_id);
        const scheduledLabel = a.statut === 'programme' && a.scheduled_at
            ? ` • Programmée pour le ${new Date(a.scheduled_at).toLocaleString()}`
            : '';

        const actions = [];
        if (a.statut === 'brouillon' || a.statut === 'programme') {
            actions.push(`<button type="button" class="btn btn-sm btn-outline-success" onclick="publishActualite('${a.id}')">Publier</button>`);
            actions.push(`<button type="button" class="btn btn-sm btn-outline-info" onclick="openScheduleModal('${a.id}')">Programmer</button>`);
        }
        if (a.statut === 'publie') {
            actions.push(`<button type="button" class="btn btn-sm btn-outline-warning" onclick="unpublishActualite('${a.id}')">Dépublier</button>`);
        }
        if (a.statut !== 'archive') {
            actions.push(`<button type="button" class="btn btn-sm btn-outline-secondary" onclick="archiveActualite('${a.id}')">Archiver</button>`);
        }
        actions.push(`<button type="button" class="btn btn-sm btn-outline-danger" onclick="deleteActualitePrompt('${a.id}')" title="Supprimer cette actualité" aria-label="Supprimer cette actualité"><i class="iconoir-trash"></i></button>`);

        return `
            <div class="border-bottom py-2">
                <div class="d-flex justify-content-between align-items-start flex-wrap gap-1">
                    <div>
                        <span class="fw-semibold">${escapeHtml(a.titre)}</span> ${badge}
                        <span class="badge bg-light text-dark border">${categoryLabel}</span>
                        <br><small class="text-muted">${metierLabel}${scheduledLabel}</small>
                    </div>
                    <div class="d-flex gap-1 flex-wrap">${actions.join('')}</div>
                </div>
                <p class="mb-0 text-muted small mt-1">${escapeHtml(a.contenu)}</p>
            </div>
        `;
    }).join('');
}

window.openCreateActualiteForm = function() {
    document.getElementById('actualite-form').classList.remove('d-none');
};

window.closeCreateActualiteForm = function() {
    document.getElementById('actualite-form').classList.add('d-none');
    document.getElementById('actu-titre').value = '';
    document.getElementById('actu-contenu').value = '';
    document.getElementById('actu-metier').value = '';
    document.getElementById('actu-category').value = 'annonce';
    document.getElementById('actu-audience').value = 'tous';
};

window.submitCreateActualite = async function() {
    const titre = document.getElementById('actu-titre').value.trim();
    const contenu = document.getElementById('actu-contenu').value.trim();
    const metierRaw = document.getElementById('actu-metier').value.trim();
    const category = document.getElementById('actu-category').value;
    const targetAudience = document.getElementById('actu-audience').value;
    if (!titre || !contenu) {
        alert('Titre et contenu sont requis.');
        return;
    }
    try {
        const res = await adminFetch('/api/admin/actualites', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                titre,
                contenu,
                metier_id: metierRaw ? parseInt(metierRaw, 10) : null,
                category,
                target_audience: targetAudience,
            }),
        });
        if (res.ok) {
            closeCreateActualiteForm();
            await loadActualitesTab();
        } else {
            const err = await res.json().catch(() => ({}));
            alert(err.detail || 'Erreur lors de la création.');
        }
    } catch (e) {
        alert('Erreur réseau');
    }
};

window.publishActualite = async function(id) {
    const notifier = confirm('Notifier les artisans concernés lors de la publication ?');
    try {
        const res = await adminFetch(`/api/admin/actualites/${id}/publish`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ notifier_artisans: notifier }),
        });
        if (res.ok) {
            await loadActualitesTab();
        } else {
            alert("Échec de la publication.");
        }
    } catch (e) {
        alert('Erreur réseau');
    }
};

window.unpublishActualite = async function(id) {
    try {
        const res = await adminFetch(`/api/admin/actualites/${id}/unpublish`, { method: 'POST' });
        if (res.ok) {
            await loadActualitesTab();
        } else {
            alert('Échec de la dépublication.');
        }
    } catch (e) {
        alert('Erreur réseau');
    }
};

window.archiveActualite = async function(id) {
    try {
        const res = await adminFetch(`/api/admin/actualites/${id}/archive`, { method: 'POST' });
        if (res.ok) {
            await loadActualitesTab();
        } else {
            alert("Échec de l'archivage.");
        }
    } catch (e) {
        alert('Erreur réseau');
    }
};

window.deleteActualitePrompt = async function(id) {
    if (!confirm('Supprimer définitivement cette actualité ?')) return;
    try {
        const res = await adminFetch(`/api/admin/actualites/${id}`, { method: 'DELETE' });
        if (res.ok) {
            await loadActualitesTab();
        } else {
            alert('Échec de la suppression.');
        }
    } catch (e) {
        alert('Erreur réseau');
    }
};

// --- Modale de programmation ---
let scheduleModalInstance = null;

window.openScheduleModal = function(id) {
    document.getElementById('schedule-actualite-id').value = id;
    document.getElementById('schedule-actualite-datetime').value = '';
    document.getElementById('schedule-actualite-feedback').textContent = '';
    if (!scheduleModalInstance) {
        scheduleModalInstance = new bootstrap.Modal(document.getElementById('modal-schedule-actualite'));
    }
    scheduleModalInstance.show();
};

window.closeScheduleModal = function() {
    if (scheduleModalInstance) scheduleModalInstance.hide();
};

window.submitScheduleActualite = async function() {
    const id = document.getElementById('schedule-actualite-id').value;
    const dtValue = document.getElementById('schedule-actualite-datetime').value;
    const feedback = document.getElementById('schedule-actualite-feedback');
    if (!dtValue) {
        feedback.className = 'mt-2 small text-danger';
        feedback.textContent = 'Choisissez une date et une heure.';
        return;
    }
    try {
        const res = await adminFetch(`/api/admin/actualites/${id}/schedule`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ scheduled_at: new Date(dtValue).toISOString() }),
        });
        const data = await res.json().catch(() => ({}));
        if (res.ok) {
            closeScheduleModal();
            await loadActualitesTab();
        } else {
            feedback.className = 'mt-2 small text-danger';
            feedback.textContent = data.detail || 'Échec de la programmation.';
        }
    } catch (e) {
        feedback.className = 'mt-2 small text-danger';
        feedback.textContent = 'Erreur réseau.';
    }
};

window.submitBroadcastNotification = async function() {
    const title = document.getElementById('notif-title').value.trim();
    const body = document.getElementById('notif-body').value.trim();
    const metierRaw = document.getElementById('notif-metier').value.trim();
    const targetAudience = document.getElementById('notif-audience').value;
    const feedback = document.getElementById('notif-broadcast-feedback');

    if (!title || !body) {
        feedback.className = 'mt-2 small text-danger';
        feedback.textContent = 'Titre et message sont requis.';
        return;
    }

    try {
        const res = await adminFetch('/api/admin/notifications/broadcast', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                title,
                body,
                metier_id: metierRaw ? parseInt(metierRaw, 10) : null,
                channel: 'in_app',
                target_audience: targetAudience,
            }),
        });
        const data = await res.json().catch(() => ({}));
        if (res.ok) {
            feedback.className = 'mt-2 small text-success';
            feedback.textContent = `Diffusion lancée vers ${data.cible_count} artisan(s).`;
            document.getElementById('notif-title').value = '';
            document.getElementById('notif-body').value = '';
            document.getElementById('notif-metier').value = '';
            document.getElementById('notif-audience').value = 'tous';
            await loadBroadcastHistory();
        } else {
            feedback.className = 'mt-2 small text-danger';
            feedback.textContent = data.detail || 'Échec de la diffusion.';
        }
    } catch (e) {
        feedback.className = 'mt-2 small text-danger';
        feedback.textContent = 'Erreur réseau.';
    }
};

// --- Historique des diffusions (dérivé du journal d'audit existant) ---
async function loadBroadcastHistory() {
    const container = document.getElementById('broadcast-history-list');
    if (!container) return;
    try {
        const res = await adminFetch('/api/admin/audit-logs?action=notification.broadcast&resource_type=notification&limit=20');
        if (!res.ok) {
            if (res.status === 403) {
                container.innerHTML = '<p class="text-muted small p-2 mb-0">Votre rôle ne donne pas accès à l\'historique.</p>';
            }
            return;
        }
        const logs = await res.json();
        if (!logs || logs.length === 0) {
            container.innerHTML = '<p class="text-muted small p-2 mb-0">Aucune diffusion envoyée pour le moment.</p>';
            return;
        }
        container.innerHTML = logs.map(l => {
            const after = l.after_json || {};
            const audienceLabel = { tous: 'Tous', abonnes_payants: 'Abonnés payants', gratuits: 'Gratuits' }[after.target_audience] || after.target_audience || 'Tous';
            const metierLabel = metierLabelFor(after.metier_id);
            return `
                <div class="border-bottom px-2 py-2">
                    <div class="fw-semibold">${escapeHtml(after.titre || '(sans titre)')}</div>
                    <div class="text-muted">${escapeHtml(new Date(l.created_at).toLocaleString())} • ${escapeHtml(metierLabel)} • ${escapeHtml(audienceLabel)}</div>
                    <div class="text-muted">${escapeHtml(after.cible_count ?? '?')} destinataire(s) • canal ${escapeHtml(after.channel || 'in_app')}</div>
                </div>
            `;
        }).join('');
    } catch (err) {
        console.error('Erreur chargement historique diffusions:', err);
    }
}

// =========================================================================
// 10. MODULE PARAMÈTRES (données de référence : métiers, sous-métiers,
//     catégories d'actualités — alimentent les listes de choix ci-dessus)
// =========================================================================

let parametresMetiersCache = null;
let parametresCategoriesCache = null;

async function loadParametresTab() {
    try {
        const [metiersRes, categoriesRes] = await Promise.all([
            adminFetch('/api/admin/parametres/metiers'),
            adminFetch('/api/admin/parametres/actualite-categories'),
        ]);

        if (metiersRes.ok) {
            parametresMetiersCache = await metiersRes.json();
            renderMetiersTable(parametresMetiersCache);
            renderSousMetiersTable(parametresMetiersCache);
            populateSousMetierSelect();
        } else if (metiersRes.status === 403) {
            const msg = '<tr><td colspan="4" class="text-muted">Votre rôle ne donne pas accès au module Paramètres.</td></tr>';
            const mt = document.getElementById('metiers-tbody');
            const st = document.getElementById('sous-metiers-tbody');
            if (mt) mt.innerHTML = msg;
            if (st) st.innerHTML = '<tr><td colspan="3" class="text-muted">—</td></tr>';
        }

        if (categoriesRes.ok) {
            parametresCategoriesCache = await categoriesRes.json();
            renderCategoriesTable(parametresCategoriesCache);
        } else if (categoriesRes.status === 403) {
            const ct = document.getElementById('categories-tbody');
            if (ct) ct.innerHTML = '<tr><td colspan="4" class="text-muted">Votre rôle ne donne pas accès au module Paramètres.</td></tr>';
        }
    } catch (err) {
        console.error('Erreur chargement onglet Paramètres:', err);
    }
}

// --- Métiers ---
function renderMetiersTable(metiers) {
    const tbody = document.getElementById('metiers-tbody');
    if (!tbody) return;
    if (!metiers || metiers.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="text-muted">Aucun métier.</td></tr>';
        return;
    }
    tbody.innerHTML = metiers.map(m => `
        <tr>
            <td>
                <div class="fw-semibold">${escapeHtml(m.nom)}</div>
                <div class="text-muted small">${escapeHtml(m.slug)}</div>
            </td>
            <td>${(m.sous_metiers || []).length}</td>
            <td>${m.is_active ? '<span class="badge bg-success-subtle text-success">Actif</span>' : '<span class="badge bg-secondary-subtle text-secondary">Désactivé</span>'}</td>
            <td class="text-nowrap">
                <button type="button" class="btn btn-sm btn-outline-secondary" onclick="openMetierForm(${m.id})" title="Modifier" aria-label="Modifier ${m.nom}"><i class="iconoir-edit-pencil"></i></button>
                <button type="button" class="btn btn-sm btn-outline-warning" onclick="toggleMetierActive(${m.id})" title="${m.is_active ? 'Désactiver' : 'Activer'}" aria-label="${m.is_active ? 'Désactiver' : 'Activer'} ${m.nom}"><i class="iconoir-${m.is_active ? 'eye-off' : 'eye'}"></i></button>
                <button type="button" class="btn btn-sm btn-outline-danger" onclick="deleteMetierPrompt(${m.id})" title="Supprimer" aria-label="Supprimer ${m.nom}"><i class="iconoir-trash"></i></button>
            </td>
        </tr>
    `).join('');
}

window.openMetierForm = function(metierId) {
    const form = document.getElementById('metier-form');
    const feedback = document.getElementById('metier-form-feedback');
    feedback.textContent = '';
    if (metierId) {
        const m = (parametresMetiersCache || []).find(x => x.id === metierId);
        if (!m) return;
        document.getElementById('metier-form-id').value = m.id;
        document.getElementById('metier-form-nom').value = m.nom;
        document.getElementById('metier-form-slug').value = m.slug;
        document.getElementById('metier-form-description').value = m.description || '';
    } else {
        document.getElementById('metier-form-id').value = '';
        document.getElementById('metier-form-nom').value = '';
        document.getElementById('metier-form-slug').value = '';
        document.getElementById('metier-form-description').value = '';
    }
    form.classList.remove('d-none');
};

window.closeMetierForm = function() {
    document.getElementById('metier-form').classList.add('d-none');
};

window.submitMetierForm = async function() {
    const id = document.getElementById('metier-form-id').value;
    const nom = document.getElementById('metier-form-nom').value.trim();
    const slug = document.getElementById('metier-form-slug').value.trim();
    const description = document.getElementById('metier-form-description').value.trim();
    const feedback = document.getElementById('metier-form-feedback');
    if (!nom || !slug) {
        feedback.className = 'mt-2 small text-danger';
        feedback.textContent = 'Nom et slug sont requis.';
        return;
    }
    try {
        const res = id
            ? await adminFetch(`/api/admin/parametres/metiers/${id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ nom, slug, description: description || null }),
            })
            : await adminFetch('/api/admin/parametres/metiers', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ nom, slug, description: description || null }),
            });
        const data = await res.json().catch(() => ({}));
        if (res.ok) {
            closeMetierForm();
            metiersCache = null; // invalide les <select> "Métier ciblé" du module Communication
            await loadParametresTab();
        } else {
            feedback.className = 'mt-2 small text-danger';
            feedback.textContent = data.detail || 'Erreur lors de l\'enregistrement.';
        }
    } catch (e) {
        feedback.className = 'mt-2 small text-danger';
        feedback.textContent = 'Erreur réseau.';
    }
};

window.toggleMetierActive = async function(id) {
    try {
        const res = await adminFetch(`/api/admin/parametres/metiers/${id}/toggle`, { method: 'PATCH' });
        if (res.ok) {
            metiersCache = null;
            await loadParametresTab();
        } else {
            alert('Échec de la mise à jour du statut.');
        }
    } catch (e) {
        alert('Erreur réseau');
    }
};

window.deleteMetierPrompt = async function(id) {
    if (!confirm('Supprimer définitivement ce métier ? Cette action est refusée s\'il est encore utilisé.')) return;
    try {
        const res = await adminFetch(`/api/admin/parametres/metiers/${id}`, { method: 'DELETE' });
        const data = await res.json().catch(() => ({}));
        if (res.ok) {
            metiersCache = null;
            await loadParametresTab();
        } else {
            alert(data.detail || 'Échec de la suppression.');
        }
    } catch (e) {
        alert('Erreur réseau');
    }
};

// --- Sous-métiers ---
function renderSousMetiersTable(metiers) {
    const tbody = document.getElementById('sous-metiers-tbody');
    if (!tbody) return;
    const rows = [];
    (metiers || []).forEach(m => {
        (m.sous_metiers || []).forEach(sm => rows.push({ ...sm, metierNom: m.nom }));
    });
    if (rows.length === 0) {
        tbody.innerHTML = '<tr><td colspan="3" class="text-muted">Aucun sous-métier.</td></tr>';
        return;
    }
    tbody.innerHTML = rows.map(sm => `
        <tr>
            <td>
                <div class="fw-semibold">${escapeHtml(sm.nom)}</div>
                <div class="text-muted small">${escapeHtml(sm.slug)}</div>
            </td>
            <td>${escapeHtml(sm.metierNom)}</td>
            <td class="text-nowrap">
                <button type="button" class="btn btn-sm btn-outline-secondary" onclick="openSousMetierForm(${sm.id})" title="Modifier" aria-label="Modifier ${sm.nom}"><i class="iconoir-edit-pencil"></i></button>
                <button type="button" class="btn btn-sm btn-outline-danger" onclick="deleteSousMetierPrompt(${sm.id})" title="Supprimer" aria-label="Supprimer ${sm.nom}"><i class="iconoir-trash"></i></button>
            </td>
        </tr>
    `).join('');
}

function populateSousMetierSelect() {
    const sel = document.getElementById('sm-form-metier');
    if (!sel) return;
    sel.innerHTML = (parametresMetiersCache || []).map(m => `<option value="${m.id}">${escapeHtml(m.nom)}</option>`).join('');
}

window.openSousMetierForm = function(sousMetierId) {
    populateSousMetierSelect();
    const form = document.getElementById('sous-metier-form');
    const feedback = document.getElementById('sous-metier-form-feedback');
    feedback.textContent = '';
    if (sousMetierId) {
        let found = null;
        (parametresMetiersCache || []).forEach(m => {
            (m.sous_metiers || []).forEach(sm => { if (sm.id === sousMetierId) found = sm; });
        });
        if (!found) return;
        document.getElementById('sm-form-id').value = found.id;
        document.getElementById('sm-form-metier').value = found.metier_id;
        document.getElementById('sm-form-nom').value = found.nom;
        document.getElementById('sm-form-slug').value = found.slug;
    } else {
        document.getElementById('sm-form-id').value = '';
        document.getElementById('sm-form-nom').value = '';
        document.getElementById('sm-form-slug').value = '';
    }
    form.classList.remove('d-none');
};

window.closeSousMetierForm = function() {
    document.getElementById('sous-metier-form').classList.add('d-none');
};

window.submitSousMetierForm = async function() {
    const id = document.getElementById('sm-form-id').value;
    const metierId = document.getElementById('sm-form-metier').value;
    const nom = document.getElementById('sm-form-nom').value.trim();
    const slug = document.getElementById('sm-form-slug').value.trim();
    const feedback = document.getElementById('sous-metier-form-feedback');
    if (!metierId || !nom || !slug) {
        feedback.className = 'mt-2 small text-danger';
        feedback.textContent = 'Métier, nom et slug sont requis.';
        return;
    }
    try {
        const res = id
            ? await adminFetch(`/api/admin/parametres/sous-metiers/${id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ nom, slug }),
            })
            : await adminFetch('/api/admin/parametres/sous-metiers', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ metier_id: parseInt(metierId, 10), nom, slug }),
            });
        const data = await res.json().catch(() => ({}));
        if (res.ok) {
            closeSousMetierForm();
            await loadParametresTab();
        } else {
            feedback.className = 'mt-2 small text-danger';
            feedback.textContent = data.detail || 'Erreur lors de l\'enregistrement.';
        }
    } catch (e) {
        feedback.className = 'mt-2 small text-danger';
        feedback.textContent = 'Erreur réseau.';
    }
};

window.deleteSousMetierPrompt = async function(id) {
    if (!confirm('Supprimer cette spécialité ? Cette action est refusée si des artisans la référencent encore.')) return;
    try {
        const res = await adminFetch(`/api/admin/parametres/sous-metiers/${id}`, { method: 'DELETE' });
        const data = await res.json().catch(() => ({}));
        if (res.ok) {
            await loadParametresTab();
        } else {
            alert(data.detail || 'Échec de la suppression.');
        }
    } catch (e) {
        alert('Erreur réseau');
    }
};

// --- Catégories d'actualités ---
function renderCategoriesTable(categories) {
    const tbody = document.getElementById('categories-tbody');
    if (!tbody) return;
    if (!categories || categories.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="text-muted">Aucune catégorie.</td></tr>';
        return;
    }
    tbody.innerHTML = categories.map(c => `
        <tr>
            <td class="font-monospace small">${escapeHtml(c.code)}</td>
            <td>${escapeHtml(c.label)}</td>
            <td>${c.is_active ? '<span class="badge bg-success-subtle text-success">Active</span>' : '<span class="badge bg-secondary-subtle text-secondary">Désactivée</span>'}</td>
            <td class="text-nowrap">
                <button type="button" class="btn btn-sm btn-outline-secondary" onclick="openCategorieForm(${c.id})" title="Modifier" aria-label="Modifier ${c.label}"><i class="iconoir-edit-pencil"></i></button>
                <button type="button" class="btn btn-sm btn-outline-warning" onclick="toggleCategorieActive(${c.id})" title="${c.is_active ? 'Désactiver' : 'Activer'}" aria-label="${c.is_active ? 'Désactiver' : 'Activer'} ${c.label}"><i class="iconoir-${c.is_active ? 'eye-off' : 'eye'}"></i></button>
                <button type="button" class="btn btn-sm btn-outline-danger" onclick="deleteCategoriePrompt(${c.id})" title="Supprimer" aria-label="Supprimer ${c.label}"><i class="iconoir-trash"></i></button>
            </td>
        </tr>
    `).join('');
}

window.openCategorieForm = function(categorieId) {
    const form = document.getElementById('categorie-form');
    const feedback = document.getElementById('categorie-form-feedback');
    const codeInput = document.getElementById('cat-form-code');
    feedback.textContent = '';
    if (categorieId) {
        const c = (parametresCategoriesCache || []).find(x => x.id === categorieId);
        if (!c) return;
        document.getElementById('cat-form-id').value = c.id;
        codeInput.value = c.code;
        codeInput.disabled = true;
        document.getElementById('cat-form-label').value = c.label;
    } else {
        document.getElementById('cat-form-id').value = '';
        codeInput.value = '';
        codeInput.disabled = false;
        document.getElementById('cat-form-label').value = '';
    }
    form.classList.remove('d-none');
};

window.closeCategorieForm = function() {
    document.getElementById('categorie-form').classList.add('d-none');
    document.getElementById('cat-form-code').disabled = false;
};

window.submitCategorieForm = async function() {
    const id = document.getElementById('cat-form-id').value;
    const code = document.getElementById('cat-form-code').value.trim();
    const label = document.getElementById('cat-form-label').value.trim();
    const feedback = document.getElementById('categorie-form-feedback');
    if (!label || (!id && !code)) {
        feedback.className = 'mt-2 small text-danger';
        feedback.textContent = 'Code et libellé sont requis.';
        return;
    }
    try {
        const res = id
            ? await adminFetch(`/api/admin/parametres/actualite-categories/${id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ label }),
            })
            : await adminFetch('/api/admin/parametres/actualite-categories', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code, label }),
            });
        const data = await res.json().catch(() => ({}));
        if (res.ok) {
            closeCategorieForm();
            actuCategoriesCache = null; // invalide le <select> "Catégorie" du formulaire actualité
            await loadParametresTab();
        } else {
            feedback.className = 'mt-2 small text-danger';
            feedback.textContent = data.detail || 'Erreur lors de l\'enregistrement.';
        }
    } catch (e) {
        feedback.className = 'mt-2 small text-danger';
        feedback.textContent = 'Erreur réseau.';
    }
};

window.toggleCategorieActive = async function(id) {
    try {
        const res = await adminFetch(`/api/admin/parametres/actualite-categories/${id}/toggle`, { method: 'PATCH' });
        if (res.ok) {
            actuCategoriesCache = null;
            await loadParametresTab();
        } else {
            alert('Échec de la mise à jour du statut.');
        }
    } catch (e) {
        alert('Erreur réseau');
    }
};

window.deleteCategoriePrompt = async function(id) {
    if (!confirm('Supprimer définitivement cette catégorie ?')) return;
    try {
        const res = await adminFetch(`/api/admin/parametres/actualite-categories/${id}`, { method: 'DELETE' });
        const data = await res.json().catch(() => ({}));
        if (res.ok) {
            actuCategoriesCache = null;
            await loadParametresTab();
        } else {
            alert(data.detail || 'Échec de la suppression.');
        }
    } catch (e) {
        alert('Erreur réseau');
    }
};

// =========================================================================
// DEVIS & CALCULATEURS MÉTIER DÉTERMINISTES — BACK-OFFICE
// =========================================================================

async function loadQuotesAndCalculatorsTab() {
    await Promise.all([
        loadAdminQuotes(),
        loadCalculatorsStats()
    ]);
}

window.loadAdminQuotes = async function() {
    const tbody = document.getElementById('admin-quotes-tbody');
    const kpiTotal = document.getElementById('kpi-quotes-total');
    const kpiHt = document.getElementById('kpi-quotes-volume-ht');
    const kpiTtc = document.getElementById('kpi-quotes-volume-ttc');

    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="8" class="text-center py-3 text-muted"><div class="spinner-border spinner-border-sm text-primary me-2"></div>Chargement des devis...</td></tr>';

    try {
        const res = await adminFetch('/api/admin/quotes?limit=50');
        if (!res.ok) {
            tbody.innerHTML = '<tr><td colspan="8" class="text-center py-3 text-danger">Impossible de charger les devis.</td></tr>';
            return;
        }

        const data = await res.json();
        const stats = data.stats || {};
        if (kpiTotal) kpiTotal.textContent = (stats.total_quotes_count || 0).toLocaleString('fr-FR');
        if (kpiHt) kpiHt.textContent = `${Math.round(stats.total_montant_ht || 0).toLocaleString('fr-FR')} F`;
        if (kpiTtc) kpiTtc.textContent = `${Math.round(stats.total_montant_ttc || 0).toLocaleString('fr-FR')} F`;

        const quotes = data.quotes || [];
        if (quotes.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="text-center py-4 text-muted">Aucun devis créé pour le moment.</td></tr>';
            return;
        }

        tbody.innerHTML = '';
        quotes.forEach(q => {
            const tr = document.createElement('tr');
            const dateStr = q.created_at ? new Date(q.created_at).toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '-';
            
            let statusBadge = '<span class="badge bg-secondary">Brouillon</span>';
            if (q.statut === 'ENVOYE') statusBadge = '<span class="badge bg-info">Envoyé</span>';
            else if (q.statut === 'ACCEPTE') statusBadge = '<span class="badge bg-success">Accepté</span>';
            else if (q.statut === 'FACTURE') statusBadge = '<span class="badge bg-primary">Facturé</span>';
            else if (q.statut === 'REFUSE' || q.statut === 'ANNULE') statusBadge = '<span class="badge bg-danger">Annulé</span>';

            tr.innerHTML = `
                <td class="fw-bold text-primary font-monospace">${escapeHtml(q.numero || 'DEV')}</td>
                <td>
                    <div class="fw-medium">${escapeHtml(q.client_nom || 'Client')}</div>
                    ${q.client_telephone ? `<small class="text-muted">${escapeHtml(q.client_telephone)}</small>` : ''}
                </td>
                <td class="text-truncate" style="max-width: 180px;" title="${escapeHtml(q.titre || '')}">${escapeHtml(q.titre || 'Devis')}</td>
                <td class="fw-semibold">${(q.total_ht || 0).toLocaleString('fr-FR')} F</td>
                <td class="fw-bold text-dark">${(q.total_ttc || 0).toLocaleString('fr-FR')} F</td>
                <td>${statusBadge}</td>
                <td class="small text-muted">${dateStr}</td>
                <td>
                    <a href="/api/quotes/${q.id}/html" target="_blank" class="btn btn-sm btn-outline-secondary" title="Voir version imprimable">
                        <i class="iconoir-eye"></i>
                    </a>
                </td>
            `;
            tbody.appendChild(tr);
        });

    } catch (err) {
        console.error("Erreur chargement devis admin:", err);
        tbody.innerHTML = '<tr><td colspan="8" class="text-center py-3 text-danger">Erreur réseau.</td></tr>';
    }
};

window.loadCalculatorsStats = async function() {
    const kpiCalc = document.getElementById('kpi-calc-total');
    const countBeton = document.getElementById('calc-count-beton');
    const countCable = document.getElementById('calc-count-cable');
    const countPlomb = document.getElementById('calc-count-plomb');
    const countCarr = document.getElementById('calc-count-carr');
    const countClim = document.getElementById('calc-count-clim');

    try {
        const res = await adminFetch('/api/admin/calculators/stats');
        if (!res.ok) return;

        const data = await res.json();
        const byTool = data.by_tool || {};

        if (kpiCalc) kpiCalc.textContent = (data.total_calculator_calls || 0).toLocaleString('fr-FR');
        if (countBeton) countBeton.textContent = byTool['calculer_dosage_beton_mortier'] || 0;
        if (countCable) countCable.textContent = byTool['calculer_section_cable_nfc15100'] || 0;
        if (countPlomb) countPlomb.textContent = byTool['calculer_pente_evacuation_dtu60'] || 0;
        if (countCarr) countCarr.textContent = byTool['calculer_surface_carrelage_colle'] || 0;
        if (countClim) countClim.textContent = byTool['calculer_bilan_thermique_climatisation'] || 0;

    } catch (err) {
        console.error("Erreur chargement stats calculateurs:", err);
    }
};
