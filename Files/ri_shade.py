import copy
import ctypes
import hashlib
import json
import os
import pickle
import threading
import time
import tkinter as tk
from dataclasses import asdict, dataclass, field
from tkinter import filedialog
from typing import List, Optional, Tuple

import glfw
import imgui
import numpy as np
import psutil
import win32api
import win32con
import win32gui
import win32process
import win32ui
from imgui.integrations.glfw import GlfwRenderer
from OpenGL.GL import *

# This project took approximately days to complete not hours days,
# I am currently learning Python and utilized a significant amount of AI assistance for this mini project
# If this project grows significantly, I plan to continue developing my Python skills further
# I also watched numerous tutorials throughout the process.

# Day 2 of wasting my life

try:
    import dxcam

    HAS_DXCAM = True
except ImportError:
    import mss

    HAS_DXCAM = False

user32 = ctypes.windll.user32

_LOCALAPPDATA = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
SAVE_DIR = os.path.join(_LOCALAPPDATA, "RiShade")
SAVE_PATH = os.path.join(SAVE_DIR, "settings.json")
PRESETS_DIR = os.path.join(SAVE_DIR, "CreatedPresets")
SHADER_CACHE_DIR = os.path.join(SAVE_DIR, "shader_cache")

for _d in (SAVE_DIR, PRESETS_DIR, SHADER_CACHE_DIR):
    os.makedirs(_d, exist_ok=True)


def _to_serialisable(obj):
    if isinstance(obj, dict):
        return {k: _to_serialisable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_serialisable(i) for i in obj]
    return obj


def save_settings(s: "Settings") -> None:
    try:
        with open(SAVE_PATH, "w", encoding="utf-8") as f:
            json.dump(_to_serialisable(asdict(s)), f, indent=2)
    except Exception as e:
        print(f"settings save failed: {e}")


