"""
Service d'orchestration multi-fournisseurs LLM (Mistral AI & Google Gemini).

Fonctionnalités :
- Bascule intelligente (failover automatique) entre Mistral et Gemini en cas
  d'indisponibilité, timeout ou dépassement de quota (429 / 5xx).
- Coupe-circuit (circuit breaker) partagé via Redis (`cache_service`) avec suivi
  du score de stabilité, des pannes consécutives et de la latence par fournisseur.
- Commutation dynamique depuis le back-office (`auto`, `mistral`, `gemini`) pour
  router les requêtes vers la ressource la plus stable et la plus disponible.
- Support complet de l'API Google Gemini Interactions (`/v1beta/interactions`,
  modèle `gemini-3.8-flash` par défaut, multimodal vision, outils calculateurs
  et streaming SSE).
"""

from __future__ import annotations

import base64
import json
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from app.config import settings
from app.services.cache_service import cache_service

logger = logging.getLogger(__name__)

PROVIDER_MISTRAL = "mistral"
PROVIDER_GEMINI = "gemini"
VALID_PROVIDERS: tuple[str, str] = (PROVIDER_MISTRAL, PROVIDER_GEMINI)
VALID_LLM_MODES: tuple[str, str, str] = ("auto", PROVIDER_MISTRAL, PROVIDER_GEMINI)

_CONFIG_MODE_KEY = "prosartisan:llm:config:mode"
_CONFIG_FAILOVER_KEY = "prosartisan:llm:config:failover"
_CONFIG_TTL_SECONDS = 30 * 86400  # 30 jours
_HEALTH_TTL_SECONDS = 24 * 3600  # 24 heures

_DEPRECATED_GEMINI_PREFIXES: tuple[str, ...] = (
    "gemini-1.5",
    "gemini-2.0",
    "gemini-2.5",
    "gemini-3-flash",
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-3.7-flash",
)

_AUDIO_MIME_TYPES: dict[str, str] = {
    "flac": "audio/flac",
    "m4a": "audio/mp4",
    "mp3": "audio/mpeg",
    "mp4": "audio/mp4",
    "mpeg": "audio/mpeg",
    "mpga": "audio/mpeg",
    "oga": "audio/ogg",
    "ogg": "audio/ogg",
    "wav": "audio/wav",
    "webm": "audio/webm",
}


@dataclass
class LLMToolCall:
    """Appel d'outil normalisé entre Mistral et Gemini."""

    id: str
    name: str
    arguments: str = ""


@dataclass
class LLMCompletionResult:
    """Résultat normalisé d'une complétion LLM non streamée."""

    content: str
    tool_calls: list[LLMToolCall]
    provider: str
    model: str


def normalize_gemini_model(model_name: str) -> str:
    """Remplace tout identifiant Gemini déprécié par `gemini-3.8-flash`."""
    cleaned = (model_name or "").strip()
    if not cleaned:
        return "gemini-3.8-flash"
    lower = cleaned.lower()
    if lower != "gemini-3.5-flash-lite" and any(
        lower.startswith(prefix) for prefix in _DEPRECATED_GEMINI_PREFIXES
    ):
        logger.info(
            "Modèle Gemini '%s' déprécié : substitution automatique par 'gemini-3.8-flash'.",
            cleaned,
        )
        return "gemini-3.8-flash"
    return cleaned


def _parse_json_safe(raw: str | dict[str, Any] | list[Any]) -> Any:
    """Parse une chaîne JSON en objet Python ou retourne la valeur brute."""
    if not isinstance(raw, str):
        return raw
    try:
        return json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return {"raw": raw}


def _convert_image_url_to_gemini_part(url: str) -> dict[str, Any]:
    """Convertit une URL d'image (`data:...;base64,...` ou `http(s)://`) au format Gemini Interactions."""
    if url.startswith("data:"):
        header, _, b64_data = url.partition(",")
        mime_type = "image/jpeg"
        if ";" in header and ":" in header:
            mime_type = header.split(":", 1)[1].split(";", 1)[0] or "image/jpeg"
        return {
            "type": "image",
            "mime_type": mime_type,
            "data": b64_data,
        }
    return {
        "type": "image",
        "uri": url,
    }


