#!/usr/bin/env python3
"""Kael Apple-Intelligence GPU Rainbow Glow + Dual Animated Captions + On-Screen Image Cards."""

from __future__ import annotations

import ctypes

# Must load libgtk4-layer-shell before libwayland-client initializes (try versioned soname first for Debian/Ubuntu/Fedora)
_LAYER_SHELL_LIB_LOADED = False
for _lib_name in ("libgtk4-layer-shell.so.0", "libgtk4-layer-shell.so"):
    try:
        ctypes.CDLL(_lib_name)
        _LAYER_SHELL_LIB_LOADED = True
        break
    except OSError:
        continue

import json
import math
import os
import signal
import socket
import time

import cairo
import gi
import numpy as np
from OpenGL import GL

from config import get_hud_theme, load_config

gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk

Gtk4LayerShell = None
if _LAYER_SHELL_LIB_LOADED:
    try:
        gi.require_version("Gtk4LayerShell", "1.0")
        from gi.repository import Gtk4LayerShell as _Gtk4LayerShell

        Gtk4LayerShell = _Gtk4LayerShell
    except (ValueError, ImportError):
        Gtk4LayerShell = None

SOCK_PATH = os.path.join(
    os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"),
    "kael-hud.sock",
)

VERT_BODY = """
in vec2 a_pos;
out vec2 v_uv;
void main() {
    v_uv = a_pos * 0.5 + 0.5;
    gl_Position = vec4(a_pos, 0.0, 1.0);
}
"""

FRAG_BODY = """
in vec2 v_uv;
out vec4 fragColor;

uniform vec2 u_res;
uniform float u_time;
uniform float u_alpha;
uniform float u_voice;
uniform float u_intensity;
uniform vec3 u_pal_a;
uniform vec3 u_pal_b;
uniform vec3 u_pal_c;
uniform vec3 u_pal_d;

vec3 themePalette(float t) {
    vec3 col = u_pal_a + u_pal_b * cos(6.2831853 * (u_pal_c * t + u_pal_d));
    return clamp(pow(max(col, 0.0), vec3(0.88)) * 1.18, 0.0, 1.0);
}

float sdRoundedBox(vec2 p, vec2 b, float r) {
    vec2 q = abs(p) - b + vec2(r);
    return min(max(q.x, q.y), 0.0) + length(max(q, 0.0)) - r;
}

void main() {
    if (u_alpha <= 0.002) {
        fragColor = vec4(0.0);
        return;
    }

    vec2 px = v_uv * u_res;
    vec2 halfRes = u_res * 0.5;
    vec2 p = px - halfRes;

    float cornerR = 16.0;
    float edgeDist = max(0.0, -sdRoundedBox(p, halfRes, cornerR));

    // Early-out interior pixels where glow alpha is guaranteed < 0.004
    float maxReach = (26.0 + 54.0 * u_voice) * 4.4 * u_alpha * max(1.0, u_intensity);
    if (edgeDist > maxReach) {
        fragColor = vec4(0.0);
        return;
    }

    float ang = atan(p.y, p.x);
    float normAng = ang / 6.2831853 + 0.5;

    float wave1 = sin(ang * 2.0 + u_time * 1.35) * 0.5 + 0.5;
    float wave2 = sin(ang * 3.0 - u_time * 1.85 + 1.4) * 0.5 + 0.5;
    float wave3 = sin(ang * 5.0 + u_time * 2.40 - 0.7) * 0.5 + 0.5;
    float fluid = (wave1 * 0.50 + wave2 * 0.32 + wave3 * 0.18);

    float voiceBoost = u_voice * (0.65 + 0.75 * fluid);
    float bloomWidth = (18.0 + 38.0 * voiceBoost + 7.0 * fluid) * u_alpha * u_intensity;
    float rimWidth   = (3.2  + 4.5  * voiceBoost) * u_alpha * (0.75 + 0.25 * u_intensity);

    float rim   = exp(-edgeDist / max(1.0, rimWidth));
    float mid   = exp(-edgeDist / max(2.0, bloomWidth * 0.42));
    float bloom = exp(-edgeDist / max(3.0, bloomWidth));

    float hueT = fract(normAng + u_time * 0.14 + 0.06 * sin(ang * 2.0 - u_time * 1.1));
    vec3 color = themePalette(hueT);

    vec3 finalRgb = mix(color, vec3(1.0), rim * (0.28 + 0.22 * u_voice));
    float glowAlpha = clamp((rim * 0.92 + mid * 0.48 + bloom * 0.28) * u_alpha, 0.0, 0.96);

    if (glowAlpha < 0.004) {
        fragColor = vec4(0.0);
        return;
    }

    fragColor = vec4(finalRgb * glowAlpha, glowAlpha);
}
"""


