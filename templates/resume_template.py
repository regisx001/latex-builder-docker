import re
from typing import Any, List
from src.modules.resumes.schemas import ResumeCompileRequest, clean_bullets


def escape_latex(text: Any) -> str:
    """Escape special LaTeX characters in user inputs using a single-pass regex to prevent double escaping and build failures."""
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


def normalize_url(url: Any, default_prefix: str = "https://") -> str:
    """Ensure a web URL has a valid protocol prefix (https://, http://, mailto:, etc.)."""
    if not url:
        return ""
    u = str(url).strip()
    if not u:
        return ""
    if u.startswith(("http://", "https://", "mailto:", "tel:")):
        return u
    return f"{default_prefix}{u}"


def extract_github_username(github_url: Any) -> str:
    """Extract GitHub username from URL or identifier."""
    if not github_url:
        return ""
    cleaned = str(github_url).strip().rstrip("/")
    m = re.search(r"github\.com/([a-zA-Z0-9_-]+)", cleaned, re.IGNORECASE)
    if m:
        return m.group(1)
    if "/" not in cleaned and "." not in cleaned and cleaned.lower() != "github":
        return cleaned
    return ""


def slugify_title(text: str) -> str:
    """Convert a project title to a URL-safe repository slug."""
    cleaned = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", cleaned)


def resolve_project_url(raw_url: Any, project_title: str, candidate_gh_url: Any = None) -> str:
    """Resolves project URL, converting placeholder keywords like 'GitHub' into full repository URLs."""
    if not raw_url:
        return ""
    u = str(raw_url).strip()
    if not u:
        return ""

    # Check if raw_url is just a placeholder keyword
    if u.lower() in ("github", "repo", "repository", "code"):
        gh_user = extract_github_username(candidate_gh_url)
        if gh_user:
            slug = slugify_title(project_title)
            return f"https://github.com/{gh_user}/{slug}"
        return "https://github.com"

    if not u.startswith(("http://", "https://")):
        parts = u.split("/")
        if len(parts) == 2 and "." not in parts[0]:
            return f"https://github.com/{u}"
        return f"https://{u}"
    return u


