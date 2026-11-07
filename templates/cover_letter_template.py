import re
from src.modules.cover_letters.schemas import CoverLetterCompileRequest


def format_title_case_name(name: str) -> str:
    if not name:
        return ""
    return " ".join(word.capitalize() for word in name.split())


def _escape_raw_latex(text: str) -> str:
    """Single-pass regex escape for LaTeX special characters."""
    if not text:
        return ""
    latex_special = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    pattern = re.compile("|".join(re.escape(k) for k in latex_special.keys()))
    return pattern.sub(lambda m: latex_special[m.group(0)], str(text))


def escape_latex(text: str) -> str:
    """Escapes LaTeX reserved characters (&, %, $, #, _, {, }, ~, ^, \\) everywhere while keeping \\textbf{...} wrappers intact."""
    if not text:
        return ""
    tokens = re.split(r"(\\textbf\{[^{}]*\}|\\today)", str(text))
    out = []
    for token in tokens:
        if token.startswith(r"\textbf{"):
            inner = token[8:-1]
            out.append(f"\\textbf{{{_escape_raw_latex(inner)}}}")
        elif token == r"\today":
            out.append(token)
        else:
            out.append(_escape_raw_latex(token))
    return "".join(out)


def render_cover_letter_latex(data: CoverLetterCompileRequest) -> str:
    """Render XeLaTeX cover letter template with safe escaping for all user inputs."""
    formatted_name = escape_latex(
        data.candidate_name.upper().strip() if data.candidate_name else "CANDIDATE NAME"
    )

    name = formatted_name
    headline = escape_latex(data.candidate_headline.strip())
    location = escape_latex(data.candidate_location.strip())
    phone = escape_latex(data.candidate_phone.strip())
    email = escape_latex(data.candidate_email.strip())

    loc_phone_parts = [p for p in [location, phone] if p]
    loc_phone = " \\quad | \\quad ".join(loc_phone_parts)

    links = []
    if data.linkedin_url and data.linkedin_url.strip():
        li_url = data.linkedin_url.strip()
        if not li_url.startswith(("http://", "https://")):
            li_url = f"https://{li_url}"
        links.append(f"\\href{{{li_url}}}{{LinkedIn}}")
    if data.github_url and data.github_url.strip():
        gh_url = data.github_url.strip()
        if not gh_url.startswith(("http://", "https://")):
            gh_url = f"https://{gh_url}"
        links.append(f"\\href{{{gh_url}}}{{GitHub}}")
    links_str = " \\quad | \\quad ".join(links)

    recipient = escape_latex(data.recipient_attention.strip())
    company = escape_latex(data.company_name.strip())
    if data.city_date and data.city_date.strip() and "Paris, le" not in data.city_date:
        city_date = escape_latex(data.city_date.strip())
    elif data.candidate_location and data.candidate_location.strip():
        city = data.candidate_location.split(",")[0].strip()
        city_date = escape_latex(f"{city}, le \\today")
    elif data.city_date and data.city_date.strip():
        city_date = escape_latex(data.city_date.strip())
    else:
        city_date = escape_latex(r"\today")

    subject = escape_latex(data.subject_line.strip())

    salutation = escape_latex(data.salutation.strip())
    p1 = escape_latex(data.paragraph_1.strip())
    p2 = escape_latex(data.paragraph_2.strip())
    p3 = escape_latex(data.paragraph_3.strip())
    p4 = escape_latex(data.paragraph_4.strip())
    raw_sign_off = data.sign_off.strip() if data.sign_off else "Sincerely,"
    if "\n" in raw_sign_off:
        raw_sign_off = raw_sign_off.split("\n")[0].strip()
    raw_sign_off = re.sub(r",+", ",", raw_sign_off).strip()
    if not raw_sign_off.endswith(","):
        raw_sign_off += ","
    sign_off = escape_latex(raw_sign_off)

    return f"""\\documentclass[11pt,a4paper]{{article}}

\\usepackage{{fontspec}}
\\setmainfont{{Liberation Serif}}

\\usepackage[french]{{babel}}
\\usepackage[
    top=2cm,
    bottom=2.2cm,
    left=2.5cm,
    right=2.5cm
]{{geometry}}
\\usepackage[hidelinks]{{hyperref}}
\\usepackage{{xcolor}}
\\usepackage{{setspace}}
\\usepackage{{parskip}}
\\usepackage{{graphicx}}

% --------------------------------------------------
% Colors
% --------------------------------------------------

\\definecolor{{accent}}{{HTML}}{{1F2937}}
\\definecolor{{textgray}}{{HTML}}{{4B5563}}

% --------------------------------------------------
% Typography
% --------------------------------------------------

\\pagestyle{{empty}}
\\setlength{{\\parindent}}{{0pt}}
\\setlength{{\\parskip}}{{9pt}}
\\setstretch{{1.1}}

\\hypersetup{{
    colorlinks=true,
    urlcolor=accent,
    linkcolor=accent,
    pdfnewwindow=true
}}

\\begin{{document}}

% ==================================================
% HEADER
% ==================================================

\\noindent
\\begin{{minipage}}[c]{{0.62\\textwidth}}

    {{\\fontsize{{23}}{{27}}\\selectfont\\bfseries {name}}}

    {f"\\vspace{{5pt}}\n\n    {{\\small\n    {headline}\n    }}" if headline else ""}

    {f"\\vspace{{7pt}}\n\n    {{\\small\\color{{textgray}}\n    {loc_phone}\n    }}" if loc_phone else ""}

    {f"\\vspace{{4pt}}\n\n    {{\\small\\color{{textgray}}\n    \\href{{mailto:{email}}}{{{email}}}\n    }}" if email else ""}

    {f"\\vspace{{4pt}}\n\n    {{\\small\\color{{textgray}}\n    {links_str}\n    }}" if links_str else ""}

\\end{{minipage}}%
\\hfill
\\begin{{minipage}}[c]{{0.34\\textwidth}}
    \\raggedleft

    \\includegraphics[
        width=0.95\\linewidth,
        height=2.7cm,
        keepaspectratio
    ]{{company-logo.png}}

\\end{{minipage}}

\\vspace{{14pt}}

{{\\color{{accent}}\\rule{{\\textwidth}}{{1pt}}}}

\\vspace{{20pt}}

% ==================================================
% RECIPIENT
% ==================================================

\\begin{{minipage}}[t]{{0.55\\textwidth}}
    \\textbf{{{recipient}}}

    \\vspace{{3pt}}

    \\textbf{{{company}}}
\\end{{minipage}}%
\\hfill
\\begin{{minipage}}[t]{{0.4\\textwidth}}
    \\raggedleft
    {city_date}
\\end{{minipage}}

\\vspace{{22pt}}

% ==================================================
% SUBJECT
% ==================================================

{{\\large\\bfseries Objet : {subject}}}

\\vspace{{16pt}}

% ==================================================
% LETTER
% ==================================================

{salutation}

{p1}

{p2}

{p3}

{p4}

\\vspace{{12pt}}

{sign_off}

\\vspace{{16pt}}

\\textbf{{{formatted_name}}}

\\end{{document}}
"""