def load_settings() -> "Settings":
    if not os.path.exists(SAVE_PATH):
        return Settings()
    try:
        with open(SAVE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        s = Settings()
        for key, val in data.items():
            if not hasattr(s, key):
                continue
            if isinstance(getattr(s, key), tuple):
                setattr(s, key, tuple(val))
            else:
                setattr(s, key, val)
        print(f"loaded settings from {SAVE_PATH}")
        return s
    except Exception as e:
        print(f"settings load failed ({e}), using defaults")
        return Settings()


def list_custom_presets() -> List[str]:
    try:
        return sorted(f[:-5] for f in os.listdir(PRESETS_DIR) if f.endswith(".json"))
    except Exception:
        return []


def save_custom_preset(name: str, s: "Settings") -> bool:
    safe = name.strip().replace("/", "_").replace("\\", "_")
    if not safe:
        return False
    path = os.path.join(PRESETS_DIR, f"{safe}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(_to_serialisable(asdict(s)), f, indent=2)
        return True
    except Exception as e:
        print(f"preset save failed: {e}")
        return False


def load_custom_preset(name: str) -> Optional["Settings"]:
    path = os.path.join(PRESETS_DIR, f"{name}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        s = Settings()
        for key, val in data.items():
            if not hasattr(s, key):
                continue
            if isinstance(getattr(s, key), tuple):
                setattr(s, key, tuple(val))
            else:
                setattr(s, key, val)
        return s
    except Exception as e:
        print(f"preset load failed: {e}")
        return None


def delete_custom_preset(name: str) -> bool:
    path = os.path.join(PRESETS_DIR, f"{name}.json")
    try:
        os.remove(path)
        return True
    except Exception:
        return False


def _force_tk_topmost(hwnd_tk):
    try:
        if not hwnd_tk:
            hwnd_tk = win32gui.FindWindow("TkTopLevel", None)
        if hwnd_tk:
            win32gui.SetWindowPos(
                hwnd_tk,
                win32con.HWND_TOPMOST,
                0,
                0,
                0,
                0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW,
            )
    except Exception:
        pass


def import_preset_from_file() -> Optional[str]:
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    _force_tk_topmost(None)
    path = filedialog.askopenfilename(
        title="Import preset",
        filetypes=[("JSON preset", "*.json")],
        parent=root,
    )
    root.destroy()
    if not path or not os.path.isfile(path):
        return None
    name = os.path.splitext(os.path.basename(path))[0]
    dest = os.path.join(PRESETS_DIR, f"{name}.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return name
    except Exception as e:
        print(f"import failed: {e}")
        return None


def export_preset_to_file(name: str) -> bool:
    src = os.path.join(PRESETS_DIR, f"{name}.json")
    if not os.path.exists(src):
        return False
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    _force_tk_topmost(None)
    dest = filedialog.asksaveasfilename(
        title="Export preset",
        initialfile=f"{name}.json",
        defaultextension=".json",
        filetypes=[("JSON preset", "*.json")],
        parent=root,
    )
    root.destroy()
    if not dest:
        return False
    try:
        with open(src, "r", encoding="utf-8") as f:
            data = f.read()
        with open(dest, "w", encoding="utf-8") as f:
            f.write(data)
        return True
    except Exception as e:
        print(f"export failed: {e}")
        return False


def _cache_key(vs: str, fs: str) -> str:
    return hashlib.md5((vs + fs).encode()).hexdigest()


def link_program_cached(vs: str, fs: str) -> int:
    key = _cache_key(vs, fs)
    path = os.path.join(SHADER_CACHE_DIR, f"{key}.bin")
    if os.path.exists(path):
        try:
            with open(path, "rb") as f:
                fmt, binary = pickle.load(f)
            prog = glCreateProgram()
            glProgramBinary(prog, fmt, binary, len(binary))
            if glGetProgramiv(prog, GL_LINK_STATUS):
                return prog
            glDeleteProgram(prog)
        except Exception as e:
            print(f"shader cache read failed: {e}")
    prog = link_program(vs, fs)
    try:
        length = glGetProgramiv(prog, GL_PROGRAM_BINARY_LENGTH)
        _, fmt, binary = glGetProgramBinary(prog, length)
        with open(path, "wb") as f:
            pickle.dump((int(fmt), bytes(binary)), f)
    except Exception as e:
        print(f"shader cache write failed: {e}")
    return prog


def psc(idx, rgba):
    imgui.push_style_color(idx, *rgba)


def set_clickthrough(hwnd, enable: bool):
    if not hwnd:
        return
    _get = ctypes.windll.user32.GetWindowLongPtrW
    _set = ctypes.windll.user32.SetWindowLongPtrW
    ex = _get(hwnd, -20)
    ex = (
        (ex | win32con.WS_EX_TRANSPARENT)
        if enable
        else (ex & ~win32con.WS_EX_TRANSPARENT)
    )
    _set(hwnd, -20, ex)


def get_proc_name(hwnd) -> str:
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        return psutil.Process(pid).name().lower()
    except Exception:
        return ""


def find_roblox():
    result = []

    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        if "roblox" in win32gui.GetWindowText(hwnd).lower() or any(
            p in get_proc_name(hwnd) for p in ["robloxplayerbeta.exe"]
        ):
            result.append(hwnd)

    win32gui.EnumWindows(cb, None)
    return result[0] if result else None


def force_borderless_windowed(hwnd):
    if not hwnd:
        return
    W = user32.GetSystemMetrics(0)
    H = user32.GetSystemMetrics(1)
    style = ctypes.windll.user32.GetWindowLongPtrW(hwnd, win32con.GWL_STYLE)
    style &= ~(
        win32con.WS_CAPTION
        | win32con.WS_THICKFRAME
        | win32con.WS_MINIMIZE
        | win32con.WS_MAXIMIZE
        | win32con.WS_SYSMENU
    )
    style |= win32con.WS_POPUP
    ctypes.windll.user32.SetWindowLongPtrW(hwnd, win32con.GWL_STYLE, style)
    ex = ctypes.windll.user32.GetWindowLongPtrW(hwnd, win32con.GWL_EXSTYLE)
    ex &= ~(
        win32con.WS_EX_DLGMODALFRAME
        | win32con.WS_EX_CLIENTEDGE
        | win32con.WS_EX_STATICEDGE
    )
    ctypes.windll.user32.SetWindowLongPtrW(hwnd, win32con.GWL_EXSTYLE, ex)
    win32gui.SetWindowPos(
        hwnd,
        win32con.HWND_TOP,
        0,
        0,
        W,
        H,
        win32con.SWP_FRAMECHANGED | win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW,
    )


@dataclass
class Settings:
    grade_en: bool = False
    saturation: float = 1.0
    contrast: float = 1.0
    brightness: float = 0.0
    gamma: float = 1.0
    hue_shift: float = 0.0
    lift: Tuple = field(default_factory=lambda: (0.0, 0.0, 0.0))
    gain: Tuple = field(default_factory=lambda: (1.0, 1.0, 1.0))
    color_balance: Tuple = field(default_factory=lambda: (1.0, 1.0, 1.0))
    color_temp: int = 1
    color_temp_cust: Tuple = field(default_factory=lambda: (1.0, 1.0, 1.0))

    tonemap_en: bool = False
    tonemap_mode: int = 0
    tonemap_exposure: float = 1.0
    tonemap_whitepoint: float = 4.0

    vignette_en: bool = False
    vignette_str: float = 0.5
    vignette_feather: float = 1.2
    vignette_r: float = 0.0
    vignette_ry: float = 0.0

    sharpen_en: bool = False
    sharpen_str: float = 0.8
    sharpen_radius: float = 1.0
    sharpen_clamp: float = 0.08

    bloom_en: bool = False
    bloom_str: float = 0.4
    bloom_passes: int = 2
    bloom_threshold: float = 0.6
    bloom_radius: float = 1.5
    bloom_tint: Tuple = field(default_factory=lambda: (1.0, 1.0, 1.0))

    chroma_en: bool = False
    chroma_str: float = 0.003
    chroma_radial: bool = True

    grain_en: bool = False
    grain_str: float = 0.04
    grain_size: float = 1.0
    grain_colored: bool = False

    dof_en: bool = False
    dof_str: float = 0.6
    dof_focus_range: float = 0.25
    dof_feather: float = 0.4

    ssr_en: bool = False
    ssr_str: float = 1.00
    ssr_threshold: float = 0.50
    ssr_roughness: float = 0.000
    ssr_max_dist: float = 0.500
    ssr_x_nudge: float = 0.010
    ssr_motion_scale: float = 0.45
    ssr_fade_lo: float = 0.001
    ssr_fade_hi: float = 1.000
    ssr_rim: float = 0.35

    gloss_fresnel: float = 1.0
    gloss_nz: float = 0.570
    gloss_darken: float = 0.80
    gloss_bright: float = 1.10
    gloss_cap: float = 0.50
    gloss_tint: Tuple = field(default_factory=lambda: (1.0, 1.0, 1.0))
    gloss_spec_pow: float = 4.5
    gloss_spec_scale: float = 0.55
    gloss_spec_tint: Tuple = field(default_factory=lambda: (1.0, 1.0, 1.0))

    ao_en: bool = False
    ao_str: float = 0.6
    ao_radius: float = 0.012
    ao_samples: int = 1

    fps_cap: int = 0
    gui_visible: bool = True
    gui_alpha: float = 0.95
    obs_mode: bool = False
    perf_mode: bool = False


AO_SAMPLE_COUNTS = [2, 4, 8, 16]
AO_SAMPLE_LABELS = ["2  (fastest)", "4", "8  (default)", "16  (quality)"]
TONEMAP_LABELS = ["Reinhard", "ACES", "Uncharted 2", "Filmic"]
COLOR_TEMP_NAMES = ["Warm", "Neutral", "Cool", "Custom"]
COLOR_TEMP_VALUES = [(1.00, 0.96, 0.88), (1.00, 1.00, 1.00), (0.88, 0.96, 1.00)]

BUILTIN_PRESETS = {
    "Vanilla (off)": dict(),
    "Cinematic": dict(
        grade_en=True,
        tonemap_en=True,
        tonemap_mode=1,
        tonemap_exposure=1.1,
        saturation=1.15,
        contrast=1.12,
        vignette_en=True,
        vignette_str=0.4,
        bloom_en=True,
        bloom_str=0.3,
        bloom_threshold=0.65,
        grain_en=True,
        grain_str=0.025,
    ),
    "Vibrant": dict(
        grade_en=True,
        saturation=1.5,
        contrast=1.1,
        brightness=0.05,
        bloom_en=True,
        bloom_str=0.25,
        tonemap_en=True,
        tonemap_mode=0,
        tonemap_exposure=1.05,
    ),
    "Dark & Moody": dict(
        grade_en=True,
        saturation=0.75,
        contrast=1.3,
        brightness=-0.08,
        gamma=0.88,
        vignette_en=True,
        vignette_str=0.7,
        tonemap_en=True,
        tonemap_mode=3,
        tonemap_exposure=0.9,
    ),
    "Retro Film": dict(
        grade_en=True,
        saturation=0.85,
        contrast=1.15,
        grain_en=True,
        grain_str=0.07,
        grain_colored=True,
        chroma_en=True,
        chroma_str=0.004,
        vignette_en=True,
        vignette_str=0.55,
        tonemap_en=True,
        tonemap_mode=3,
    ),
    "Dreamy Blur": dict(
        dof_en=True,
        dof_str=0.7,
        dof_focus_range=0.18,
        bloom_en=True,
        bloom_str=0.5,
        bloom_threshold=0.5,
        bloom_radius=2.0,
        grade_en=True,
        saturation=1.1,
        brightness=0.04,
    ),
}


def apply_builtin_preset(name: str) -> Settings:
    s = Settings()
    for k, v in BUILTIN_PRESETS.get(name, {}).items():
        setattr(s, k, v)
    return s


VERT = """
#version 330 core
layout(location=0) in vec2 pos;
layout(location=1) in vec2 uv;
out vec2 vUV;
void main(){ vUV=uv; gl_Position=vec4(pos,0.,1.); }
"""

FRAG_PASSTHROUGH = """
#version 330 core
in vec2 vUV; out vec4 fragColor;
uniform sampler2D uTex;
void main(){ fragColor = vec4(texture(uTex, vUV).rgb, 1.0); }
"""

FRAG_DEPTH = """
#version 330 core
in vec2 vUV; out vec4 fragColor;
uniform sampler2D uTex;
float lum(vec3 c){ return dot(c,vec3(0.2126,0.7152,0.0722)); }
void main(){
    vec2 px = 1.0/vec2(textureSize(uTex,0));
    float l  = lum(texture(uTex,vUV).rgb);
    float tl = lum(texture(uTex,vUV+vec2(-px.x, px.y)).rgb);
    float t  = lum(texture(uTex,vUV+vec2(    0., px.y)).rgb);
    float tr = lum(texture(uTex,vUV+vec2( px.x, px.y)).rgb);
    float ml = lum(texture(uTex,vUV+vec2(-px.x,    0.)).rgb);
    float mr = lum(texture(uTex,vUV+vec2( px.x,    0.)).rgb);
    float bl = lum(texture(uTex,vUV+vec2(-px.x,-px.y)).rgb);
    float bm = lum(texture(uTex,vUV+vec2(    0.,-px.y)).rgb);
    float br = lum(texture(uTex,vUV+vec2( px.x,-px.y)).rgb);
    float sx = -tl-2.*ml-bl+tr+2.*mr+br;
    float sy = -tl-2.*t -tr+bl+2.*bm+br;
    float lumMask = 1.0 - smoothstep(0.40, 0.75, l);
    float depth   = lumMask * (1.0 - l * 0.35);
    float edgeMag = clamp(length(vec2(sx,sy))*2.0, 0.0, 1.0);
    depth = mix(depth, 0.4, edgeMag*0.3);
    fragColor = vec4(clamp(depth,0.,1.), sx*0.5+0.5, sy*0.5+0.5, 1.0);
}
"""

FRAG_SSR_ONLY = """
#version 330 core
in vec2 vUV; out vec4 fragColor;
uniform sampler2D uTex;
uniform sampler2D uDepthTex;
uniform sampler2D uPrevTex;
uniform float uSSRStr, uSSRThresh, uSSRMaxDist, uSSRRough;
uniform float uSSRXNudge, uGNZ, uGDarken, uGBright, uGCap;
uniform vec3  uGTint, uGSpecTint;
uniform float uGSpecPow, uGSpecScale;
uniform float uGFresnel;
float lum(vec3 c){ return dot(c, vec3(0.2126, 0.7152, 0.0722)); }
void main(){
    vec3 col  = texture(uTex, vUV).rgb;
    vec3 dbuf = texture(uDepthTex, vUV).rgb;
    float sx  = dbuf.g * 2.0 - 1.0;
    float sy  = dbuf.b * 2.0 - 1.0;
    if(lum(col) > 0.95){ fragColor = vec4(0.0); return; }
    float dist = uSSRMaxDist * 0.2;
    vec2 rUV = vUV + vec2(sx * uGNZ * 0.04, dist);
    rUV.x -= uSSRXNudge * sx;
    vec3  acc = vec3(0.0);
    float totalWeight = 0.0;
    float rough = uSSRRough * 0.004;
    for(int i = 0; i < 64; i++){
        float t = float(i) / 63.0;
        float curve = t * t;
        vec2 sampleUV = rUV + vec2(sin(t*10.0)*rough*t, curve*uSSRMaxDist*0.12);
        vec3 sampleCol = texture(uPrevTex, clamp(sampleUV, 0.001, 0.999)).rgb;
        float weight = (1.0-t) * (lum(sampleCol)+0.1);
        acc += sampleCol * weight;
        totalWeight += weight;
    }
    vec3 refl = acc / max(totalWeight, 0.001);
    float fres = pow(1.0 - clamp(vUV.y, 0.0, 1.0), uGFresnel);
    float weight = uSSRStr * fres * 5.0;
    refl *= uGTint * uGBright * uGDarken;
    float spec = pow(max(lum(refl)-0.05, 0.0), uGSpecPow) * uGSpecScale;
    refl += uGSpecTint * spec * 4.0;
    fragColor = vec4(refl, clamp(weight, 0.0, uGCap));
}
"""

FRAG_ACCUM = """
#version 330 core
in vec2 vUV; out vec4 fragColor;
uniform sampler2D uNewRefl;
uniform sampler2D uAccum;
uniform sampler2D uCurFrame;
uniform sampler2D uPrevFrame;
uniform float uMotionScale;
float lum(vec3 c){ return dot(c,vec3(0.2126,0.7152,0.0722)); }
void main(){
    float diff   = abs(lum(texture(uCurFrame,vUV).rgb) - lum(texture(uPrevFrame,vUV).rgb));
    float motion = clamp(diff * uMotionScale * 10.0, 0.0, 1.0);
    vec4 newR = texture(uNewRefl, vUV);
    vec4 accR = texture(uAccum,   vUV);
    vec4 accumulated = mix(newR, accR, 0.6);
    vec4 faded = vec4(accR.rgb, accR.a * (1.0 - motion * 0.80));
    fragColor = clamp(mix(accumulated, faded, motion), 0.0, 1.0);
}
"""

FRAG_COMPOSITE = """
#version 330 core
in vec2 vUV; out vec4 fragColor;
uniform sampler2D uScene;
uniform sampler2D uRefl;
void main(){
    vec3 scene = texture(uScene, vUV).rgb;
    vec4 refl  = texture(uRefl,  vUV);
    fragColor  = vec4(mix(scene, refl.rgb, clamp(refl.a, 0., 1.)), 1.0);
}
"""

FRAG_MAIN = """
#version 330 core
in vec2 vUV; out vec4 fragColor;
uniform sampler2D uTex;
uniform bool  uGrade;
uniform float uSat,uCon,uBri,uGamma,uHue;
uniform vec3  uLift,uGain,uBalance,uTemp;
uniform bool  uTonemap;
uniform int   uTonemapMode;
uniform float uExposure,uWhitepoint;
uniform bool  uVignette;
uniform float uVigStr,uVigFeat,uVigCX,uVigCY;
uniform bool  uSharpen;
uniform float uShStr,uShRadius,uShClamp;
uniform bool  uChroma;
uniform float uChStr;
uniform bool  uChRadial;
uniform bool  uGrain;
uniform float uGrStr,uGrSize;
uniform bool  uGrColored;
uniform float uTime;
uniform bool  uDOF;
uniform float uDOFStr,uDOFFocus,uDOFFeather;
uniform bool  uAO;
uniform float uAOStr,uAORadius;
uniform int   uAOSamples;

vec3 rgb2hsv(vec3 c){
    vec4 K=vec4(0.,-1./3.,2./3.,-1.);
    vec4 p=mix(vec4(c.bg,K.wz),vec4(c.gb,K.xy),step(c.b,c.g));
    vec4 q=mix(vec4(p.xyw,c.r),vec4(c.r,p.yzx),step(p.x,c.r));
    float d=q.x-min(q.w,q.y);
    return vec3(abs(q.z+(q.w-q.y)/(6.*d+1e-10)),d/(q.x+1e-10),q.x);
}
vec3 hsv2rgb(vec3 c){
    vec4 K=vec4(1.,2./3.,1./3.,3.);
    vec3 p=abs(fract(c.xxx+K.xyz)*6.-K.www);
    return c.z*mix(K.xxx,clamp(p-K.xxx,0.,1.),c.y);
}
float lum(vec3 c){ return dot(c,vec3(0.2126,0.7152,0.0722)); }
float hash(vec2 p){ return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5); }

vec3 reinhard(vec3 c, float wp){ return c*(1.+c/(wp*wp))/(1.+c); }
vec3 aces(vec3 x){
    float a=2.51,b=0.03,g=2.43,d=0.59,e=0.14;
    return clamp((x*(a*x+b))/(x*(g*x+d)+e),0.,1.);
}
vec3 uncharted2(vec3 x){
    float A=0.15,B=0.50,C=0.10,D=0.20,E=0.02,F=0.30;
    return ((x*(A*x+C*B)+D*E)/(x*(A*x+B)+D*F))-E/F;
}
vec3 filmic(vec3 c){
    c=max(vec3(0.),c-0.004);
    return (c*(6.2*c+0.5))/(c*(6.2*c+1.7)+0.06);
}
vec3 applyTonemap(vec3 c){
    c*=uExposure;
    if(uTonemapMode==0) return clamp(reinhard(c,uWhitepoint),0.,1.);
    if(uTonemapMode==1) return clamp(aces(c),0.,1.);
    if(uTonemapMode==2){ vec3 w=uncharted2(vec3(uWhitepoint)); return clamp(uncharted2(c)/w,0.,1.); }
    return clamp(filmic(c),0.,1.);
}
float sampleAO(vec2 uv){
    float ao=0.,l=lum(texture(uTex,uv).rgb);
    int n=max(uAOSamples,1);
    for(int i=0;i<n;i++){
        float a=float(i)*(6.28318/float(n));
        ao+=clamp(l-lum(texture(uTex,uv+vec2(cos(a),sin(a))*uAORadius).rgb),0.,1.);
    }
    return 1.-(ao/float(n))*uAOStr;
}
void main(){
    vec2 uv=vUV;
    vec3 col;
    if(uChroma){
        vec2 off=vec2(uChStr,0.);
        if(uChRadial){ vec2 dir=uv-0.5; off=dir*uChStr; }
        col.r=texture(uTex,uv-off).r;
        col.g=texture(uTex,uv     ).g;
        col.b=texture(uTex,uv+off).b;
    } else {
        col=texture(uTex,uv).rgb;
    }
    if(uDOF){
        vec2 d=uv-0.5;
        float dist=length(d);
        float blur=smoothstep(uDOFFocus,uDOFFocus+uDOFFeather,dist)*uDOFStr;
        if(blur>0.001){
            vec2 px=1./vec2(textureSize(uTex,0));
            float r=blur*6.0;
            vec3 acc=col; float w=1.;
            for(int i=-3;i<=3;i++) for(int j=-3;j<=3;j++){
                float wij=exp(-0.5*float(i*i+j*j)/4.);
                acc+=texture(uTex,uv+vec2(float(i),float(j))*px*r).rgb*wij;
                w+=wij;
            }
            col=mix(col,acc/w,blur);
        }
    }
    if(uSharpen && uShStr>0.){
        vec2 px=1./vec2(textureSize(uTex,0))*uShRadius;
        vec3 blur=(texture(uTex,uv+vec2( px.x,0.)).rgb
                  +texture(uTex,uv+vec2(-px.x,0.)).rgb
                  +texture(uTex,uv+vec2(0., px.y)).rgb
                  +texture(uTex,uv+vec2(0.,-px.y)).rgb)*0.25;
        vec3 delta=clamp((col-blur)*uShStr,-uShClamp,uShClamp);
        col=clamp(col+delta,0.,1.);
    }
    if(uAO) col*=sampleAO(uv);
    if(uGrade){
        col*=uTemp*uBalance;
        col=col*(uGain-uLift)+uLift;
        vec3 hsv=rgb2hsv(col);
        hsv.y=clamp(hsv.y*uSat,0.,1.);
        hsv.x=fract(hsv.x+uHue/360.);
        col=hsv2rgb(hsv);
        col=(col-0.5)*uCon+0.5+uBri;
        col=pow(max(col,vec3(0.)),vec3(1./max(uGamma,0.01)));
    }
    if(uTonemap) col=applyTonemap(col);
    if(uGrain){
        vec2 gUV=uv*uGrSize+vec2(uTime*0.01);
        float n=hash(gUV)-0.5;
        if(uGrColored){
            vec3 noise=vec3(hash(gUV+0.1),hash(gUV+0.2),hash(gUV+0.3))-0.5;
            col+=noise*uGrStr;
        } else {
            col+=vec3(n)*uGrStr;
        }
    }
    if(uVignette){
        vec2 v=(uv-vec2(0.5+uVigCX,0.5+uVigCY))*2.;
        col*=clamp(1.-pow(dot(v,v),uVigFeat)*uVigStr,0.,1.);
    }
    fragColor=vec4(clamp(col,0.,1.),1.);
}
"""

FRAG_BLOOM_H = """
#version 330 core
in vec2 vUV; out vec4 fragColor;
uniform sampler2D uTex;
uniform float uStr,uThresh,uRadius;
uniform vec3  uTint;
void main(){
    vec2 px=1./vec2(textureSize(uTex,0))*uRadius;
    const float w[9]=float[](0.05,0.09,0.12,0.15,0.18,0.15,0.12,0.09,0.05);
    vec3 c=vec3(0.);
    for(int i=0;i<9;i++)
        c+=max(texture(uTex,vUV+vec2((float(i)-4.)*px.x,0.)).rgb-vec3(uThresh),vec3(0.))*w[i];
    fragColor=vec4(texture(uTex,vUV).rgb+c*uStr*uTint,1.);
}
"""

FRAG_BLOOM_V = """
#version 330 core
in vec2 vUV; out vec4 fragColor;
uniform sampler2D uTex;
uniform float uStr,uThresh,uRadius;
uniform vec3  uTint;
void main(){
    vec2 px=1./vec2(textureSize(uTex,0))*uRadius;
    const float w[9]=float[](0.05,0.09,0.12,0.15,0.18,0.15,0.12,0.09,0.05);
    vec3 c=vec3(0.);
    for(int i=0;i<9;i++)
        c+=max(texture(uTex,vUV+vec2(0.,(float(i)-4.)*px.y)).rgb-vec3(uThresh),vec3(0.))*w[i];
    fragColor=vec4(texture(uTex,vUV).rgb+c*uStr*uTint,1.);
}
"""


def compile_shader(src: str, kind: int) -> int:
    s = glCreateShader(kind)
    glShaderSource(s, src)
    glCompileShader(s)
    if not glGetShaderiv(s, GL_COMPILE_STATUS):
        raise RuntimeError(f"Shader compile error:\n{glGetShaderInfoLog(s).decode()}")
    return s


def link_program(vs: str, fs: str) -> int:
    v = compile_shader(vs, GL_VERTEX_SHADER)
    f = compile_shader(fs, GL_FRAGMENT_SHADER)
    p = glCreateProgram()
    glAttachShader(p, v)
    glAttachShader(p, f)
    glLinkProgram(p)
    if not glGetProgramiv(p, GL_LINK_STATUS):
        raise RuntimeError(glGetProgramInfoLog(p).decode())
    glDeleteShader(v)
    glDeleteShader(f)
    return p


def make_fbo(w: int, h: int):
    fbo, tex = glGenFramebuffers(1), glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, tex)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB16F, w, h, 0, GL_RGB, GL_FLOAT, None)
    for p, v in [
        (GL_TEXTURE_MIN_FILTER, GL_LINEAR),
        (GL_TEXTURE_MAG_FILTER, GL_LINEAR),
        (GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE),
        (GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE),
    ]:
        glTexParameteri(GL_TEXTURE_2D, p, v)
    glBindFramebuffer(GL_FRAMEBUFFER, fbo)
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, tex, 0)
    glBindFramebuffer(GL_FRAMEBUFFER, 0)
    return fbo, tex


def make_rgba_fbo(w: int, h: int):
    fbo, tex = glGenFramebuffers(1), glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, tex)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA16F, w, h, 0, GL_RGBA, GL_FLOAT, None)
    for p, v in [
        (GL_TEXTURE_MIN_FILTER, GL_LINEAR),
        (GL_TEXTURE_MAG_FILTER, GL_LINEAR),
        (GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE),
        (GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE),
    ]:
        glTexParameteri(GL_TEXTURE_2D, p, v)
    glBindFramebuffer(GL_FRAMEBUFFER, fbo)
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, tex, 0)
    glBindFramebuffer(GL_FRAMEBUFFER, 0)
    return fbo, tex