def render_resume_latex(data: ResumeCompileRequest) -> str:
    """Render a full XeLaTeX document string using the exact provided Resume template structure."""

    # 1. Accent Color (Hex without #)
    raw_color = (data.accent_color or "1F6FB2").strip().lstrip("#")
    accent_hex = raw_color if raw_color else "1F6FB2"

    # 2. Header Fields
    raw_name = (data.full_name or "FIRSTNAME LASTNAME").strip().upper()
    full_name = escape_latex(raw_name)
    headline = escape_latex(data.headline or "Professional Headline")
    location = escape_latex(data.location or "")
    phone = escape_latex(data.phone or "")
    email = escape_latex(data.email or "")

    # Build Compact Single-Line Contact Header (including LinkedIn & GitHub icons)
    contact_parts = []
    if location:
        contact_parts.append(location)
    if phone:
        contact_parts.append(phone)
    if email:
        raw_email = data.email.strip()
        escaped_email = escape_latex(raw_email)
        contact_parts.append(
            f"\\href{{mailto:{raw_email}}}{{{escaped_email}}}")
    if data.linkedin_url and data.linkedin_url.strip():
        clean_li = normalize_url(data.linkedin_url)
        contact_parts.append(
            f"\\href{{{clean_li}}}{{\\faLinkedin\\ \\textnormal{{\\small LinkedIn}}}}")
    if data.github_url and data.github_url.strip():
        clean_gh = normalize_url(data.github_url)
        contact_parts.append(
            f"\\href{{{clean_gh}}}{{\\faGithub\\ \\textnormal{{\\small GitHub}}}}")

    contact_block = " \\quad\\textbar\\quad ".join(
        contact_parts) if contact_parts else ""

    # Localization Dictionaries for Section Headers
    lang_code = (getattr(data, "language", "en") or "en").strip().lower()

    match lang_code:
        case "fr":
            sec_titles = {
                "summary": "Résumé Professionnel",
                "objective": "Objectif Professionnel",
                "education": "Formation",
                "experience": "Expériences Professionnelles",
                "projects": "Projets Techniques",
                "skills_and_lang": "Compétences \\& Langues",
                "interpersonal": "Compétences Relationnelles",
                "languages": "Langues",
            }
        case "es":
            sec_titles = {
                "summary": "Resumen Profesional",
                "objective": "Objetivo Profesional",
                "education": "Educación",
                "experience": "Experiencia Profesional",
                "projects": "Proyectos Técnicos",
                "skills_and_lang": "Habilidades y Idiomas",
                "interpersonal": "Habilidades Interpersonales",
                "languages": "Idiomas",
            }
        case _:
            sec_titles = {
                "summary": "Profile Summary",
                "objective": "Career Objective",
                "education": "Education",
                "experience": "Professional Experience",
                "projects": "Academic Projects",
                "skills_and_lang": "Skills \\& Languages",
                "interpersonal": "Interpersonal Skills",
                "languages": "Languages",
            }

    # 3. Profile Summary Section
    summary_tex = ""
    if data.summary and data.summary.strip():
        summary_body = escape_latex(data.summary.strip())
        summary_tex = f"""% ---------------- Profile Summary ----------------
\\section*{{{sec_titles['summary']}}}
\\color{{darktext}}
{summary_body}
"""

    # 3b. Career Objective Section (Optional, auto-generated in ~3 lines)
    objective_tex = ""
    if data.career_objective and data.career_objective.strip():
        obj_body = escape_latex(data.career_objective.strip())
        objective_tex = f"""% ---------------- Career Objective ----------------
\\section*{{{sec_titles['objective']}}}
\\color{{darktext}}
{obj_body}
"""

    # 4. Education Section
    education_tex = ""
    if data.education:
        edu_blocks = []
        has_any_bullets = any(bool(getattr(e, "bullets", None))
                              for e in data.education)

        for edu in data.education:
            deg = escape_latex(edu.degree)
            inst = escape_latex(edu.institution)
            yrs = escape_latex(edu.years)

            b_items = []
            for b in getattr(edu, "bullets", []):
                for sub_b in clean_bullets(b):
                    if sub_b and sub_b.strip():
                        b_items.append(f"\\item {escape_latex(sub_b.strip())}")

            bullets_str = ""
            if b_items:
                b_joined = "\n  ".join(b_items)
                bullets_str = f"""\\begin{{itemize}}
  {b_joined}
\\end{{itemize}}"""

            if deg or inst:
                if has_any_bullets:
                    edu_blocks.append(
                        f"\\cvedu{{{deg}}}{{{inst}}}{{{yrs}}}\n{bullets_str}".strip())
                else:
                    item_str = f"\\item \\textbf{{{deg}}}"
                    if inst:
                        item_str += f" --- {inst}"
                    if yrs:
                        item_str += f" ({yrs})"
                    item_str += "."
                    edu_blocks.append(item_str)

        if edu_blocks:
            if has_any_bullets:
                edus_joined = "\n\n".join(edu_blocks)
                education_tex = f"""% ---------------- Education ----------------
\\section*{{{sec_titles['education']}}}

{edus_joined}
"""
            else:
                items_joined = "\n  ".join(edu_blocks)
                education_tex = f"""% ---------------- Education ----------------
\\section*{{{sec_titles['education']}}}
\\begin{{itemize}}
  {items_joined}
\\end{{itemize}}
"""

    # 5. Professional Experience Section
    experience_tex = ""
    if data.experiences:
        exp_blocks = []
        for exp in data.experiences:
            title = escape_latex(exp.title)
            org = escape_latex(exp.organisation)
            dates = escape_latex(exp.dates)

            b_items = []
            for b in exp.bullets:
                for sub_b in clean_bullets(b):
                    if sub_b and sub_b.strip():
                        b_items.append(f"\\item {escape_latex(sub_b.strip())}")

            bullets_str = ""
            if b_items:
                b_joined = "\n  ".join(b_items)
                bullets_str = f"""\\begin{{itemize}}
  {b_joined}
\\end{{itemize}}"""

            exp_blocks.append(
                f"\\cvjob{{{title}}}{{{org}}}{{{dates}}}\n{bullets_str}")

        if exp_blocks:
            exps_joined = "\n\n".join(exp_blocks)
            experience_tex = f"""% ---------------- Professional Experience ----------------
\\section*{{{sec_titles['experience']}}}

{exps_joined}
"""

    # 6. Academic Projects Section
    projects_tex = ""
    if data.projects:
        proj_blocks = []
        for proj in data.projects:
            title = escape_latex(proj.title)
            stack = escape_latex(proj.stack)
            raw_url = (getattr(proj, "url", None) or "").strip()

            link_tex = ""
            if raw_url:
                href_url = resolve_project_url(
                    raw_url, proj.title, getattr(data, "github_url", None))
                if href_url:
                    if "github" in href_url.lower():
                        link_tex = f"\\href{{{href_url}}}{{\\small\\faGithub\\ \\textnormal{{\\small Repository}}}}"
                    else:
                        link_tex = f"\\href{{{href_url}}}{{\\small\\faExternalLink*\\ \\textnormal{{\\small Link}}}}"

            b_items = []
            for b in proj.bullets:
                for sub_b in clean_bullets(b):
                    if sub_b and sub_b.strip():
                        b_items.append(f"\\item {escape_latex(sub_b.strip())}")

            bullets_str = ""
            if b_items:
                b_joined = "\n  ".join(b_items)
                bullets_str = f"""\\begin{{itemize}}
  {b_joined}
\\end{{itemize}}"""

            proj_blocks.append(
                f"\\cvproject{{{title}}}{{{stack}}}{{{link_tex}}}\n{bullets_str}")

        if proj_blocks:
            projs_joined = "\n\n".join(proj_blocks)
            projects_tex = f"""% ---------------- Academic Projects ----------------
\\section*{{{sec_titles['projects']}}}

{projs_joined}
"""

    # 7. Unified Skills & Languages Section (Grouped by Category)
    skills_and_lang_tex = ""

    category_groups: dict[str, list[str]] = {}
    db_skill_to_cat = {}
    try:
        from sqlmodel import Session, select
        from src.core.database import engine
        from src.modules.profile.models import Skill
        with Session(engine) as session:
            db_skills = session.exec(select(Skill)).all()
            for dbs in db_skills:
                if dbs.category:
                    db_skill_to_cat[dbs.name.strip().lower()
                                    ] = dbs.category.strip()
    except Exception:
        pass

    if data.technical_skills:
        for s_item in data.technical_skills:
            if not s_item or not s_item.strip():
                continue
            s_str = s_item.strip()
            if ": " in s_str:
                cat, skill_name = s_str.split(": ", 1)
                cat = cat.strip()
                skill_name = skill_name.strip()
            else:
                cat = db_skill_to_cat.get(s_str.lower(), "Technical Skills")
                skill_name = s_str

            category_groups.setdefault(cat, []).append(
                escape_latex(skill_name))

    lang_item_str = ""
    if data.languages:
        lang_formatted = []
        for l in data.languages:
            lang_name = escape_latex(l.language)
            prof = escape_latex(l.proficiency)
            if lang_name and prof:
                lang_formatted.append(f"{lang_name} --- {prof}")
            elif lang_name:
                lang_formatted.append(f"{lang_name}")
        if lang_formatted:
            l_str = ", ".join(lang_formatted)
            lang_item_str = f"\\item \\textbf{{{sec_titles['languages']}:}} {l_str}."

    skill_items = []
    soft_cat_key = sec_titles['interpersonal']
    soft_skills_list = []

    soft_keys_to_pop = [k for k in list(category_groups.keys()) if any(
        sub in k.lower() for sub in ["soft", "interpersonal", "relationn", "interpersonal"])]
    for k in soft_keys_to_pop:
        soft_skills_list.extend(category_groups.pop(k, []))

    for cat_name, skill_list in category_groups.items():
        if skill_list:
            joined_skills = ", ".join(skill_list)
            skill_items.append(
                f"\\item \\textbf{{{escape_latex(cat_name)}:}} {joined_skills}.")

    if lang_item_str:
        skill_items.append(lang_item_str)

    if skill_items:
        items_joined = "\n  ".join(skill_items)
        skills_and_lang_tex = f"""% ---------------- Skills & Languages ----------------
\\section*{{{sec_titles['skills_and_lang']}}}
\\begin{{itemize}}
  {items_joined}
\\end{{itemize}}
"""

    # 8. Soft Skills Section
    soft_skills_tex = ""
    if data.interpersonal_skills:
        interpersonal = [escape_latex(
            s.strip()) for s in data.interpersonal_skills if s and s.strip()]
        if interpersonal:
            soft_skills_list.extend(interpersonal)

    seen = set()
    dedup_soft = []
    for s in soft_skills_list:
        if s.lower() not in seen:
            seen.add(s.lower())
            dedup_soft.append(s)

    if dedup_soft:
        joined_soft = ", ".join(dedup_soft)
        soft_skills_tex = f"""% ---------------- Soft Skills ----------------
\\section*{{{soft_cat_key}}}
\\color{{darktext}}
{joined_soft}.
"""

    # 10. Assemble Full XeLaTeX Document
    latex_code = f"""\\documentclass[10pt,a4paper]{{article}}

% ---------- Packages ----------
\\usepackage[margin=0.8in]{{geometry}}
\\usepackage{{fontspec}}
\\defaultfontfeatures{{Ligatures=TeX}}
\\IfFontExistsTF{{Times New Roman}}{{
  \\setmainfont{{Times New Roman}}
}}{{
  \\IfFontExistsTF{{TeX Gyre Termes}}{{
    \\setmainfont{{TeX Gyre Termes}}
  }}{{
    \\setmainfont{{Liberation Serif}}
  }}
}}
\\usepackage{{xcolor}}
\\usepackage{{titlesec}}
\\usepackage{{enumitem}}
\\usepackage{{tabularx}}
\\usepackage{{hyperref}}
\\usepackage{{paracol}}
\\usepackage{{graphicx}}
\\usepackage{{fontawesome5}}

% ---------- Colors ----------
\\definecolor{{accent}}{{HTML}}{{{accent_hex}}}
\\definecolor{{darktext}}{{HTML}}{{2B2B2B}}
\\definecolor{{greytext}}{{HTML}}{{595959}}

% ---------- Hyperlinks ----------
\\hypersetup{{
    colorlinks=true,
    linkcolor=accent,
    urlcolor=accent,
    pdfnewwindow=true
}}

% ---------- Section formatting ----------
\\titleformat{{\\section}}
  {{\\large\\bfseries\\color{{accent}}}}
  {{}}{{0em}}{{}}
  [{{\\color{{accent}}\\titlerule[1pt]}}]
\\titlespacing{{\\section}}{{0pt}}{{8pt}}{{4pt}}

% ---------- Subsection formatting ----------
\\titleformat{{\\subsection}}
  {{\\bfseries\\color{{darktext}}}}
  {{}}{{0em}}{{}}
  [\\vspace{{-4pt}}]
\\titlespacing{{\\subsection}}{{0pt}}{{6pt}}{{3pt}}

% ---------- Subsubsection formatting ----------
\\titleformat{{\\subsubsection}}
  {{\\normalsize\\bfseries\\color{{darktext}}}}
  {{}}{{0em}}{{}}
\\titlespacing{{\\subsubsection}}{{0pt}}{{4pt}}{{2pt}}

% ---------- List formatting ----------
\\setlist[itemize]{{
  leftmargin=1.1em,
  topsep=2pt,
  itemsep=2pt,
  parsep=0pt,
  label=\\textcolor{{accent}}{{\\small\\textbullet}}
}}

\\setlength{{\\parindent}}{{0pt}}
\\pagestyle{{empty}}

% ---------- Helper commands ----------
% \\cvjob{{Title}}{{Organisation}}{{Dates}}
\\newcommand{{\\cvjob}}[3]{{%
  \\subsection*{{#1}}%
  \\noindent{{\\color{{greytext}}\\textit{{#2}}}} \\hfill {{\\color{{greytext}}\\small #3}}\\par\\vspace{{2pt}}%
}}

% \\cvedu{{Degree}}{{Institution}}{{Dates}}
\\newcommand{{\\cvedu}}[3]{{%
  \\subsection*{{#1}}%
  \\noindent{{\\color{{greytext}}\\textit{{#2}}}} \\hfill {{\\color{{greytext}}\\small #3}}\\par\\vspace{{2pt}}%
}}

% \\cvproject{{Title}}{{Stack}}{{Link}}
\\newcommand{{\\cvproject}}[3]{{%
  \\subsubsection*{{#1 \\ifx&#3&\\else\\hfill #3\\fi}}%
  \\ifx&#2&\\else\\noindent{{\\color{{accent}}\\small\\textit{{Stack:}}}} {{\\color{{greytext}}\\small\\textit{{#2}}}}\\par\\vspace{{2pt}}\\fi%
}}

\\begin{{document}}

% ---------------- Header ----------------
\\begin{{center}}
  {{\\Huge\\bfseries\\color{{darktext}} {full_name}}}\\\\[3pt]
  {{\\color{{accent}}\\bfseries\\large {headline}}}\\\\[3pt]
  {{\\small\\color{{greytext}} {contact_block}}}
\\end{{center}}
\\vspace{{-8pt}}
\\textcolor{{accent}}{{\\rule{{\\linewidth}}{{0.8pt}}}}
\\vspace{{0pt}}

{objective_tex}
{summary_tex}
{experience_tex}
{education_tex}
{projects_tex}
{skills_and_lang_tex}
{soft_skills_tex}

\\end{{document}}
"""
    return latex_code


# Alias for backward compatibility
render_cv_latex = render_resume_latex
