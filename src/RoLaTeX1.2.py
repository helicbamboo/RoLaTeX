import os
import re
import subprocess
import threading
import time
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# --- 配置 ---
WATCH_DIR = ".."
TEXT_EXT = ".rltx"
OUTPUT_EXT = ".tex"

AUTO_COMPILE_PDF = True
LATEX_COMPILER = "pdflatex"
CLEAN_TEMP_FILES = True
TEMP_EXTS = [
    ".aux",
    ".log",
    ".out",
    ".toc",
    ".synctex.gz",
    ".fls",
    ".fdb_latexmk",
]

# --- 希腊大写字母风格配置 ---
# "upright": 保持大写希腊字母全部为正体 (如 \Gamma, \mathrm{A})
# "italic":  大写希腊字母全部与英文字母一样使用斜体 (如 \varGamma, A)
GREEK_UPPERCASE_STYLE = "upright" 

# --- 基础自动符号定义 ---
BASE_SYMBOL_DEFINITIONS = [
    {"id": "le", "aliases": ["<=", "le", r"\le"], "display": "<=", "tex": r"\le{}"},
    {"id": "ge", "aliases": [">=", "ge", r"\ge"], "display": ">=", "tex": r"\ge{}"},
    {"id": "ne", "aliases": ["!=", "ne", r"\ne"], "display": "!=", "tex": r"\ne{}"},
    {"id": "to", "aliases": ["->", "to", r"\to"], "display": "->", "tex": r"\to{}"},
    {
        "id": "Rightarrow",
        "aliases": ["=>", "Rightarrow", r"\Rightarrow"],
        "display": "=>",
        "tex": r"\Rightarrow{}",
    },
]

# --- 希腊字母定义 ---
# 1. 小写希腊字母及常用变体 (LaTeX 默认斜体)
LOWER_GREEK = [
    ("alpha", "α", r"\alpha{}"),
    ("beta", "β", r"\beta{}"),
    ("gamma", "γ", r"\gamma{}"),
    ("delta", "δ", r"\delta{}"),
    ("epsilon", "ϵ", r"\epsilon{}"),
    ("varepsilon", "ε", r"\varepsilon{}"),
    ("zeta", "ζ", r"\zeta{}"),
    ("eta", "η", r"\eta{}"),
    ("theta", "θ", r"\theta{}"),
    ("vartheta", "ϑ", r"\vartheta{}"),
    ("iota", "ι", r"\iota{}"),
    ("kappa", "κ", r"\kappa{}"),
    ("varkappa", "ϰ", r"\varkappa{}"),
    ("lambda", "λ", r"\lambda{}"),
    ("mu", "μ", r"\mu{}"),
    ("nu", "ν", r"\nu{}"),
    ("xi", "ξ", r"\xi{}"),
    ("omicron", "ο", "o"),
    ("pi", "π", r"\pi{}"),
    ("varpi", "ϖ", r"\varpi{}"),
    ("rho", "ρ", r"\rho{}"),
    ("varrho", "ϱ", r"\varrho{}"),
    ("sigma", "σ", r"\sigma{}"),
    ("varsigma", "ς", r"\varsigma{}"),
    ("tau", "τ", r"\tau{}"),
    ("upsilon", "υ", r"\upsilon{}"),
    ("phi", "ϕ", r"\phi{}"),
    ("varphi", "φ", r"\varphi{}"),
    ("chi", "χ", r"\chi{}"),
    ("psi", "ψ", r"\psi{}"),
    ("omega", "ω", r"\omega{}"),
]