def _rounded_rect(
    cr: cairo.Context, x: float, y: float, w: float, h: float, r: float
) -> None:
    r = max(0.0, min(r, w / 2.0, h / 2.0))
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def _ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def _pixbuf_to_cairo_surface(
    pixbuf: GdkPixbuf.Pixbuf,
) -> tuple[cairo.ImageSurface, np.ndarray]:
    """Convert a GdkPixbuf to a Cairo ARGB32 ImageSurface (handles unpadded final row)."""
    w = pixbuf.get_width()
    h = pixbuf.get_height()
    n_ch = pixbuf.get_n_channels()
    stride = pixbuf.get_rowstride()
    flat = np.frombuffer(pixbuf.get_pixels(), dtype=np.uint8)
    expected = h * stride
    if flat.size < expected:
        flat = np.pad(flat, (0, expected - flat.size), mode="constant")
    raw = flat[:expected].reshape((h, stride))
    rgb = raw[:, : w * n_ch].reshape((h, w, n_ch))

    bgra = np.empty((h, w, 4), dtype=np.uint8)
    bgra[:, :, 0] = rgb[:, :, 2]  # B
    bgra[:, :, 1] = rgb[:, :, 1]  # G
    bgra[:, :, 2] = rgb[:, :, 0]  # R
    if n_ch == 4:
        a = rgb[:, :, 3].astype(np.float32) / 255.0
        bgra[:, :, 0] = (bgra[:, :, 0] * a).astype(np.uint8)
        bgra[:, :, 1] = (bgra[:, :, 1] * a).astype(np.uint8)
        bgra[:, :, 2] = (bgra[:, :, 2] * a).astype(np.uint8)
        bgra[:, :, 3] = rgb[:, :, 3]
    else:
        bgra[:, :, 3] = 255

    arr = np.ascontiguousarray(bgra)
    surf = cairo.ImageSurface.create_for_data(arr, cairo.FORMAT_ARGB32, w, h, w * 4)
    return surf, arr


class AppleGlowGLArea(Gtk.GLArea):
    """Hardware-accelerated OpenGL shader widget rendering Apple Intelligence edge glow."""

    def __init__(self, app: KaelHUDApp) -> None:
        super().__init__()
        self._app = app
        self.set_has_depth_buffer(False)
        self.set_has_stencil_buffer(False)
        self.set_auto_render(True)

        self._program: int = 0
        self._vao: int = 0
        self._vbo: int = 0
        self._u_res: int = -1
        self._u_time: int = -1
        self._u_alpha: int = -1
        self._u_voice: int = -1
        self._u_intensity: int = -1
        self._u_pal_a: int = -1
        self._u_pal_b: int = -1
        self._u_pal_c: int = -1
        self._u_pal_d: int = -1

        self.connect("realize", self._on_realize)
        self.connect("unrealize", self._on_unrealize)
        self.connect("render", self._on_render)

    def _compile_shader(self, src: str, shader_type: int) -> int:
        shader = GL.glCreateShader(shader_type)
        GL.glShaderSource(shader, src)
        GL.glCompileShader(shader)
        if not GL.glGetShaderiv(shader, GL.GL_COMPILE_STATUS):
            log = GL.glGetShaderInfoLog(shader).decode("utf-8", errors="replace")
            raise RuntimeError(f"GLSL compile error: {log}")
        return shader

    def _on_realize(self, area: Gtk.GLArea) -> None:
        area.make_current()
        if area.get_error() is not None:
            return

        ctx = area.get_context()
        use_es = ctx.get_use_es() if ctx is not None else False
        header = "#version 300 es\nprecision highp float;\n" if use_es else "#version 330 core\n"

        vs = self._compile_shader(header + VERT_BODY, GL.GL_VERTEX_SHADER)
        fs = self._compile_shader(header + FRAG_BODY, GL.GL_FRAGMENT_SHADER)

        prog = GL.glCreateProgram()
        GL.glAttachShader(prog, vs)
        GL.glAttachShader(prog, fs)
        GL.glLinkProgram(prog)
        if not GL.glGetProgramiv(prog, GL.GL_LINK_STATUS):
            log = GL.glGetProgramInfoLog(prog).decode("utf-8", errors="replace")
            raise RuntimeError(f"GLSL link error: {log}")
        GL.glDeleteShader(vs)
        GL.glDeleteShader(fs)

        self._program = prog
        self._u_res = GL.glGetUniformLocation(prog, "u_res")
        self._u_time = GL.glGetUniformLocation(prog, "u_time")
        self._u_alpha = GL.glGetUniformLocation(prog, "u_alpha")
        self._u_voice = GL.glGetUniformLocation(prog, "u_voice")
        self._u_intensity = GL.glGetUniformLocation(prog, "u_intensity")
        self._u_pal_a = GL.glGetUniformLocation(prog, "u_pal_a")
        self._u_pal_b = GL.glGetUniformLocation(prog, "u_pal_b")
        self._u_pal_c = GL.glGetUniformLocation(prog, "u_pal_c")
        self._u_pal_d = GL.glGetUniformLocation(prog, "u_pal_d")

        verts = np.array(
            [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, 1.0, 1.0],
            dtype=np.float32,
        )
        self._vao = GL.glGenVertexArrays(1)
        self._vbo = GL.glGenBuffers(1)
        GL.glBindVertexArray(self._vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, verts.nbytes, verts, GL.GL_STATIC_DRAW)
        loc = GL.glGetAttribLocation(prog, "a_pos")
        GL.glEnableVertexAttribArray(loc)
        GL.glVertexAttribPointer(loc, 2, GL.GL_FLOAT, GL.GL_FALSE, 0, None)
        GL.glBindVertexArray(0)

    def _on_unrealize(self, area: Gtk.GLArea) -> None:
        area.make_current()
        if self._vbo:
            GL.glDeleteBuffers(1, [self._vbo])
            self._vbo = 0
        if self._vao:
            GL.glDeleteVertexArrays(1, [self._vao])
            self._vao = 0
        if self._program:
            GL.glDeleteProgram(self._program)
            self._program = 0

    def _on_render(self, area: Gtk.GLArea, _ctx: Gdk.GLContext) -> bool:
        scale = area.get_scale_factor()
        w = max(1, area.get_width() * scale)
        h = max(1, area.get_height() * scale)

        GL.glViewport(0, 0, w, h)
        GL.glClearColor(0.0, 0.0, 0.0, 0.0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)

        if not self._program or self._app.alpha <= 0.002:
            return True

        GL.glUseProgram(self._program)
        GL.glUniform2f(self._u_res, float(w), float(h))
        GL.glUniform1f(self._u_time, float(self._app.phase))
        GL.glUniform1f(self._u_alpha, float(self._app.alpha))
        GL.glUniform1f(self._u_voice, float(self._app.smooth_level))
        GL.glUniform1f(self._u_intensity, float(self._app.glow_intensity))
        GL.glUniform3f(self._u_pal_a, *self._app.pal_a)
        GL.glUniform3f(self._u_pal_b, *self._app.pal_b)
        GL.glUniform3f(self._u_pal_c, *self._app.pal_c)
        GL.glUniform3f(self._u_pal_d, *self._app.pal_d)

        GL.glBindVertexArray(self._vao)
        GL.glDrawArrays(GL.GL_TRIANGLE_STRIP, 0, 4)
        GL.glBindVertexArray(0)
        GL.glUseProgram(0)
        return True