def build_gemini_interaction_payload(
    *,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    stream: bool = False,
) -> dict[str, Any]:
    """Construit le corps de requête pour `POST /v1beta/interactions` (API Gemini Interactions)."""
    normalized_model = normalize_gemini_model(model)
    system_parts: list[str] = []
    steps_input: list[dict[str, Any]] = []

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if role == "system":
            if isinstance(content, str) and content.strip():
                system_parts.append(content.strip())
            continue

        if role == "user":
            if isinstance(content, list):
                user_parts: list[dict[str, Any]] = []
                for item in content:
                    if not isinstance(item, dict):
                        continue
                    item_type = item.get("type")
                    if item_type == "text":
                        user_parts.append(
                            {"type": "text", "text": str(item.get("text", ""))}
                        )
                    elif item_type == "image_url":
                        img_obj = item.get("image_url") or {}
                        img_url = (
                            img_obj.get("url", "")
                            if isinstance(img_obj, dict)
                            else str(img_obj)
                        )
                        if img_url:
                            user_parts.append(
                                _convert_image_url_to_gemini_part(img_url)
                            )
                steps_input.append({"type": "user_input", "content": user_parts})
            else:
                steps_input.append(
                    {
                        "type": "user_input",
                        "content": [{"type": "text", "text": str(content)}],
                    }
                )
            continue

        if role == "assistant":
            if isinstance(content, str) and content.strip():
                steps_input.append(
                    {
                        "type": "model_output",
                        "content": [{"type": "text", "text": content}],
                    }
                )
            for tc in msg.get("tool_calls") or []:
                fn = tc.get("function") or {}
                steps_input.append(
                    {
                        "type": "function_call",
                        "id": tc.get("id") or "call_0",
                        "name": fn.get("name", ""),
                        "arguments": _parse_json_safe(fn.get("arguments", "{}")),
                    }
                )
            continue

        if role == "tool":
            steps_input.append(
                {
                    "type": "function_result",
                    "call_id": msg.get("tool_call_id") or "call_0",
                    "name": msg.get("name", ""),
                    "result": _parse_json_safe(content),
                }
            )

    # Simplification lorsqu'il n'y a qu'un seul tour texte utilisateur
    input_value: str | list[dict[str, Any]]
    if (
        len(steps_input) == 1
        and steps_input[0].get("type") == "user_input"
        and len(steps_input[0].get("content", [])) == 1
        and steps_input[0]["content"][0].get("type") == "text"
    ):
        input_value = steps_input[0]["content"][0]["text"]
    else:
        input_value = steps_input

    thinking_level = settings.gemini_thinking_level.lower().strip()
    if thinking_level not in ("minimal", "low", "medium", "high"):
        thinking_level = "low"

    payload: dict[str, Any] = {
        "model": normalized_model,
        "input": input_value,
        "store": False,
        "generation_config": {
            "thinking_level": thinking_level,
        },
    }

    if system_parts:
        payload["system_instruction"] = "\n\n".join(system_parts)

    if tools:
        gemini_tools: list[dict[str, Any]] = []
        for tool in tools:
            fn_def = tool.get("function") if isinstance(tool, dict) else None
            if isinstance(fn_def, dict) and fn_def.get("name"):
                gemini_tools.append(
                    {
                        "type": "function",
                        "name": fn_def["name"],
                        "description": fn_def.get("description", ""),
                        "parameters": fn_def.get("parameters", {}),
                    }
                )
        if gemini_tools:
            payload["tools"] = gemini_tools

    if stream:
        payload["stream"] = True

    return payload


