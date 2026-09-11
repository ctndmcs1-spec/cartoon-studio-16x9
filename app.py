"""
Cong cu tao hoat hinh ghep manh (cutout animation) dieu khien boi AI Groq.

Gom 2 phan trong cung 1 app (2 tab):
1) Canh chinh nhan vat (rig): dinh vi tri/pivot cho tung manh ghep, tao cac
   tu the (pose), xuat/nap goi rig de dung lai sau nay.
2) Tao hoat hinh tu kich ban: goi Groq (Structured Outputs) de bien kich ban
   thanh 1 timeline hanh dong + loi thoai, roi ghep frame va xuat video
   bang ffmpeg.

Chay thu: streamlit run app.py

Yeu cau khi deploy tren Streamlit Community Cloud:
- packages.txt: them "ffmpeg" (bat buoc, de xuat video) va "fonts-dejavu-core"
  (de co font ho tro dau tieng Viet khi ve phu de).
- Secrets: dat GROQ_API_KEY trong muc Secrets cua app (khong de trong code).
"""

import io
import json
import os
import subprocess
import tempfile
import textwrap
import zipfile

import requests
import streamlit as st
from PIL import Image, ImageDraw, ImageFont
from streamlit_image_coordinates import streamlit_image_coordinates

st.set_page_config(page_title="Cong cu hoat hinh AI", layout="centered")

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

GROQ_MODEL_OPTIONS = [
    "moonshotai/kimi-k2-instruct",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
    "openai/gpt-oss-120b",
    "llama-3.3-70b-versatile",
]


# ---------------------------------------------------------------------------
# Ham tien ich chung (dung cho ca 2 tab)
# ---------------------------------------------------------------------------
def find_font():
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


def render_pose(parts, canvas_w, canvas_h, background, pose_overrides=None):
    """Ghep tat ca cac manh len nen theo dung thu tu z, ap dung override cua
    1 tu the (neu co). Moi manh duoc dan len 1 lop to bang ca khung hinh sao
    cho diem pivot nam dung vi tri (x, y), roi xoay ca lop do quanh diem
    (x, y) - nho vay xoay goc nao cung khong bi lech vi tri."""
    pose_overrides = pose_overrides or {}
    if background is not None:
        canvas = background.copy()
    else:
        canvas = Image.new("RGBA", (canvas_w, canvas_h), (255, 255, 255, 255))

    ordered = sorted(parts.items(), key=lambda kv: kv[1]["z"])
    for name, p in ordered:
        ov = pose_overrides.get(name, {})
        img = ov.get("alt_image", p["image"])
        x = p["x"] + ov.get("x_delta", 0)
        y = p["y"] + ov.get("y_delta", 0)
        rot = p["rotation"] + ov.get("rotation_delta", 0)
        pivot_x, pivot_y = p["pivot_x"], p["pivot_y"]

        layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        paste_x = int(x - pivot_x)
        paste_y = int(y - pivot_y)
        layer.paste(img, (paste_x, paste_y), img)

        if rot:
            layer = layer.rotate(rot, resample=Image.BICUBIC, center=(x, y))

        canvas = Image.alpha_composite(canvas, layer)
    return canvas


def interpolate_overrides(overrides_a, overrides_b, t):
    """Noi suy tuyen tinh giua 2 tu the (t: 0 -> overrides_a, 1 -> overrides_b)
    de chuyen canh muot hon thay vi doi tu the tuc thi. Anh thay the
    (alt_image) khong noi suy duoc nen se lay cua tu the dich ngay khi
    bat dau chuyen."""
    result = {}
    names = set(overrides_a.keys()) | set(overrides_b.keys())
    for name in names:
        a = overrides_a.get(name, {})
        b = overrides_b.get(name, {})
        ax, ay, arot = a.get("x_delta", 0), a.get("y_delta", 0), a.get("rotation_delta", 0)
        bx, by, brot = b.get("x_delta", 0), b.get("y_delta", 0), b.get("rotation_delta", 0)
        entry = {
            "x_delta": ax + (bx - ax) * t,
            "y_delta": ay + (by - ay) * t,
            "rotation_delta": arot + (brot - arot) * t,
        }
        if "alt_image" in b:
            entry["alt_image"] = b["alt_image"]
        elif "alt_image" in a:
            entry["alt_image"] = a["alt_image"]
        result[name] = entry
    return result