def draw_quad(vao: int):
    glBindVertexArray(vao)
    glDrawElements(GL_TRIANGLES, 6, GL_UNSIGNED_INT, None)


class FrameGrabber(threading.Thread):
    def __init__(self, W: int, H: int, roblox_hwnd=None):
        super().__init__(daemon=True)
        self.W, self.H = W, H
        self.roblox_hwnd = roblox_hwnd
        self.obs_mode = False
        self._frame = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._new = False
        self.restarted = threading.Event()

    def _grab_printwindow(self):
        hwnd = self.roblox_hwnd
        if not hwnd:
            return None
        try:
            left, top, right, bottom = win32gui.GetClientRect(hwnd)
            w, h = right - left, bottom - top
            if w <= 0 or h <= 0:
                return None
            hwnd_dc = win32gui.GetWindowDC(hwnd)
            src_dc = win32ui.CreateDCFromHandle(hwnd_dc)
            mem_dc = src_dc.CreateCompatibleDC()
            bmp = win32ui.CreateBitmap()
            bmp.CreateCompatibleBitmap(src_dc, w, h)
            mem_dc.SelectObject(bmp)
            ctypes.windll.user32.PrintWindow(hwnd, mem_dc.GetSafeHdc(), 0x2)
            raw = bmp.GetBitmapBits(True)
            img = (
                np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 4)[:, :, 2::-1].copy()
            )
            win32gui.DeleteObject(bmp.GetHandle())
            mem_dc.DeleteDC()
            src_dc.DeleteDC()
            win32gui.ReleaseDC(hwnd, hwnd_dc)
            if img.mean() < 2.0:
                return None
            if img.shape[1] != self.W or img.shape[0] != self.H:
                ys = np.linspace(0, img.shape[0] - 1, self.H).astype(np.int32)
                xs = np.linspace(0, img.shape[1] - 1, self.W).astype(np.int32)
                img = img[np.ix_(ys, xs)]
            return img
        except Exception:
            return None

    def run(self):
        if HAS_DXCAM:
            self._run_dxcam()
        else:
            self._run_mss()

    def _run_dxcam(self):
        while not self._stop.is_set():
            cam = None
            try:
                cam = dxcam.create(output_color="RGB")
                cam.start(target_fps=0, video_mode=True)
                while not self._stop.is_set():
                    f = (
                        self._grab_printwindow()
                        if self.obs_mode
                        else cam.get_latest_frame()
                    )
                    if f is not None:
                        with self._lock:
                            self._frame = f
                            self._new = True
                    else:
                        time.sleep(0.001)
            except Exception as e:
                print(f"restarting capture in 0.5s: {e}")
            finally:
                try:
                    if cam is not None:
                        cam.stop()
                        del cam
                except Exception:
                    pass
            # Brief pause lets the GPU settlw
            if not self._stop.is_set():
                time.sleep(0.5)
                self.restarted.set()

    def _run_mss(self):
        with mss.mss() as sct:
            mon = {"left": 0, "top": 0, "width": self.W, "height": self.H}
            while not self._stop.is_set():
                if self.obs_mode:
                    f = self._grab_printwindow()
                    if f is not None:
                        with self._lock:
                            self._frame = f
                            self._new = True
                else:
                    raw = np.array(sct.grab(mon), dtype=np.uint8)
                    with self._lock:
                        self._frame = raw[:, :, 2::-1].copy()
                        self._new = True

    def get_frame(self):
        with self._lock:
            if not self._new:
                return None
            self._new = False
            return self._frame

    def stop(self):
        self._stop.set()


