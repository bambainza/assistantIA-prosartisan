// State Variables
let selectedUserIdForGrant = null;
let grantModal = null;

// Unified Admin Fetch Wrapper
async function adminFetch(url, options = {}) {
    const token = localStorage.getItem('prosartisan_admin_token');
    if (!token) {
        logoutAdmin();
        throw new Error('Not authenticated');
    }
    
    options.headers = options.headers || {};
    options.headers['Authorization'] = `Bearer ${token}`;
    
    const res = await fetch(url, options);
    if (res.status === 401 || res.status === 403) {
        logoutAdmin();
        throw new Error('Session expired or unauthorized');
    }
    return res;
}

window.logoutAdmin = function() {
    localStorage.removeItem('prosartisan_admin_token');
    document.getElementById('login-container').classList.remove('d-none');
    window.location.reload();
};

document.addEventListener('DOMContentLoaded', () => {
    if (window.location.search.includes('logout=1')) {
        localStorage.removeItem('prosartisan_admin_token');
        window.history.replaceState({}, document.title, window.location.pathname);
    }

    initTabs();
    initLoginForm();
    initUploadForm();
    loadPromptInspector();

    // Check if already authenticated
    const token = localStorage.getItem('prosartisan_admin_token');
    if (token) {
        document.getElementById('login-container').classList.add('d-none');
        refreshDashboard();
    } else {
        document.getElementById('login-container').classList.remove('d-none');
    }
});

// Helper pour pré-remplir les identifiants démo
window.fillDemoCredentials = function(pwd = 'admin123') {
    const emailInput = document.getElementById('admin-email');
    const pwdInput = document.getElementById('admin-password');
    if (emailInput) emailInput.value = 'admin@prosartisan.ci';
    if (pwdInput) pwdInput.value = pwd;
    const errMsg = document.getElementById('login-error-msg');
    if (errMsg) errMsg.classList.add('d-none');
};

