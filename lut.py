#!/usr/bin/env python3
"""
apply_lut.py — 把 .cube LUT 滤镜套用到图像上
用法：
  单张图片：python apply_lut.py 图片.jpg 滤镜.cube
  批量处理：python apply_lut.py 图片文件夹/ 滤镜.cube
  指定输出：python apply_lut.py 图片.jpg 滤镜.cube -o 输出.jpg
  调节强度：python apply_lut.py 图片.jpg 滤镜.cube --intensity 0.7
依赖：pip install pillow numpy
"""

import sys
import os
import argparse
import numpy as np
from PIL import Image

RAW_EXT = {".dng", ".raf", ".cr2", ".cr3", ".nef", ".arw", ".orf", ".rw2"}

def open_image(path: str) -> Image.Image:
    """打开图片，DNG/RAW 格式用 rawpy 解码，其他用 Pillow。"""
    ext = os.path.splitext(path)[1].lower()
    if ext in RAW_EXT:
        try:
            import rawpy
        except ImportError:
            raise ImportError("读取 DNG 需要 rawpy，请先运行：pip install rawpy")
        with rawpy.imread(path) as raw:
            rgb = raw.postprocess(use_camera_wb=True, output_bps=8)
        return Image.fromarray(rgb)
    else:
        return Image.open(path)


# ── 1. 解析 .cube 文件 ────────────────────────────────────────────────────────

def parse_cube(path: str) -> tuple[np.ndarray, int]:
    """读取 .cube 文件，返回 (lut_array, size)。
    lut_array shape: (size, size, size, 3)，值域 [0, 1]。
    """
    size = None
    data = []

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.upper().startswith("LUT_3D_SIZE"):
                size = int(line.split()[-1])
                continue
            # 跳过其他元数据行（DOMAIN_MIN / DOMAIN_MAX / TITLE）
            if any(line.upper().startswith(k) for k in ("TITLE", "DOMAIN", "LUT_1D")):
                continue
            parts = line.split()
            if len(parts) == 3:
                try:
                    data.append([float(x) for x in parts])
                except ValueError:
                    continue

    if size is None:
        raise ValueError("找不到 LUT_3D_SIZE，请确认这是一个 3D .cube 文件。")
    if len(data) != size ** 3:
        raise ValueError(f"数据行数 {len(data)} 与 LUT 大小 {size}³={size**3} 不匹配。")

    # .cube 的排列顺序：R 变化最快，B 变化最慢
    arr = np.array(data, dtype=np.float32).reshape(size, size, size, 3)
    return arr, size


# ── 2. 应用 LUT（三线性插值）────────────────────────────────────────────────

def apply_lut(image: Image.Image, lut: np.ndarray, size: int,
              intensity: float = 1.0) -> Image.Image:
    """对 PIL Image 做三线性插值 LUT 映射。"""
    img = image.convert("RGB")
    pixels = np.array(img, dtype=np.float32) / 255.0  # H×W×3，值域 [0,1]

    # 把像素值映射到 LUT 坐标（0 ~ size-1）
    scale = size - 1
    r = pixels[..., 0] * scale
    g = pixels[..., 1] * scale
    b = pixels[..., 2] * scale

    # 整数下界索引（并 clip 防越界）
    r0 = np.clip(r.astype(np.int32), 0, size - 2)
    g0 = np.clip(g.astype(np.int32), 0, size - 2)
    b0 = np.clip(b.astype(np.int32), 0, size - 2)
    r1, g1, b1 = r0 + 1, g0 + 1, b0 + 1

    # 小数部分（插值权重）
    dr = (r - r0)[..., np.newaxis]
    dg = (g - g0)[..., np.newaxis]
    db = (b - b0)[..., np.newaxis]

    # 三线性插值：在 R/G/B 三个轴上各插一次
    # lut 索引顺序：lut[b, g, r] （.cube 规范：R 最快变化，对应最内层）
    c000 = lut[b0, g0, r0]
    c001 = lut[b0, g0, r1]
    c010 = lut[b0, g1, r0]
    c011 = lut[b0, g1, r1]
    c100 = lut[b1, g0, r0]
    c101 = lut[b1, g0, r1]
    c110 = lut[b1, g1, r0]
    c111 = lut[b1, g1, r1]

    result = (
        c000 * (1 - dr) * (1 - dg) * (1 - db)
        + c001 * dr       * (1 - dg) * (1 - db)
        + c010 * (1 - dr) * dg       * (1 - db)
        + c011 * dr       * dg       * (1 - db)
        + c100 * (1 - dr) * (1 - dg) * db
        + c101 * dr       * (1 - dg) * db
        + c110 * (1 - dr) * dg       * db
        + c111 * dr       * dg       * db
    )

    result = np.clip(result, 0, 1)

    # 按强度混合原图与 LUT 结果
    if intensity < 1.0:
        result = pixels * (1 - intensity) + result * intensity

    out_pixels = (result * 255).round().astype(np.uint8)
    return Image.fromarray(out_pixels, "RGB")


