// ProsArtisan Back-Office — Simulateur RAG, inspecteur du prompt système, journaux système.
// Script classique (non module) : partage la portée globale avec les autres
// fichiers de admin_web/js/, chargés dans l'ordre par index.html.

// 6. RAG Simulator
async function sendSimulatedChat() {
    const qInput = document.getElementById('chat-input-q');
    const imgInput = document.getElementById('chat-input-img');
    const q = qInput.value.trim();
    if (!q) return;

    const messages = document.getElementById('chat-messages');
    messages.innerHTML += `<div class="msg user">${escapeHtml(q)} ${imgInput.value ? '📷 [Photo jointe]' : ''}</div>`;

    qInput.value = '';

    try {
        // Envoi public
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question: q,
                image_url: imgInput.value || null
            })
        });
        const data = await res.json();
        messages.innerHTML += `<div class="msg assistant">${escapeHtml(data.reponse).replace(/\n/g, '<br>')}</div>`;
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
            logsConsole.innerHTML = data.logs.map(
                l => `[${escapeHtml(l.timestamp)}] [${escapeHtml(l.level)}] ${escapeHtml(l.event)}`
            ).join('<br>');
        }
    } catch (err) {
        console.error('Erreur chargement logs:', err);
    }
}