// Login Form handler
function initLoginForm() {
    const form = document.getElementById('admin-login-form');
    if (!form) return;

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = (document.getElementById('admin-email').value || '').trim();
        const password = (document.getElementById('admin-password').value || '').trim();
        const errMsg = document.getElementById('login-error-msg');
        const submitBtn = document.getElementById('btn-login-submit');

        submitBtn.disabled = true;
        submitBtn.textContent = 'Connexion...';
        errMsg.classList.add('d-none');

        try {
            const res = await fetch('/api/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password })
            });

            if (res.status === 200) {
                const data = await res.json();
                if (data.user && data.user.is_admin) {
                    localStorage.setItem('prosartisan_admin_token', data.access_token);
                    document.getElementById('login-container').classList.add('d-none');
                    refreshDashboard();
                } else {
                    errMsg.textContent = 'Accès interdit : privilèges administrateur requis.';
                    errMsg.classList.remove('d-none');
                }
            } else {
                const errData = await res.json().catch(() => ({}));
                errMsg.textContent = errData.detail || 'Identifiants incorrects.';
                errMsg.classList.remove('d-none');
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

// Tab Navigation
function initTabs() {
    const navItems = document.querySelectorAll('.nav-menu-item');
    const tabPages = document.querySelectorAll('.tab-page');
    const pageTitle = document.getElementById('page-title');

    navItems.forEach(item => {
        item.addEventListener('click', () => {
            navItems.forEach(n => n.classList.remove('active'));
            tabPages.forEach(p => p.classList.remove('active'));

            item.classList.add('active');
            const targetTab = item.getAttribute('data-tab');
            const targetEl = document.getElementById(targetTab);
            if (targetEl) targetEl.classList.add('active');

            if (item.querySelector('span')) {
                pageTitle.textContent = item.querySelector('span').textContent;
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
    await fetchTransactions();
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
                            <span>${m.nom}</span>
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
                    <td><strong>${u.nom}</strong></td>
                    <td>${u.telephone}</td>
                    <td>${u.metier}</td>
                    <td><span class="${badgeClass}">${u.type_abonnement.toUpperCase()}</span></td>
                    <td>${reqLabel}</td>
                    <td>
                        <button class="btn btn-sm btn-outline-primary" onclick="openGrantModal('${u.id}', '${u.nom}')">
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

// 5. Fetch Transactions Table
async function fetchTransactions() {
    try {
        const res = await adminFetch('/api/admin/transactions');
        const data = await res.json();
        const tbody = document.getElementById('payments-table-body');
        tbody.innerHTML = '';

        data.transactions.forEach(t => {
            const badgeClass = t.statut === 'ACCEPTED' ? 'badge bg-success-subtle text-success' : 'badge bg-danger-subtle text-danger';
            tbody.innerHTML += `
                <tr>
                    <td><strong>${t.id}</strong></td>
                    <td><code>${t.reference_externe}</code></td>
                    <td>${t.artisan}</td>
                    <td><strong>${t.montant.toLocaleString()} ${t.devise}</strong></td>
                    <td>${t.operateur}</td>
                    <td><span class="${badgeClass}">${t.statut}</span></td>
                    <td>${new Date(t.timestamp).toLocaleTimeString()}</td>
                </tr>
            `;
        });
    } catch (err) {
        console.error('Erreur chargement transactions:', err);
    }
}

// 6. RAG Simulator
async function sendSimulatedChat() {
    const qInput = document.getElementById('chat-input-q');
    const imgInput = document.getElementById('chat-input-img');
    const q = qInput.value.trim();
    if (!q) return;

    const messages = document.getElementById('chat-messages');
    messages.innerHTML += `<div class="msg user">${q} ${imgInput.value ? '📷 [Photo jointe]' : ''}</div>`;

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
        messages.innerHTML += `<div class="msg assistant">${data.reponse.replace(/\n/g, '<br>')}</div>`;
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
            logsConsole.innerHTML = data.logs.map(l => `[${l.timestamp}] [${l.level}] ${l.event}`).join('<br>');
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
        filterSelect.innerHTML += `<option value="${p.code}">${p.nom} (${p.code})</option>`;
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
        const featuresHtml = features.map(f => `<li><i class="iconoir-check text-success me-1"></i>${f}</li>`).join('');
        
        let durationBadge = '';
        if (pkg.duree_jours) {
            durationBadge = `<span class="badge bg-light text-dark me-1"><i class="iconoir-calendar me-1"></i>${pkg.duree_jours} jours</span>`;
        }
        if (pkg.quota_requetes) {
            durationBadge += `<span class="badge bg-light text-dark"><i class="iconoir-chat-bubble-check me-1"></i>${pkg.quota_requetes} req.</span>`;
        }

        const safeNom = (pkg.nom || '').replace(/'/g, "\\'").replace(/"/g, '&quot;');

        grid.innerHTML += `
            <div class="col-md-6 col-xl-4 mb-3">
                <div class="card package-card h-100 ${isActive ? '' : 'package-card-inactive'}">
                    <div class="card-body d-flex flex-column">
                        <div class="d-flex justify-content-between align-items-start mb-2">
                            <div>
                                <span class="badge ${isActive ? 'bg-success-subtle text-success' : 'badge-sub-expired text-danger'} mb-1">
                                    ${isActive ? '● En vente (Actif)' : '○ Désactivé (Inactif)'}
                                </span>
                                <h5 class="card-title mb-0 text-truncate" title="${pkg.nom}">${pkg.nom}</h5>
                                <small class="text-muted font-monospace">${pkg.code}</small>
                            </div>
                            <div class="dropdown">
                                <button class="btn btn-sm btn-light border-0" type="button" data-bs-toggle="dropdown" aria-expanded="false">
                                    <i class="iconoir-more-vert"></i>
                                </button>
                                <ul class="dropdown-menu dropdown-menu-end shadow-sm">
                                    <li><a class="dropdown-item" href="javascript:void(0)" onclick="openEditPackageModal('${pkg.id}')"><i class="iconoir-edit me-2 text-primary"></i>Modifier la formule</a></li>
                                    <li><a class="dropdown-item" href="javascript:void(0)" onclick="togglePackageActive('${pkg.id}', ${!isActive})"><i class="${isActive ? 'iconoir-eye-closed text-warning' : 'iconoir-eye text-success'} me-2"></i>${isActive ? 'Désactiver de la vente' : 'Réactiver la formule'}</a></li>
                                    <li><hr class="dropdown-divider"></li>
                                    <li><a class="dropdown-item text-danger" href="javascript:void(0)" onclick="deletePackagePrompt('${pkg.id}', '${safeNom}')"><i class="iconoir-trash me-2"></i>Supprimer définitivement</a></li>
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
                        <p class="text-muted small flex-grow-0 mb-3">${pkg.description || 'Aucune description'}</p>
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
                            <button class="btn btn-sm btn-outline-danger" onclick="deletePackagePrompt('${pkg.id}', '${safeNom}')" title="Supprimer définitivement cette formule">
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
                            ${(s.artisan_nom || 'A')[0].toUpperCase()}
                        </div>
                        <div>
                            <strong>${s.artisan_nom || 'Artisan #' + s.user_id}</strong>
                            <div class="text-muted small">${s.artisan_email || ''}</div>
                        </div>
                    </div>
                </td>
                <td><small>${s.artisan_telephone || '-'}</small></td>
                <td><span class="badge bg-light text-dark">${s.artisan_metier || 'BTP'}</span></td>
                <td>
                    <strong>${s.package_nom}</strong>
                    <div class="text-muted font-monospace small">${s.package_code}</div>
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
                            <button class="btn btn-sm btn-outline-danger" title="Résilier" onclick="cancelSubscription('${s.id}')">
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
                    userSelect.innerHTML += `<option value="${u.id}">${u.nom} (${u.telephone || u.email || 'Sans contact'}) - ${u.metier || 'Métier'}</option>`;
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
            pkgSelect.innerHTML += `<option value="${p.code}">${p.nom} - ${p.prix.toLocaleString()} F CFA${actifLabel}</option>`;
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

async function loadSecurityTab() {
    try {
        const [rolesRes, auditRes, statsRes] = await Promise.all([
            adminFetch('/api/admin/roles'),
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
                <span class="fw-semibold">${role.label}</span>
                <br><small class="text-muted font-monospace">${role.code}</small>
            </div>
            <span class="badge bg-primary-subtle text-primary">${role.permissions.length} permission(s)</span>
        </div>
    `).join('');
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
                <td class="font-monospace small" title="${entry.actor_id || ''}">${actor}</td>
                <td><span class="badge bg-light text-dark">${entry.action}</span></td>
                <td class="text-muted small">${resource}</td>
            </tr>
        `;
    }).join('');
}

// =========================================================================
// 9. MODULE ACTUALITÉS & CENTRE DE NOTIFICATIONS
// =========================================================================

async function loadActualitesTab() {
    try {
        const [actuRes, suggestRes] = await Promise.all([
            adminFetch('/api/admin/actualites'),
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
    } catch (err) {
        console.error('Erreur chargement onglet actualités:', err);
    }
}

function renderActualitesList(actualites) {
    const container = document.getElementById('actualites-list');
    if (!container) return;

    if (!actualites || actualites.length === 0) {
        container.innerHTML = '<p class="text-muted mb-0">Aucune actualité créée pour le moment.</p>';
        return;
    }

    container.innerHTML = actualites.map(a => {
        const isPublished = a.statut === 'publie';
        const badge = isPublished
            ? '<span class="badge bg-success-subtle text-success">Publiée</span>'
            : '<span class="badge bg-secondary-subtle text-secondary">Brouillon</span>';
        const metierLabel = a.metier_id ? `Métier #${a.metier_id}` : 'Tous métiers';

        return `
            <div class="border-bottom py-2">
                <div class="d-flex justify-content-between align-items-start">
                    <div>
                        <span class="fw-semibold">${a.titre}</span> ${badge}
                        <br><small class="text-muted">${metierLabel}</small>
                    </div>
                    <div>
                        ${isPublished
                            ? `<button class="btn btn-sm btn-outline-warning" onclick="unpublishActualite('${a.id}')">Dépublier</button>`
                            : `<button class="btn btn-sm btn-outline-success" onclick="publishActualite('${a.id}')">Publier</button>`}
                        <button class="btn btn-sm btn-outline-danger" onclick="deleteActualitePrompt('${a.id}')">
                            <i class="iconoir-trash"></i>
                        </button>
                    </div>
                </div>
                <p class="mb-0 text-muted small mt-1">${a.contenu}</p>
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
};

window.submitCreateActualite = async function() {
    const titre = document.getElementById('actu-titre').value.trim();
    const contenu = document.getElementById('actu-contenu').value.trim();
    const metierRaw = document.getElementById('actu-metier').value.trim();
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

window.submitBroadcastNotification = async function() {
    const title = document.getElementById('notif-title').value.trim();
    const body = document.getElementById('notif-body').value.trim();
    const metierRaw = document.getElementById('notif-metier').value.trim();
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
            }),
        });
        const data = await res.json().catch(() => ({}));
        if (res.ok) {
            feedback.className = 'mt-2 small text-success';
            feedback.textContent = `Diffusion lancée vers ${data.cible_count} artisan(s).`;
            document.getElementById('notif-title').value = '';
            document.getElementById('notif-body').value = '';
            document.getElementById('notif-metier').value = '';
        } else {
            feedback.className = 'mt-2 small text-danger';
            feedback.textContent = data.detail || 'Échec de la diffusion.';
        }
    } catch (e) {
        feedback.className = 'mt-2 small text-danger';
        feedback.textContent = 'Erreur réseau.';
    }
};