def parse_gemini_interaction_response(
    data: dict[str, Any], model: str
) -> LLMCompletionResult:
    """Extrait le texte et les appels d'outils d'une réponse Gemini Interactions."""
    text_chunks: list[str] = []
    tool_calls: list[LLMToolCall] = []

    steps = data.get("steps")
    if isinstance(steps, list):
        for idx, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            step_type = step.get("type")
            if step_type == "model_output":
                for part in step.get("content") or []:
                    if isinstance(part, dict) and part.get("type") == "text":
                        txt = part.get("text")
                        if isinstance(txt, str) and txt:
                            text_chunks.append(txt)
            elif step_type == "function_call":
                args = step.get("arguments", {})
                args_str = args if isinstance(args, str) else json.dumps(args)
                tool_calls.append(
                    LLMToolCall(
                        id=str(step.get("id") or f"gemini_call_{idx}"),
                        name=str(step.get("name") or ""),
                        arguments=args_str,
                    )
                )

    if not text_chunks and isinstance(data.get("output_text"), str):
        text_chunks.append(data["output_text"])

    # Tolérance si un format candidat classique est retourné par un proxy de test
    if not text_chunks and isinstance(data.get("candidates"), list):
        for cand in data["candidates"]:
            content_obj = cand.get("content") if isinstance(cand, dict) else None
            parts = content_obj.get("parts") if isinstance(content_obj, dict) else None
            for idx, part in enumerate(parts or []):
                if not isinstance(part, dict):
                    continue
                if isinstance(part.get("text"), str):
                    text_chunks.append(part["text"])
                if isinstance(part.get("functionCall"), dict):
                    fc = part["functionCall"]
                    args = fc.get("args", {})
                    tool_calls.append(
                        LLMToolCall(
                            id=str(fc.get("id") or f"gemini_call_{idx}"),
                            name=str(fc.get("name") or ""),
                            arguments=args
                            if isinstance(args, str)
                            else json.dumps(args),
                        )
                    )

    return LLMCompletionResult(
        content="".join(text_chunks),
        tool_calls=tool_calls,
        provider=PROVIDER_GEMINI,
        model=normalize_gemini_model(model),
    )


