from flask import Flask, render_template, jsonify, request
import os
import json
import requests
from dotenv import load_dotenv
import re
from typing import Optional, Callable, Dict, List

load_dotenv()

app = Flask(__name__)

ONEMAP_BASE = "https://www.onemap.gov.sg"


def _get_token():
    token = os.environ.get("ONEMAP_TOKEN")
    if not token:
        return None
    return token

# ---------------------- Dynamic Layer Registry ----------------------
# Define a registry of layers so chat/tool-calling and grounding are dynamic and extensible.
# Each layer entry provides:
# - title: display name
# - synonyms: list of keywords to detect in user queries
# - context_builder: callable(max_items:int)->str that returns a brief, parseable context
# - total_regex: regex to extract an integer total from the first summary line of the context

def _planning_context_builder(max_items: int = 100) -> str:
    return _build_planning_context(max_items=max_items, year="2019")

def get_layer_registry() -> Dict[str, Dict[str, object]]:
    return {
        "dengue": {
            "title": "Dengue Hotspots",
            "synonyms": ["dengue", "hotspot", "cluster", "clusters"],
            "context_builder": lambda max_items=50: _build_dengue_context(max_items=max_items),
            "total_regex": r":\s*(\d+)\s*unique",
        },
        "planning": {
            "title": "Planning Areas (2019)",
            "synonyms": ["planning area", "planning", "boundary", "boundaries"],
            "context_builder": lambda max_items=100: _planning_context_builder(max_items=max_items),
            "total_regex": r":\s*(\d+)\s*total",
        },
        # For myself to take note
        # To add a new layer in the future, register here with
        # "layer_key": {"title": "...", "synonyms": ["..."], "context_builder": callable, "total_regex": r"..."}
    }


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/planning-areas')
def planning_areas():
    token = _get_token()
    if not token:
        return jsonify({"error": "Missing ONEMAP_TOKEN environment variable."}), 400
    year = request.args.get('year')
    url = f"{ONEMAP_BASE}/api/public/popapi/getAllPlanningarea"
    params = {}
    if year:
        params['year'] = year
    try:
        r = requests.get(url, headers={'Authorization': token}, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        features = []
        for item in data.get('SearchResults', []):
            name = item.get('pln_area_n')
            geojson_str = item.get('geojson')
            if not geojson_str:
                continue
            try:
                geom = json.loads(geojson_str)
            except Exception:
                continue
            features.append({
                "type": "Feature",
                "properties": {"name": name},
                "geometry": geom
            })
        return jsonify({"type": "FeatureCollection", "features": features})
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 502


@app.route('/api/dengue-clusters')
def dengue_clusters():
    token = _get_token()
    if not token:
        return jsonify({"error": "Missing ONEMAP_TOKEN environment variable."}), 400
    url = f"{ONEMAP_BASE}/api/public/themesvc/retrieveTheme"
    params = {"queryName": "dengue_cluster"}
    try:
        r = requests.get(url, headers={'Authorization': token}, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        features = []
        for item in data.get('SrchResults', []):
            if 'GeoJSON' in item:
                gj = item['GeoJSON']
                geom = gj.get('geometry') if isinstance(gj, dict) else None
                if not geom:
                    continue
                coords = geom.get('coordinates')
                if isinstance(coords, str):
                    try:
                        coords = json.loads(coords)
                    except Exception:
                        continue
                    geom['coordinates'] = coords
                if geom.get('type') == 'Polygon' and coords and isinstance(coords, list) and coords and isinstance(coords[0][0], (int, float)):
                    geom['coordinates'] = [coords]
                properties = {k: v for k, v in item.items() if k != 'GeoJSON'}
                features.append({
                    "type": "Feature",
                    "properties": properties,
                    "geometry": geom
                })
        return jsonify({"type": "FeatureCollection", "features": features})
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 502


def _get_planning_features(year: Optional[str] = "2019") -> list:
    """Internal helper to fetch planning area features (GeoJSON Features)."""
    token = _get_token()
    if not token:
        return []
    url = f"{ONEMAP_BASE}/api/public/popapi/getAllPlanningarea"
    params = {"year": year} if year else {}
    try:
        r = requests.get(url, headers={'Authorization': token}, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        features = []
        for item in data.get('SearchResults', []):
            name = item.get('pln_area_n')
            geojson_str = item.get('geojson')
            if not geojson_str:
                continue
            try:
                geom = json.loads(geojson_str)
            except Exception:
                continue
            features.append({
                "type": "Feature",
                "properties": {"name": name},
                "geometry": geom
            })
        return features
    except Exception:
        return []


def _get_dengue_features() -> list:
    """Internal helper to fetch dengue cluster features (GeoJSON Features)."""
    token = _get_token()
    if not token:
        return []
    url = f"{ONEMAP_BASE}/api/public/themesvc/retrieveTheme"
    params = {"queryName": "dengue_cluster"}
    try:
        r = requests.get(url, headers={'Authorization': token}, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        features = []
        for item in data.get('SrchResults', []):
            if 'GeoJSON' in item:
                gj = item['GeoJSON']
                geom = gj.get('geometry') if isinstance(gj, dict) else None
                if not geom:
                    continue
                coords = geom.get('coordinates')
                if isinstance(coords, str):
                    try:
                        coords = json.loads(coords)
                    except Exception:
                        continue
                    geom['coordinates'] = coords
                if geom.get('type') == 'Polygon' and coords and isinstance(coords, list) and coords and isinstance(coords[0][0], (int, float)):
                    geom['coordinates'] = [coords]
                properties = {k: v for k, v in item.items() if k != 'GeoJSON'}
                features.append({
                    "type": "Feature",
                    "properties": properties,
                    "geometry": geom
                })
        return features
    except Exception:
        return []


def _build_dengue_context(max_items: int = 50) -> str:
    """Build a compact text context from dengue cluster features for LLM grounding."""
    feats = _get_dengue_features()
    names = []
    for f in feats:
        p = f.get('properties') or {}
        name = p.get('DESCRIPTION') or p.get('NAME') or p.get('Description') or p.get('Name')
        if name:
            names.append(str(name))
    # de-dup while preserving order
    seen = set()
    unique = []
    for n in names:
        if n not in seen:
            unique.append(n)
            seen.add(n)
    total = len(unique)
    sample = unique[:max_items]
    lines = "\n".join(f"- {n}" for n in sample)
    return f"Latest dengue clusters: {total} unique clusters.\nList (first {len(sample)}):\n{lines}"


def _build_planning_context(max_items: int = 100, year: Optional[str] = "2019") -> str:
    """Build a compact text context from planning area features for LLM grounding."""
    feats = _get_planning_features(year=year)
    names = []
    for f in feats:
        p = f.get('properties') or {}
        name = p.get('name')
        if name:
            names.append(str(name))
    seen = set()
    unique = []
    for n in names:
        if n not in seen:
            unique.append(n)
            seen.add(n)
    total = len(unique)
    sample = unique[:max_items]
    lines = "\n".join(f"- {n}" for n in sample)
    return f"Planning areas (year={year}): {total} total.\nList (first {len(sample)}):\n{lines}"


def _get_all_theme_infos(token: str):
    try:
        url = f"{ONEMAP_BASE}/api/public/themesvc/getAllThemesInfo"
        r = requests.get(url, headers={'Authorization': token}, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


@app.route('/api/themes-info')
def themes_info():
    token = _get_token()
    if not token:
        return jsonify({"error": "Missing ONEMAP_TOKEN environment variable."}), 400
    info = _get_all_theme_infos(token)
    return jsonify(info if info is not None else {"error": "Failed to fetch."})

# ---------------------- Chatbot API ----------------------

def _classify_intents(message: str):
    """Very small rule-based intent extractor for map actions."""
    text = message.lower().strip()
    intents = []

    # Clear/reset map
    if re.search(r"\b(clear|reset|remove\s+all)\b", text):
        intents.append({"type": "clear_all"})

    wants_hide = any(w in text for w in ["hide", "off", "remove", "turn off", "disable"])
    wants_show = any(w in text for w in ["show", "on", "display", "enable", "where", "see"]) or not wants_hide

    # Dynamic layer mentions based on registry
    registry = get_layer_registry()
    for layer_key, meta in registry.items():
        syns: List[str] = [layer_key] + list(meta.get("synonyms") or [])
        if any(s in text for s in syns):
            intents.append({"type": "hide_layer" if wants_hide else "show_layer", "layer": layer_key})

    return intents


def _azure_openai_reply(user_message: str) -> Optional[str]:
    """Optional: Use Azure OpenAI to craft a friendly reply. Returns None on any issue."""
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    api_key = os.environ.get("AZURE_OPENAI_API_KEY")
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT")
    api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
    if not (endpoint and api_key and deployment):
        return None
    try:
        url = f"{endpoint.rstrip('/')}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
        headers = {
            "Content-Type": "application/json",
            "api-key": api_key,
        }
        payload = {
            "messages": [
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.2,
            "top_p": 0.9,
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices") or []
        if choices and choices[0].get("message", {}).get("content"):
            return choices[0]["message"]["content"].strip()
    except Exception:
        return None
    return None


def _azure_openai_chat_with_tools(user_message: str) -> Optional[dict]:
    """Use Azure OpenAI tool calling to both answer briefly and emit map intents.
    Returns dict with keys: reply (str or None), intents (list) or None on error/unavailable.
    """
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    api_key = os.environ.get("AZURE_OPENAI_API_KEY")
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT")
    api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
    if not (endpoint and api_key and deployment):
        return None

    # Build tool schemas dynamically from registered layers
    layer_names = list(get_layer_registry().keys())
    tools = [
        {
            "type": "function",
            "function": {
                "name": "show_layer",
                "description": "Show a specific map layer to the user. Use fit=true to fit map to that layer.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer": {"type": "string", "enum": layer_names},
                        "fit": {"type": "boolean", "description": "Whether to fit/zoom to the layer after showing."}
                    },
                    "required": ["layer"],
                    "additionalProperties": False
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "hide_layer",
                "description": "Hide a specific map layer from the user interface.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer": {"type": "string", "enum": layer_names}
                    },
                    "required": ["layer"],
                    "additionalProperties": False
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "clear_all",
                "description": "Clear or remove all overlays from the map.",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False}
            }
        }
    ]

    try:
        url = f"{endpoint.rstrip('/')}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
        headers = {"Content-Type": "application/json", "api-key": api_key}
        payload = {
            "messages": [
                {"role": "user", "content": user_message},
            ],
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 0.2,
            "top_p": 0.9,
        }
        # Optional: Azure OpenAI on your data (Azure AI Search) for knowledge grounding
        search_endpoint = os.environ.get("AZURE_SEARCH_ENDPOINT")
        search_index = os.environ.get("AZURE_SEARCH_INDEX")
        search_key = os.environ.get("AZURE_SEARCH_API_KEY")
        if search_endpoint and search_index and search_key:
            payload["data_sources"] = [
                {
                    "type": "azure_search",
                    "parameters": {
                        "endpoint": search_endpoint,
                        "index_name": search_index,
                        "authentication": {"type": "api_key", "key": search_key},
                        "in_scope": True,
                        # Use default query behavior; env overrides optional
                        # "query_type": os.environ.get("AZURE_SEARCH_QUERY_TYPE", "simple")
                    },
                }
            ]
        resp = requests.post(url, headers=headers, json=payload, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            return {"reply": None, "intents": []}
        message = choices[0].get("message") or {}
        reply_text = (message.get("content") or "").strip() or None

        intents = []
        # Azure returns tool calls under message.tool_calls for the 2024 API
        tool_calls = message.get("tool_calls") or []
        for call in tool_calls:
            fn = (call.get("function") or {})
            name = fn.get("name")
            args_str = fn.get("arguments") or "{}"
            try:
                args = json.loads(args_str)
            except Exception:
                args = {}
            if name == "show_layer":
                layer = args.get("layer")
                if layer in layer_names:
                    intent = {"type": "show_layer", "layer": layer}
                    if isinstance(args.get("fit"), bool):
                        intent["fit"] = args.get("fit")
                    intents.append(intent)
            elif name == "hide_layer":
                layer = args.get("layer")
                if layer in layer_names:
                    intents.append({"type": "hide_layer", "layer": layer})
            elif name == "clear_all":
                intents.append({"type": "clear_all"})

        # Back-compat: some models may use function_call instead of tool_calls
        if not intents and message.get("function_call"):
            fn = message.get("function_call")
            name = fn.get("name")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except Exception:
                args = {}
            if name == "show_layer" and args.get("layer") in layer_names:
                intents.append({"type": "show_layer", "layer": args.get("layer")})
            elif name == "hide_layer" and args.get("layer") in layer_names:
                intents.append({"type": "hide_layer", "layer": args.get("layer")})
            elif name == "clear_all":
                intents.append({"type": "clear_all"})

        return {"reply": reply_text, "intents": intents}
    except Exception:
        return None

@app.route('/api/chat', methods=['POST'])
def chat_api():
    data = request.get_json(silent=True) or {}
    message = data.get('message', '')
    if not message:
        return jsonify({"reply": "Please type a question.", "intents": []})

    # Build dynamic dengue context and prepend to the conversation to ground the model
    try:
        registry = get_layer_registry()
        context_sections: List[str] = []
        for key, meta in registry.items():
            builder: Callable[..., str] = meta.get("context_builder")  # type: ignore
            if callable(builder):
                try:
                    # Use larger max for planning-like lists; default to 100
                    ctx = builder(100)
                    context_sections.append(ctx)
                except Exception:
                    continue
        context_blob = (
            "Context from live API data (use for answers):\n"
            + "\n\n".join(context_sections)
            + "\n\nInstructions: Answer strictly using the context lists above for available layers. "
              "When asked to list items, provide a concise bullet or numbered list from the context. "
              "If a layer has no context, say that data is currently unavailable. Keep answers short."
        )
        enriched_message = f"{context_blob}\n\nUser: {message}"
    except Exception:
        enriched_message = message

    # Prefer tool-calling path when Azure is configured
    tool_out = _azure_openai_chat_with_tools(enriched_message)
    if tool_out is not None:
        intents = tool_out.get("intents") or []
        reply = tool_out.get("reply")
        # If no intents from tools, fall back to simple rule-based intents for UI updates
        if not intents:
            intents = _classify_intents(message)
        # Prefer Azure model reply; if missing (e.g., only tool calls), try a second Azure reply
        if not reply:
            second = _azure_openai_reply(enriched_message)
            if second:
                reply = second
        # Deterministic fallbacks for common queries when model reply is still missing
        if not reply:
            low = message.lower()
            # Try to detect a target layer dynamically
            def _detect_layers(txt: str) -> List[str]:
                keys: List[str] = []
                reg = get_layer_registry()
                for k, meta in reg.items():
                    syns = [k] + list(meta.get("synonyms") or [])
                    if any(s in txt for s in syns):
                        keys.append(k)
                return keys or list(get_layer_registry().keys())  # fallback to all

            registry = get_layer_registry()
            target_layers = _detect_layers(low)
            # List flow
            if re.search(r"\b(list|show)\b", low):
                bucket: List[str] = []
                for key in target_layers:
                    meta = registry.get(key) or {}
                    builder: Callable[..., str] = meta.get("context_builder")  # type: ignore
                    if not callable(builder):
                        continue
                    try:
                        ctx = builder(300)
                        lines = [ln for ln in ctx.splitlines() if ln.startswith("- ")]
                        if lines:
                            title = str(meta.get("title") or key.title())
                            bucket.append(f"{title}:\n" + "\n".join(lines[:100]))
                    except Exception:
                        continue
                if bucket:
                    reply = "\n\n".join(bucket)
            # Summarize flow
            if not reply and re.search(r"\b(summarize|summary)\b", low):
                pieces: List[str] = []
                for key in target_layers:
                    meta = registry.get(key) or {}
                    builder: Callable[..., str] = meta.get("context_builder")  # type: ignore
                    total_rx = meta.get("total_regex")
                    if not callable(builder):
                        continue
                    try:
                        ctx = builder(50)
                        total = 0
                        if isinstance(total_rx, str):
                            m = re.search(total_rx, ctx)
                            if m:
                                total = int(m.group(1))
                        examples = [ln[2:] for ln in ctx.splitlines() if ln.startswith("- ")][:5]
                        title = str(meta.get("title") or key.title())
                        if total:
                            line = f"{title}: {total} items." + (f" Examples: {', '.join(examples)}." if examples else "")
                            pieces.append(line)
                    except Exception:
                        continue
                if pieces:
                    reply = " ".join(pieces)
        # Final minimal fallback
        if not reply:
            reply = ""
        return jsonify({"reply": reply, "intents": intents})

    # Fallback path: rule-based intents + deterministic summaries/lists + optional Azure reply (grounded)
    intents = _classify_intents(message)
    reply = None

    # Deterministic answers for common queries (registry-based)
    low = message.lower()
    try:
        registry = get_layer_registry()
        def _detect_layers(txt: str) -> List[str]:
            keys: List[str] = []
            for k, meta in registry.items():
                syns = [k] + list(meta.get("synonyms") or [])
                if any(s in txt for s in syns):
                    keys.append(k)
            return keys or list(registry.keys())

        targets = _detect_layers(low)
        if re.search(r"\b(list|show)\b", low):
            bucket: List[str] = []
            for key in targets:
                meta = registry.get(key) or {}
                builder: Callable[..., str] = meta.get("context_builder")  # type: ignore
                if not callable(builder):
                    continue
                ctx = builder(300)
                lines = [ln for ln in ctx.splitlines() if ln.startswith("- ")]
                if lines:
                    title = str(meta.get("title") or key.title())
                    bucket.append(f"{title}:\n" + "\n".join(lines[:100]))
            if bucket:
                reply = "\n\n".join(bucket)
        elif re.search(r"\b(summarize|summary)\b", low):
            pieces: List[str] = []
            for key in targets:
                meta = registry.get(key) or {}
                builder: Callable[..., str] = meta.get("context_builder")  # type: ignore
                total_rx = meta.get("total_regex")
                if not callable(builder):
                    continue
                ctx = builder(50)
                total = 0
                if isinstance(total_rx, str):
                    m = re.search(total_rx, ctx)
                    if m:
                        total = int(m.group(1))
                examples = [ln[2:] for ln in ctx.splitlines() if ln.startswith("- ")][:5]
                title = str(meta.get("title") or key.title())
                if total:
                    pieces.append(f"{title}: {total} items." + (f" Examples: {', '.join(examples)}." if examples else ""))
            if pieces:
                reply = " ".join(pieces)
    except Exception:
        pass

    # If still no reply, compose simple action phrases from intents
    if not reply and intents:
        phrases = []
        for it in intents:
            if it.get("type") == "show_layer" and it.get("layer") == "dengue":
                phrases.append("Showing dengue hotspots on the map.")
            elif it.get("type") == "hide_layer" and it.get("layer") == "dengue":
                phrases.append("Hiding dengue hotspots.")
            elif it.get("type") == "show_layer" and it.get("layer") == "planning":
                phrases.append("Showing planning area boundaries.")
            elif it.get("type") == "hide_layer" and it.get("layer") == "planning":
                phrases.append("Hiding planning area boundaries.")
            elif it.get("type") == "clear_all":
                phrases.append("Clearing map overlays.")
        if phrases:
            reply = " ".join(phrases)

    # Try Azure reply grounded in context; only override if no reply yet
    azure_reply = _azure_openai_reply(enriched_message)
    if azure_reply and not reply:
        reply = azure_reply

    if not reply:
        reply = "Here to help with dengue hotspots and planning areas."
    return jsonify({"reply": reply, "intents": intents})


@app.route('/api/azure-health')
def azure_health():
    """Runtime health check for Azure OpenAI integration."""
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    api_key = os.environ.get("AZURE_OPENAI_API_KEY")
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT")
    configured = bool(endpoint and api_key and deployment)

    tool_calling_ok = False
    tool_detail = ""
    basic_chat_ok = False
    basic_detail = ""

    if configured:
        try:
            out = _azure_openai_chat_with_tools("show dengue layer and hide planning")
            if out is not None and ((out.get("intents") or out.get("reply"))):
                tool_calling_ok = True
            else:
                tool_detail = "No response or empty output from tool-calling"
        except Exception as e:
            tool_detail = f"Exception: {e}"
        try:
            txt = _azure_openai_reply("Say in one short sentence")
            if txt:
                basic_chat_ok = True
            else:
                basic_detail = "Empty reply"
        except Exception as e:
            basic_detail = f"Exception: {e}"
    else:
        tool_detail = basic_detail = "Missing AZURE_OPENAI_* env vars"

    return jsonify({
        "configured": configured,
        "tool_calling_ok": tool_calling_ok,
        "tool_detail": tool_detail,
        "basic_chat_ok": basic_chat_ok,
        "basic_detail": basic_detail,
    })


@app.route('/api/welcome')
def welcome_message():
    """Return a dynamic welcome generated by Azure OpenAI using live dengue + planning data."""
    try:
        registry = get_layer_registry()
        contexts = []
        for key, meta in registry.items():
            builder: Callable[..., str] = meta.get("context_builder")  # type: ignore
            if callable(builder):
                try:
                    # Slightly smaller per-layer for the welcome
                    contexts.append(builder(60))
                except Exception:
                    continue
        ctx = "\n\n".join(contexts)
    except Exception:
        ctx = ""
    prompt = (
        "Using the live context below about Singapore dengue clusters and planning areas, write a brief 1-2 sentence welcome. "
        "Summarize the current hotspot situation and invite the user to toggle layers or ask questions.\n\n"
        f"Context:\n{ctx}"
    ).strip()
    reply = _azure_openai_reply(prompt)
    if not reply:
        # Dynamic non-static fallback from all registered layer counts (no LLM)
        registry = get_layer_registry()
        bits: List[str] = []
        for key, meta in registry.items():
            builder: Callable[..., str] = meta.get("context_builder")  # type: ignore
            total_rx = meta.get("total_regex")
            if not callable(builder) or not isinstance(total_rx, str):
                continue
            try:
                c = builder(30)
                m = re.search(total_rx, c)
                if m:
                    total = int(m.group(1))
                    title = str(meta.get("title") or key.title())
                    bits.append(f"{total} {title.lower()}")
            except Exception:
                continue
        intro = (
            "Welcome. Explore the map to see available layers, "
            "and ask the assistant for quick summaries or lists."
        )
        if bits:
            reply = f"{intro} For context, currently tracked: " + ", ".join(bits) + "."
        else:
            reply = intro
    return jsonify({"reply": reply})

if __name__ == '__main__':
    app.run(debug=True)
