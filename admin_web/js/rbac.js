// ProsArtisan Back-Office — Rôles RBAC & journal d'audit.
// Script classique (non module) : partage la portée globale avec les autres
// fichiers de admin_web/js/, chargés dans l'ordre par index.html.

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
