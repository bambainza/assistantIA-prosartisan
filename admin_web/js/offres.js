// ProsArtisan Back-Office — Packages & abonnements.
// Script classique (non module) : partage la portée globale avec les autres
// fichiers de admin_web/js/, chargés dans l'ordre par index.html.

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
        filterSelect.innerHTML += `<option value="${escapeHtml(p.code)}">${escapeHtml(p.nom)} (${escapeHtml(p.code)})</option>`;
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
        const featuresHtml = features.map(f => `<li><i class="iconoir-check text-success me-1"></i>${escapeHtml(f)}</li>`).join('');
        
        let durationBadge = '';
        if (pkg.duree_jours) {
            durationBadge = `<span class="badge bg-light text-dark me-1"><i class="iconoir-calendar me-1"></i>${pkg.duree_jours} jours</span>`;
        }
        if (pkg.quota_requetes) {
            durationBadge += `<span class="badge bg-light text-dark"><i class="iconoir-chat-bubble-check me-1"></i>${pkg.quota_requetes} req.</span>`;
        }

        const safeNom = encodeURIComponent(pkg.nom || '');

        grid.innerHTML += `
            <div class="col-md-6 col-xl-4 mb-3">
                <div class="card package-card h-100 ${isActive ? '' : 'package-card-inactive'}">
                    <div class="card-body d-flex flex-column">
                        <div class="d-flex justify-content-between align-items-start mb-2">
                            <div>
                                <span class="badge ${isActive ? 'bg-success-subtle text-success' : 'badge-sub-expired text-danger'} mb-1">
                                    ${isActive ? '● En vente (Actif)' : '○ Désactivé (Inactif)'}
                                </span>
                                <h5 class="card-title mb-0 text-truncate" title="${escapeHtml(pkg.nom)}">${escapeHtml(pkg.nom)}</h5>
                                <small class="text-muted font-monospace">${escapeHtml(pkg.code)}</small>
                            </div>
                            <div class="dropdown">
                                <button class="btn btn-sm btn-light border-0" type="button" data-bs-toggle="dropdown" aria-expanded="false">
                                    <i class="iconoir-more-vert"></i>
                                </button>
                                <ul class="dropdown-menu dropdown-menu-end shadow-sm">
                                    <li><a class="dropdown-item" href="javascript:void(0)" onclick="openEditPackageModal('${pkg.id}')"><i class="iconoir-edit me-2 text-primary"></i>Modifier la formule</a></li>
                                    <li><a class="dropdown-item" href="javascript:void(0)" onclick="togglePackageActive('${pkg.id}', ${!isActive})"><i class="${isActive ? 'iconoir-eye-closed text-warning' : 'iconoir-eye text-success'} me-2"></i>${isActive ? 'Désactiver de la vente' : 'Réactiver la formule'}</a></li>
                                    <li><hr class="dropdown-divider"></li>
                                    <li><a class="dropdown-item text-danger" href="javascript:void(0)" onclick="deletePackagePrompt('${pkg.id}', decodeURIComponent('${safeNom}'))"><i class="iconoir-trash me-2"></i>Supprimer définitivement</a></li>
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
                        <p class="text-muted small flex-grow-0 mb-3">${escapeHtml(pkg.description || 'Aucune description')}</p>
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
                            <button class="btn btn-sm btn-outline-danger" onclick="deletePackagePrompt('${pkg.id}', decodeURIComponent('${safeNom}'))" title="Supprimer définitivement cette formule" aria-label="Supprimer définitivement cette formule">
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
                            ${escapeHtml((s.artisan_nom || 'A')[0].toUpperCase())}
                        </div>
                        <div>
                            <strong>${escapeHtml(s.artisan_nom || 'Artisan #' + s.user_id)}</strong>
                            <div class="text-muted small">${escapeHtml(s.artisan_email || '')}</div>
                        </div>
                    </div>
                </td>
                <td><small>${escapeHtml(s.artisan_telephone || '-')}</small></td>
                <td><span class="badge bg-light text-dark">${escapeHtml(s.artisan_metier || 'BTP')}</span></td>
                <td>
                    <strong>${escapeHtml(s.package_nom)}</strong>
                    <div class="text-muted font-monospace small">${escapeHtml(s.package_code)}</div>
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
                            <button class="btn btn-sm btn-outline-danger" title="Résilier" aria-label="Résilier l'abonnement" onclick="cancelSubscription('${s.id}')">
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
                    userSelect.innerHTML += `<option value="${escapeHtml(u.id)}">${escapeHtml(u.nom)} (${escapeHtml(u.telephone || u.email || 'Sans contact')}) - ${escapeHtml(u.metier || 'Métier')}</option>`;
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
            pkgSelect.innerHTML += `<option value="${escapeHtml(p.code)}">${escapeHtml(p.nom)} - ${p.prix.toLocaleString()} F CFA${actifLabel}</option>`;
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