def draw_dialogue(frame, text, canvas_w, canvas_h, font_path):
    if not text:
        return frame
    frame = frame.copy()
    font_size = max(20, canvas_w // 28)
    try:
        font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()

    approx_char_w = font_size * 0.55
    wrap_width = max(10, int(canvas_w * 0.9 / approx_char_w))
    lines = textwrap.fill(text, width=wrap_width).split("\n")

    line_height = font_size + 10
    bar_height = line_height * len(lines) + 24
    bar = Image.new("RGBA", (canvas_w, bar_height), (0, 0, 0, 165))
    frame.paste(bar, (0, canvas_h - bar_height), bar)

    draw = ImageDraw.Draw(frame)
    y = canvas_h - bar_height + 12
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_w = bbox[2] - bbox[0]
        x = (canvas_w - line_w) // 2
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))
        y += line_height
    return frame


def frames_to_video(frames, fps, out_path):
    with tempfile.TemporaryDirectory() as tmpdir:
        for i, frame in enumerate(frames):
            frame.convert("RGB").save(os.path.join(tmpdir, f"frame_{i:05d}.png"))
        cmd = [
            "ffmpeg", "-y", "-framerate", str(fps),
            "-i", os.path.join(tmpdir, "frame_%05d.png"),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            out_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                "ffmpeg loi (kiem tra da them 'ffmpeg' vao packages.txt chua):\n"
                + result.stderr[-1500:]
            )