# 2. 大写希腊字母根据风格动态构建
if GREEK_UPPERCASE_STYLE == "italic":
    UPPER_GREEK = [
        ("Gamma", "Γ", r"\varGamma{}"),
        ("Delta", "Δ", r"\varDelta{}"),
        ("Theta", "Θ", r"\varTheta{}"),
        ("Lambda", "Λ", r"\varLambda{}"),
        ("Xi", "Ξ", r"\varXi{}"),
        ("Pi", "Π", r"\varPi{}"),
        ("Sigma", "Σ", r"\varSigma{}"),
        ("Upsilon", "Υ", r"\varUpsilon{}"),
        ("Phi", "Φ", r"\varPhi{}"),
        ("Psi", "Ψ", r"\varPsi{}"),
        ("Omega", "Ω", r"\varOmega{}"),
        ("Alpha", "Α", "A"),
        ("Beta", "Β", "B"),
        ("Epsilon", "Ε", "E"),
        ("Zeta", "Ζ", "Z"),
        ("Eta", "Η", "H"),
        ("Iota", "Ι", "I"),
        ("Kappa", "Κ", "K"),
        ("Mu", "Μ", "M"),
        ("Nu", "Ν", "N"),
        ("Omicron", "Ο", "O"),
        ("Rho", "Ρ", "P"),
        ("Tau", "Τ", "T"),
        ("Chi", "Χ", "X"),
    ]
else:  # "upright" 正体风格
    UPPER_GREEK = [
        ("Gamma", "Γ", r"\Gamma{}"),
        ("Delta", "Δ", r"\Delta{}"),
        ("Theta", "Θ", r"\Theta{}"),
        ("Lambda", "Λ", r"\Lambda{}"),
        ("Xi", "Ξ", r"\Xi{}"),
        ("Pi", "Π", r"\Pi{}"),
        ("Sigma", "Σ", r"\Sigma{}"),
        ("Upsilon", "Υ", r"\Upsilon{}"),
        ("Phi", "Φ", r"\Phi{}"),
        ("Psi", "Ψ", r"\Psi{}"),
        ("Omega", "Ω", r"\Omega{}"),
        ("Alpha", "Α", r"\mathrm{A}{}"),
        ("Beta", "Β", r"\mathrm{B}{}"),
        ("Epsilon", "Ε", r"\mathrm{E}{}"),
        ("Zeta", "Ζ", r"\mathrm{Z}{}"),
        ("Eta", "Η", r"\mathrm{H}{}"),
        ("Iota", "Ι", r"\mathrm{I}{}"),
        ("Kappa", "Κ", r"\mathrm{K}{}"),
        ("Mu", "Μ", r"\mathrm{M}{}"),
        ("Nu", "Ν", r"\mathrm{N}{}"),
        ("Omicron", "Ο", r"\mathrm{O}{}"),
        ("Rho", "Ρ", r"\mathrm{P}{}"),
        ("Tau", "Τ", r"\mathrm{T}{}"),
        ("Chi", "Χ", r"\mathrm{X}{}"),
    ]

GREEK_SYMBOL_DEFINITIONS = [
    {
        "id": name,
        "aliases": [char, name, f"\\{name}"],
        "display": char,
        "tex": tex,
    }
    for name, char, tex in (LOWER_GREEK + UPPER_GREEK)
]

# 合并所有符号定义
SYMBOL_DEFINITIONS = BASE_SYMBOL_DEFINITIONS + GREEK_SYMBOL_DEFINITIONS

ALIAS_TO_ID = {}
for spec in SYMBOL_DEFINITIONS:
    for alias in spec["aliases"]:
        ALIAS_TO_ID[alias] = spec["id"]

# --- 基础字符集 (4.2.1) ---
BASE_CHARS = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789()[]+-=_^/~><,.:;!|&'*"
)

PROCESSING_FILES = set()
PENDING_FILES = set()
FILE_LOCK = threading.Lock()


def is_target_file(path):
    return path.endswith(TEXT_EXT) and not os.path.basename(path).startswith("~")


def get_output_path(input_path):
    base, _ = os.path.splitext(input_path)
    return base + OUTPUT_EXT