ACCENT = (0.62, 0.22, 0.92, 1.0)
ACCENT_DIM = (0.42, 0.12, 0.65, 1.0)
ACCENT_HOV = (0.75, 0.38, 1.00, 1.0)
BTN_ON = (0.32, 0.18, 0.60, 1.0)
BTN_ON_HOV = (0.44, 0.26, 0.80, 1.0)
BTN_OFF = (0.22, 0.22, 0.22, 1.0)
BTN_OFF_HOV = (0.30, 0.30, 0.30, 1.0)
BG = (0.08, 0.08, 0.08, 1.0)
BG2 = (0.12, 0.12, 0.12, 1.0)
BG3 = (0.17, 0.17, 0.17, 1.0)
TXT = (0.92, 0.92, 0.92, 1.0)
TXT_DIM = (0.45, 0.45, 0.45, 1.0)
BORDER = (0.22, 0.22, 0.22, 1.0)
TAB_ACTIVE = (0.13, 0.13, 0.13, 1.0)
RED = (0.75, 0.18, 0.18, 1.0)
RED_HOV = (0.90, 0.22, 0.22, 1.0)
GREEN = (0.18, 0.55, 0.26, 1.0)
GREEN_HOV = (0.22, 0.70, 0.32, 1.0)
ORANGE = (0.70, 0.40, 0.08, 1.0)
ORANGE_HOV = (0.88, 0.50, 0.12, 1.0)


def apply_theme():
    s = imgui.get_style()
    s.window_rounding = 7
    s.frame_rounding = 4
    s.grab_rounding = 4
    s.scrollbar_rounding = 4
    s.tab_rounding = 5
    s.frame_padding = (8, 4)
    s.item_spacing = (8, 5)
    s.window_padding = (10, 10)
    s.scrollbar_size = 9

    def c(i, v):
        s.colors[i] = v

    c(imgui.COLOR_WINDOW_BACKGROUND, BG)
    c(imgui.COLOR_CHILD_BACKGROUND, BG)
    c(imgui.COLOR_POPUP_BACKGROUND, BG2)
    c(imgui.COLOR_BORDER, BORDER)
    c(imgui.COLOR_FRAME_BACKGROUND, BG2)
    c(imgui.COLOR_FRAME_BACKGROUND_HOVERED, BG3)
    c(imgui.COLOR_FRAME_BACKGROUND_ACTIVE, BG3)
    c(imgui.COLOR_TITLE_BACKGROUND, (0.06, 0.06, 0.06, 1.0))
    c(imgui.COLOR_TITLE_BACKGROUND_ACTIVE, (0.10, 0.10, 0.10, 1.0))
    c(imgui.COLOR_TITLE_BACKGROUND_COLLAPSED, (0.06, 0.06, 0.06, 1.0))
    c(imgui.COLOR_SCROLLBAR_BACKGROUND, BG)
    c(imgui.COLOR_SCROLLBAR_GRAB, BG3)
    c(imgui.COLOR_SCROLLBAR_GRAB_HOVERED, ACCENT_DIM)
    c(imgui.COLOR_SCROLLBAR_GRAB_ACTIVE, ACCENT)
    c(imgui.COLOR_CHECK_MARK, ACCENT)
    c(imgui.COLOR_SLIDER_GRAB, ACCENT_DIM)
    c(imgui.COLOR_SLIDER_GRAB_ACTIVE, ACCENT)
    c(imgui.COLOR_BUTTON, BG3)
    c(imgui.COLOR_BUTTON_HOVERED, ACCENT_DIM)
    c(imgui.COLOR_BUTTON_ACTIVE, ACCENT)
    c(imgui.COLOR_HEADER, (0.16, 0.16, 0.16, 1.0))
    c(imgui.COLOR_HEADER_HOVERED, (0.22, 0.22, 0.22, 1.0))
    c(imgui.COLOR_HEADER_ACTIVE, (0.26, 0.26, 0.26, 1.0))
    c(imgui.COLOR_SEPARATOR, BORDER)
    c(imgui.COLOR_RESIZE_GRIP, ACCENT_DIM)
    c(imgui.COLOR_RESIZE_GRIP_HOVERED, ACCENT)
    c(imgui.COLOR_RESIZE_GRIP_ACTIVE, ACCENT_HOV)
    c(imgui.COLOR_TEXT, TXT)
    c(imgui.COLOR_TEXT_DISABLED, TXT_DIM)
    c(imgui.COLOR_TAB, (0.10, 0.10, 0.10, 1.0))
    c(imgui.COLOR_TAB_HOVERED, (0.20, 0.20, 0.20, 1.0))
    c(imgui.COLOR_TAB_ACTIVE, TAB_ACTIVE)
    c(imgui.COLOR_TAB_UNFOCUSED, (0.08, 0.08, 0.08, 1.0))
    c(imgui.COLOR_TAB_UNFOCUSED_ACTIVE, TAB_ACTIVE)


def slid(label, val, lo, hi, fmt="%.2f", width=-1):
    if width != -1:
        imgui.push_item_width(width)
    _, v = imgui.slider_float(label, val, lo, hi, fmt)
    if width != -1:
        imgui.pop_item_width()
    return v


def toggle_btn(label, enabled, uid=""):
    key = uid or label
    if enabled:
        psc(imgui.COLOR_BUTTON, BTN_ON)
        psc(imgui.COLOR_BUTTON_HOVERED, BTN_ON_HOV)
        psc(imgui.COLOR_BUTTON_ACTIVE, ACCENT_HOV)
        psc(imgui.COLOR_TEXT, (1.0, 1.0, 1.0, 1.0))
        clicked = imgui.button(f" ON ##{key}", 44, 0)
        imgui.pop_style_color(4)
        if clicked:
            enabled = False
    else:
        psc(imgui.COLOR_BUTTON, BTN_OFF)
        psc(imgui.COLOR_BUTTON_HOVERED, BTN_OFF_HOV)
        psc(imgui.COLOR_BUTTON_ACTIVE, BG3)
        psc(imgui.COLOR_TEXT, TXT_DIM)
        clicked = imgui.button(f"OFF##{key}", 44, 0)
        imgui.pop_style_color(4)
        if clicked:
            enabled = True
    return enabled


def section_header(title, enabled, uid=""):
    key = uid or title
    psc(imgui.COLOR_TEXT, TXT)
    imgui.text(f"  {title}")
    imgui.pop_style_color()
    imgui.same_line()
    avail = imgui.get_content_region_available_width()
    imgui.set_cursor_pos_x(imgui.get_cursor_pos_x() + avail - 50)
    enabled = toggle_btn(title, enabled, key)
    psc(imgui.COLOR_SEPARATOR, BORDER)
    imgui.separator()
    imgui.pop_style_color()
    psc(imgui.COLOR_HEADER, BG2)
    psc(imgui.COLOR_HEADER_HOVERED, BG3)
    psc(imgui.COLOR_HEADER_ACTIVE, BG3)
    open_ = imgui.tree_node(f"  details##body{key}")
    imgui.pop_style_color(3)
    return open_, enabled


def subheading(text):
    psc(imgui.COLOR_TEXT, ACCENT)
    imgui.text(f"  {text}")
    imgui.pop_style_color()


def hint(text):
    psc(imgui.COLOR_TEXT, TXT_DIM)
    imgui.text(f"    {text}")
    imgui.pop_style_color()


def rgb_sliders(label, tup, lo=0.0, hi=2.0):
    r, g, b = tup
    _, r = imgui.slider_float(f"R##{label}r", r, lo, hi, "%.3f")
    _, g = imgui.slider_float(f"G##{label}g", g, lo, hi, "%.3f")
    _, b = imgui.slider_float(f"B##{label}b", b, lo, hi, "%.3f")
    return (r, g, b)


def tab_colour(s: Settings) -> Settings:
    imgui.push_item_width(-1)
    open_, s.grade_en = section_header("Colour Grade", s.grade_en, "cg")
    if open_:
        imgui.indent(10)
        if s.grade_en:
            s.saturation = slid("Saturation##sat", s.saturation, 0.0, 3.0)
            s.contrast = slid("Contrast##con", s.contrast, 0.0, 3.0)
            s.brightness = slid("Brightness##bri", s.brightness, -1.0, 1.0)
            s.gamma = slid("Gamma##gam", s.gamma, 0.2, 3.0)
            s.hue_shift = slid("Hue Shift##hue", s.hue_shift, -180.0, 180.0, "%.1f°")
            imgui.spacing()
            subheading("Colour Temp")
            imgui.push_item_width(140)
            _, s.color_temp = imgui.combo("##ct", s.color_temp, COLOR_TEMP_NAMES)
            imgui.pop_item_width()
            if s.color_temp == 3:
                s.color_temp_cust = rgb_sliders("ctc", s.color_temp_cust, 0.5, 1.5)
            imgui.spacing()
            subheading("Balance  (R / G / B)")
            s.color_balance = rgb_sliders("cb", s.color_balance, 0.0, 2.0)
            imgui.spacing()
            subheading("Lift  (Shadow Tint)")
            s.lift = rgb_sliders("lift", s.lift, -0.2, 0.2)
            subheading("Gain  (Highlight Tint)")
            s.gain = rgb_sliders("gain", s.gain, 0.5, 2.0)
        else:
            hint("disabled")
        imgui.tree_pop()
        imgui.unindent(10)
    imgui.spacing()
    open_, s.tonemap_en = section_header("Tonemapping", s.tonemap_en, "tm")
    if open_:
        imgui.indent(10)
        if s.tonemap_en:
            imgui.text("Mode:")
            imgui.same_line()
            imgui.push_item_width(160)
            _, s.tonemap_mode = imgui.combo("##tmm", s.tonemap_mode, TONEMAP_LABELS)
            imgui.pop_item_width()
            s.tonemap_exposure = slid("Exposure##tme", s.tonemap_exposure, 0.1, 5.0)
            s.tonemap_whitepoint = slid(
                "White Point##tmw", s.tonemap_whitepoint, 1.0, 16.0
            )
        else:
            hint("disabled")
        imgui.tree_pop()
        imgui.unindent(10)
    imgui.spacing()
    open_, s.vignette_en = section_header("Vignette", s.vignette_en, "vig")
    if open_:
        imgui.indent(10)
        if s.vignette_en:
            s.vignette_str = slid("Strength##vstr", s.vignette_str, 0.0, 4.0)
            s.vignette_feather = slid("Feather##vfeat", s.vignette_feather, 0.1, 4.0)
            s.vignette_r = slid("Centre X##vcx", s.vignette_r, -0.5, 0.5)
            s.vignette_ry = slid("Centre Y##vcy", s.vignette_ry, -0.5, 0.5)
        else:
            hint("disabled")
        imgui.tree_pop()
        imgui.unindent(10)
    imgui.spacing()
    open_, s.grain_en = section_header("Film Grain", s.grain_en, "gr")
    if open_:
        imgui.indent(10)
        if s.grain_en:
            s.grain_str = slid("Strength##grstr", s.grain_str, 0.0, 0.3, "%.4f")
            s.grain_size = slid("Size##grsize", s.grain_size, 0.1, 5.0)
            _, s.grain_colored = imgui.checkbox("Coloured Grain##grc", s.grain_colored)
        else:
            hint("disabled")
        imgui.tree_pop()
        imgui.unindent(10)
    imgui.pop_item_width()
    return s


