// ProsArtisan Back-Office — Supervision des devis & statistiques des calculateurs.
// Script classique (non module) : partage la portée globale avec les autres
// fichiers de admin_web/js/, chargés dans l'ordre par index.html.

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
