// ProsArtisan Back-Office — Paramètres : métiers, sous-métiers, catégories d'actualités.
// Script classique (non module) : partage la portée globale avec les autres
// fichiers de admin_web/js/, chargés dans l'ordre par index.html.

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