def mask_escaped_percent(text):
    """根据 3.1.2 和 3.1.3，将奇数个 \\ 后的 % 掩码为转义文本"""
    return re.sub(r"(?<!\\)((?:\\\\)*)\\%", r"\1__ESCAPED_PERCENT_TOKEN__", text)


def unmask_escaped_percent(text):
    return text.replace("__ESCAPED_PERCENT_TOKEN__", r"\%")


# =========================================================================
# 4.4.1 一级块状态机解析器
# =========================================================================
def scan_first_level_blocks(text):
    n = len(text)
    i = 0
    state = "BODY"
    meta_blocks = []
    head_blocks = []
    body_stream = []
    curr_buf = []

    def flush_curr(new_state=None):
        nonlocal curr_buf, state
        content = "".join(curr_buf)
        curr_buf = []
        if content:
            if state == "BODY":
                body_stream.append(("BODY", content))
            elif state == "META":
                meta_blocks.append(content)
            elif state == "HEAD":
                head_blocks.append(content)
            elif state == "LATEX":
                body_stream.append(("LATEX", content))
        if new_state:
            state = new_state

    while i < n:
        if state == "BODY":
            if text.startswith("%on{meta}", i):
                flush_curr("META")
                i += len("%on{meta}")
                if i < n and text[i] == "\n":
                    i += 1
                continue
            elif text.startswith("%on{head}", i):
                flush_curr("HEAD")
                i += len("%on{head}")
                if i < n and text[i] == "\n":
                    i += 1
                continue
            elif text.startswith("%on{latex}", i):
                flush_curr("LATEX")
                i += len("%on{latex}")
                if i < n and text[i] == "\n":
                    i += 1
                continue
            else:
                curr_buf.append(text[i])
                i += 1

        elif state == "META":
            if text.startswith("%off{meta}", i):
                flush_curr("BODY")
                i += len("%off{meta}")
                if i < n and text[i] == "\n":
                    i += 1
                continue
            else:
                curr_buf.append(text[i])
                i += 1

        elif state == "HEAD":
            if text.startswith("%off{head}", i):
                flush_curr("BODY")
                i += len("%off{head}")
                if i < n and text[i] == "\n":
                    i += 1
                continue
            else:
                curr_buf.append(text[i])
                i += 1

        elif state == "LATEX":
            if text.startswith("%off{latex}", i):
                flush_curr("BODY")
                i += len("%off{latex}")
                if i < n and text[i] == "\n":
                    i += 1
                continue
            else:
                curr_buf.append(text[i])
                i += 1

    flush_curr()
    return meta_blocks, head_blocks, body_stream


def parse_meta_configs(meta_blocks):
    """4.3.1 解析 meta 块中的 key:value 或 key=value"""
    config = {}
    for block in meta_blocks:
        for line in block.split("\n"):
            line = line.strip()
            if not line or line.startswith("%"):
                continue
            if "=" in line or ":" in line:
                parts = re.split(r"[=:]", line, maxsplit=1)
                key = parts[0].strip().lower()
                val = parts[1].strip()
                config[key] = val
    return config


def build_header(head_blocks):
    """4.1 & 4.3.3 构建导言区"""
    custom_preamble = "\n".join(head_blocks)
    return f"""\\documentclass[UTF8,space]{{ctexart}} 
\\ctexset{{auto-spacing = false}}
\\CJKsetecglue{{}}
\\usepackage{{amsmath, lmodern}}
\\usepackage{{accents}}
\\emergencystretch=1em
\\thickmuskip=0mu
\\medmuskip=0mu
\\thinmuskip=0mu
{custom_preamble}
\\obeyspaces
\\begin{{document}}
"""


