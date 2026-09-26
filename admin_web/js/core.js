// ProsArtisan Back-Office — État global, fetch admin, connexion, navigation, tableau de bord, artisans, documents, upload.
// Script classique (non module) : partage la portée globale avec les autres
// fichiers de admin_web/js/, chargés dans l'ordre par index.html.

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
    loadUploadMetiers();
    loadPromptInspector();

    // Check if already authenticated: only a 2xx response opens the dashboard.
    // Plain fetch, not adminFetch: a 401 here just means "not logged in yet";
    // adminFetch would call logoutAdmin(), whose reload re-runs this check
    // forever (infinite reload loop until the rate limiter answers 429).
    // A 429/5xx must not leave a blank page (neither login nor dashboard).
    fetch('/api/auth/me', { credentials: 'same-origin' }).then((res) => {
        if (!res.ok) {
            const err = new Error(`HTTP ${res.status}`);
            err.status = res.status;
            throw err;
        }
        document.getElementById('login-container').classList.add('d-none');
        refreshDashboard();
    }).catch((err) => {
        document.getElementById('login-container').classList.remove('d-none');
        const errMsg = document.getElementById('login-error-msg');
        if (errMsg && err && err.status && err.status !== 401 && err.status !== 403) {
            errMsg.textContent = err.status === 429
                ? 'Trop de requêtes. Patientez une minute puis réessayez.'
                : 'Serveur momentanément indisponible. Réessayez dans un instant.';
            errMsg.classList.remove('d-none');
        }
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

async function loadUploadMetiers() {
    const metierSelect = document.getElementById('metier_id');
    const secteurSelect = document.getElementById('secteur_id');
    if (!metierSelect || !secteurSelect) return;

    try {
        const res = await fetch('/api/metiers', { credentials: 'same-origin' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const metiers = await res.json();
        const options = ['<option value="">Sélectionner…</option>'].concat(
            metiers.map((metier) => `<option value="${Number(metier.id)}">${escapeHtml(metier.nom)}</option>`)
        ).join('');
        metierSelect.innerHTML = options;
        secteurSelect.innerHTML = options;
    } catch (err) {
        const unavailable = '<option value="">Référentiel indisponible</option>';
        metierSelect.innerHTML = unavailable;
        secteurSelect.innerHTML = unavailable;
    }
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
// La session admin repose sur le cookie HttpOnly (plus de jeton localStorage) :
// adminFetch renvoie vers l'écran de connexion si elle a expiré.
async function refreshDashboard() {
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
        const total = data.kpis.total_artisans || 0;
        document.getElementById('kpi-engagement').textContent = total
            ? `${Math.round((data.kpis.artisans_actifs_dau / total) * 1000) / 10}%`
            : '—';
        document.getElementById('kpi-documents').textContent = (data.kpis.total_documents_qdrant || 0).toLocaleString();
        renderSubscriptionDistribution(data.abonnements || {});

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

// Répartition réelle des abonnements (réponse de /api/admin/overview).
function renderSubscriptionDistribution(abonnements) {
    const rows = { mois: abonnements.pass_mois || 0, '24h': abonnements.pass_24h || 0, free: abonnements.free || 0 };
    const max = Math.max(...Object.values(rows), 1);
    Object.entries(rows).forEach(([key, count]) => {
        const val = document.getElementById(`sub-val-${key}`);
        const bar = document.getElementById(`sub-bar-${key}`);
        if (val) val.textContent = count.toLocaleString();
        if (bar) bar.style.width = `${(count / max) * 100}%`;
    });
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
        formData.append('secteur_id', document.getElementById('secteur_id').value);
        formData.append('type_document', document.getElementById('type_document').value);
        formData.append('niveau_expertise', document.getElementById('niveau_expertise').value);

        const btn = document.getElementById('btn-submit-upload');
        btn.textContent = '⏳ Ingestion vectorielle en cours...';
        btn.disabled = true;

        try {
            const res = await adminFetch('/api/admin/upload-pdf', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
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