class KaelHUDApp(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id="dev.kael.arch.hud")
        self.state: str = "standby"
        self.target_level: float = 0.0
        self.smooth_level: float = 0.0
        self.kael_pid: int | None = None

        self.alpha: float = 0.0
        self.phase: float = 0.0
        self.last_tick: float = time.monotonic()

        # Configurable appearance (live-reloaded from ~/.config/kael/config.json)
        self.glow_intensity: float = 1.0
        self.glow_speed: float = 1.0
        self.show_captions: bool = True
        self.caption_scale: float = 1.0
        self.image_duration: float = 14.0
        self.pal_a: tuple[float, float, float] = (0.62, 0.52, 0.68)
        self.pal_b: tuple[float, float, float] = (0.38, 0.36, 0.32)
        self.pal_c: tuple[float, float, float] = (1.00, 1.00, 1.00)
        self.pal_d: tuple[float, float, float] = (0.00, 0.28, 0.55)
        self.border_stops: list[list[float]] = [
            [0.38, 0.82, 1.00],
            [0.78, 0.46, 1.00],
            [1.00, 0.50, 0.45],
        ]
        self._reload_appearance_config()

        # Dual animated captions: keep BOTH your words and Kael's reply visible
        self.user_words: list[tuple[str, float]] = []
        self.kael_words: list[tuple[str, float]] = []
        self.tool_label: str = ""
        self.caption_alpha: float = 0.0
        self.pill_w_smooth: float = 0.0
        self.pill_h_smooth: float = 0.0
        self._pill_animating: bool = False
        self._last_word_birth: float = 0.0
        self._overlay_dirty: bool = False
        self._overlay_has_pixels: bool = False

        # Floating on-screen image card
        self.image_surface: cairo.ImageSurface | None = None
        self._image_buf: np.ndarray | None = None
        self.image_title: str = ""
        self.image_alpha: float = 0.0
        self.image_shown_at: float = 0.0
        self.image_visible: bool = False

        self.glow_win: Gtk.Window | None = None
        self.glow_area: AppleGlowGLArea | None = None
        self.overlay_area: Gtk.DrawingArea | None = None
        self.sock: socket.socket | None = None
        self._tick_id: int | None = None
        self._tick_pending_idle: bool = False
        self._hide_pending_idle: bool = False
        self._image_hide_timer_id: int | None = None

    def _reload_appearance_config(self) -> None:
        cfg = load_config()
        theme = get_hud_theme(cfg)
        self.glow_intensity = float(cfg.get("hud_glow_intensity", 1.0))
        self.glow_speed = float(cfg.get("hud_glow_speed", 1.0))
        self.show_captions = bool(cfg.get("hud_show_captions", True))
        self.caption_scale = float(cfg.get("hud_caption_scale", 1.0))
        self.image_duration = float(cfg.get("hud_image_duration", 14.0))
        self.pal_a = tuple(float(v) for v in theme["a"])  # type: ignore[assignment]
        self.pal_b = tuple(float(v) for v in theme["b"])  # type: ignore[assignment]
        self.pal_c = tuple(float(v) for v in theme["c"])  # type: ignore[assignment]
        self.pal_d = tuple(float(v) for v in theme["d"])  # type: ignore[assignment]
        self.border_stops = theme["border_rgba"]
        self._overlay_dirty = True

    def do_activate(self) -> None:
        self._apply_transparent_css()
        self._setup_glow_window()
        self._setup_socket()

    def _apply_transparent_css(self) -> None:
        css = Gtk.CssProvider()
        css.load_from_data(b"window, window.background { background: transparent; }")
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _setup_glow_window(self) -> None:
        win = Gtk.Window(application=self)
        win.set_decorated(False)

        if Gtk4LayerShell is not None and Gtk4LayerShell.is_supported():
            Gtk4LayerShell.init_for_window(win)
            Gtk4LayerShell.set_namespace(win, "kael-glow")
            Gtk4LayerShell.set_layer(win, Gtk4LayerShell.Layer.OVERLAY)
            Gtk4LayerShell.set_keyboard_mode(win, Gtk4LayerShell.KeyboardMode.NONE)
            Gtk4LayerShell.set_exclusive_zone(win, -1)
            for edge in (
                Gtk4LayerShell.Edge.TOP,
                Gtk4LayerShell.Edge.BOTTOM,
                Gtk4LayerShell.Edge.LEFT,
                Gtk4LayerShell.Edge.RIGHT,
            ):
                Gtk4LayerShell.set_anchor(win, edge, True)
        else:
            # Graceful fallback for non-layer-shell desktops (e.g., GNOME Wayland or X11)
            win.set_title("Kael HUD")
            win.fullscreen()

        overlay = Gtk.Overlay()

        gl_area = AppleGlowGLArea(self)
        gl_area.set_hexpand(True)
        gl_area.set_vexpand(True)
        overlay.set_child(gl_area)

        draw_area = Gtk.DrawingArea()
        draw_area.set_hexpand(True)
        draw_area.set_vexpand(True)
        draw_area.set_draw_func(self._draw_overlay)
        overlay.add_overlay(draw_area)

        # Clicking anywhere dismisses Kael AND any floating image card immediately
        click = Gtk.GestureClick.new()
        click.set_button(0)
        click.connect("pressed", self._on_screen_clicked)
        overlay.add_controller(click)

        win.set_child(overlay)
        self.glow_win = win
        self.glow_area = gl_area
        self.overlay_area = draw_area
        win.set_visible(False)

    def _cancel_image_hide_timer(self) -> None:
        if self._image_hide_timer_id is not None:
            GLib.source_remove(self._image_hide_timer_id)
            self._image_hide_timer_id = None

    def _on_image_hide_timeout(self) -> bool:
        self._image_hide_timer_id = None
        if self.image_visible and self.state == "standby":
            self.image_visible = False
            self._overlay_dirty = True
            self._ensure_animating()
        return False

    def _show_window(self) -> None:
        if self.glow_win and not self.glow_win.get_visible():
            self.glow_win.set_visible(True)
        # Defer attaching tick callback to idle so GdkFrameClock finishes surface map cleanly
        if self._tick_id is None and not self._tick_pending_idle:
            self._tick_pending_idle = True
            GLib.idle_add(self._start_tick_idle)

    def _start_tick_idle(self) -> bool:
        self._tick_pending_idle = False
        if (
            self._tick_id is None
            and self.glow_area is not None
            and self.glow_win is not None
            and self.glow_win.get_visible()
        ):
            self.last_tick = time.monotonic()
            self._tick_id = self.glow_area.add_tick_callback(self._on_frame_tick)
        return False

    def _hide_window_idle(self) -> bool:
        self._hide_pending_idle = False
        if (
            self.state == "standby"
            and self.alpha <= 0.004
            and self.caption_alpha <= 0.004
            and self.image_alpha <= 0.004
            and not self.image_visible
            and self.glow_win is not None
            and self.glow_win.get_visible()
        ):
            self.glow_win.set_visible(False)
        return False

    def _ensure_animating(self) -> None:
        if self.glow_win is not None and not self.glow_win.get_visible():
            self._show_window()
            return
        if self._tick_id is None and self.glow_area is not None and not self._tick_pending_idle:
            self.last_tick = time.monotonic()
            self._tick_id = self.glow_area.add_tick_callback(self._on_frame_tick)

    def _on_screen_clicked(self, *_args: object) -> None:
        if self.state != "standby" and self.kael_pid is not None:
            try:
                os.kill(self.kael_pid, signal.SIGUSR2)
            except OSError:
                pass
        self._cancel_image_hide_timer()
        self.state = "standby"
        self.target_level = 0.0
        self.user_words = []
        self.kael_words = []
        self.tool_label = ""
        self.image_visible = False
        self._overlay_dirty = True
        self._ensure_animating()

    def _merge_words(
        self,
        existing: list[tuple[str, float]],
        text: str,
        max_words: int = 24,
    ) -> list[tuple[str, float]]:
        now = time.monotonic()
        clean = " ".join(text.strip().split())
        if not clean:
            return []
        new_words = clean.split(" ")[-max_words:]
        old_words = [w for w, _ in existing]
        updated: list[tuple[str, float]] = []
        added = 0
        for i, w in enumerate(new_words):
            if i < len(old_words) and old_words[i] == w:
                updated.append(existing[i])
            else:
                birth = now + added * 0.02
                updated.append((w, birth))
                if birth > self._last_word_birth:
                    self._last_word_birth = birth
                added += 1
        return updated

    def _load_image(self, path: str, title: str) -> None:
        try:
            pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 500, 360, True)
            self.image_surface, self._image_buf = _pixbuf_to_cairo_surface(pb)
            self.image_title = title.strip()
            self.tool_label = ""
            self.image_visible = True
            self.image_shown_at = time.monotonic()
            self._overlay_dirty = True
            self._cancel_image_hide_timer()
            self._show_window()
        except Exception as exc:
            print(f"[HUD] Failed to load image {path}: {exc}", flush=True)

    def _setup_socket(self) -> None:
        try:
            os.unlink(SOCK_PATH)
        except FileNotFoundError:
            pass
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        sock.bind(SOCK_PATH)
        sock.setblocking(False)
        self.sock = sock
        GLib.io_add_watch(sock.fileno(), GLib.IO_IN, self._on_socket_data)

    def _on_socket_data(self, _fd: int, _cond: GLib.IOCondition) -> bool:
        assert self.sock is not None
        while True:
            try:
                raw = self.sock.recv(4096)
            except BlockingIOError:
                break
            try:
                msg = json.loads(raw.decode("utf-8"))
            except Exception:
                continue

            if msg.get("reload_config"):
                self._reload_appearance_config()

            if "pid" in msg:
                self.kael_pid = int(msg["pid"])

            if "image" in msg:
                self._load_image(str(msg["image"]), str(msg.get("image_title", "")))

            if "state" in msg:
                new_state = str(msg["state"])
                if new_state == "standby" and self.state != "standby":
                    self.user_words = []
                    self.kael_words = []
                    self.tool_label = ""
                    self._overlay_dirty = True
                elif new_state != "standby" and self.state == "standby":
                    # Fresh wake-up: clear old image & captions
                    self._cancel_image_hide_timer()
                    self.image_visible = False
                    self.user_words = []
                    self.kael_words = []
                    self.tool_label = ""
                    self._overlay_dirty = True
                self.state = new_state

            if "level" in msg:
                self.target_level = max(0.0, min(1.0, float(msg["level"])))

            if "subtitle" in msg:
                sub = str(msg["subtitle"]).strip()
                if sub.startswith("You:"):
                    self.user_words = self._merge_words(self.user_words, sub[4:], max_words=20)
                    if self.state == "listening":
                        self.kael_words = []
                        self.tool_label = ""
                elif sub:
                    self.tool_label = ""
                    self.kael_words = self._merge_words(self.kael_words, sub, max_words=28)
                else:
                    # Explicit empty subtitle clears stale captions (e.g., on barge-in/interruption)
                    self.user_words = []
                    self.kael_words = []
                    self.tool_label = ""
                self._overlay_dirty = True
            elif msg.get("state") == "thinking" and msg.get("label"):
                new_label = str(msg["label"])
                if new_label != self.tool_label:
                    self.tool_label = new_label
                    self._overlay_dirty = True

            if self.state != "standby" or self.image_visible:
                self._show_window()
            elif self.alpha > 0.01 or self.image_alpha > 0.01 or self.caption_alpha > 0.01:
                self._ensure_animating()

        return True

    def _on_frame_tick(self, area: Gtk.Widget, _clock: Gdk.FrameClock) -> bool:
        now = time.monotonic()
        dt = min(0.05, max(0.001, now - self.last_tick))
        self.last_tick = now

        base_speed = (
            1.9 if self.state == "thinking" else (1.35 if self.state == "speaking" else 1.0)
        ) * self.glow_speed
        self.phase += dt * (base_speed + self.smooth_level * 1.8 * self.glow_speed)

        lerp = 0.28 if self.target_level > self.smooth_level else 0.12
        self.smooth_level += (self.target_level - self.smooth_level) * lerp
        self.target_level *= 0.91

        prev_alpha = self.alpha
        if self.state != "standby":
            self.alpha = min(1.0, self.alpha + dt * 4.5)
        else:
            self.alpha = max(0.0, self.alpha - dt * 4.0)

        prev_caption_alpha = self.caption_alpha
        has_caption = (
            self.show_captions
            and bool(self.user_words or self.kael_words or self.tool_label)
            and self.state != "standby"
        )
        if has_caption:
            self.caption_alpha = min(1.0, self.caption_alpha + dt * 6.5)
        else:
            self.caption_alpha = max(0.0, self.caption_alpha - dt * 5.5)
            if self.caption_alpha <= 0.004:
                self.pill_w_smooth = 0.0
                self.pill_h_smooth = 0.0
                self._pill_animating = False

        # Auto-hide floating image after configured duration when Kael is standing by
        if (
            self.image_visible
            and self.state == "standby"
            and (now - self.image_shown_at > self.image_duration)
        ):
            self.image_visible = False
            self._overlay_dirty = True

        prev_image_alpha = self.image_alpha
        if self.image_visible and self.image_surface is not None:
            self.image_alpha = min(1.0, self.image_alpha + dt * 5.5)
        else:
            self.image_alpha = max(0.0, self.image_alpha - dt * 5.0)
            if self.image_alpha <= 0.005:
                self.image_surface = None
                self._image_buf = None

        # Only redraw GL shader when glow is visible or just finished fading to transparent
        if self.alpha > 0.002 or prev_alpha > 0.002:
            area.queue_draw()

        # Only redraw Cairo overlay when captions/images are dirty or actively animating
        ca = self.caption_alpha * self.alpha
        overlay_active = (ca > 0.005) or (self.image_alpha > 0.005)
        overlay_animating = (
            self._overlay_dirty
            or (abs(self.caption_alpha - prev_caption_alpha) > 0.0005)
            or (abs(self.image_alpha - prev_image_alpha) > 0.0005)
            or (ca > 0.005 and abs(self.alpha - prev_alpha) > 0.0005)
            or (ca > 0.005 and (now - self._last_word_birth) < 0.35)
            or (ca > 0.005 and self._pill_animating)
        )
        if self.overlay_area is not None and (
            overlay_animating or (self._overlay_has_pixels and not overlay_active)
        ):
            self._overlay_dirty = False
            self.overlay_area.queue_draw()

        # Completely faded out -> stop tick loop and defer window hide outside frame tick
        if (
            self.state == "standby"
            and self.alpha <= 0.004
            and self.caption_alpha <= 0.004
            and self.image_alpha <= 0.004
            and not self.image_visible
        ):
            self._tick_id = None
            if not self._hide_pending_idle:
                self._hide_pending_idle = True
                GLib.idle_add(self._hide_window_idle)
            return False

        # Standby with only a fully-settled static image card -> pause 60 FPS ticks until auto-hide
        if (
            self.state == "standby"
            and self.alpha <= 0.004
            and self.caption_alpha <= 0.004
            and self.image_visible
            and self.image_alpha >= 0.996
        ):
            self._tick_id = None
            remaining_ms = max(
                100, int((self.image_duration - (now - self.image_shown_at)) * 1000)
            )
            self._cancel_image_hide_timer()
            self._image_hide_timer_id = GLib.timeout_add(
                remaining_ms, self._on_image_hide_timeout
            )
            return False

        return True

    def _layout_word_lines(
        self,
        cr: cairo.Context,
        words: list[tuple[str, float]],
        max_w: float,
        max_lines: int,
    ) -> tuple[list[list[tuple[str, float, float]]], list[float], float]:
        space_w = cr.text_extents(" ").x_advance
        lines: list[list[tuple[str, float, float]]] = []
        cur: list[tuple[str, float, float]] = []
        cur_w = 0.0
        for word, birth in words:
            adv = cr.text_extents(word).x_advance
            needed = adv if not cur else (space_w + adv)
            if cur and cur_w + needed > max_w:
                lines.append(cur)
                cur = [(word, birth, adv)]
                cur_w = adv
            else:
                cur.append((word, birth, adv))
                cur_w += needed
        if cur:
            lines.append(cur)
        if len(lines) > max_lines:
            lines = lines[-max_lines:]
        widths = [sum(w for _, _, w in ln) + space_w * max(0, len(ln) - 1) for ln in lines]
        return lines, widths, space_w

    def _draw_overlay(
        self, _area: Gtk.DrawingArea, cr: cairo.Context, width: int, height: int
    ) -> None:
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        if width <= 0 or height <= 0:
            self._overlay_has_pixels = False
            return

        drew_anything = False
        caption_top = float(height) - 46.0

        # 1. Dual Apple-style animated captions (your words + Kael's reply)
        ca = self.caption_alpha * self.alpha
        if ca > 0.005 and (self.user_words or self.kael_words or self.tool_label):
            caption_top = self._draw_caption_card(cr, width, height, ca)
            drew_anything = True

        # 2. Floating on-screen Apple-style Image Card (above captions)
        if self.image_alpha > 0.005 and self.image_surface is not None:
            self._draw_image_card(cr, width, height, caption_top)
            drew_anything = True

        self._overlay_has_pixels = drew_anything

    def _draw_caption_card(
        self, cr: cairo.Context, width: int, height: int, ca: float
    ) -> float:
        now = time.monotonic()
        max_text_w = min(680.0, width * 0.72)

        user_font = 15.5 * self.caption_scale
        kael_font = 19.0 * self.caption_scale
        user_lines: list[list[tuple[str, float, float]]] = []
        user_widths: list[float] = []
        user_space = 0.0
        if self.user_words:
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(user_font)
            user_lines, user_widths, user_space = self._layout_word_lines(
                cr, self.user_words, max_text_w, max_lines=2
            )

        kael_lines: list[list[tuple[str, float, float]]] = []
        kael_widths: list[float] = []
        kael_space = 0.0
        if self.kael_words:
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(kael_font)
            kael_lines, kael_widths, kael_space = self._layout_word_lines(
                cr, self.kael_words, max_text_w, max_lines=3
            )
        elif self.tool_label:
            cr.select_font_face("Sans", cairo.FONT_SLANT_ITALIC, cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(16.0)
            kael_lines, kael_widths, kael_space = self._layout_word_lines(
                cr, [(w, now - 0.3) for w in self.tool_label.split()], max_text_w, max_lines=1
            )

        content_w = max(user_widths + kael_widths + [0.0])
        u_lh = user_font * 1.38
        k_lh = kael_font * 1.40
        gap = 8.0 if (user_lines and kael_lines) else 0.0
        content_h = len(user_lines) * u_lh + gap + len(kael_lines) * k_lh

        pad_x, pad_y = 26.0, 14.0
        target_w = max(130.0, content_w + pad_x * 2)
        target_h = content_h + pad_y * 2

        if self.pill_w_smooth <= 1.0:
            self.pill_w_smooth = target_w
            self.pill_h_smooth = target_h
            self._pill_animating = False
        else:
            dw = target_w - self.pill_w_smooth
            dh = target_h - self.pill_h_smooth
            if abs(dw) < 0.4 and abs(dh) < 0.4:
                self.pill_w_smooth = target_w
                self.pill_h_smooth = target_h
                self._pill_animating = False
            else:
                self.pill_w_smooth += dw * 0.24
                self.pill_h_smooth += dh * 0.24
                self._pill_animating = True

        pill_w = self.pill_w_smooth
        pill_h = self.pill_h_smooth
        pill_x = (width - pill_w) * 0.5
        pill_y = height - pill_h - 42.0 + (1.0 - ca) * 14.0
        radius = min(24.0, pill_h * 0.5)

        _rounded_rect(cr, pill_x, pill_y, pill_w, pill_h, radius)
        cr.set_source_rgba(0.05, 0.06, 0.10, 0.72 * ca)
        cr.fill_preserve()

        border = cairo.LinearGradient(pill_x, pill_y, pill_x + pill_w, pill_y + pill_h)
        s0, s1, s2 = self.border_stops[0], self.border_stops[1], self.border_stops[2]
        border.add_color_stop_rgba(0.0, s0[0], s0[1], s0[2], 0.48 * ca)
        border.add_color_stop_rgba(0.5, s1[0], s1[1], s1[2], 0.42 * ca)
        border.add_color_stop_rgba(1.0, s2[0], s2[1], s2[2], 0.45 * ca)
        cr.set_source(border)
        cr.set_line_width(1.25)
        cr.stroke()

        cursor_y = pill_y + pad_y

        # Render user's words (top section, soft silver-blue)
        if user_lines:
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(user_font)
            for row_idx, (ln, lw) in enumerate(zip(user_lines, user_widths)):
                x = (width - lw) * 0.5
                base_y = cursor_y + user_font * 0.86 + row_idx * u_lh
                for word, birth, adv in ln:
                    p = _ease_out_cubic((now - birth) / 0.20)
                    wa = p * ca
                    if wa > 0.01:
                        cr.save()
                        cr.translate(x + adv * 0.5, base_y + (1.0 - p) * 7.0)
                        s = 0.95 + 0.05 * p
                        cr.scale(s, s)
                        cr.translate(-adv * 0.5, 0.0)
                        cr.set_source_rgba(0.74, 0.84, 0.98, 0.84 * wa)
                        cr.move_to(0.0, 0.0)
                        cr.show_text(word)
                        cr.restore()
                    x += adv + user_space
            cursor_y += len(user_lines) * u_lh + gap

        # Render Kael's words (bottom section, crisp bright white)
        if kael_lines:
            is_tool_only = not self.kael_words and bool(self.tool_label)
            cr.select_font_face(
                "Sans",
                cairo.FONT_SLANT_ITALIC if is_tool_only else cairo.FONT_SLANT_NORMAL,
                cairo.FONT_WEIGHT_NORMAL if is_tool_only else cairo.FONT_WEIGHT_BOLD,
            )
            fsize = 16.0 if is_tool_only else kael_font
            cr.set_font_size(fsize)
            for row_idx, (ln, lw) in enumerate(zip(kael_lines, kael_widths)):
                x = (width - lw) * 0.5
                base_y = cursor_y + fsize * 0.88 + row_idx * k_lh
                for word, birth, adv in ln:
                    p = _ease_out_cubic((now - birth) / 0.22)
                    wa = p * ca
                    if wa > 0.01:
                        cr.save()
                        cr.translate(x + adv * 0.5, base_y + (1.0 - p) * 9.0)
                        s = 0.94 + 0.06 * p
                        cr.scale(s, s)
                        cr.translate(-adv * 0.5, 0.0)
                        if is_tool_only:
                            cr.set_source_rgba(0.68, 0.88, 1.00, 0.90 * wa)
                        else:
                            cr.set_source_rgba(1.00, 1.00, 1.00, 0.98 * wa)
                        cr.move_to(0.0, 0.0)
                        cr.show_text(word)
                        cr.restore()
                    x += adv + kael_space

        return pill_y

    def _draw_image_card(
        self, cr: cairo.Context, width: int, height: int, caption_top: float
    ) -> None:
        assert self.image_surface is not None
        ia = _ease_out_cubic(self.image_alpha)
        img_w = float(self.image_surface.get_width())
        img_h = float(self.image_surface.get_height())
        if img_w <= 0 or img_h <= 0:
            return

        pad = 10.0
        title_h = 26.0 if self.image_title else 0.0
        card_w = img_w + pad * 2
        card_h = img_h + pad * 2 + title_h

        # Ensure card fits cleanly between top bar (52px) and caption pill
        top_margin = 52.0
        bottom_limit = max(top_margin + 120.0, caption_top - 18.0)
        avail_h = bottom_limit - top_margin
        avail_w = max(200.0, width - 64.0)
        fit_scale = min(1.0, avail_h / card_h, avail_w / card_w)

        eff_h = card_h * fit_scale
        cx = width * 0.5
        ideal_cy = min(height * 0.45, bottom_limit - eff_h * 0.5)
        cy = max(top_margin + eff_h * 0.5, ideal_cy)
        scale = fit_scale * (0.92 + 0.08 * ia)

        cr.save()
        cr.translate(cx, cy + (1.0 - ia) * 16.0)
        cr.scale(scale, scale)
        x = -card_w * 0.5
        y = -card_h * 0.5

        # Soft ambient drop shadow
        _rounded_rect(cr, x - 4, y + 6, card_w + 8, card_h + 8, 24.0)
        cr.set_source_rgba(0.0, 0.0, 0.0, 0.36 * ia)
        cr.fill()

        # Frosted glass card frame
        _rounded_rect(cr, x, y, card_w, card_h, 20.0)
        cr.set_source_rgba(0.06, 0.07, 0.11, 0.86 * ia)
        cr.fill_preserve()
        border = cairo.LinearGradient(x, y, x + card_w, y + card_h)
        s0, s1, s2 = self.border_stops[0], self.border_stops[1], self.border_stops[2]
        border.add_color_stop_rgba(0.0, s0[0], s0[1], s0[2], 0.58 * ia)
        border.add_color_stop_rgba(0.5, s1[0], s1[1], s1[2], 0.48 * ia)
        border.add_color_stop_rgba(1.0, s2[0], s2[1], s2[2], 0.52 * ia)
        cr.set_source(border)
        cr.set_line_width(1.5)
        cr.stroke()

        # Clipped rounded image
        cr.save()
        _rounded_rect(cr, x + pad, y + pad, img_w, img_h, 14.0)
        cr.clip()
        cr.set_source_surface(self.image_surface, x + pad, y + pad)
        cr.paint_with_alpha(ia)
        cr.restore()

        # Subtle title + dismiss hint (clamped to card width)
        if self.image_title:
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(12.5)
            cr.set_source_rgba(0.84, 0.90, 0.98, 0.82 * ia)
            short_title = (
                self.image_title[:42] + "…"
                if len(self.image_title) > 42
                else self.image_title
            )
            label = f"{short_title}  ·  click anywhere to close"
            ext = cr.text_extents(label)
            if ext.x_advance > card_w - pad * 2:
                label = short_title
                ext = cr.text_extents(label)
            cr.move_to(-ext.x_advance * 0.5, y + pad + img_h + 20.0)
            cr.show_text(label)

        cr.restore()


def main() -> None:
    app = KaelHUDApp()
    app.run(None)


if __name__ == "__main__":
    main()