# =========================================================================
# 主体块语法处理
# =========================================================================
def handle_accentset(text):
    """处理 %^ 与 %l^ 装饰符扩展"""
    idx = 0
    while True:
        idx_normal = text.find("%^", idx)
        idx_large = text.find("%l^", idx)

        if idx_normal == -1 and idx_large == -1:
            break

        if idx_normal != -1 and idx_large != -1:
            is_large = idx_large < idx_normal
        else:
            is_large = idx_large != -1

        idx = idx_large if is_large else idx_normal
        cmd_len = 3 if is_large else 2

        start = idx - 1
        if start < 0:
            idx += cmd_len
            continue

        if text[start] == "}":
            depth = 1
            curr = start - 1
            while curr >= 0 and depth > 0:
                if text[curr] == "}":
                    depth += 1
                elif text[curr] == "{":
                    depth -= 1
                curr -= 1
            brace_start = curr + 1

            cmd_curr = brace_start - 1
            while cmd_curr >= 0 and text[cmd_curr].isalpha():
                cmd_curr -= 1
            if cmd_curr >= 0 and text[cmd_curr] == "\\":
                start_idx = cmd_curr
            else:
                start_idx = brace_start
        else:
            curr = start
            while curr >= 0 and text[curr].isalpha():
                curr -= 1
            if curr >= 0 and text[curr] == "\\":
                start_idx = curr
            else:
                start_idx = start

        base = text[start_idx:idx]
        end_idx = idx + cmd_len
        n = len(text)
        if end_idx >= n:
            idx += cmd_len
            continue

        if text[end_idx] == "{":
            depth = 1
            curr = end_idx + 1
            while curr < n and depth > 0:
                if text[curr] == "{":
                    depth += 1
                elif text[curr] == "}":
                    depth -= 1
                curr += 1
            accent_end = curr
        elif text[end_idx] == "\\":
            curr = end_idx + 1
            while curr < n and text[curr].isalpha():
                curr += 1
            if curr < n and text[curr] == "{":
                depth = 1
                curr += 1
                while curr < n and depth > 0:
                    if text[curr] == "{":
                        depth += 1
                    elif text[curr] == "}":
                        depth -= 1
                    curr += 1
            accent_end = curr
        else:
            accent_end = end_idx + 1

        accent = text[idx + cmd_len : accent_end]
        clean_base = base[1:-1] if base.startswith("{") and base.endswith("}") else base
        clean_accent = accent[1:-1] if accent.startswith("{") and accent.endswith("}") else accent

        if is_large:
            replacement = f"\\overset{{{clean_accent}}}{{{clean_base}}}"
        else:
            replacement = f"\\accentset{{{clean_accent}}}{{{clean_base}}}"

        text = text[:start_idx] + replacement + text[accent_end:]
        idx = start_idx + len(replacement)

    return text


