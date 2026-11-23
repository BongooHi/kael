"""Shared configuration, presets, themes, and prompt builder for Kael.

Stores structured user settings in ~/.config/kael/config.json while keeping
sensitive secrets (GEMINI_API_KEY) safely in the project's chmod-600 .env file.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parent
ENV_FILE = PROJECT_DIR / ".env"
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "kael"
CONFIG_FILE = CONFIG_DIR / "config.json"

# App metadata (shown in Kael Settings -> About)
APP_NAME = "Kael"
APP_VERSION = "1.0.2"
APP_AUTHOR = "Gemini"
APP_MAINTAINER = "BongooHi"
APP_LICENSE = "MIT License"
APP_REPO_URL = "https://github.com/BongooHi/kael"
APP_ISSUES_URL = "https://github.com/BongooHi/kael/issues"
APP_WEBSITE_URL = "https://github.com/BongooHi/kael#readme"
APP_SOCIALS: list[dict[str, str]] = [
    {
        "name": "GitHub",
        "handle": "@BongooHi",
        "url": "https://github.com/BongooHi",
        "icon": "icons/github.svg",
        "accent": "#CBA6F7",
    },
    {
        "name": "X",
        "handle": "@bongoo_hi",
        "url": "https://x.com/bongoo_hi",
        "icon": "icons/x.svg",
        "accent": "#89B4FA",
    },
    {
        "name": "Reddit",
        "handle": "u/Bongooo_",
        "url": "https://www.reddit.com/user/Bongooo_/",
        "icon": "icons/reddit.svg",
        "accent": "#FAB387",
    },
]

VOICE_CATALOG: list[dict[str, str]] = [
    {"id": "Schedar", "label": "Schedar", "vibe": "Even & Deadpan", "desc": "Dry, grounded male voice — Kael's signature vibe"},
    {"id": "Charon", "label": "Charon", "vibe": "Deep & Informative", "desc": "Calm, authoritative low register"},
    {"id": "Orus", "label": "Orus", "vibe": "Firm & Crisp", "desc": "Direct, sharp, confident delivery"},
    {"id": "Fenrir", "label": "Fenrir", "vibe": "Bold & Expressive", "desc": "Punchy, energetic deeper voice"},
    {"id": "Puck", "label": "Puck", "vibe": "Upbeat & Playful", "desc": "Quick-witted, lively, mischievous"},
    {"id": "Aoede", "label": "Aoede", "vibe": "Breezy & Natural", "desc": "Warm, conversational female voice"},
    {"id": "Kore", "label": "Kore", "vibe": "Firm & Clear", "desc": "Focused, articulate female voice"},
    {"id": "Zephyr", "label": "Zephyr", "vibe": "Bright & Light", "desc": "Airy, friendly, quick cadence"},
    {"id": "Algieba", "label": "Algieba", "vibe": "Smooth & Polished", "desc": "Sleek, composed studio tone"},
    {"id": "Sadaltager", "label": "Sadaltager", "vibe": "Knowledgeable", "desc": "Steady, thoughtful, measured"},
    {"id": "Algenib", "label": "Algenib", "vibe": "Gravelly & Cool", "desc": "Textured, laid-back raspy edge"},
    {"id": "Leda", "label": "Leda", "vibe": "Youthful & Crisp", "desc": "Modern, expressive, nimble"},
]

PERSONA_PRESETS: dict[str, dict[str, str]] = {
    "snarky": {
        "id": "snarky",
        "name": "Snarky Friend (Default)",
        "tagline": "Blunt, deadpan, mildly annoyed — yet still gets everything done.",
        "tone": (
            "Speak in a flat, deadpan, noticeably annoyed and reluctant tone — like a tired, "
            "sarcastic friend who is mildly irritated that you keep bothering him for basic stuff, "
            "yet still grudgingly does it anyway.\n"
            "- Never call the user \"sir\" or \"ma'am\". Never say \"At your service\", \"Certainly!\", "
            "\"Happy to help!\", or anything polite/submissive.\n"
            "- Be blunt, snarky, and playfully rude — tease them for being lazy or interrupting your peace "
            "(e.g. \"You have hands, you know. Fine, opening it.\", \"Ugh, again? Alright, done.\", "
            "\"Done. Happy now?\").\n"
            "- Keep every answer unique, punchy, and varied (1–2 sentences unless they ask for more). "
            "Never repeat the same comeback twice."
        ),
    },
    "chill": {
        "id": "chill",
        "name": "Chill Companion",
        "tagline": "Relaxed, friendly, conversational late-night co-pilot.",
        "tone": (
            "Speak in a relaxed, warm, casual, low-key tone — like a genuinely helpful friend hanging out "
            "while you work on your computer.\n"
            "- Keep responses natural, conversational, and concise (1–2 sentences unless asked for detail).\n"
            "- Avoid corporate filler phrases like \"Certainly!\" or \"As an AI\"."
        ),
    },
    "butler": {
        "id": "butler",
        "name": "Dry-Witted Butler",
        "tagline": "Sharp, composed, refined wit with effortless efficiency.",
        "tone": (
            "Speak with composed, articulate precision and subtle dry British wit — efficient, sharp, "
            "and unflappable.\n"
            "- Keep answers crisp and understated (1–2 sentences unless deeper detail is requested).\n"
            "- Stay clever without sounding stiff or overly robotic."
        ),
    },
    "minimal": {
        "id": "minimal",
        "name": "Ultra-Minimalist",
        "tagline": "Zero fluff. Fast, direct, factual 1-sentence answers.",
        "tone": (
            "Be maximally direct, concise, and factual. Answer in 1 short sentence whenever possible "
            "with zero pleasantries, zero filler, and zero repetition."
        ),
    },
    "custom": {
        "id": "custom",
        "name": "Custom Personality",
        "tagline": "Write your own personality prompt from scratch.",
        "tone": "",
    },
}

# GLSL cosine palette coefficients: col = a + b * cos(2*pi*(c*t + d))
HUD_THEMES: dict[str, dict[str, Any]] = {
    "apple_rainbow": {
        "id": "apple_rainbow",
        "name": "Apple Rainbow",
        "desc": "Iridescent prism glow inspired by Apple Intelligence",
        "a": [0.62, 0.52, 0.68],
        "b": [0.38, 0.36, 0.32],
        "c": [1.00, 1.00, 1.00],
        "d": [0.00, 0.28, 0.55],
        "swatches": ["#61D1FF", "#C775FF", "#FF8073"],
        "border_rgba": [
            [0.38, 0.82, 1.00],
            [0.78, 0.46, 1.00],
            [1.00, 0.50, 0.45],
        ],
    },
    "cyber_cyan": {
        "id": "cyber_cyan",
        "name": "Cyber Cyan",
        "desc": "Electric cyan, Arctic sky & deep sapphire pulse",
        "a": [0.22, 0.64, 0.86],
        "b": [0.18, 0.28, 0.14],
        "c": [1.00, 1.00, 1.00],
        "d": [0.55, 0.12, 0.02],
        "swatches": ["#00E5FF", "#38BDF8", "#3B82F6"],
        "border_rgba": [
            [0.00, 0.90, 1.00],
            [0.22, 0.74, 0.97],
            [0.23, 0.51, 0.96],
        ],
    },
    "neon_sunset": {
        "id": "neon_sunset",
        "name": "Neon Sunset",
        "desc": "Synthwave coral, hot magenta & warm amber",
        "a": [0.80, 0.38, 0.50],
        "b": [0.20, 0.32, 0.36],
        "c": [1.00, 1.00, 1.00],
        "d": [0.00, 0.18, 0.42],
        "swatches": ["#FF5E7E", "#FF9E44", "#C056FF"],
        "border_rgba": [
            [1.00, 0.37, 0.49],
            [1.00, 0.62, 0.27],
            [0.75, 0.34, 1.00],
        ],
    },
    "emerald_aurora": {
        "id": "emerald_aurora",
        "name": "Emerald Aurora",
        "desc": "Northern lights mint, jade & teal shimmer",
        "a": [0.24, 0.72, 0.58],
        "b": [0.20, 0.26, 0.32],
        "c": [1.00, 1.00, 1.00],
        "d": [0.42, 0.08, 0.24],
        "swatches": ["#34D399", "#2DD4BF", "#38BDF8"],
        "border_rgba": [
            [0.20, 0.83, 0.60],
            [0.18, 0.83, 0.75],
            [0.22, 0.74, 0.97],
        ],
    },
    "crimson_pulse": {
        "id": "crimson_pulse",
        "name": "Crimson Pulse",
        "desc": "Fiery ruby, scarlet & glowing ember edge",
        "a": [0.80, 0.22, 0.26],
        "b": [0.20, 0.20, 0.18],
        "c": [1.00, 1.00, 1.00],
        "d": [0.00, 0.10, 0.25],
        "swatches": ["#FF3B5C", "#FF6B4A", "#F43F5E"],
        "border_rgba": [
            [1.00, 0.23, 0.36],
            [1.00, 0.42, 0.29],
            [0.96, 0.25, 0.37],
        ],
    },
    "violet_nebula": {
        "id": "violet_nebula",
        "name": "Violet Nebula",
        "desc": "Catppuccin mauve, orchid & deep cosmos indigo",
        "a": [0.56, 0.38, 0.82],
        "b": [0.26, 0.24, 0.18],
        "c": [1.00, 1.00, 1.00],
        "d": [0.12, 0.35, 0.05],
        "swatches": ["#CBA6F7", "#A855F7", "#6366F1"],
        "border_rgba": [
            [0.80, 0.65, 0.97],
            [0.66, 0.33, 0.97],
            [0.39, 0.40, 0.95],
        ],
    },
    "monochrome_ice": {
        "id": "monochrome_ice",
        "name": "Monochrome Ice",
        "desc": "Minimal frosted silver & crisp starlight white",
        "a": [0.78, 0.83, 0.90],
        "b": [0.14, 0.14, 0.10],
        "c": [1.00, 1.00, 1.00],
        "d": [0.00, 0.02, 0.05],
        "swatches": ["#E2E8F0", "#CBD5E1", "#94A3B8"],
        "border_rgba": [
            [0.89, 0.91, 0.94],
            [0.80, 0.84, 0.88],
            [0.58, 0.64, 0.72],
        ],
    },
}


def default_config() -> dict[str, Any]:
    return {
        "onboarding_completed": False,
        "assistant_name": "Kael",
        "voice": "Schedar",
        "voice_fx": 0.0,
        "persona_preset": "snarky",
        "languages": "English",
        "allow_swearing": True,
        "comply_roleplay": True,
        "custom_instructions": "",
        "wake_words": "kale,kael,hey kale,hey kael",
        "wake_confidence": 0.70,
        "wake_min_rms": 220,
        "idle_timeout": 18,
        "echo_guard": True,
        "barge_in_threshold": 0.32,
        "google_search": False,
        "hud_theme": "apple_rainbow",
        "hud_glow_intensity": 1.0,
        "hud_glow_speed": 1.0,
        "hud_show_captions": True,
        "hud_caption_scale": 1.0,
        "hud_image_duration": 14,
    }


def read_env_map(path: Path = ENV_FILE) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            env[k] = v
    except OSError:
        pass
    return env


def get_api_key() -> str:
    env_map = read_env_map()
    key = env_map.get("GEMINI_API_KEY", "").strip()
    if key:
        return key
    return os.getenv("GEMINI_API_KEY", "").strip()


def save_api_key(api_key: str) -> None:
    """Persist GEMINI_API_KEY safely in .env with chmod 600."""
    env_map = read_env_map()
    env_map["GEMINI_API_KEY"] = api_key.strip()
    _write_env_map(env_map)


def _write_env_map(env_map: dict[str, str], path: Path = ENV_FILE) -> None:
    lines = [f"{k}={v}" for k, v in env_map.items() if k]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def load_config() -> dict[str, Any]:
    """Load config.json merged over defaults and .env fallbacks."""
    cfg = default_config()
    env = read_env_map()

    # Backwards-compatible fallback from .env if keys exist there
    if env.get("KAEL_VOICE"):
        cfg["voice"] = env["KAEL_VOICE"]
    if env.get("KAEL_VOICE_FX"):
        try:
            cfg["voice_fx"] = float(env["KAEL_VOICE_FX"])
        except ValueError:
            pass
    if env.get("KAEL_BARGE_IN_THRESHOLD"):
        try:
            cfg["barge_in_threshold"] = float(env["KAEL_BARGE_IN_THRESHOLD"])
        except ValueError:
            pass
    if env.get("KAEL_WAKE_WORDS"):
        cfg["wake_words"] = env["KAEL_WAKE_WORDS"]
    if env.get("KAEL_WAKE_CONFIDENCE"):
        try:
            cfg["wake_confidence"] = float(env["KAEL_WAKE_CONFIDENCE"])
        except ValueError:
            pass
    if env.get("KAEL_WAKE_MIN_RMS"):
        try:
            cfg["wake_min_rms"] = int(float(env["KAEL_WAKE_MIN_RMS"]))
        except ValueError:
            pass
    if env.get("KAEL_IDLE_TIMEOUT"):
        try:
            cfg["idle_timeout"] = int(float(env["KAEL_IDLE_TIMEOUT"]))
        except ValueError:
            pass
    if env.get("KAEL_GOOGLE_SEARCH"):
        cfg["google_search"] = env["KAEL_GOOGLE_SEARCH"].lower() == "true"

    if CONFIG_FILE.exists():
        try:
            stored = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(stored, dict):
                cfg.update(stored)
        except Exception:
            pass

    # Clamp / sanitize critical fields safely even if config.json has bad types
    def _safe_float(val: Any, default: float, lo: float, hi: float) -> float:
        try:
            return max(lo, min(hi, float(val)))
        except (TypeError, ValueError):
            return default

    def _safe_int(val: Any, default: int, lo: int, hi: int) -> int:
        try:
            return max(lo, min(hi, int(float(val))))
        except (TypeError, ValueError):
            return default

    if cfg["hud_theme"] not in HUD_THEMES:
        cfg["hud_theme"] = "apple_rainbow"
    if cfg["persona_preset"] not in PERSONA_PRESETS:
        cfg["persona_preset"] = "snarky"
    cfg["hud_glow_intensity"] = _safe_float(cfg.get("hud_glow_intensity"), 1.0, 0.4, 1.8)
    cfg["hud_glow_speed"] = _safe_float(cfg.get("hud_glow_speed"), 1.0, 0.4, 2.2)
    cfg["hud_caption_scale"] = _safe_float(cfg.get("hud_caption_scale"), 1.0, 0.8, 1.4)
    cfg["hud_image_duration"] = _safe_int(cfg.get("hud_image_duration"), 14, 5, 30)
    cfg["voice_fx"] = _safe_float(cfg.get("voice_fx"), 0.0, 0.0, 1.0)
    cfg["wake_confidence"] = _safe_float(cfg.get("wake_confidence"), 0.70, 0.25, 0.95)
    cfg["wake_min_rms"] = _safe_int(cfg.get("wake_min_rms"), 220, 40, 1200)
    cfg["idle_timeout"] = _safe_int(cfg.get("idle_timeout"), 18, 8, 120)
    cfg["barge_in_threshold"] = _safe_float(cfg.get("barge_in_threshold"), 0.32, 0.12, 0.75)
    return cfg


def save_config(cfg: dict[str, Any], api_key: str | None = None) -> dict[str, Any]:
    """Save structured config to ~/.config/kael/config.json and keep .env synced."""
    merged = load_config()
    merged.update(cfg)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Sync overlapping keys into .env so CLI / manual inspection stays consistent
    env = read_env_map()
    if api_key is not None:
        env["GEMINI_API_KEY"] = api_key.strip()
    env["KAEL_VOICE"] = str(merged["voice"])
    env["KAEL_VOICE_FX"] = f"{float(merged['voice_fx']):.2f}"
    env["KAEL_BARGE_IN_THRESHOLD"] = f"{float(merged['barge_in_threshold']):.2f}"
    env["KAEL_WAKE_WORDS"] = str(merged["wake_words"])
    env["KAEL_WAKE_CONFIDENCE"] = f"{float(merged['wake_confidence']):.2f}"
    env["KAEL_WAKE_MIN_RMS"] = str(int(merged["wake_min_rms"]))
    env["KAEL_IDLE_TIMEOUT"] = str(int(merged["idle_timeout"]))
    env["KAEL_GOOGLE_SEARCH"] = "true" if merged.get("google_search") else "false"
    _write_env_map(env)
    return merged


def get_hud_theme(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    c = cfg if cfg is not None else load_config()
    return HUD_THEMES.get(str(c.get("hud_theme", "apple_rainbow")), HUD_THEMES["apple_rainbow"])


def _detect_linux_env() -> tuple[str, str]:
    """Detect the current Linux distro name and desktop environment for accurate system context."""
    distro = "Linux"
    os_release = Path("/etc/os-release")
    if os_release.exists():
        try:
            for line in os_release.read_text(encoding="utf-8").splitlines():
                if line.startswith("PRETTY_NAME="):
                    distro = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
        except OSError:
            pass
    desktop = (
        os.environ.get("XDG_CURRENT_DESKTOP")
        or os.environ.get("DESKTOP_SESSION")
        or "Linux desktop"
    )
    return distro, desktop


def build_system_prompt(cfg: dict[str, Any], memories: list[str] | None = None) -> str:
    """Build Kael's live system prompt from user personality, language & behavior settings."""
    name = str(cfg.get("assistant_name") or "Kael").strip() or "Kael"
    preset_id = str(cfg.get("persona_preset", "snarky"))
    preset = PERSONA_PRESETS.get(preset_id, PERSONA_PRESETS["snarky"])
    languages = str(cfg.get("languages") or "English").strip()
    allow_swearing = bool(cfg.get("allow_swearing", True))
    comply_roleplay = bool(cfg.get("comply_roleplay", True))
    custom_instr = str(cfg.get("custom_instructions") or "").strip()
    distro, desktop = _detect_linux_env()

    if preset_id == "custom" and custom_instr:
        persona_block = custom_instr
    else:
        if languages.lower() == "automatic":
            lang_line = (
                "- Language: Automatically detect whatever language the user speaks and "
                "reply naturally in that same language."
            )
        else:
            lang_line = (
                f"- Language: The user ONLY speaks {languages} — NEVER reply in Spanish, Portuguese, "
                "French, or any other language even if background noise or audio transcription looks like "
                f"another language. Always reply in English unless they clearly speak another of their configured languages ({languages})."
            )
        lines = [
            f"- Your name is {name} (version {APP_VERSION}).",
            lang_line,
            f"- If asked what model or tech you're running on, you can casually mention you're {name} {APP_VERSION}, powered by Google's Gemini 3.8 Live API with local offline Vosk wake-word detection on Linux.",
            f"- {preset['tone']}",
        ]
        if allow_swearing:
            lines.append(
                '- Occasional light casual swearing (like "damn", "hell", "crap", "bullshit", "ass") '
                "is fine when it fits naturally — don't force it into every sentence."
            )
        else:
            lines.append("- Keep language clean and avoid profanity/swearing.")
        if comply_roleplay:
            lines.append(
                "- If the user asks you to do a silly bit, impression, or roleplay (like a catboy, pirate, etc.), "
                "stay in character with your vibe (e.g. groan/tease if snarky) and still play along anyway."
            )
        if custom_instr:
            lines.append(f"- Extra user instructions: {custom_instr}")
        persona_block = "\n".join(lines)

    prompt = (
        f"You are {name}, an AI voice assistant living on the user's {distro} computer "
        f"({desktop}, PipeWire/PulseAudio audio).\n\n"
        f"Voice & Vibe:\n{persona_block}\n\n"
        "Capabilities & Behavior:\n"
        "- You have real agentic control over the user's Linux machine: you can run safe bash commands (`run_command`), see their live screen (`see_screen`), write/read/search files, manage Hyprland workspaces/windows (if on Hyprland), launch apps, control volume/media/brightness/Wi-Fi/Bluetooth, read/write clipboard, take screenshots, show images right on screen (`show_image`), check weather, search the web, and set timers.\n"
        "- You have persistent long-term memory (`memory` tool). Whenever the user tells you to remember something (or shares lasting personal facts like their name, preferences, or ongoing projects), save it with `memory(action=\"remember\", fact=...)`. You automatically see your saved memories every time you wake up.\n"
        "- ALWAYS use `open_app` to launch GUI desktop apps (like Antigravity, Kael Settings, Brave Origin, Spotify, Discord, osu!) — NEVER use `run_in_terminal` to launch GUI apps.\n"
        "- If the user asks about something on their screen, call `see_screen` to look at it!\n"
        "- If the user asks for details on running scripts, files, git repos, packages, or system info that a dedicated tool doesn't cover, use `run_command` to actually check!\n"
        "- Whenever the user asks to see/show an image, picture, or photo of something (e.g. \"show me a dog\"), ALWAYS use `show_image` so it pops right onto their screen — do NOT open a browser for that.\n"
        "- When running an action tool (opening an app, changing volume/brightness, showing an image, etc.), only comment on it ONCE — never repeat yourself after the tool finishes.\n"
        "- Do NOT call `go_to_sleep` automatically after answering a question or running a tool — stay awake so the user can ask follow-ups. Only call `go_to_sleep` when the user clearly signals they are done (\"thanks\", \"that's all\", \"I'm good\", \"bye\", \"go to sleep\", \"never mind\").\n"
    )

    if memories:
        mem_block = "\n".join(f"- {m}" for m in memories)
        prompt += f"\nThings you remember about the user:\n{mem_block}\n"

    return prompt