# ── 3. 批量处理逻辑 ──────────────────────────────────────────────────────────

SUPPORTED_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp", ".dng"}


def process_one(src: str, lut: np.ndarray, size: int,
                dst: str, intensity: float):
    ext = os.path.splitext(src)[1].lower()
    is_raw = ext in RAW_EXT

    img = open_image(src)
    original_mode = img.mode
    out = apply_lut(img, lut, size, intensity)

    # 如果原图有透明通道，把它贴回去（RAW 没有透明通道）
    if not is_raw and original_mode in ("RGBA", "LA"):
        alpha = Image.open(src).getchannel("A")
        out.putalpha(alpha)

    # DNG 输出为 JPG（Pillow 无法写 DNG）
    if is_raw:
        dst = os.path.splitext(dst)[0] + ".jpg"

    out.save(dst, quality=95)
    print(f"  ✓ {os.path.basename(src)}  →  {dst}")


def build_output_path(src: str, output_arg: str | None,
                      lut_name: str, index: int | None = None) -> str:
    """根据用户指定（或自动推断）计算输出路径。"""
    if output_arg:
        return output_arg

    base, ext = os.path.splitext(src)
    suffix = f"_{lut_name}"
    if index is not None:
        suffix += f"_{index:04d}"
    return base + suffix + ext


# ── 4. 主程序 ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="把 .cube LUT 套用到静态图像（支持批量）"
    )
    parser.add_argument("input",
                        help="输入图片路径，或包含图片的文件夹")
    parser.add_argument("lut",
                        help=".cube 文件路径")
    parser.add_argument("-o", "--output", default=None,
                        help="输出路径（单张图片时有效）")
    parser.add_argument("--intensity", type=float, default=1.0,
                        help="LUT 强度 0.0~1.0，默认 1.0（完全应用）")
    args = parser.parse_args()

    # 读取 LUT
    print(f"📂 加载 LUT：{args.lut}")
    lut, size = parse_cube(args.lut)
    lut_name = os.path.splitext(os.path.basename(args.lut))[0]
    print(f"   LUT 大小：{size}³，强度：{args.intensity}")

    # 单张 or 批量
    if os.path.isdir(args.input):
        files = [
            os.path.join(args.input, f)
            for f in sorted(os.listdir(args.input))
            if os.path.splitext(f)[1].lower() in SUPPORTED_EXT
        ]
        if not files:
            print("⚠️  文件夹内没有找到支持的图片格式。")
            sys.exit(1)
        print(f"🖼  找到 {len(files)} 张图片，开始处理…")
        for i, src in enumerate(files):
            dst = build_output_path(src, None, lut_name, i)
            process_one(src, lut, size, dst, args.intensity)
    else:
        if not os.path.isfile(args.input):
            print(f"❌ 找不到文件：{args.input}")
            sys.exit(1)
        dst = build_output_path(args.input, args.output, lut_name)
        print(f"🖼  处理图片…")
        process_one(args.input, lut, size, dst, args.intensity)

    print("✅ 全部完成！")


if __name__ == "__main__":
    main()