def wrap_math_blocks(text):
    """
    规范 4.2.1, 4.2.3, 4.2.5：
    - 基础字符集扫描与自动包裹 $
    - \\ 字符指令识别
    - 公式环境内部非基础字符 \\text{} 包裹
    """
    result = []
    math_block = []
    brace_depth = 0
    display_math_closer = None
    i = 0
    n = len(text)

    while i < n:
        if display_math_closer:
            if text.startswith(display_math_closer, i):
                if math_block:
                    result.append("".join(math_block))
                    math_block = []
                result.append(display_math_closer)
                i += len(display_math_closer)
                display_math_closer = None
                continue

            c = text[i]
            if c == "\\":
                result.append(c)
                if i + 1 < n:
                    result.append(text[i + 1])
                    i += 2
                else:
                    i += 1
            elif c == "{":
                brace_depth += 1
                result.append(c)
                i += 1
            elif c == "}":
                if brace_depth > 0:
                    brace_depth -= 1
                result.append(c)
                i += 1
            elif c == "\n":
                result.append(c)
                i += 1
            elif c in BASE_CHARS:
                result.append(c)
                i += 1
            else:
                text_buffer = []
                while (
                    i < n
                    and text[i] not in BASE_CHARS
                    and text[i] not in "\\{}\n"
                    and not text.startswith(display_math_closer, i)
                ):
                    text_buffer.append(text[i])
                    i += 1
                if text_buffer:
                    result.append("\\text{" + "".join(text_buffer) + "}")
            continue

        if text.startswith("$$", i):
            if math_block:
                result.append("$" + "".join(math_block) + "$")
                math_block = []
            result.append("$$")
            display_math_closer = "$$"
            i += 2
            continue

        if text.startswith("\\[", i):
            if math_block:
                result.append("$" + "".join(math_block) + "$")
                math_block = []
            result.append("\\[")
            display_math_closer = "\\]"
            i += 2
            continue

        if text.startswith("\\begin{align*}", i):
            if math_block:
                result.append("$" + "".join(math_block) + "$")
                math_block = []
            result.append("\\begin{align*}")
            display_math_closer = "\\end{align*}"
            i += len("\\begin{align*}")
            continue

        c = text[i]

        if c == "\\":
            if i == n - 1 or text[i + 1] == "\n":
                if math_block:
                    result.append("$" + "".join(math_block) + "$")
                    math_block = []
                i += 1
                continue

            math_block.append(c)
            i += 1
            if i < n and (("a" <= text[i] <= "z") or ("A" <= text[i] <= "Z")):
                while i < n and (("a" <= text[i] <= "z") or ("A" <= text[i] <= "Z")):
                    math_block.append(text[i])
                    i += 1
            elif i < n:
                math_block.append(text[i])
                i += 1
            continue

        elif c == "{":
            brace_depth += 1
            math_block.append(c)
            i += 1
            continue

        elif c == "}":
            if brace_depth > 0:
                brace_depth -= 1
                math_block.append(c)
                i += 1
            else:
                if math_block:
                    result.append("$" + "".join(math_block) + "$")
                    math_block = []
                result.append(c)
                i += 1
            continue

        if brace_depth > 0:
            if c == "\n":
                if math_block:
                    result.append("$" + "".join(math_block) + "$")
                    math_block = []
                result.append(c)
                brace_depth = 0
                i += 1
            elif c in BASE_CHARS:
                math_block.append(c)
                i += 1
            else:
                text_buffer = []
                while i < n and text[i] not in BASE_CHARS and text[i] not in "\\{}\n":
                    text_buffer.append(text[i])
                    i += 1
                if text_buffer:
                    math_block.append("\\text{" + "".join(text_buffer) + "}")
            continue
        else:
            if c in BASE_CHARS:
                math_block.append(c)
                i += 1
            else:
                if math_block and math_block[-1] in ("^", "_") and not c.isspace():
                    math_block.append("{\\text{" + c + "}}")
                    i += 1
                    result.append("$" + "".join(math_block) + "$")
                    math_block = []
                else:
                    if math_block:
                        result.append("$" + "".join(math_block) + "$")
                        math_block = []
                    result.append(c)
                    i += 1

    if math_block:
        result.append("$" + "".join(math_block) + "$")

    return "".join(result)


