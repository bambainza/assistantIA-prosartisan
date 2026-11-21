// ProsArtisan Back-Office — Grille de prix de référence des devis.
// Script classique (non module) : partage la portée globale avec les autres
// fichiers de admin_web/js/, chargés dans l'ordre par index.html.
//
// Seule source des prix pré-remplis par l'IA dans les devis : un prix n'est
// appliqué qu'à une ligne de même unité, de la commune du chantier ou sans
// commune (prix national). Permissions : prix.read / prix.write.

let prixReferencesCache = [];
let prixMetiersCharges = false;
let prixSearchTimer = null;

function formatPrixFcfa(valeur) {
    return `${Math.round(Number(valeur) || 0).toLocaleString('fr-FR')}`;
}

async function chargerMetiersPourPrix() {
    if (prixMetiersCharges) return;
    const select = document.getElementById('prix-form-metier');
    if (!select) return;
    try {
        const res = await adminFetch('/api/admin/metiers');
        if (!res.ok) return;
        const data = await res.json();
        const metiers = data.metiers || [];
        select.innerHTML = '<option value="">Tous les métiers</option>' + metiers.map(m =>
            `<option value="${Number(m.id)}">${escapeHtml(m.nom)}</option>`
        ).join('');
        prixMetiersCharges = true;
    } catch (err) {
        console.error('Erreur chargement des métiers (grille de prix):', err);
    }
}

window.loadPrixReferences = async function() {
    const tbody = document.getElementById('prix-tbody');
    if (!tbody) return;
    const recherche = (document.getElementById('prix-search')?.value || '').trim();
    const url = recherche
        ? `/api/admin/parametres/prix-references?q=${encodeURIComponent(recherche)}`
        : '/api/admin/parametres/prix-references';

    try {
        const res = await adminFetch(url);
        if (res.status === 403) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-muted">Votre rôle ne donne pas accès à la grille de prix.</td></tr>';
            return;
        }
        if (!res.ok) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-danger">Impossible de charger la grille de prix.</td></tr>';
            return;
        }
        prixReferencesCache = await res.json();
        renderPrixReferences(prixReferencesCache);
    } catch (err) {
        console.error('Erreur chargement grille de prix:', err);
        tbody.innerHTML = '<tr><td colspan="7" class="text-danger">Erreur réseau.</td></tr>';
    }
};

function renderPrixReferences(prix) {
    const tbody = document.getElementById('prix-tbody');
    if (!tbody) return;
    if (!prix.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-muted py-3">Aucun prix de référence : les lignes des devis pré-remplis restent à compléter par les artisans.</td></tr>';
        return;
    }
    tbody.innerHTML = prix.map(p => {
        const releve = p.date_releve ? new Date(`${p.date_releve}T00:00:00`).toLocaleDateString('fr-FR') : '—';
        const statut = p.is_active
            ? '<span class="badge bg-success">Actif</span>'
            : '<span class="badge bg-secondary">Inactif</span>';
        const id = Number(p.id);
        return `
            <tr>
                <td>
                    <div class="fw-medium">${escapeHtml(p.designation)}</div>
                    ${p.mots_cles ? `<small class="text-muted">${escapeHtml(p.mots_cles)}</small>` : ''}
                </td>
                <td>${escapeHtml(p.unite)}</td>
                <td class="text-end fw-semibold">${formatPrixFcfa(p.prix_unitaire)}</td>
                <td>${p.commune ? escapeHtml(p.commune) : '<span class="text-muted">Partout</span>'}</td>
                <td>
                    <div>${escapeHtml(releve)}</div>
                    ${p.source ? `<small class="text-muted">${escapeHtml(p.source)}</small>` : ''}
                </td>
                <td>${statut}</td>
                <td class="text-nowrap">
                    <button type="button" class="btn btn-sm btn-outline-secondary" onclick="openPrixForm(${id})" aria-label="Modifier ${escapeHtml(p.designation)}"><i class="iconoir-edit-pencil"></i></button>
                    <button type="button" class="btn btn-sm btn-outline-${p.is_active ? 'warning' : 'success'}" onclick="togglePrixActif(${id})">${p.is_active ? 'Désactiver' : 'Activer'}</button>
                    <button type="button" class="btn btn-sm btn-outline-danger" onclick="deletePrix(${id})" aria-label="Supprimer ${escapeHtml(p.designation)}"><i class="iconoir-trash"></i></button>
                </td>
            </tr>`;
    }).join('');
}

