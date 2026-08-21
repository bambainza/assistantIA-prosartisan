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

function logoutAdmin() {
    localStorage.removeItem('prosartisan_admin_token');
    document.getElementById('login-container').classList.remove('d-none');
}

document.addEventListener('DOMContentLoaded', () => {
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

// Login Form handler
function initLoginForm() {
    const form = document.getElementById('admin-login-form');
    if (!form) return;

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = document.getElementById('admin-email').value;
        const password = document.getElementById('admin-password').value;
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
            document.getElementById(targetTab).classList.add('active');

            pageTitle.textContent = item.querySelector('span').textContent;
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
            docList.innerHTML += `
                <div class="card mb-3 shadow-none border">
                    <div class="card-body p-3">
                        <div class="d-flex justify-content-between align-items-center mb-2">
                            <span class="fw-semibold text-truncate" style="max-width: 70%;"><i class="iconoir-paste-clipboard me-1 text-primary"></i> ${d.filename}</span>
                            <span class="badge bg-success-subtle text-success">${d.metier}</span>
                        </div>
                        <p class="text-muted mb-3" style="font-size: 11px;">
                            ${d.chunks_count} chunks vectoriels • Ingéré le ${d.date_ingestion}
                        </p>
                        <button class="btn btn-sm btn-outline-danger" onclick="deleteDoc('${d.filename}')">
                            <i class="iconoir-trash me-1"></i> Supprimer de Qdrant
                        </button>
                    </div>
                </div>
            `;
        });
    } catch (err) {
        console.error('Erreur chargement documents:', err);
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