def handle_body_instructions_and_symbols(body_chunks):
    """维护主体指令与自动符号替换"""
    auto_sub_active = False
    active_symbol_ids = {spec["id"] for spec in SYMBOL_DEFINITIONS}

    processed_chunks = []

    for kind, text in body_chunks:
        if kind == "LATEX":
            processed_chunks.append((kind, text))
            continue

        pattern = r"(%on\{auto_\}\n?|%off\{auto_\}\n?|%add_auto\{.*?\}\n?|%remove_auto\{.*?\}\n?)"
        parts = re.split(pattern, text)
        buffer_parts = []

        for part in parts:
            if not part:
                continue

            clean_cmd = part.strip()
            if clean_cmd == "%on{auto_}":
                auto_sub_active = True
                continue
            elif clean_cmd == "%off{auto_}":
                auto_sub_active = False
                continue

            add_match = re.match(r"%add_auto\{(.*?)\}", clean_cmd)
            if add_match:
                items = [i.strip() for i in add_match.group(1).split(",")]
                for item in items:
                    if item.lower() == "all":
                        active_symbol_ids.update({spec["id"] for spec in SYMBOL_DEFINITIONS})
                    elif item in ALIAS_TO_ID:
                        active_symbol_ids.add(ALIAS_TO_ID[item])
                continue

            rem_match = re.match(r"%remove_auto\{(.*?)\}", clean_cmd)
            if rem_match:
                items = [i.strip() for i in rem_match.group(1).split(",")]
                for item in items:
                    if item.lower() == "all":
                        active_symbol_ids.clear()
                    elif item in ALIAS_TO_ID:
                        target_id = ALIAS_TO_ID[item]
                        if target_id in active_symbol_ids:
                            active_symbol_ids.remove(target_id)
                continue

            segment = part
            if active_symbol_ids:
                current_rules = [spec for spec in SYMBOL_DEFINITIONS if spec["id"] in active_symbol_ids]
                current_rules.sort(key=lambda x: len(x["display"]), reverse=True)
                for spec in current_rules:
                    segment = segment.replace(spec["display"], spec["tex"])

            if auto_sub_active:
                segment = re.sub(r"([a-zA-Z])(\d)", r"\1_\2", segment)

            buffer_parts.append(segment)

        processed_chunks.append(("BODY", "".join(buffer_parts)))

    return processed_chunks


def format_final_body(body_chunks):
    """拼装并处理换行"""
    RESTORE_DEFAULT_LATEX = (
        "\n\\catcode`\\ =10\\relax"
        "\\thinmuskip=3mu\\medmuskip=4mu plus 2mu minus 4mu\\thickmuskip=5mu plus 5mu\n"
    )
    REAPPLY_RLTX_STYLE = (
        "\n\\obeyspaces"
        "\\thickmuskip=0mu\\medmuskip=0mu\\thinmuskip=0mu\n"
    )

    rendered_parts = []
    for kind, text in body_chunks:
        if kind == "LATEX":
            inner = text.strip("\n")
            rendered_parts.append(RESTORE_DEFAULT_LATEX + inner + REAPPLY_RLTX_STYLE)
        else:
            t = handle_accentset(text)
            t = wrap_math_blocks(t)
            rendered_parts.append(t)

    full_body = "".join(rendered_parts)

    pattern = rf"(\$\$.*?\$\$|\\\[.*?\\\]|\\begin\{{align\*\}}.*?\\end\{{align\*\}})"
    parts = re.split(pattern, full_body, flags=re.DOTALL)
    n = len(parts)
    final_output = []

    for i in range(n):
        part = parts[i]
        is_math = part.startswith("$$") or part.startswith("\\[") or part.startswith("\\begin{align*}")

        if is_math:
            final_output.append(part)
        else:
            temp = part
            if i < n - 1 and (parts[i + 1].startswith("$$") or parts[i + 1].startswith("\\[") or parts[i + 1].startswith("\\begin{align*}")):
                if temp.endswith("\n"):
                    temp = temp[:-1]

            if i > 0 and (parts[i - 1].startswith("$$") or parts[i - 1].startswith("\\[") or parts[i - 1].startswith("\\begin{align*}")):
                if temp.startswith("\n"):
                    temp = "\\indent{}" + temp[1:]

            temp = re.sub(
                r"\n+",
                lambda m: "\\par\n" + "\\null\\par\n" * (len(m.group(0)) - 1),
                temp,
            )
            final_output.append(temp)

    return "".join(final_output)