def build_video(parts, canvas_w, canvas_h, background, poses, timeline, fps, out_path,
                 transition_frames=6, progress_cb=None):
    font_path = find_font()
    frames = []
    prev_overrides = poses.get("idle", {})
    total = max(1, len(timeline))
    for idx, entry in enumerate(timeline):
        pose_name = entry.get("pose", "idle")
        dialogue = entry.get("dialogue", "")
        duration = max(0.5, float(entry.get("duration", 2)))
        n_frames = max(1, int(round(duration * fps)))
        cur_overrides = poses.get(pose_name, {})

        trans_n = min(transition_frames, n_frames // 2) if idx > 0 else 0
        for f in range(n_frames):
            if trans_n > 0 and f < trans_n:
                t = (f + 1) / trans_n
                overrides = interpolate_overrides(prev_overrides, cur_overrides, t)
            else:
                overrides = cur_overrides
            frame = render_pose(parts, canvas_w, canvas_h, background, overrides)
            frame = draw_dialogue(frame, dialogue, canvas_w, canvas_h, font_path)
            frames.append(frame)
        prev_overrides = cur_overrides
        if progress_cb:
            progress_cb((idx + 1) / total)

    frames_to_video(frames, fps, out_path)


def call_groq_director(api_key, model, script_text, pose_names, pose_descriptions):
    pose_info = "\n".join(
        f"- {name}: {pose_descriptions.get(name, '(khong co mo ta)')}" for name in pose_names
    )
    system_prompt = (
        "Ban la dao dien hoat hinh 2D. Doc kich ban do nguoi dung cung cap, chia thanh "
        "cac doan thoai/hanh dong ngan theo dung trinh tu, va voi moi doan chon DUNG 1 "
        "ten tu the phu hop nhat tu danh sach co san ben duoi cho nhan vat - khong duoc "
        "bia ra ten tu the khac.\n\n"
        f"Danh sach tu the co san:\n{pose_info}\n\n"
        "Voi moi doan, uoc luong so giay can de noi doan loi thoai do o toc do noi chuyen "
        "tu nhien (khoang 2-3 tu tieng Viet moi giay), toi thieu 1 giay."
    )

    schema = {
        "type": "object",
        "properties": {
            "timeline": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "pose": {"type": "string", "enum": pose_names},
                        "dialogue": {"type": "string"},
                        "duration": {"type": "number"},
                    },
                    "required": ["pose", "dialogue", "duration"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["timeline"],
        "additionalProperties": False,
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Kich ban:\n{script_text}"},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "animation_timeline", "strict": True, "schema": schema},
        },
        "temperature": 0.4,
    }

    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    return json.loads(content)["timeline"]


def validate_timeline(timeline, valid_poses):
    problems = []
    for i, entry in enumerate(timeline):
        if entry.get("pose") not in valid_poses:
            problems.append(f"Dong {i + 1}: tu the '{entry.get('pose')}' khong co trong rig hien tai.")
    return problems


def export_rig_bytes():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        rig = {
            "canvas": {"width": st.session_state.canvas_w, "height": st.session_state.canvas_h},
            "parts": {},
            "poses": {},
            "pose_descriptions": st.session_state.pose_descriptions,
        }
        for name, pp in st.session_state.parts.items():
            fname = f"{name}.png"
            img_bytes = io.BytesIO()
            pp["image"].save(img_bytes, format="PNG")
            zf.writestr(fname, img_bytes.getvalue())
            rig["parts"][name] = {
                "file": fname, "pivot_x": pp["pivot_x"], "pivot_y": pp["pivot_y"],
                "x": pp["x"], "y": pp["y"], "rotation": pp["rotation"], "z": pp["z"],
            }
        for pose_name, overrides in st.session_state.poses.items():
            pose_data = {}
            for pname, ov in overrides.items():
                entry = {k: v for k, v in ov.items() if k != "alt_image"}
                if "alt_image" in ov:
                    alt_fname = f"{pname}__{pose_name}.png"
                    alt_bytes = io.BytesIO()
                    ov["alt_image"].save(alt_bytes, format="PNG")
                    zf.writestr(alt_fname, alt_bytes.getvalue())
                    entry["alt_file"] = alt_fname
                pose_data[pname] = entry
            rig["poses"][pose_name] = pose_data

        if st.session_state.background is not None:
            bg_bytes = io.BytesIO()
            st.session_state.background.save(bg_bytes, format="PNG")
            zf.writestr("background.png", bg_bytes.getvalue())
            rig["background"] = "background.png"

        zf.writestr("rig.json", json.dumps(rig, ensure_ascii=False, indent=2))
    return buf.getvalue()


def load_rig_from_zip(file):
    with zipfile.ZipFile(file) as zf:
        rig = json.loads(zf.read("rig.json").decode("utf-8"))
        parts = {}
        for name, meta in rig["parts"].items():
            img = Image.open(io.BytesIO(zf.read(meta["file"]))).convert("RGBA")
            parts[name] = {
                "image": img, "img_w": img.width, "img_h": img.height,
                "pivot_x": meta["pivot_x"], "pivot_y": meta["pivot_y"],
                "x": meta["x"], "y": meta["y"], "rotation": meta["rotation"], "z": meta["z"],
            }
        poses = {}
        for pose_name, overrides in rig.get("poses", {}).items():
            pose_data = {}
            for pname, ov in overrides.items():
                entry = dict(ov)
                if "alt_file" in entry:
                    alt_fname = entry.pop("alt_file")
                    entry["alt_image"] = Image.open(io.BytesIO(zf.read(alt_fname))).convert("RGBA")
                pose_data[pname] = entry
            poses[pose_name] = pose_data
        background = None
        if rig.get("background"):
            background = Image.open(io.BytesIO(zf.read(rig["background"]))).convert("RGBA")
        pose_descriptions = rig.get("pose_descriptions", {})
        return rig["canvas"]["width"], rig["canvas"]["height"], parts, poses, background, pose_descriptions


# ---------------------------------------------------------------------------
# Khoi tao session state
# ---------------------------------------------------------------------------
_defaults = {
    "parts": {}, "poses": {"idle": {}}, "pose_descriptions": {},
    "canvas_w": 1080, "canvas_h": 1920, "background": None, "timeline": None,
}
for _key, _val in _defaults.items():
    if _key not in st.session_state:
        st.session_state[_key] = _val


st.title("Cong cu hoat hinh ghep manh (AI dao dien)")

tab1, tab2 = st.tabs(["1. Canh chinh nhan vat", "2. Tao hoat hinh tu kich ban"])

# ===========================================================================
# TAB 1: CANH CHINH NHAN VAT (RIG)
# ===========================================================================
with tab1:
    with st.expander("Nap lai goi rig da luu (bo qua neu lam tu dau)"):
        rig_zip = st.file_uploader("Chon file rig_package.zip", type=["zip"], key="rig_zip_upload")
        if rig_zip is not None and st.button("Nap goi rig nay"):
            w, h, parts, poses, background, pose_desc = load_rig_from_zip(rig_zip)
            st.session_state.canvas_w = w
            st.session_state.canvas_h = h
            st.session_state.parts = parts
            st.session_state.poses = poses
            st.session_state.background = background
            st.session_state.pose_descriptions = pose_desc
            st.success("Da nap rig thanh cong.")
            st.rerun()

    st.header("Khung hinh")
    col_a, col_b = st.columns(2)
    with col_a:
        st.session_state.canvas_w = st.number_input(
            "Chieu rong (px)", min_value=100, value=st.session_state.canvas_w, step=10
        )
    with col_b:
        st.session_state.canvas_h = st.number_input(
            "Chieu cao (px)", min_value=100, value=st.session_state.canvas_h, step=10
        )

    bg_file = st.file_uploader("Anh nen (tuy chon)", type=["png", "jpg", "jpeg"], key="bg_upload")
    if bg_file is not None:
        st.session_state.background = Image.open(bg_file).convert("RGBA").resize(
            (st.session_state.canvas_w, st.session_state.canvas_h)
        )
    st.caption("Neu doi kich thuoc khung hinh sau khi da tai anh nen, tai lai anh nen de co gian dung.")

    st.divider()
    st.header("Them manh ghep")
    with st.form("add_part_form", clear_on_submit=True):
        new_name = st.text_input("Ten manh (vd: dau, tay_phai, mieng_dong)")
        new_file = st.file_uploader("Anh PNG nen trong suot", type=["png"], key="new_part_file")
        if st.form_submit_button("Them manh"):
            if not new_name:
                st.warning("Nhap ten manh truoc.")
            elif not new_file:
                st.warning("Chon anh PNG truoc.")
            elif new_name in st.session_state.parts:
                st.warning("Ten manh nay da ton tai.")
            else:
                img = Image.open(new_file).convert("RGBA")
                st.session_state.parts[new_name] = {
                    "image": img, "img_w": img.width, "img_h": img.height,
                    "pivot_x": img.width / 2, "pivot_y": img.height / 2,
                    "x": st.session_state.canvas_w / 2, "y": st.session_state.canvas_h / 2,
                    "rotation": 0, "z": len(st.session_state.parts),
                }
                st.success(f"Da them manh '{new_name}'.")

    st.divider()
    st.header("Hoac: bat dau tu 1 anh nhan vat day du")
    st.caption(
        "Neu ban chi co 1 anh nhan vat hoan chinh (chua tach lop san): tai anh len lam "
        "lop nen, roi cham 2 diem tren anh de khoanh vung va 'cat' tung bo phan (vd "
        "tay_phai) ra thanh 1 manh rieng co the di chuyen duoc."
    )
    full_char_file = st.file_uploader(
        "Anh nhan vat day du (PNG nen trong suot)", type=["png"], key="full_char_upload"
    )
    base_name_input = st.text_input("Dat ten cho lop nen nay", value="nhan_vat_goc", key="base_name_input")
    if full_char_file is not None and st.button("Dung anh nay lam lop nen"):
        img = Image.open(full_char_file).convert("RGBA")
        if not st.session_state.parts:
            st.session_state.canvas_w = img.width
            st.session_state.canvas_h = img.height
        canvas_img = Image.new("RGBA", (st.session_state.canvas_w, st.session_state.canvas_h), (0, 0, 0, 0))
        canvas_img.paste(img, (0, 0), img)
        st.session_state.parts[base_name_input] = {
            "image": canvas_img, "img_w": canvas_img.width, "img_h": canvas_img.height,
            "pivot_x": canvas_img.width / 2, "pivot_y": canvas_img.height / 2,
            "x": st.session_state.canvas_w / 2, "y": st.session_state.canvas_h / 2,
            "rotation": 0, "z": 0,
        }
        st.success(f"Da them '{base_name_input}' lam lop nen. Keo xuong de cat tung bo phan.")
        st.rerun()

    if st.session_state.parts:
        st.subheader("Cat 1 bo phan ra khoi 1 manh co san")
        source_part = st.selectbox(
            "Cat tu manh nao", list(st.session_state.parts.keys()), key="cut_source_part"
        )
        src_img = st.session_state.parts[source_part]["image"]

        st.caption(
            "Cham vao anh de danh dau goc TREN-TRAI cua vung can cat, roi cham lan nua "
            "de danh dau goc DUOI-PHAI. Nen cat rong ra mot chut o dau noi voi khop "
            "(vd bo vai) de khi xoay khong bi ho. (Luu y: chuc nang nay gia dinh manh "
            "nguon dang o goc xoay 0 do - nen cat truoc khi tao tu the xoay.)"
        )
        coords = streamlit_image_coordinates(src_img, key=f"cut_coords_{source_part}")

        if "cut_points" not in st.session_state:
            st.session_state.cut_points = []
        if coords is not None:
            pt = (coords["x"], coords["y"])
            if not st.session_state.cut_points or st.session_state.cut_points[-1] != pt:
                st.session_state.cut_points.append(pt)
                st.session_state.cut_points = st.session_state.cut_points[-2:]

        col_cut1, col_cut2 = st.columns(2)
        with col_cut1:
            if st.session_state.cut_points:
                st.caption("Da danh dau: " + ", ".join(str(p) for p in st.session_state.cut_points))
        with col_cut2:
            if st.button("Xoa diem da danh dau"):
                st.session_state.cut_points = []
                st.rerun()

        if len(st.session_state.cut_points) == 2:
            (x1, y1), (x2, y2) = st.session_state.cut_points
            left, right = sorted([int(x1), int(x2)])
            top, bottom = sorted([int(y1), int(y2)])

            preview = src_img.copy()
            pd = ImageDraw.Draw(preview)
            pd.rectangle([left, top, right, bottom], outline=(255, 0, 0, 255), width=2)
            st.image(preview, caption=f"Vung se cat: ({left},{top}) - ({right},{bottom})")

            new_part_name = st.text_input("Dat ten cho manh moi (vd: tay_phai)", key="new_cut_name")
            if st.button("Cat manh nay ra") and new_part_name:
                if right - left < 4 or bottom - top < 4:
                    st.warning("Vung chon qua nho, cham lai 2 diem khac.")
                elif new_part_name in st.session_state.parts:
                    st.warning("Ten manh nay da ton tai.")
                else:
                    cropped = src_img.crop((left, top, right, bottom))
                    src_part = st.session_state.parts[source_part]
                    canvas_left = src_part["x"] - src_part["pivot_x"] + left
                    canvas_top = src_part["y"] - src_part["pivot_y"] + top
                    cx = canvas_left + (right - left) / 2
                    cy = canvas_top + (bottom - top) / 2

                    st.session_state.parts[new_part_name] = {
                        "image": cropped, "img_w": cropped.width, "img_h": cropped.height,
                        "pivot_x": cropped.width / 2, "pivot_y": cropped.height / 2,
                        "x": cx, "y": cy, "rotation": 0,
                        "z": max(pp["z"] for pp in st.session_state.parts.values()) + 1,
                    }
                    src_img_copy = src_img.copy()
                    transparent_box = Image.new("RGBA", (right - left, bottom - top), (0, 0, 0, 0))
                    src_img_copy.paste(transparent_box, (left, top))
                    st.session_state.parts[source_part]["image"] = src_img_copy

                    st.session_state.cut_points = []
                    st.success(f"Da cat '{new_part_name}'. Keo len phan 'Canh vi tri goc' de chinh pivot cho khop.")
                    st.rerun()

    st.divider()

    if not st.session_state.parts:
        st.info("Them it nhat 1 manh ghep de bat dau canh chinh.")
    else:
        st.header("Canh vi tri goc (tu the idle)")
        part_name = st.selectbox("Chon manh de chinh", list(st.session_state.parts.keys()))
        p = st.session_state.parts[part_name]

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Vi tri tren khung hinh**")
            p["x"] = st.slider("X", 0, st.session_state.canvas_w, int(p["x"]), key=f"x_{part_name}")
            p["y"] = st.slider("Y", 0, st.session_state.canvas_h, int(p["y"]), key=f"y_{part_name}")
            p["rotation"] = st.slider("Goc xoay (do)", -180, 180, int(p["rotation"]), key=f"rot_{part_name}")
            p["z"] = st.number_input("Thu tu lop (so lon = nam tren)", value=p["z"], step=1, key=f"z_{part_name}")
        with col2:
            st.markdown("**Diem xoay (pivot) trong anh nay**")
            p["pivot_x"] = st.slider("Pivot X", 0, p["img_w"], int(p["pivot_x"]), key=f"pvx_{part_name}")
            p["pivot_y"] = st.slider("Pivot Y", 0, p["img_h"], int(p["pivot_y"]), key=f"pvy_{part_name}")
            st.image(p["image"], caption=f"Anh goc: {part_name}", width=140)

        if st.button(f"Xoa manh '{part_name}'"):
            del st.session_state.parts[part_name]
            st.rerun()

        st.subheader("Xem truoc (tu the idle)")
        st.image(
            render_pose(st.session_state.parts, st.session_state.canvas_w,
                        st.session_state.canvas_h, st.session_state.background),
            use_container_width=True,
        )

        st.divider()
        st.header("Tu the (pose)")
        st.caption(
            "Tao them cac tu the khac idle (vd vay_tay_phai, noi_chuyen). Chi can chinh "
            "LECH so voi idle cho manh nao thay doi."
        )

        new_pose_name = st.text_input("Ten tu the moi (vd: vay_tay_phai)")
        if st.button("Tao tu the moi") and new_pose_name:
            if new_pose_name in st.session_state.poses:
                st.warning("Tu the nay da ton tai.")
            else:
                st.session_state.poses[new_pose_name] = {}
                st.rerun()

        pose_names_all = list(st.session_state.poses.keys())
        selected_pose = st.selectbox("Chon tu the de xem/chinh", pose_names_all, key="pose_select")

        if selected_pose != "idle":
            override_part = st.selectbox(
                "Chon manh can thay doi trong tu the nay",
                ["(khong chon)"] + list(st.session_state.parts.keys()),
                key=f"ovpart_{selected_pose}",
            )
            if override_part != "(khong chon)":
                existing = st.session_state.poses[selected_pose].get(override_part, {})
                dx = st.slider("Lech X", -400, 400, int(existing.get("x_delta", 0)),
                                key=f"dx_{selected_pose}_{override_part}")
                dy = st.slider("Lech Y", -400, 400, int(existing.get("y_delta", 0)),
                                key=f"dy_{selected_pose}_{override_part}")
                drot = st.slider("Lech goc xoay", -180, 180, int(existing.get("rotation_delta", 0)),
                                  key=f"drot_{selected_pose}_{override_part}")
                alt_file = st.file_uploader(
                    f"Anh thay the cho '{override_part}' o tu the nay (tuy chon)",
                    type=["png"], key=f"alt_{selected_pose}_{override_part}",
                )
                if st.button("Luu chinh cho manh nay", key=f"save_{selected_pose}_{override_part}"):
                    entry = {"x_delta": dx, "y_delta": dy, "rotation_delta": drot}
                    if alt_file:
                        entry["alt_image"] = Image.open(alt_file).convert("RGBA")
                    st.session_state.poses[selected_pose][override_part] = entry
                    st.rerun()

            overridden = list(st.session_state.poses[selected_pose].keys())
            if overridden:
                st.caption("Manh da chinh trong tu the nay: " + ", ".join(overridden))

        st.subheader(f"Xem truoc tu the: {selected_pose}")
        st.image(
            render_pose(st.session_state.parts, st.session_state.canvas_w, st.session_state.canvas_h,
                        st.session_state.background, st.session_state.poses.get(selected_pose, {})),
            use_container_width=True,
        )

        st.divider()
        st.subheader("Mo ta cac tu the (giup AI chon dung hon)")
        for pn in st.session_state.poses.keys():
            st.session_state.pose_descriptions[pn] = st.text_input(
                f"Mo ta cho '{pn}'", value=st.session_state.pose_descriptions.get(pn, ""), key=f"desc_{pn}"
            )

        st.divider()
        st.header("Xuat goi rig")
        zip_bytes = export_rig_bytes()
        st.download_button("Tai rig_package.zip", data=zip_bytes,
                            file_name="rig_package.zip", mime="application/zip")

# ===========================================================================
# TAB 2: TAO HOAT HINH TU KICH BAN (AI GROQ LAM DAO DIEN)
# ===========================================================================
with tab2:
    if not st.session_state.parts:
        st.warning("Chua co manh ghep nao. Sang Tab 1 de canh chinh nhan vat truoc (hoac nap goi rig co san).")
    else:
        pose_names = list(st.session_state.poses.keys())
        if len(pose_names) < 2:
            st.info("Ban moi co tu the 'idle'. Nen tao them vai tu the khac o Tab 1 de hoat hinh sinh dong hon.")

        st.caption("Cac tu the AI co the chon: " + ", ".join(pose_names))

        script_text = st.text_area(
            "Kich ban cua ban", height=180,
            placeholder="Nhap loi thoai / dien bien ban muon nhan vat the hien...",
        )

        try:
            default_key = st.secrets.get("GROQ_API_KEY", "")
        except Exception:
            default_key = ""
        api_key = st.text_input(
            "Groq API key", value=default_key, type="password",
            help="Nen dat trong Secrets cua app khi deploy that, khong de lo trong code.",
        )

        with st.expander("Tuy chon nang cao"):
            model = st.selectbox("Model Groq", GROQ_MODEL_OPTIONS)
            fps = st.slider("FPS video", 6, 24, 12)
            transition_frames = st.slider("So khung hinh chuyen canh giua 2 tu the", 0, 20, 6)

        if st.button("1. Tao timeline tu kich ban (goi AI)"):
            if not api_key:
                st.error("Chua nhap Groq API key.")
            elif not script_text.strip():
                st.error("Chua nhap kich ban.")
            else:
                with st.spinner("Dang goi Groq..."):
                    try:
                        timeline = call_groq_director(
                            api_key, model, script_text, pose_names, st.session_state.pose_descriptions
                        )
                        st.session_state.timeline = timeline
                    except Exception as e:
                        st.error(f"Loi khi goi Groq: {e}")

        if st.session_state.timeline:
            st.subheader("Timeline (xem va co the chinh tay truoc khi render)")
            edited_json = st.text_area(
                "Timeline JSON",
                value=json.dumps(st.session_state.timeline, ensure_ascii=False, indent=2),
                height=280,
            )
            if st.button("2. Dung video tu timeline nay"):
                try:
                    timeline = json.loads(edited_json)
                except Exception:
                    st.error("JSON khong hop le.")
                else:
                    problems = validate_timeline(timeline, pose_names)
                    if problems:
                        st.error("Timeline co loi:\n" + "\n".join(problems))
                    else:
                        progress = st.progress(0.0)
                        out_path = os.path.join(tempfile.gettempdir(), "hoat_hinh_output.mp4")
                        try:
                            build_video(
                                st.session_state.parts, st.session_state.canvas_w, st.session_state.canvas_h,
                                st.session_state.background, st.session_state.poses, timeline, fps, out_path,
                                transition_frames=transition_frames, progress_cb=progress.progress,
                            )
                        except Exception as e:
                            st.error(f"Loi khi dung video: {e}")
                        else:
                            with open(out_path, "rb") as f:
                                video_bytes = f.read()
                            st.video(video_bytes)
                            st.download_button("Tai video", data=video_bytes,
                                                file_name="hoat_hinh.mp4", mime="video/mp4")