window.openPrixForm = async function(id = null) {
    await chargerMetiersPourPrix();
    const p = id !== null ? prixReferencesCache.find(x => x.id === id) : null;
    document.getElementById('prix-form-id').value = p ? p.id : '';
    document.getElementById('prix-form-designation').value = p ? p.designation : '';
    document.getElementById('prix-form-unite').value = p ? p.unite : '';
    document.getElementById('prix-form-prix').value = p ? p.prix_unitaire : '';
    document.getElementById('prix-form-type').value = p ? p.type_item : 'FOURNITURE';
    document.getElementById('prix-form-date').value = p ? p.date_releve : new Date().toISOString().slice(0, 10);
    document.getElementById('prix-form-mots-cles').value = p && p.mots_cles ? p.mots_cles : '';
    document.getElementById('prix-form-metier').value = p && p.metier_id ? String(p.metier_id) : '';
    document.getElementById('prix-form-commune').value = p && p.commune ? p.commune : '';
    document.getElementById('prix-form-source').value = p && p.source ? p.source : '';
    document.getElementById('prix-form-actif').checked = p ? !!p.is_active : true;
    document.getElementById('prix-form-feedback').textContent = '';
    document.getElementById('prix-form').classList.remove('d-none');
    document.getElementById('prix-form-designation').focus();
};

window.closePrixForm = function() {
    document.getElementById('prix-form').classList.add('d-none');
};

window.submitPrixForm = async function() {
    const feedback = document.getElementById('prix-form-feedback');
    const id = document.getElementById('prix-form-id').value;
    const valeur = (champ) => document.getElementById(champ).value.trim();
    const prix = valeur('prix-form-prix');
    const payload = {
        designation: valeur('prix-form-designation'),
        unite: valeur('prix-form-unite'),
        prix_unitaire: prix === '' ? NaN : Number(prix),
        type_item: valeur('prix-form-type'),
        date_releve: valeur('prix-form-date') || null,
        mots_cles: valeur('prix-form-mots-cles') || null,
        metier_id: valeur('prix-form-metier') ? Number(valeur('prix-form-metier')) : null,
        commune: valeur('prix-form-commune') || null,
        source: valeur('prix-form-source') || null,
        is_active: document.getElementById('prix-form-actif').checked,
    };
    if (payload.designation.length < 2 || !payload.unite || !Number.isInteger(payload.prix_unitaire) || payload.prix_unitaire < 0) {
        feedback.className = 'mt-2 small text-danger';
        feedback.textContent = 'Désignation, unité et prix entier positif (en F CFA) sont requis.';
        return;
    }
    if (!payload.date_releve) delete payload.date_releve;

    try {
        const res = await adminFetch(
            id ? `/api/admin/parametres/prix-references/${Number(id)}` : '/api/admin/parametres/prix-references',
            {
                method: id ? 'PUT' : 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            }
        );
        const data = await res.json().catch(() => ({}));
        if (res.ok) {
            closePrixForm();
            await loadPrixReferences();
        } else {
            feedback.className = 'mt-2 small text-danger';
            feedback.textContent = typeof data.detail === 'string' ? data.detail : 'Valeurs invalides : vérifiez le formulaire.';
        }
    } catch (err) {
        feedback.className = 'mt-2 small text-danger';
        feedback.textContent = 'Erreur réseau.';
    }
};

window.togglePrixActif = async function(id) {
    const p = prixReferencesCache.find(x => x.id === id);
    if (!p) return;
    try {
        const res = await adminFetch(`/api/admin/parametres/prix-references/${Number(id)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_active: !p.is_active }),
        });
        if (res.ok) {
            await loadPrixReferences();
        } else {
            alert('Échec de la mise à jour du statut.');
        }
    } catch (err) {
        alert('Erreur réseau');
    }
};

window.deletePrix = async function(id) {
    if (!confirm('Supprimer définitivement ce prix de référence ? Les devis déjà enregistrés ne changent pas.')) return;
    try {
        const res = await adminFetch(`/api/admin/parametres/prix-references/${Number(id)}`, { method: 'DELETE' });
        const data = await res.json().catch(() => ({}));
        if (res.ok) {
            await loadPrixReferences();
        } else {
            alert(data.detail || 'Échec de la suppression.');
        }
    } catch (err) {
        alert('Erreur réseau');
    }
};

document.addEventListener('DOMContentLoaded', () => {
    const recherche = document.getElementById('prix-search');
    if (!recherche) return;
    recherche.addEventListener('input', () => {
        clearTimeout(prixSearchTimer);
        prixSearchTimer = setTimeout(() => loadPrixReferences(), 300);
    });
});