def convert_file(src_path):
    try:
        with open(src_path, "r", encoding="utf-8") as f:
            content = f.read()

        content = mask_escaped_percent(content)

        meta_blocks, head_blocks, body_stream = scan_first_level_blocks(content)
        _ = parse_meta_configs(meta_blocks)
        header_latex = build_header(head_blocks)

        body_stream = handle_body_instructions_and_symbols(body_stream)
        processed_body = format_final_body(body_stream)

        footer_latex = "\n" + r"\end{document}"
        output_path = get_output_path(src_path)

        final_content = header_latex + processed_body + footer_latex
        final_content = unmask_escaped_percent(final_content)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(final_content)

        print(f"--- 转换成功: {output_path} ---")
        compile_tex_to_pdf(output_path)

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"转换 {src_path} 时出错: {e}")


def compile_tex_to_pdf(tex_path):
    if not AUTO_COMPILE_PDF:
        return

    tex_dir = os.path.dirname(os.path.abspath(tex_path))
    tex_file = os.path.basename(tex_path)
    base_name = os.path.splitext(tex_file)[0]
    pdf_path = os.path.join(tex_dir, base_name + ".pdf")

    old_mtime = os.path.getmtime(pdf_path) if os.path.exists(pdf_path) else None
    cmd = [LATEX_COMPILER, "-interaction=nonstopmode", tex_file]

    print(f"🚀 正在自动编译 PDF ({LATEX_COMPILER}) ...")
    try:
        process = subprocess.run(
            cmd,
            cwd=tex_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )

        pdf_exists = os.path.exists(pdf_path)
        pdf_updated = pdf_exists and (
            old_mtime is None or os.path.getmtime(pdf_path) > old_mtime
        )

        def extract_latex_errors(stdout_text):
            lines = stdout_text.splitlines()
            error_snippets = []
            for i, line in enumerate(lines):
                if line.startswith("!"):
                    context = lines[max(0, i) : min(len(lines), i + 4)]
                    error_snippets.extend(context)
                    error_snippets.append("   " + "-" * 40)
            return error_snippets

        if process.returncode == 0:
            print(f"✅ PDF 编译成功: {pdf_path}")
        elif pdf_updated:
            print(f"⚠️ PDF 已生成，但 LaTeX 存在警告: {pdf_path}")
        else:
            print(f"❌ PDF 编译失败！")
            errors = extract_latex_errors(process.stdout)
            if errors:
                for err in errors:
                    print("   | " + err)

    except Exception as e:
        print(f"❌ 编译过程发生异常: {e}")

    finally:
        if CLEAN_TEMP_FILES:
            for ext in TEMP_EXTS:
                temp_file = os.path.join(tex_dir, base_name + ext)
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except Exception:
                        pass


def trigger_file_conversion(src_path):
    src_path = os.path.abspath(src_path)

    with FILE_LOCK:
        if src_path in PROCESSING_FILES:
            PENDING_FILES.add(src_path)
            return
        else:
            PROCESSING_FILES.add(src_path)

    threading.Thread(
        target=_compile_worker, args=(src_path,), daemon=True
    ).start()


def _compile_worker(src_path):
    while True:
        convert_file(src_path)
        with FILE_LOCK:
            if src_path in PENDING_FILES:
                PENDING_FILES.remove(src_path)
                print(f"🔄 检测到文件更新，准备重新编译最新版本...")
            else:
                PROCESSING_FILES.remove(src_path)
                break


class NoteHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if not event.is_directory:
            src_path = os.path.abspath(event.src_path)
            if is_target_file(src_path):
                trigger_file_conversion(src_path)


if __name__ == "__main__":
    if not os.path.exists(WATCH_DIR):
        print(f"错误: 目录 {WATCH_DIR} 不存在。")
    else:
        for root, dirs, files in os.walk(WATCH_DIR):
            for file in files:
                full_path = os.path.join(root, file)
                if os.path.isfile(full_path) and is_target_file(full_path):
                    trigger_file_conversion(full_path)

        observer = Observer()
        observer.schedule(NoteHandler(), path=WATCH_DIR, recursive=True)
        observer.start()
        print("👀 监控已启动，等待文件修改...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()