def tab_effects(s: Settings) -> Settings:
    imgui.push_item_width(-1)
    open_, s.sharpen_en = section_header("Sharpen", s.sharpen_en, "sh")
    if open_:
        imgui.indent(10)
        if s.sharpen_en:
            s.sharpen_str = slid("Strength##shstr", s.sharpen_str, 0.0, 5.0)
            s.sharpen_radius = slid("Radius##shrad", s.sharpen_radius, 0.5, 4.0)
            s.sharpen_clamp = slid("Clamp##shcl", s.sharpen_clamp, 0.01, 1.0, "%.3f")
            hint("keep clamp low to avoid halo artifacts")
        else:
            hint("disabled")
        imgui.tree_pop()
        imgui.unindent(10)
    imgui.spacing()
    open_, s.bloom_en = section_header("Bloom", s.bloom_en, "bl")
    if open_:
        imgui.indent(10)
        if s.bloom_en:
            s.bloom_str = slid("Strength##blstr", s.bloom_str, 0.0, 5.0)
            s.bloom_threshold = slid("Threshold##blth", s.bloom_threshold, 0.0, 1.0)
            s.bloom_radius = slid("Radius##blrad", s.bloom_radius, 0.5, 4.0)
            s.bloom_passes = int(
                slid("Passes##blp", float(s.bloom_passes), 1.0, 6.0, "%.0f")
            )
            subheading("Bloom Tint  (R / G / B)")
            s.bloom_tint = rgb_sliders("blt", s.bloom_tint, 0.0, 2.0)
        else:
            hint("disabled")
        imgui.tree_pop()
        imgui.unindent(10)
    imgui.spacing()
    open_, s.chroma_en = section_header("Chromatic Aberration", s.chroma_en, "ca")
    if open_:
        imgui.indent(10)
        if s.chroma_en:
            s.chroma_str = slid("Strength##castr", s.chroma_str, 0.0, 0.02, "%.4f")
            _, s.chroma_radial = imgui.checkbox(
                "Radial (edge-based)##car", s.chroma_radial
            )
            hint("radial is more natural-looking")
        else:
            hint("disabled")
        imgui.tree_pop()
        imgui.unindent(10)
    imgui.spacing()
    open_, s.dof_en = section_header("Depth of Field", s.dof_en, "dof")
    if open_:
        imgui.indent(10)
        if s.dof_en:
            s.dof_str = slid("Blur Strength##dofstr", s.dof_str, 0.0, 1.0)
            s.dof_focus_range = slid(
                "Focus Radius##doffoc", s.dof_focus_range, 0.0, 0.5
            )
            s.dof_feather = slid("Feather##doffeat", s.dof_feather, 0.0, 1.0)
            hint("blurs edges, centre stays sharp")
        else:
            hint("disabled")
        imgui.tree_pop()
        imgui.unindent(10)
    imgui.pop_item_width()
    return s


def tab_reflections(s: Settings) -> Settings:
    imgui.push_item_width(-1)
    open_, s.ssr_en = section_header("Screen-Space Reflections", s.ssr_en, "ssr")
    if open_:
        imgui.indent(10)
        if s.ssr_en:
            subheading("Core")
            s.ssr_str = slid("Strength##ssrstr", s.ssr_str, 0.0, 1.0)
            s.ssr_threshold = slid("Threshold##ssrthr", s.ssr_threshold, 0.0, 1.0)
            s.ssr_roughness = slid(
                "Roughness##ssrrou", s.ssr_roughness, 0.0, 0.5, "%.3f"
            )
            s.ssr_max_dist = slid("Max Dist##ssrmaxd", s.ssr_max_dist, 0.0, 0.5, "%.3f")
            s.ssr_x_nudge = slid("X Nudge##ssrxnu", s.ssr_x_nudge, 0.0, 0.2, "%.3f")
            s.ssr_motion_scale = slid(
                "Motion Fade##ssrms", s.ssr_motion_scale, 0.0, 3.0
            )
            hint("higher = reflections fade faster when camera moves")
            imgui.spacing()
            subheading("Edge Fade")
            s.ssr_fade_lo = slid(
                "Fade Start##ssrflo", s.ssr_fade_lo, 0.001, 0.5, "%.3f"
            )
            s.ssr_fade_hi = slid("Fade End##ssrfhi", s.ssr_fade_hi, 0.5, 1.0, "%.3f")
            s.ssr_rim = slid("Rim Strength##ssrrim", s.ssr_rim, 0.0, 1.0)
            imgui.spacing()
            subheading("Gloss")
            s.gloss_fresnel = slid(
                "Fresnel Power##gfp", s.gloss_fresnel, 1.0, 15.0, "%.1f"
            )
            s.gloss_nz = slid("Surface Flat##gnz", s.gloss_nz, 0.01, 1.0, "%.3f")
            s.gloss_darken = slid("Darken##gdk", s.gloss_darken, 0.3, 1.0)
            s.gloss_bright = slid("Brightness##gbr", s.gloss_bright, 0.0, 3.0)
            s.gloss_cap = slid("Mirror Cap##gmc", s.gloss_cap, 0.0, 1.0)
            subheading("Gloss Tint  (R / G / B)")
            s.gloss_tint = rgb_sliders("gt", s.gloss_tint, 0.0, 2.0)
            imgui.spacing()
            subheading("Specular")
            s.gloss_spec_pow = slid(
                "Spec Power##gsp", s.gloss_spec_pow, 1.0, 16.0, "%.1f"
            )
            s.gloss_spec_scale = slid("Spec Scale##gss", s.gloss_spec_scale, 0.0, 3.0)
            subheading("Spec Tint  (R / G / B)")
            s.gloss_spec_tint = rgb_sliders("gst", s.gloss_spec_tint, 0.0, 2.0)
        else:
            hint("disabled")
        imgui.tree_pop()
        imgui.unindent(10)
    imgui.spacing()
    open_, s.ao_en = section_header("Ambient Occlusion", s.ao_en, "ao")
    if open_:
        imgui.indent(10)
        if s.ao_en:
            s.ao_str = slid("Strength##aostr", s.ao_str, 0.0, 3.0)
            s.ao_radius = slid("Radius##aorad", s.ao_radius, 0.001, 0.1, "%.4f")
            imgui.text("Samples:")
            imgui.same_line()
            imgui.push_item_width(170)
            _, s.ao_samples = imgui.combo("##aosc", s.ao_samples, AO_SAMPLE_LABELS)
            imgui.pop_item_width()
        else:
            hint("disabled")
        imgui.tree_pop()
        imgui.unindent(10)
    imgui.pop_item_width()
    return s


_preset_name_buf = [""]
_selected_custom = [-1]
_custom_list = list_custom_presets()
_preset_status_msg = [""]
_preset_status_t = [0.0]


def _ask_preset_name() -> str:

    result = [""]

    root = tk.Tk()
    root.withdraw()

    dlg = tk.Toplevel(root)
    dlg.title("Save Preset")
    dlg.resizable(False, False)
    dlg.attributes("-topmost", True)

    dlg.geometry(
        "320x110+{}+{}".format(
            (dlg.winfo_screenwidth() - 320) // 2,
            (dlg.winfo_screenheight() - 110) // 2,
        )
    )

    tk.Label(dlg, text="Enter a name for this preset:", pady=8).pack()
    entry = tk.Entry(dlg, width=36)
    entry.pack(padx=12)
    entry.focus_set()

    def _on_ok(event=None):
        result[0] = entry.get().strip()
        dlg.destroy()

    def _on_cancel(event=None):
        dlg.destroy()

    btn_frame = tk.Frame(dlg)
    btn_frame.pack(pady=8)
    tk.Button(btn_frame, text="Save", width=10, command=_on_ok).pack(
        side="left", padx=4
    )
    tk.Button(btn_frame, text="Cancel", width=10, command=_on_cancel).pack(
        side="left", padx=4
    )

    dlg.bind("<Return>", _on_ok)
    dlg.bind("<Escape>", _on_cancel)

    def _force_topmost():
        try:
            hwnd = win32gui.FindWindow(None, "Save Preset")
            if hwnd:
                win32gui.SetWindowPos(
                    hwnd,
                    win32con.HWND_TOPMOST,
                    0,
                    0,
                    0,
                    0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW,
                )
        except Exception:
            pass

    dlg.after(50, _force_topmost)
    root.wait_window(dlg)
    root.destroy()
    return result[0]


def _refresh_custom_list():
    _custom_list.clear()
    _custom_list.extend(list_custom_presets())


def tab_presets(s: Settings) -> Settings:
    # Built-in presets
    psc(imgui.COLOR_TEXT, ACCENT)
    imgui.text("  Built-in Presets")
    imgui.pop_style_color()
    imgui.spacing()
    for name in BUILTIN_PRESETS.keys():
        psc(imgui.COLOR_BUTTON, BG3)
        psc(imgui.COLOR_BUTTON_HOVERED, ACCENT_DIM)
        psc(imgui.COLOR_BUTTON_ACTIVE, ACCENT)
        if imgui.button(f"  {name}  ##bpre_{name}", -1, 0):
            imgui.pop_style_color(3)
            return apply_builtin_preset(name)
        imgui.pop_style_color(3)

    imgui.spacing()
    imgui.separator()
    imgui.spacing()

    psc(imgui.COLOR_TEXT, ACCENT)
    imgui.text("  My Presets")
    imgui.pop_style_color()
    imgui.spacing()

    psc(imgui.COLOR_BUTTON, GREEN)
    psc(imgui.COLOR_BUTTON_HOVERED, GREEN_HOV)
    psc(imgui.COLOR_BUTTON_ACTIVE, (0.28, 0.80, 0.38, 1.0))
    if imgui.button("  Save Current Settings as Preset...  ##psave", -1, 0):
        name_stripped = _ask_preset_name()
        if name_stripped:
            if save_custom_preset(name_stripped, s):
                _preset_status_msg[0] = f"Saved  '{name_stripped}'"
                _refresh_custom_list()
            else:
                _preset_status_msg[0] = "Save failed"
        else:
            _preset_status_msg[0] = "Cancelled"
        _preset_status_t[0] = time.perf_counter()
    imgui.pop_style_color(3)

    imgui.spacing()
    list_h = min(max(len(_custom_list), 1), 6) * 22 + 8
    imgui.begin_child(
        "##cplist", imgui.get_content_region_available_width(), list_h, True
    )
    if not _custom_list:
        psc(imgui.COLOR_TEXT, TXT_DIM)
        imgui.text("  No saved presets yet")
        imgui.pop_style_color()
    else:
        for i, name in enumerate(_custom_list):
            sel = i == _selected_custom[0]
            psc(imgui.COLOR_HEADER, ACCENT_DIM if sel else BG2)
            psc(imgui.COLOR_HEADER_HOVERED, ACCENT_DIM)
            psc(imgui.COLOR_HEADER_ACTIVE, ACCENT)
            clicked, _ = imgui.selectable(f"  {name}##cpsel{i}", sel)
            imgui.pop_style_color(3)
            if clicked:
                _selected_custom[0] = i
    imgui.end_child()
    imgui.spacing()

    has_sel = 0 <= _selected_custom[0] < len(_custom_list)
    btn_w = (imgui.get_content_region_available_width() - 12) / 4
    DISABLED_COL = (0.14, 0.14, 0.14, 1.0)

    def _btn_colors(active, base, hov, act_col):
        if active:
            psc(imgui.COLOR_BUTTON, base)
            psc(imgui.COLOR_BUTTON_HOVERED, hov)
            psc(imgui.COLOR_BUTTON_ACTIVE, act_col)
            psc(imgui.COLOR_TEXT, TXT)
        else:
            psc(imgui.COLOR_BUTTON, DISABLED_COL)
            psc(imgui.COLOR_BUTTON_HOVERED, DISABLED_COL)
            psc(imgui.COLOR_BUTTON_ACTIVE, DISABLED_COL)
            psc(imgui.COLOR_TEXT, TXT_DIM)

    _btn_colors(has_sel, BTN_ON, BTN_ON_HOV, ACCENT_HOV)
    if imgui.button("  Load  ##cpload", btn_w, 0) and has_sel:
        loaded = load_custom_preset(_custom_list[_selected_custom[0]])
        if loaded:
            imgui.pop_style_color(4)
            _preset_status_msg[0] = f"Loaded  '{_custom_list[_selected_custom[0]]}'"
            _preset_status_t[0] = time.perf_counter()
            return loaded
    imgui.pop_style_color(4)
    imgui.same_line()

    _btn_colors(True, ORANGE, ORANGE_HOV, (0.95, 0.60, 0.16, 1.0))
    if imgui.button("  Import  ##cpimport", btn_w, 0):
        imported = import_preset_from_file()
        if imported:
            _refresh_custom_list()
            _preset_status_msg[0] = f"Imported  '{imported}'"
        else:
            _preset_status_msg[0] = "Import cancelled"
        _preset_status_t[0] = time.perf_counter()
    imgui.pop_style_color(4)
    imgui.same_line()

    _btn_colors(has_sel, ORANGE, ORANGE_HOV, (0.95, 0.60, 0.16, 1.0))
    if imgui.button("  Export  ##cpexport", btn_w, 0) and has_sel:
        ok = export_preset_to_file(_custom_list[_selected_custom[0]])
        _preset_status_msg[0] = "Exported" if ok else "Export cancelled"
        _preset_status_t[0] = time.perf_counter()
    imgui.pop_style_color(4)
    imgui.same_line()

    _btn_colors(has_sel, RED, RED_HOV, (1.0, 0.3, 0.3, 1.0))
    if imgui.button("  Delete  ##cpdelete", btn_w, 0) and has_sel:
        deleted_name = _custom_list[_selected_custom[0]]
        delete_custom_preset(deleted_name)
        _preset_status_msg[0] = f"Deleted  '{deleted_name}'"
        _preset_status_t[0] = time.perf_counter()
        _selected_custom[0] = -1
        _refresh_custom_list()
    imgui.pop_style_color(4)

    if _preset_status_msg[0]:
        age = time.perf_counter() - _preset_status_t[0]
        if age < 3.0:
            alpha = max(0.0, 1.0 - max(0.0, age - 2.0))
            imgui.spacing()
            psc(imgui.COLOR_TEXT, (0.72, 0.72, 0.72, alpha))
            imgui.text(f"    {_preset_status_msg[0]}")
            imgui.pop_style_color()

    return s


