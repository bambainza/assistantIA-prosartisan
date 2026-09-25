// ProsArtisan Back-Office — Sécurité du compte admin : 2FA (TOTP).
// Script classique (non module) : partage la portée globale avec les autres
// fichiers de admin_web/js/, chargés dans l'ordre par index.html.

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