class LLMProviderService:
    """Gestionnaire de disponibilité, stabilité et bascule entre Mistral AI et Google Gemini."""

    def __init__(self, http_transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._http_transport = http_transport

    @staticmethod
    def _is_valid_api_key(raw_key: str | None) -> bool:
        """Retourne True uniquement si la clé API n'est ni vide ni un placeholder d'exemple."""
        key = (raw_key or "").strip()
        if not key:
            return False
        lower = key.lower()
        placeholder_prefixes = (
            "sk-placeholder",
            "aiza-placeholder",
            "your-",
            "your_",
            "votre_",
            "votre-",
            "placeholder",
            "changeme",
        )
        return not lower.startswith(placeholder_prefixes) and "placeholder" not in lower

    @classmethod
    def is_provider_configured(cls, provider: str) -> bool:
        """Vérifie si le fournisseur dispose d'une clé API configurée (hors placeholder)."""
        norm = provider.lower().strip()
        if norm == PROVIDER_MISTRAL:
            return cls._is_valid_api_key(settings.mistral_api_key)
        if norm == PROVIDER_GEMINI:
            return cls._is_valid_api_key(settings.gemini_api_key)
        return False

    def is_any_provider_configured(self) -> bool:
        """Retourne True si au moins l'un des fournisseurs (Mistral ou Gemini) est configuré."""
        return self.is_provider_configured(
            PROVIDER_MISTRAL
        ) or self.is_provider_configured(PROVIDER_GEMINI)

    async def get_routing_config(self) -> tuple[str, bool]:
        """Retourne `(mode, failover_enabled)` actifs depuis Redis ou la configuration `.env`."""
        cached_mode = await cache_service.get(_CONFIG_MODE_KEY)
        mode = (cached_mode or settings.llm_provider or "auto").lower().strip()
        if mode not in VALID_LLM_MODES:
            mode = "auto"

        cached_failover = await cache_service.get(_CONFIG_FAILOVER_KEY)
        if cached_failover is not None:
            failover_enabled = cached_failover == "1"
        else:
            failover_enabled = bool(settings.llm_failover_enabled)

        return mode, failover_enabled

    async def set_routing_config(
        self,
        *,
        mode: str,
        failover_enabled: bool | None = None,
    ) -> tuple[str, bool]:
        """Met à jour la stratégie de routage LLM partagée entre les workers."""
        normalized_mode = mode.lower().strip()
        if normalized_mode not in VALID_LLM_MODES:
            raise ValueError(
                f"Mode LLM invalide '{mode}'. Valeurs autorisées : {', '.join(VALID_LLM_MODES)}"
            )
        await cache_service.set(
            _CONFIG_MODE_KEY, normalized_mode, ttl_seconds=_CONFIG_TTL_SECONDS
        )

        if failover_enabled is not None:
            await cache_service.set(
                _CONFIG_FAILOVER_KEY,
                "1" if failover_enabled else "0",
                ttl_seconds=_CONFIG_TTL_SECONDS,
            )

        return await self.get_routing_config()

    @staticmethod
    def _health_key(provider: str, field: str) -> str:
        return f"prosartisan:llm:health:{provider.lower()}:{field}"

    async def record_success(self, provider: str, latency_ms: float = 0.0) -> None:
        """Enregistre un appel LLM réussi et réinitialise le compteur d'échecs consécutifs."""
        norm = provider.lower().strip()
        now_iso = datetime.now(UTC).isoformat()
        await cache_service.delete(self._health_key(norm, "consecutive_failures"))
        await cache_service.delete(self._health_key(norm, "cooldown_until"))
        await cache_service.increment(
            self._health_key(norm, "total_successes"),
            ttl_seconds=_HEALTH_TTL_SECONDS,
            amount=1,
        )
        if latency_ms > 0:
            prev_raw = await cache_service.get(
                self._health_key(norm, "last_latency_ms")
            )
            try:
                prev_ms = float(prev_raw) if prev_raw is not None else latency_ms
                smoothed = round((prev_ms * 0.6) + (latency_ms * 0.4), 1)
            except ValueError:
                smoothed = round(latency_ms, 1)
            await cache_service.set(
                self._health_key(norm, "last_latency_ms"),
                str(smoothed),
                ttl_seconds=_HEALTH_TTL_SECONDS,
            )
        await cache_service.set(
            self._health_key(norm, "last_used_at"),
            now_iso,
            ttl_seconds=_HEALTH_TTL_SECONDS,
        )

    async def record_failure(self, provider: str, error: Exception | str) -> None:
        """Enregistre un échec fournisseur et déclenche le coupe-circuit si le seuil est atteint."""
        norm = provider.lower().strip()
        now = time.time()
        now_iso = datetime.now(UTC).isoformat()
        consecutive = await cache_service.increment(
            self._health_key(norm, "consecutive_failures"),
            ttl_seconds=_HEALTH_TTL_SECONDS,
            amount=1,
        )
        await cache_service.increment(
            self._health_key(norm, "total_failures"),
            ttl_seconds=_HEALTH_TTL_SECONDS,
            amount=1,
        )
        error_msg = str(error)[:240]
        await cache_service.set(
            self._health_key(norm, "last_error"),
            error_msg,
            ttl_seconds=_HEALTH_TTL_SECONDS,
        )
        await cache_service.set(
            self._health_key(norm, "last_used_at"),
            now_iso,
            ttl_seconds=_HEALTH_TTL_SECONDS,
        )

        threshold = max(1, int(settings.llm_circuit_breaker_threshold))
        if consecutive >= threshold:
            cooldown_seconds = max(
                5, int(settings.llm_circuit_breaker_cooldown_seconds)
            )
            cooldown_until = now + cooldown_seconds
            await cache_service.set(
                self._health_key(norm, "cooldown_until"),
                str(cooldown_until),
                ttl_seconds=cooldown_seconds + 60,
            )
            logger.warning(
                "Coupe-circuit LLM activé pour '%s' après %d échecs consécutifs (cooldown %ds).",
                norm,
                consecutive,
                cooldown_seconds,
            )

    async def reset_health(self, provider: str | None = None) -> None:
        """Réinitialise l'état de santé et le coupe-circuit d'un ou de tous les fournisseurs."""
        targets = [provider.lower().strip()] if provider else list(VALID_PROVIDERS)
        fields = (
            "consecutive_failures",
            "total_failures",
            "total_successes",
            "cooldown_until",
            "last_latency_ms",
            "last_error",
            "last_used_at",
        )
        for p in targets:
            for field in fields:
                await cache_service.delete(self._health_key(p, field))

    async def get_provider_status(self, provider: str) -> dict[str, Any]:
        """Calcule l'état de disponibilité et le score de stabilité (0-100) d'un fournisseur."""
        norm = provider.lower().strip()
        configured = self.is_provider_configured(norm)

        consec_raw = await cache_service.get(
            self._health_key(norm, "consecutive_failures")
        )
        succ_raw = await cache_service.get(self._health_key(norm, "total_successes"))
        fail_raw = await cache_service.get(self._health_key(norm, "total_failures"))
        cooldown_raw = await cache_service.get(self._health_key(norm, "cooldown_until"))
        latency_raw = await cache_service.get(self._health_key(norm, "last_latency_ms"))
        last_error = await cache_service.get(self._health_key(norm, "last_error"))
        last_used_at = await cache_service.get(self._health_key(norm, "last_used_at"))

        consecutive_failures = (
            int(consec_raw) if consec_raw and consec_raw.lstrip("-").isdigit() else 0
        )
        total_successes = (
            int(succ_raw) if succ_raw and succ_raw.lstrip("-").isdigit() else 0
        )
        total_failures = (
            int(fail_raw) if fail_raw and fail_raw.lstrip("-").isdigit() else 0
        )

        now = time.time()
        cooldown_remaining = 0
        if cooldown_raw:
            try:
                rem = float(cooldown_raw) - now
                if rem > 0:
                    cooldown_remaining = round(rem)
            except ValueError:
                cooldown_remaining = 0

        last_latency_ms: float | None = None
        if latency_raw:
            try:
                last_latency_ms = float(latency_raw)
            except ValueError:
                last_latency_ms = None

        if not configured:
            status_str = "unconfigured"
            stability_score = 0.0
        else:
            if cooldown_remaining > 0:
                status_str = "cooldown"
            elif consecutive_failures > 0:
                status_str = "degraded"
            else:
                status_str = "healthy"

            score = 100.0
            score -= consecutive_failures * 25.0
            if cooldown_remaining > 0:
                score -= 50.0
            total_calls = total_successes + total_failures
            if total_calls > 0:
                failure_ratio = total_failures / total_calls
                score -= failure_ratio * 20.0
            if last_latency_ms is not None and last_latency_ms > 0:
                score -= min(10.0, last_latency_ms / 1500.0)
            stability_score = round(max(5.0, min(100.0, score)), 1)

        if norm == PROVIDER_MISTRAL:
            label = "Mistral AI"
            model = settings.llm_model
            vision_model = settings.llm_vision_model
        else:
            label = "Google Gemini"
            model = normalize_gemini_model(settings.gemini_model)
            vision_model = normalize_gemini_model(settings.gemini_vision_model)

        return {
            "code": norm.upper(),
            "provider": norm,
            "label": label,
            "model": model,
            "vision_model": vision_model,
            "configured": configured,
            "status": status_str,
            "stability_score": stability_score,
            "consecutive_failures": consecutive_failures,
            "total_successes": total_successes,
            "total_failures": total_failures,
            "cooldown_remaining_seconds": cooldown_remaining,
            "last_latency_ms": last_latency_ms,
            "last_error": last_error,
            "last_used_at": last_used_at,
        }

    async def get_candidate_providers(self) -> list[str]:
        """Détermine l'ordre des fournisseurs à solliciter selon la stabilité et le mode."""
        mode, failover_enabled = await self.get_routing_config()
        statuses = {p: await self.get_provider_status(p) for p in VALID_PROVIDERS}
        configured = [p for p in VALID_PROVIDERS if statuses[p]["configured"]]
        if not configured:
            return []

        if mode == "auto":
            # Tri par disponibilité immédiate (hors cooldown), score de stabilité décroissant,
            # échecs consécutifs croissants, puis latence croissante.
            def _sort_key(p: str) -> tuple[int, float, int, float, int]:
                st = statuses[p]
                in_cooldown = 1 if st["status"] == "cooldown" else 0
                latency = (
                    st["last_latency_ms"]
                    if st["last_latency_ms"] is not None
                    else 500.0
                )
                tie_breaker = 0 if p == PROVIDER_MISTRAL else 1
                return (
                    in_cooldown,
                    -float(st["stability_score"]),
                    int(st["consecutive_failures"]),
                    float(latency),
                    tie_breaker,
                )

            ordered = sorted(configured, key=_sort_key)
            return ordered if failover_enabled else ordered[:1]

        # Mode explicite ("mistral" ou "gemini")
        preferred = mode
        secondary = (
            PROVIDER_GEMINI if preferred == PROVIDER_MISTRAL else PROVIDER_MISTRAL
        )
        candidates: list[str] = []
        if preferred in configured:
            candidates.append(preferred)
        if failover_enabled and secondary in configured:
            candidates.append(secondary)

        # Si le fournisseur préféré est en cooldown (coupe-circuit ouvert) et que le
        # basculement automatique est actif avec un fournisseur secondaire sain,
        # promouvoir le fournisseur sain en tête pour éviter la latence d'échec.
        if (
            len(candidates) == 2
            and failover_enabled
            and statuses[preferred]["status"] == "cooldown"
            and statuses[secondary]["status"] != "cooldown"
        ):
            candidates = [secondary, preferred]

        return candidates

    async def get_dashboard_summary(self) -> dict[str, Any]:
        """Retourne la vue complète pour le back-office (mode, failover, fournisseur actif, métriques)."""
        mode, failover_enabled = await self.get_routing_config()
        providers = [await self.get_provider_status(p) for p in VALID_PROVIDERS]
        candidates = await self.get_candidate_providers()
        active_provider = candidates[0].upper() if candidates else "MOCK"
        return {
            "mode": mode,
            "failover_enabled": failover_enabled,
            "active_provider": active_provider,
            "candidate_order": [c.upper() for c in candidates],
            "providers": providers,
        }

    # ── Exécution Gemini via l'API Interactions (/v1beta/interactions) ──

    async def complete_gemini(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        is_vision: bool = False,
        model_override: str | None = None,
    ) -> LLMCompletionResult:
        """Exécute un appel synchrone/unitaire vers Google Gemini Interactions API."""
        target_model = normalize_gemini_model(
            model_override
            or (settings.gemini_vision_model if is_vision else settings.gemini_model)
        )
        payload = build_gemini_interaction_payload(
            model=target_model,
            messages=messages,
            tools=tools,
            stream=False,
        )
        url = f"{settings.gemini_api_base_url.rstrip('/')}/interactions"
        headers = {
            "x-goog-api-key": settings.gemini_api_key,
            "Api-Revision": "2026-05-20",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(
            timeout=settings.gemini_timeout_seconds,
            transport=self._http_transport,
        ) as client:
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code >= 400:
                detail = response.text[:300]
                raise RuntimeError(f"Gemini HTTP {response.status_code}: {detail}")
            data = response.json()

        return parse_gemini_interaction_response(data, target_model)

    async def stream_gemini(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_calls_out: list[LLMToolCall],
        is_vision: bool = False,
        model_override: str | None = None,
    ) -> AsyncIterator[str]:
        """Streame la réponse depuis Google Gemini Interactions API (`stream=True`)."""
        target_model = normalize_gemini_model(
            model_override
            or (settings.gemini_vision_model if is_vision else settings.gemini_model)
        )
        payload = build_gemini_interaction_payload(
            model=target_model,
            messages=messages,
            tools=tools,
            stream=True,
        )
        url = f"{settings.gemini_api_base_url.rstrip('/')}/interactions"
        headers = {
            "x-goog-api-key": settings.gemini_api_key,
            "Api-Revision": "2026-05-20",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }

        seen_call_ids: set[str] = set()

        def _register_tool_call(step_obj: dict[str, Any], fallback_idx: int) -> None:
            if step_obj.get("type") != "function_call":
                return
            call_id = str(step_obj.get("id") or f"gemini_call_{fallback_idx}")
            if call_id in seen_call_ids:
                return
            seen_call_ids.add(call_id)
            args = step_obj.get("arguments", {})
            args_str = args if isinstance(args, str) else json.dumps(args)
            tool_calls_out.append(
                LLMToolCall(
                    id=call_id,
                    name=str(step_obj.get("name") or ""),
                    arguments=args_str,
                )
            )

        async with (
            httpx.AsyncClient(
                timeout=settings.gemini_timeout_seconds,
                transport=self._http_transport,
            ) as client,
            client.stream("POST", url, headers=headers, json=payload) as response,
        ):
            if response.status_code >= 400:
                body = await response.aread()
                raise RuntimeError(
                    f"Gemini Stream HTTP {response.status_code}: {body.decode('utf-8', errors='replace')[:300]}"
                )

            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type:
                raw_bytes = await response.aread()
                parsed = parse_gemini_interaction_response(
                    json.loads(raw_bytes.decode("utf-8")), target_model
                )
                tool_calls_out.extend(parsed.tool_calls)
                if parsed.content:
                    yield parsed.content
                return

            step_counter = 0
            async for line in response.aiter_lines():
                stripped = line.strip()
                if not stripped or not stripped.startswith("data:"):
                    continue
                data_str = stripped[5:].strip()
                if not data_str or data_str == "[DONE]":
                    continue
                try:
                    event = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                if not isinstance(event, dict):
                    continue

                event_type = event.get("event_type")
                if event_type == "step.delta":
                    delta = event.get("delta") or {}
                    if isinstance(delta, dict):
                        if delta.get("type") == "text":
                            txt = delta.get("text")
                            if isinstance(txt, str) and txt:
                                yield txt
                        elif delta.get("type") == "function_call":
                            _register_tool_call(
                                {
                                    "type": "function_call",
                                    "id": delta.get("id"),
                                    "name": delta.get("name"),
                                    "arguments": delta.get("arguments", {}),
                                },
                                step_counter,
                            )
                            step_counter += 1
                elif event_type in ("step.start", "step.stop"):
                    step_obj = event.get("step")
                    if isinstance(step_obj, dict):
                        _register_tool_call(step_obj, step_counter)
                        step_counter += 1
                elif event_type == "interaction.completed":
                    interaction = event.get("interaction") or {}
                    if isinstance(interaction, dict):
                        for idx, step_obj in enumerate(interaction.get("steps") or []):
                            if isinstance(step_obj, dict):
                                _register_tool_call(step_obj, idx)

    async def transcribe_audio_gemini(
        self,
        *,
        file_bytes: bytes,
        ext: str,
        prompt: str | None = None,
    ) -> str:
        """Transcrit un fichier audio via Google Gemini (`gemini-3.5-transcribe`)."""
        mime_type = _AUDIO_MIME_TYPES.get(ext.lower(), "audio/wav")
        b64_audio = base64.b64encode(file_bytes).decode("ascii")
        instruction = (
            "Transcris fidèlement cet enregistrement vocal d'artisan en français. "
            f"Contexte métier : {prompt}"
            if prompt
            else "Transcris fidèlement cet enregistrement vocal d'artisan en français."
        )
        payload: dict[str, Any] = {
            "model": settings.gemini_stt_model,
            "input": [
                {
                    "type": "user_input",
                    "content": [
                        {
                            "type": "audio",
                            "mime_type": mime_type,
                            "data": b64_audio,
                        },
                        {
                            "type": "text",
                            "text": instruction,
                        },
                    ],
                }
            ],
            "store": False,
        }
        url = f"{settings.gemini_api_base_url.rstrip('/')}/interactions"
        headers = {
            "x-goog-api-key": settings.gemini_api_key,
            "Api-Revision": "2026-05-20",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(
            timeout=settings.gemini_timeout_seconds,
            transport=self._http_transport,
        ) as client:
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Gemini STT HTTP {response.status_code}: {response.text[:300]}"
                )
            data = response.json()

        parsed = parse_gemini_interaction_response(data, settings.gemini_stt_model)
        return parsed.content.strip()


llm_provider_service = LLMProviderService()
