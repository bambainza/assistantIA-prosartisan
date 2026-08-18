// State Variables
let selectedUserIdForGrant = null;

document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    refreshDashboard();
    initUploadForm();
    loadPromptInspector();
});

// Tab Navigation
function initTabs() {
    const navItems = document.querySelectorAll('.nav-item');
    const tabPages = document.querySelectorAll('.tab-page');
    const pageTitle = document.getElementById('page-title');

    navItems.forEach(item => {
        item.addEventListener('click', () => {
            navItems.forEach(n => n.classList.remove('active'));
            tabPages.forEach(p => p.classList.remove('active'));

            item.classList.add('active');
            const targetTab = item.getAttribute('data-tab');
            document.getElementById(targetTab).classList.add('active');

            pageTitle.textContent = item.querySelector('span:last-child').textContent;
        });
    });
}

// Refresh Dashboard & Data
async function refreshDashboard() {
    await fetchOverview();
    await fetchArtisans();
    await fetchDocuments();
    await fetchTransactions();
    await fetchLogs();
}

// 1. Fetch Overview (KPIs & Top Métiers)
async function fetchOverview() {
    try {
        const res = await fetch('/api/admin/overview');
        const data = await res.json();

        document.getElementById('kpi-artisans').textContent = data.kpis.total_artisans.toLocaleString();
        document.getElementById('kpi-dau').textContent = data.kpis.artisans_actifs_dau.toLocaleString();
        document.getElementById('kpi-ca').textContent = data.kpis.chiffre_affaires_mfa.toLocaleString() + ' F';
        document.getElementById('kpi-questions').textContent = data.kpis.total_questions_rag.toLocaleString();

        const barChartList = document.getElementById('top-metiers-list');
        barChartList.innerHTML = '';
        
        const maxReq = Math.max(...data.metiers_top.map(m => m.requetes));
        data.metiers_top.forEach(m => {
            const pct = (m.requetes / maxReq) * 100;
            barChartList.innerHTML += `
                <div class="bar-item">
                    <div class="bar-info">
                        <span>${m.nom}</span>
                        <span><strong>${m.requetes.toLocaleString()}</strong> req</span>
                    </div>
                    <div class="bar-track">
                        <div class="bar-fill" style="width: ${pct}%;"></div>
                    </div>
                </div>
            `;
        });
    } catch (err) {
        console.error('Erreur chargement overview:', err);
    }
}

// 2. Fetch Artisans Table
async function fetchArtisans() {
    try {
        const res = await fetch('/api/admin/users');
        const data = await res.json();
        const tbody = document.getElementById('artisans-table-body');
        tbody.innerHTML = '';

        data.users.forEach(u => {
            const badgeClass = u.type_abonnement === 'pass_mois' ? 'badge-success' :
                               (u.type_abonnement === 'pass_24h' ? 'badge-warning' : 'badge-danger');
            
            const reqLabel = u.questions_restantes > 9000 ? 'Illimité (Pro)' : `${u.questions_restantes} gratuites`;

            tbody.innerHTML += `
                <tr>
                    <td><strong>${u.nom}</strong></td>
                    <td>${u.telephone}</td>
                    <td>${u.metier}</td>
                    <td><span class="badge ${badgeClass}">${u.type_abonnement.toUpperCase()}</span></td>
                    <td>${reqLabel}</td>
                    <td>
                        <button class="btn btn-secondary" onclick="openGrantModal('${u.id}', '${u.nom}')">
                            ➕ Prolonger Pass
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
    document.getElementById('modal-grant').classList.add('active');
}

function closeModal() {
    document.getElementById('modal-grant').classList.remove('active');
}

async function submitGrantPass() {
    if (!selectedUserIdForGrant) return;
    const typePass = document.getElementById('select-type-pass').value;

    try {
        const res = await fetch(`/api/admin/users/${selectedUserIdForGrant}/grant-pass?type_pass=${typePass}`, {
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
        const res = await fetch('/api/admin/documents');
        const data = await res.json();
        const docList = document.getElementById('documents-list');
        docList.innerHTML = '';

        data.documents.forEach(d => {
            docList.innerHTML += `
                <div class="kpi-card" style="margin-bottom: 12px;">
                    <div class="kpi-header">
                        <strong>📄 ${d.filename}</strong>
                        <span class="badge badge-success">${d.metier}</span>
                    </div>
                    <div style="font-size: 12px; color: var(--text-secondary); margin-top: 8px;">
                        ${d.chunks_count} chunks vectoriels • Ingéré le ${d.date_ingestion}
                    </div>
                    <button class="btn btn-secondary" style="margin-top: 10px; font-size: 11px; padding: 4px 8px;" onclick="deleteDoc('${d.id}')">
                        🗑️ Supprimer de Qdrant
                    </button>
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
        const res = await fetch(`/api/admin/documents/${docId}`, { method: 'DELETE' });
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
            const res = await fetch('/api/admin/upload-pdf', {
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
        const res = await fetch('/api/admin/transactions');
        const data = await res.json();
        const tbody = document.getElementById('payments-table-body');
        tbody.innerHTML = '';

        data.transactions.forEach(t => {
            const badgeClass = t.statut === 'ACCEPTED' ? 'badge-success' : 'badge-danger';
            tbody.innerHTML += `
                <tr>
                    <td><strong>${t.id}</strong></td>
                    <td><code>${t.reference_externe}</code></td>
                    <td>${t.artisan}</td>
                    <td><strong>${t.montant.toLocaleString()} ${t.devise}</strong></td>
                    <td>${t.operateur}</td>
                    <td><span class="badge ${badgeClass}">${t.statut}</span></td>
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
        messages.innerHTML += `<div class="msg assistant" style="color: var(--danger)">Erreur de génération RAG</div>`;
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
    document.getElementById('prompt-code-block').textContent = promptText;
}

// Fetch System Logs
async function fetchLogs() {
    try {
        const res = await fetch('/api/admin/logs');
        const data = await res.json();
        const logsConsole = document.getElementById('logs-console');
        logsConsole.innerHTML = data.logs.map(l => `[${l.timestamp}] [${l.level}] ${l.event}`).join('<br>');
    } catch (err) {
        console.error('Erreur chargement logs:', err);
    }
}