def tab_app(s: Settings) -> Settings:
    imgui.push_item_width(-1)
    imgui.spacing()
    subheading("FPS")
    cap_label = "Unlimited" if s.fps_cap == 0 else f"{s.fps_cap} FPS"
    s.fps_cap = int(
        slid(f"FPS Cap:  {cap_label}##fpc", float(s.fps_cap), 0.0, 360.0, "%.0f")
    )
    imgui.spacing()
    subheading("Panel")
    s.gui_alpha = slid("Opacity##pa", s.gui_alpha, 0.1, 1.0)
    imgui.spacing()
    imgui.separator()
    imgui.spacing()
    subheading("OBS / Recording")
    imgui.spacing()
    hint("Normal: low latency, OBS won't capture the overlay")
    hint("OBS Mode: OBS captures it, slight performance cost")
    imgui.spacing()
    imgui.text("  Capture mode:")
    imgui.same_line()
    avail = imgui.get_content_region_available_width()
    imgui.set_cursor_pos_x(imgui.get_cursor_pos_x() + avail - 110)
    if s.obs_mode:
        psc(imgui.COLOR_BUTTON, ACCENT)
        psc(imgui.COLOR_BUTTON_HOVERED, ACCENT_HOV)
        psc(imgui.COLOR_BUTTON_ACTIVE, ACCENT_DIM)
        if imgui.button("  OBS Mode  ##obsm", 110, 0):
            s.obs_mode = False
        imgui.pop_style_color(3)
    else:
        psc(imgui.COLOR_BUTTON, BG3)
        psc(imgui.COLOR_BUTTON_HOVERED, BTN_OFF_HOV)
        psc(imgui.COLOR_BUTTON_ACTIVE, BG3)
        if imgui.button("  Normal Mode  ##obsm", 110, 0):
            s.obs_mode = True
        imgui.pop_style_color(3)
    imgui.spacing()
    imgui.separator()
    imgui.spacing()
    psc(imgui.COLOR_TEXT, TXT_DIM)
    imgui.text(f"  Saves to:  {SAVE_PATH}")
    imgui.text(f"  Presets:   {PRESETS_DIR}")
    imgui.pop_style_color()
    imgui.spacing()
    imgui.separator()
    imgui.spacing()
    psc(imgui.COLOR_BUTTON, RED)
    psc(imgui.COLOR_BUTTON_HOVERED, RED_HOV)
    psc(imgui.COLOR_BUTTON_ACTIVE, (1.0, 0.3, 0.3, 1.0))
    if imgui.button("  Reset Everything to Defaults  ", -1, 0):
        imgui.pop_style_color(3)
        imgui.pop_item_width()
        new_s = Settings()
        save_settings(new_s)
        return new_s
    imgui.pop_style_color(3)
    imgui.pop_item_width()
    return s


def draw_perf_bar(s: Settings) -> Settings:
    imgui.spacing()
    imgui.separator()
    imgui.spacing()

    if s.perf_mode:
        col = (0.18, 0.48, 0.18, 1.0)
        hov = (0.24, 0.62, 0.24, 1.0)
        act = (0.30, 0.76, 0.30, 1.0)
        txt = (0.82, 1.00, 0.82, 1.0)
        label = "  RiShade  OFF"
    else:
        col = (0.48, 0.18, 0.18, 1.0)
        hov = (0.62, 0.22, 0.22, 1.0)
        act = (0.76, 0.28, 0.28, 1.0)
        txt = (1.00, 0.82, 0.82, 1.0)
        label = "  RiShade  ON"

    psc(imgui.COLOR_BUTTON, col)
    psc(imgui.COLOR_BUTTON_HOVERED, hov)
    psc(imgui.COLOR_BUTTON_ACTIVE, act)
    psc(imgui.COLOR_TEXT, txt)
    if imgui.button(f"{label}##perfmode", -1, 0):
        s.perf_mode = not s.perf_mode
    imgui.pop_style_color(4)
    imgui.spacing()
    return s


def draw_ui(s: Settings, fps: float) -> Settings:
    io = imgui.get_io()
    W, H = io.display_size.x, io.display_size.y

    if s.gui_visible:
        imgui.set_next_window_position(W - 130, H - 28, imgui.ALWAYS)
        imgui.set_next_window_size(124, 22, imgui.ALWAYS)
        imgui.set_next_window_bg_alpha(0.45)
        hint_flags = (
            imgui.WINDOW_NO_TITLE_BAR
            | imgui.WINDOW_NO_RESIZE
            | imgui.WINDOW_NO_SCROLLBAR
            | imgui.WINDOW_NO_SAVED_SETTINGS
            | imgui.WINDOW_NO_MOVE
            | imgui.WINDOW_NO_INPUTS
            | imgui.WINDOW_NO_NAV
        )
        imgui.begin("##hint", False, hint_flags)
        psc(imgui.COLOR_TEXT, TXT_DIM)
        imgui.text("F8  show / hide")
        imgui.pop_style_color()
        imgui.end()

    if not s.gui_visible:
        return s

    imgui.set_next_window_size(400, 700, imgui.ONCE)
    imgui.set_next_window_position(16, 16, imgui.ONCE)
    imgui.set_next_window_bg_alpha(s.gui_alpha)

    flags = imgui.WINDOW_NO_SAVED_SETTINGS | imgui.WINDOW_NO_COLLAPSE
    imgui.begin("RiShade##main", False, flags)

    psc(imgui.COLOR_TEXT, ACCENT)
    imgui.text(f"  {fps:.0f} FPS")
    imgui.pop_style_color()
    imgui.same_line()
    psc(imgui.COLOR_TEXT, TXT_DIM)
    capture_tag = "PrintWindow" if s.obs_mode else ("DXCam" if HAS_DXCAM else "mss")
    imgui.text(f"  {capture_tag}{'  [OBS]' if s.obs_mode else ''}")
    imgui.pop_style_color()
    imgui.same_line()
    avail = imgui.get_content_region_available_width()
    imgui.set_cursor_pos_x(imgui.get_cursor_pos_x() + avail - 60)
    psc(imgui.COLOR_TEXT, TXT_DIM)
    imgui.text("F8  hide")
    imgui.pop_style_color()

    active = [
        n
        for n, e in [
            ("Grade", s.grade_en),
            ("Tonemap", s.tonemap_en),
            ("Vig", s.vignette_en),
            ("Sharp", s.sharpen_en),
            ("Bloom", s.bloom_en),
            ("CA", s.chroma_en),
            ("Grain", s.grain_en),
            ("DoF", s.dof_en),
            ("SSR", s.ssr_en),
            ("AO", s.ao_en),
        ]
        if e
    ]
    if active:
        imgui.same_line()
        psc(imgui.COLOR_TEXT, TXT_DIM if s.perf_mode else BTN_ON)
        imgui.text("  |  " + "  ·  ".join(active))
        imgui.pop_style_color()

    imgui.separator()

    if imgui.begin_tab_bar("##tabs"):
        if imgui.begin_tab_item("  Colour  ")[0]:
            imgui.begin_child("##col_sc", 0, -52, False)
            s = tab_colour(s)
            imgui.end_child()
            s = draw_perf_bar(s)
            imgui.end_tab_item()
        if imgui.begin_tab_item("  Effects  ")[0]:
            imgui.begin_child("##eff_sc", 0, -52, False)
            s = tab_effects(s)
            imgui.end_child()
            s = draw_perf_bar(s)
            imgui.end_tab_item()
        if imgui.begin_tab_item("  Reflect  ")[0]:
            imgui.begin_child("##ref_sc", 0, -52, False)
            s = tab_reflections(s)
            imgui.end_child()
            s = draw_perf_bar(s)
            imgui.end_tab_item()
        if imgui.begin_tab_item("  Presets  ")[0]:
            imgui.begin_child("##pre_sc", 0, -52, False)
            s = tab_presets(s)
            imgui.end_child()
            s = draw_perf_bar(s)
            imgui.end_tab_item()
        if imgui.begin_tab_item("  Settings  ")[0]:
            imgui.begin_child("##set_sc", 0, -52, False)
            s = tab_app(s)
            imgui.end_child()
            s = draw_perf_bar(s)
            imgui.end_tab_item()
        imgui.end_tab_bar()

    imgui.end()
    return s


