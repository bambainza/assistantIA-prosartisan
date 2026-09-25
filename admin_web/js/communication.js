// ProsArtisan Back-Office — Actualités & centre de notifications.
// Script classique (non module) : partage la portée globale avec les autres
// fichiers de admin_web/js/, chargés dans l'ordre par index.html.

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