def main():
    roblox_hwnd = find_roblox()
    if not roblox_hwnd:
        print("Please Open Roblox")
        return

    W = user32.GetSystemMetrics(0)
    H = user32.GetSystemMetrics(1)
    print(f"{W}x{H}  capture={'DXCam' if HAS_DXCAM else 'mss'}")

    if not glfw.init():
        raise RuntimeError("GLFW init failed")
    glfw.window_hint(glfw.DECORATED, glfw.FALSE)
    glfw.window_hint(glfw.FLOATING, glfw.TRUE)
    glfw.window_hint(glfw.TRANSPARENT_FRAMEBUFFER, glfw.TRUE)
    glfw.window_hint(glfw.FOCUS_ON_SHOW, glfw.FALSE)
    glfw.window_hint(glfw.DOUBLEBUFFER, glfw.TRUE)

    window = glfw.create_window(W, H, "rishade", None, None)
    if not window:
        glfw.terminate()
        raise RuntimeError("Window creation failed")
    glfw.set_window_pos(window, 0, 0)
    glfw.make_context_current(window)
    glfw.swap_interval(1)

    hwnd_gl = win32gui.FindWindow(None, "rishade")
    if hwnd_gl:
        user32.SetWindowDisplayAffinity(hwnd_gl, 0x11)
        _get = ctypes.windll.user32.GetWindowLongPtrW
        _set = ctypes.windll.user32.SetWindowLongPtrW
        ex = _get(hwnd_gl, -20)
        ex = (
            ex | win32con.WS_EX_LAYERED | win32con.WS_EX_NOACTIVATE
        ) & ~win32con.WS_EX_TRANSPARENT
        _set(hwnd_gl, -20, ex)
        win32gui.SetLayeredWindowAttributes(hwnd_gl, 0, 255, win32con.LWA_ALPHA)
        user32.SetWindowPos(hwnd_gl, -1, 0, 0, W, H, 0x0040)

    imgui.create_context()
    imgui.get_io()
    apply_theme()
    impl = GlfwRenderer(window)

    verts = np.array(
        [
            -1.0,
            -1.0,
            0.0,
            0.0,
            1.0,
            -1.0,
            1.0,
            0.0,
            1.0,
            1.0,
            1.0,
            1.0,
            -1.0,
            1.0,
            0.0,
            1.0,
        ],
        dtype=np.float32,
    )
    idx = np.array([0, 1, 2, 0, 2, 3], dtype=np.uint32)
    vao = glGenVertexArrays(1)
    vbo = glGenBuffers(1)
    ebo = glGenBuffers(1)
    glBindVertexArray(vao)
    glBindBuffer(GL_ARRAY_BUFFER, vbo)
    glBufferData(GL_ARRAY_BUFFER, verts.nbytes, verts, GL_STATIC_DRAW)
    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, ebo)
    glBufferData(GL_ELEMENT_ARRAY_BUFFER, idx.nbytes, idx, GL_STATIC_DRAW)
    glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 16, ctypes.c_void_p(0))
    glEnableVertexAttribArray(0)
    glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 16, ctypes.c_void_p(8))
    glEnableVertexAttribArray(1)

    prog_main = link_program_cached(VERT, FRAG_MAIN)
    prog_bloom_h = link_program_cached(VERT, FRAG_BLOOM_H)
    prog_bloom_v = link_program_cached(VERT, FRAG_BLOOM_V)
    prog_passthrough = link_program_cached(VERT, FRAG_PASSTHROUGH)
    prog_depth = link_program_cached(VERT, FRAG_DEPTH)
    prog_ssr = link_program_cached(VERT, FRAG_SSR_ONLY)
    prog_accum = link_program_cached(VERT, FRAG_ACCUM)
    prog_composite = link_program_cached(VERT, FRAG_COMPOSITE)

    pt_tex_loc = glGetUniformLocation(prog_passthrough, "uTex")
    dep_tex_loc = glGetUniformLocation(prog_depth, "uTex")

    fbo_a, tex_a = make_fbo(W, H)
    fbo_b, tex_b = make_fbo(W, H)
    fbo_depth, tex_depth = make_fbo(W, H)
    fbo_prev, tex_prev = make_fbo(W, H)
    fbo_refl, tex_refl = make_rgba_fbo(W, H)
    fbo_accum, tex_accum = make_rgba_fbo(W, H)
    fbo_accum2, tex_accum2 = make_rgba_fbo(W, H)
    fbo_comp, tex_comp = make_fbo(W, H)

    for _fbo in (fbo_refl, fbo_accum, fbo_accum2, fbo_prev, fbo_depth):
        glBindFramebuffer(GL_FRAMEBUFFER, _fbo)
        glClearColor(0.0, 0.0, 0.0, 0.0)
        glClear(GL_COLOR_BUFFER_BIT)
    glBindFramebuffer(GL_FRAMEBUFFER, 0)

    screen_tex = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, screen_tex)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, W, H, 0, GL_RGB, GL_UNSIGNED_BYTE, None)
    for p, v in [
        (GL_TEXTURE_MIN_FILTER, GL_LINEAR),
        (GL_TEXTURE_MAG_FILTER, GL_LINEAR),
        (GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE),
        (GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE),
    ]:
        glTexParameteri(GL_TEXTURE_2D, p, v)

    frame_bytes = W * H * 3
    upload_buf = np.empty((H, W, 3), dtype=np.uint8)
    pbos = glGenBuffers(2)
    for p in pbos:
        glBindBuffer(GL_PIXEL_UNPACK_BUFFER, p)
        glBufferData(GL_PIXEL_UNPACK_BUFFER, frame_bytes, None, GL_STREAM_DRAW)
    glBindBuffer(GL_PIXEL_UNPACK_BUFFER, 0)
    pbo_idx = 0

    grabber = FrameGrabber(W, H, roblox_hwnd)
    grabber.start()

    def locs(prog, names):
        return {n: glGetUniformLocation(prog, n) for n in names}

    mu = locs(
        prog_main,
        [
            "uTex",
            "uGrade",
            "uSat",
            "uCon",
            "uBri",
            "uGamma",
            "uHue",
            "uLift",
            "uGain",
            "uBalance",
            "uTemp",
            "uTonemap",
            "uTonemapMode",
            "uExposure",
            "uWhitepoint",
            "uVignette",
            "uVigStr",
            "uVigFeat",
            "uVigCX",
            "uVigCY",
            "uSharpen",
            "uShStr",
            "uShRadius",
            "uShClamp",
            "uChroma",
            "uChStr",
            "uChRadial",
            "uGrain",
            "uGrStr",
            "uGrSize",
            "uGrColored",
            "uTime",
            "uDOF",
            "uDOFStr",
            "uDOFFocus",
            "uDOFFeather",
            "uAO",
            "uAOStr",
            "uAORadius",
            "uAOSamples",
        ],
    )
    ssr_u = locs(
        prog_ssr,
        [
            "uTex",
            "uDepthTex",
            "uPrevTex",
            "uSSRStr",
            "uSSRThresh",
            "uSSRMaxDist",
            "uSSRRough",
            "uSSRXNudge",
            "uSSRFadeLo",
            "uSSRFadeHi",
            "uSSRRim",
            "uGFresnel",
            "uGNZ",
            "uGDarken",
            "uGBright",
            "uGCap",
            "uGTint",
            "uGSpecTint",
            "uGSpecPow",
            "uGSpecScale",
        ],
    )
    ac_u = locs(
        prog_accum, ["uNewRefl", "uAccum", "uCurFrame", "uPrevFrame", "uMotionScale"]
    )
    co_u = locs(prog_composite, ["uScene", "uRefl"])
    bh_u = locs(prog_bloom_h, ["uTex", "uStr", "uThresh", "uRadius", "uTint"])
    bv_u = locs(prog_bloom_v, ["uTex", "uStr", "uThresh", "uRadius", "uTint"])

    s = load_settings()
    s.gui_visible = True
    prev_s = copy.deepcopy(s)

    fps_display = 0.0
    fps_alpha = 0.01
    last_t = time.perf_counter()
    prev_f11 = False
    prev_visible = True
    prev_obs = False
    topmost_tick = 0
    tex_ready = False
    has_frame = False
    t_start = time.perf_counter()
    cap_debt = 0.0
    accum_ping = True
    ssr_warmup = 0
    prev_ssr_en = False
    last_save_t = time.perf_counter()
    SAVE_INTERVAL = 2.0

    while not glfw.window_should_close(window):
        t0 = time.perf_counter()
        glfw.poll_events()
        impl.process_inputs()

        f12 = bool(win32api.GetAsyncKeyState(win32con.VK_F8) & 0x8000)
        if f12 and not prev_f11:
            s.gui_visible = not s.gui_visible
        prev_f11 = f12

        if s.gui_visible != prev_visible:
            set_clickthrough(hwnd_gl, not s.gui_visible)
            prev_visible = s.gui_visible

        if s.obs_mode != prev_obs:
            if hwnd_gl:
                user32.SetWindowDisplayAffinity(hwnd_gl, 0x00 if s.obs_mode else 0x11)
            grabber.obs_mode = s.obs_mode
            prev_obs = s.obs_mode

        if s.ssr_en and not prev_ssr_en:
            for _fbo in (fbo_refl, fbo_accum, fbo_accum2, fbo_prev):
                glBindFramebuffer(GL_FRAMEBUFFER, _fbo)
                glClearColor(0.0, 0.0, 0.0, 0.0)
                glClear(GL_COLOR_BUFFER_BIT)
            glBindFramebuffer(GL_FRAMEBUFFER, 0)
            ssr_warmup = 0
        prev_ssr_en = s.ssr_en

        if grabber.restarted.is_set():
            grabber.restarted.clear()
            for _fbo in (fbo_refl, fbo_accum, fbo_accum2, fbo_prev):
                glBindFramebuffer(GL_FRAMEBUFFER, _fbo)
                glClearColor(0.0, 0.0, 0.0, 0.0)
                glClear(GL_COLOR_BUFFER_BIT)
            glBindFramebuffer(GL_FRAMEBUFFER, 0)
            ssr_warmup = 0

        if (
            glfw.get_key(window, glfw.KEY_P) == glfw.PRESS
            or glfw.get_key(window, glfw.KEY_ESCAPE) == glfw.PRESS
            or win32api.GetAsyncKeyState(ord("P")) & 0x8000
        ):
            break

        frame = grabber.get_frame()
        if frame is not None:
            np.copyto(upload_buf, frame[::-1])
            cur_pbo = pbos[pbo_idx]
            next_pbo = pbos[1 - pbo_idx]
            glBindBuffer(GL_PIXEL_UNPACK_BUFFER, next_pbo)
            glBufferData(GL_PIXEL_UNPACK_BUFFER, frame_bytes, None, GL_STREAM_DRAW)
            glBufferSubData(GL_PIXEL_UNPACK_BUFFER, 0, frame_bytes, upload_buf)
            glBindBuffer(GL_PIXEL_UNPACK_BUFFER, cur_pbo)
            glBindTexture(GL_TEXTURE_2D, screen_tex)
            if not tex_ready:
                glTexImage2D(
                    GL_TEXTURE_2D, 0, GL_RGB, W, H, 0, GL_RGB, GL_UNSIGNED_BYTE, None
                )
                tex_ready = True
            else:
                glTexSubImage2D(
                    GL_TEXTURE_2D, 0, 0, 0, W, H, GL_RGB, GL_UNSIGNED_BYTE, None
                )
            glBindBuffer(GL_PIXEL_UNPACK_BUFFER, 0)
            pbo_idx = 1 - pbo_idx
            has_frame = True

        if not has_frame:
            glfw.swap_buffers(window)
            continue

        glViewport(0, 0, W, H)

        if s.perf_mode:
            glBindFramebuffer(GL_FRAMEBUFFER, 0)
            glUseProgram(prog_passthrough)
            glActiveTexture(GL_TEXTURE0)
            glBindTexture(GL_TEXTURE_2D, screen_tex)
            glUniform1i(pt_tex_loc, 0)
            draw_quad(vao)
        else:
            ct = (
                COLOR_TEMP_VALUES[s.color_temp]
                if s.color_temp < 3
                else s.color_temp_cust
            )
            now_t = time.perf_counter() - t_start

            if s.ssr_en:
                glBindFramebuffer(GL_FRAMEBUFFER, fbo_depth)
                glUseProgram(prog_depth)
                glActiveTexture(GL_TEXTURE0)
                glBindTexture(GL_TEXTURE_2D, screen_tex)
                glUniform1i(dep_tex_loc, 0)
                draw_quad(vao)

            glBindFramebuffer(GL_FRAMEBUFFER, fbo_a)
            glUseProgram(prog_main)
            glActiveTexture(GL_TEXTURE0)
            glBindTexture(GL_TEXTURE_2D, screen_tex)
            glUniform1i(mu["uTex"], 0)
            glUniform1i(mu["uGrade"], int(s.grade_en))
            glUniform1f(mu["uSat"], s.saturation)
            glUniform1f(mu["uCon"], s.contrast)
            glUniform1f(mu["uBri"], s.brightness)
            glUniform1f(mu["uGamma"], s.gamma)
            glUniform1f(mu["uHue"], s.hue_shift)
            glUniform3f(mu["uLift"], *s.lift)
            glUniform3f(mu["uGain"], *s.gain)
            glUniform3f(mu["uBalance"], *s.color_balance)
            glUniform3f(mu["uTemp"], *ct)
            glUniform1i(mu["uTonemap"], int(s.tonemap_en))
            glUniform1i(mu["uTonemapMode"], s.tonemap_mode)
            glUniform1f(mu["uExposure"], s.tonemap_exposure)
            glUniform1f(mu["uWhitepoint"], s.tonemap_whitepoint)
            glUniform1i(mu["uVignette"], int(s.vignette_en))
            glUniform1f(mu["uVigStr"], s.vignette_str)
            glUniform1f(mu["uVigFeat"], s.vignette_feather)
            glUniform1f(mu["uVigCX"], s.vignette_r)
            glUniform1f(mu["uVigCY"], s.vignette_ry)
            glUniform1i(mu["uSharpen"], int(s.sharpen_en))
            glUniform1f(mu["uShStr"], s.sharpen_str)
            glUniform1f(mu["uShRadius"], s.sharpen_radius)
            glUniform1f(mu["uShClamp"], s.sharpen_clamp)
            glUniform1i(mu["uChroma"], int(s.chroma_en))
            glUniform1f(mu["uChStr"], s.chroma_str)
            glUniform1i(mu["uChRadial"], int(s.chroma_radial))
            glUniform1i(mu["uGrain"], int(s.grain_en))
            glUniform1f(mu["uGrStr"], s.grain_str)
            glUniform1f(mu["uGrSize"], s.grain_size)
            glUniform1i(mu["uGrColored"], int(s.grain_colored))
            glUniform1f(mu["uTime"], now_t)
            glUniform1i(mu["uDOF"], int(s.dof_en))
            glUniform1f(mu["uDOFStr"], s.dof_str)
            glUniform1f(mu["uDOFFocus"], s.dof_focus_range)
            glUniform1f(mu["uDOFFeather"], s.dof_feather)
            glUniform1i(mu["uAO"], int(s.ao_en))
            glUniform1f(mu["uAOStr"], s.ao_str)
            glUniform1f(mu["uAORadius"], s.ao_radius)
            glUniform1i(mu["uAOSamples"], AO_SAMPLE_COUNTS[s.ao_samples])
            draw_quad(vao)

            src_tex, dst_tex = tex_a, tex_b
            src_fbo, dst_fbo = fbo_a, fbo_b

            if s.bloom_en and s.bloom_str > 0.0:
                passes = max(s.bloom_passes, 1)
                for _ in range(passes):
                    for prog, u in [(prog_bloom_h, bh_u), (prog_bloom_v, bv_u)]:
                        glBindFramebuffer(GL_FRAMEBUFFER, dst_fbo)
                        glUseProgram(prog)
                        glActiveTexture(GL_TEXTURE0)
                        glBindTexture(GL_TEXTURE_2D, src_tex)
                        glUniform1i(u["uTex"], 0)
                        glUniform1f(u["uStr"], s.bloom_str / passes)
                        glUniform1f(u["uThresh"], s.bloom_threshold)
                        glUniform1f(u["uRadius"], s.bloom_radius)
                        glUniform3f(u["uTint"], *s.bloom_tint)
                        draw_quad(vao)
                        src_tex, dst_tex = dst_tex, src_tex
                        src_fbo, dst_fbo = dst_fbo, src_fbo

            if s.ssr_en:
                glBindFramebuffer(GL_FRAMEBUFFER, fbo_refl)
                glUseProgram(prog_ssr)
                glActiveTexture(GL_TEXTURE0)
                glBindTexture(GL_TEXTURE_2D, screen_tex)
                glUniform1i(ssr_u["uTex"], 0)
                glActiveTexture(GL_TEXTURE1)
                glBindTexture(GL_TEXTURE_2D, tex_depth)
                glUniform1i(ssr_u["uDepthTex"], 1)
                glActiveTexture(GL_TEXTURE2)
                glBindTexture(GL_TEXTURE_2D, tex_prev)
                glUniform1i(ssr_u["uPrevTex"], 2)
                glUniform1f(ssr_u["uSSRStr"], s.ssr_str)
                glUniform1f(ssr_u["uSSRThresh"], s.ssr_threshold)
                glUniform1f(ssr_u["uSSRMaxDist"], s.ssr_max_dist)
                glUniform1f(ssr_u["uSSRRough"], s.ssr_roughness)
                glUniform1f(ssr_u["uSSRXNudge"], s.ssr_x_nudge)
                glUniform1f(ssr_u["uSSRFadeLo"], s.ssr_fade_lo)
                glUniform1f(ssr_u["uSSRFadeHi"], s.ssr_fade_hi)
                glUniform1f(ssr_u["uSSRRim"], s.ssr_rim)
                glUniform1f(ssr_u["uGFresnel"], s.gloss_fresnel)
                glUniform1f(ssr_u["uGNZ"], s.gloss_nz)
                glUniform1f(ssr_u["uGDarken"], s.gloss_darken)
                glUniform1f(ssr_u["uGBright"], s.gloss_bright)
                glUniform1f(ssr_u["uGCap"], s.gloss_cap)
                glUniform3f(ssr_u["uGTint"], *s.gloss_tint)
                glUniform3f(ssr_u["uGSpecTint"], *s.gloss_spec_tint)
                glUniform1f(ssr_u["uGSpecPow"], s.gloss_spec_pow)
                glUniform1f(ssr_u["uGSpecScale"], s.gloss_spec_scale)
                draw_quad(vao)

                cur_acc_fbo = fbo_accum if accum_ping else fbo_accum2
                cur_acc_tex = tex_accum if accum_ping else tex_accum2
                prev_acc_tex = tex_accum2 if accum_ping else tex_accum
                glBindFramebuffer(GL_FRAMEBUFFER, cur_acc_fbo)
                glUseProgram(prog_accum)
                glActiveTexture(GL_TEXTURE0)
                glBindTexture(GL_TEXTURE_2D, tex_refl)
                glUniform1i(ac_u["uNewRefl"], 0)
                glActiveTexture(GL_TEXTURE1)
                glBindTexture(
                    GL_TEXTURE_2D, prev_acc_tex if ssr_warmup > 0 else tex_refl
                )
                glUniform1i(ac_u["uAccum"], 1)
                glActiveTexture(GL_TEXTURE2)
                glBindTexture(GL_TEXTURE_2D, screen_tex)
                glUniform1i(ac_u["uCurFrame"], 2)
                glActiveTexture(GL_TEXTURE3)
                glBindTexture(GL_TEXTURE_2D, tex_prev)
                glUniform1i(ac_u["uPrevFrame"], 3)
                glUniform1f(ac_u["uMotionScale"], s.ssr_motion_scale)
                draw_quad(vao)
                accum_ping = not accum_ping
                ssr_warmup += 1

                glBindFramebuffer(GL_FRAMEBUFFER, fbo_comp)
                glUseProgram(prog_composite)
                glActiveTexture(GL_TEXTURE0)
                glBindTexture(GL_TEXTURE_2D, src_tex)
                glUniform1i(co_u["uScene"], 0)
                glActiveTexture(GL_TEXTURE1)
                glBindTexture(GL_TEXTURE_2D, cur_acc_tex)
                glUniform1i(co_u["uRefl"], 1)
                draw_quad(vao)
                src_tex = tex_comp
                src_fbo = fbo_comp

            glBindFramebuffer(GL_READ_FRAMEBUFFER, src_fbo)
            glBindFramebuffer(GL_DRAW_FRAMEBUFFER, fbo_prev)
            glBlitFramebuffer(0, 0, W, H, 0, 0, W, H, GL_COLOR_BUFFER_BIT, GL_LINEAR)

            glBindFramebuffer(GL_FRAMEBUFFER, 0)
            glUseProgram(prog_passthrough)
            glActiveTexture(GL_TEXTURE0)
            glBindTexture(GL_TEXTURE_2D, src_tex)
            glUniform1i(pt_tex_loc, 0)
            draw_quad(vao)

        imgui.new_frame()
        s = draw_ui(s, fps_display)
        imgui.render()
        impl.render(imgui.get_draw_data())

        glfw.swap_buffers(window)

        now = time.perf_counter()
        dt = now - last_t
        last_t = now
        if dt > 0.0:
            inst_fps = 1.0 / dt
            fps_display = (
                inst_fps
                if fps_display == 0.0
                else fps_display + fps_alpha * (inst_fps - fps_display)
            )

        topmost_tick = (topmost_tick + 1) % 10
        if hwnd_gl and topmost_tick == 0:
            win32gui.SetWindowPos(
                hwnd_gl,
                win32con.HWND_TOPMOST,
                0,
                0,
                W,
                H,
                win32con.SWP_NOACTIVATE | win32con.SWP_NOSIZE | win32con.SWP_NOMOVE,
            )

        now_save = time.perf_counter()
        if s != prev_s and (now_save - last_save_t) >= SAVE_INTERVAL:
            save_settings(s)
            prev_s = copy.deepcopy(s)
            last_save_t = now_save

        if s.fps_cap > 0:
            target = 1.0 / s.fps_cap
            cap_debt += target - (time.perf_counter() - t0)
            cap_debt = max(cap_debt, -target)
            if cap_debt > 0.0005:
                time.sleep(cap_debt)
                cap_debt -= time.perf_counter() - t0 - (now - t0)
        else:
            cap_debt = 0.0

    save_settings(s)
    print(f"settings saved to {SAVE_PATH}")
    impl.shutdown()
    grabber.stop()
    glfw.terminate()


if __name__ == "__main__":
    main()
