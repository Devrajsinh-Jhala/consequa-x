"""Build explicitly allowlisted public docs and deterministic synthetic examples.

This authoring tool has no runtime dependencies. It never scans the repository
for publication candidates: every input and output is named below. Run it again
after editing the public community documentation or the two example modules.
"""

import argparse
from html import escape
import json
from pathlib import Path
import re
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_REPOSITORY = "https://github.com/Devrajsinh-Jhala/consequa-x-community"
SITE = "https://consequa-x.brawny-deer-5658.chatgpt.site"
EXAMPLES = ("artifact_delivery.py", "report_quickstart.py")


def code(source: str, language: str = "console") -> str:
    return (f'<div class="code-block"><span class="code-label">{escape(language)}</span>'
            f'<pre><code>{escape(source.strip())}</code></pre></div>')


def inline(text: str) -> str:
    """Render this project's small, trusted Markdown subset with escaped values."""
    token = re.compile(r"(`[^`]+`|\[[^\]]+\]\([^\s)]+\))")
    output = []
    for part in token.split(text):
        if part.startswith("`") and part.endswith("`"):
            output.append(f"<code>{escape(part[1:-1])}</code>")
        elif (match := re.fullmatch(r"\[([^\]]+)\]\(([^\s)]+)\)", part)):
            label, target = match.groups()
            if not (target.startswith(("https://", "http://", "#"))
                    or re.fullmatch(r"[A-Za-z0-9_./-]+", target)):
                raise ValueError("Unsupported URL in public Markdown")
            target = {"QUICKSTART.md": "docs.html", "SECURITY.md": "security.html",
                      "CHANGELOG.md": "changelog.html"}.get(target, target)
            output.append(f'<a href="{escape(target, quote=True)}">{escape(label)}</a>')
        else:
            output.append(escape(part))
    return "".join(output)


def markdown_body(source: str) -> str:
    """Render authored paragraphs, headings and bullets; reject richer syntax."""
    sections = []
    paragraph = []
    items = []

    def flush():
        if paragraph:
            sections.append("<p>" + inline(" ".join(paragraph)) + "</p>")
            paragraph.clear()
        if items:
            sections.append("<ul>" + "".join(f"<li>{inline(item)}</li>" for item in items) + "</ul>")
            items.clear()

    for line in source.splitlines():
        if line.startswith("# "):
            flush()  # The page shell already contains its only h1.
        elif line.startswith("## "):
            flush()
            sections.append(f"<h2>{inline(line[3:])}</h2>")
        elif line.startswith("- "):
            if paragraph:
                flush()
            items.append(line[2:])
        elif not line.strip():
            flush()
        elif line.startswith("```") or line.startswith("### "):
            raise ValueError("Extend the deliberately small renderer before using this Markdown")
        elif items:
            items[-1] += " " + line.strip()
        else:
            paragraph.append(line.strip())
    flush()
    return "\n".join(sections)


def page(title: str, description: str, body: str, active: str) -> str:
    links = (("docs", "Documentation"), ("support", "Support"),
             ("security", "Security"), ("changelog", "Changelog"))
    navigation = "".join(
        f'<a href="{name}.html"' + (' aria-current="page"' if name == active else "")
        + f">{label}</a>" for name, label in links)
    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#f6f3e9">
  <meta name="description" content="{escape(description, quote=True)}">
  <title>{escape(title)} — Consequa-X</title>
  <link rel="icon" type="image/svg+xml" href="favicon.svg">
  <link rel="stylesheet" href="styles.css">
  <link rel="stylesheet" href="docs.css">
</head>
<body class="docs-site">
  <a class="skip-link" href="#main">Skip to content</a>
  <header class="docs-header section-shell">
    <a class="wordmark" href="index.html" aria-label="Consequa-X home"><span>consequa<span class="brand-x">×</span></span></a>
    <nav aria-label="Main navigation">{navigation}<a class="package-link" href="https://pypi.org/project/consequa-x/">Python package <span aria-hidden="true">↗</span></a></nav>
  </header>
  {body}
  <footer class="docs-footer section-shell"><a href="index.html">Consequa-X</a><p>Evidence-aware explanation of consequential agent actions.</p><nav aria-label="Footer">{navigation}<a href="{PUBLIC_REPOSITORY}">Public community <span aria-hidden="true">↗</span></a></nav><small>© 2026 Devrajsinh Jhala · MIT licensed package</small></footer>
</body>
</html>
'''


def documentation(*, published: bool = False) -> str:
    release_status = (
        '<strong>Version 1.1.0 is available.</strong><p>Install the verified '
        '<a href="https://pypi.org/project/consequa-x/1.1.0/">1.1.0 release from PyPI</a>. '
        '<a href="changelog.html">Read release notes and the actual platform checks.</a></p>'
        if published else
        '<strong>1.1 is being prepared.</strong><p>The report command and API below belong '
        'to 1.1. Check the <a href="https://pypi.org/project/consequa-x/">published version '
        'on PyPI</a> before installing a pinned release. <a href="changelog.html">Read '
        'release status and validated platforms.</a></p>'
    )
    installation = code("python -m pip install consequa-x==1.1.0\nconsequa-x --version")
    run_example = code("python report_quickstart.py --output my-first-capture")
    render = code("consequa-x report my-first-capture/verified.json --output another-report.html")
    detailed = code("consequa-x report my-first-capture/verified.json "
                    "--output detailed-report.html --include-details")
    api = code('''from pathlib import Path
from consequa_x import Trace, render_report

trace = Trace.from_json(Path("trace.json").read_text(encoding="utf-8"))
document = render_report(trace)  # Minimal disclosure by default.
with Path("report.html").open("x", encoding="utf-8") as destination:
    destination.write(document)''', "python")
    demo = code("consequa-x demo --output sample-run\nconsequa-x report sample-run/traces/episode_00.json --output sample-report.html")
    return f'''<div class="docs-layout section-shell">
  <aside class="docs-sidebar" aria-label="On this page"><span class="eyebrow">THE FIELD GUIDE</span><nav><a href="#quickstart">Five-minute quickstart</a><a href="#read-the-evidence">Read the evidence</a><a href="#reports">Offline reports</a><a href="#privacy">Disclosure &amp; sharing</a><a href="#python-api">Python API</a><a href="#integration">Connect your application</a><a href="#boundaries">Trust boundaries</a><a href="#help">Get help</a></nav><a class="sidebar-download" href="quickstart.zip" download>Download the examples <span aria-hidden="true">↓</span><small>Two Python files · synthetic data · MIT</small></a></aside>
  <main class="docs-content" id="main">
    <div class="docs-hero"><span class="eyebrow">DOCUMENTATION / VERSION 1.1</span><h1>From a trace<br>to a <em>clear account.</em></h1><p class="docs-lead">Create your first offline report, read what the evidence supports, and connect a verifier for your own application.</p><div class="docs-prerequisites"><span>Python 3.11 or 3.12</span><span>No API key</span><span>No required runtime dependencies</span></div></div>
    <div class="docs-callout release-callout">{release_status}</div>
    <section id="quickstart"><span class="eyebrow">01 / YOUR FIRST FIVE MINUTES</span><h2>Make the evidence visible.</h2><p>This example performs no delivery or payment. It reads synthetic artifact-store fixtures using the public package APIs.</p>
      <div class="guide-step"><span class="guide-step-number" aria-hidden="true">1</span><div><h3>Install the package.</h3><p>Use a Python 3.11 or 3.12 environment.</p>{installation}</div></div>
      <div class="guide-step"><span class="guide-step-number" aria-hidden="true">2</span><div><h3>Get the two example files.</h3><p><a href="quickstart.zip" download>Download the quickstart archive</a> and extract it. Keep <code>artifact_delivery.py</code> and <code>report_quickstart.py</code> in the same folder. The archive includes its README and MIT license.</p><p class="small-text">Prefer reading first? <a href="examples/artifact_delivery.py">View the artifact adapter</a> or <a href="examples/report_quickstart.py">view the report example</a>.</p></div></div>
      <div class="guide-step"><span class="guide-step-number" aria-hidden="true">3</span><div><h3>Generate three captured examples.</h3><p>Open a terminal in the extracted folder, then use a new output directory:</p>{run_example}<p>Open <code>my-first-capture/verified.html</code> in your browser. Compare <code>unknown.html</code> and <code>other-actor.html</code>. Each report has a separate original JSON trace.</p></div></div>
      <div class="guide-step"><span class="guide-step-number" aria-hidden="true">4</span><div><h3>Render a saved trace again.</h3>{render}<p>The destination must be new. If the console command is not on your PATH, replace <code>consequa-x</code> with <code>python -m consequa_x</code>.</p></div></div>
    </section>
    <section id="read-the-evidence"><span class="eyebrow">02 / THREE DISTINCT CONCLUSIONS</span><h2>State and origin stay separate.</h2><p>A timeout describes a tool response. It cannot by itself determine the requested outcome.</p><div class="docs-table-wrap" tabindex="0" role="region" aria-label="Synthetic example outcomes"><table><caption>What the artifact-delivery fixtures establish</caption><thead><tr><th scope="col">Example</th><th scope="col">Verified state</th><th scope="col">Effect origin</th><th scope="col">Interpretation</th></tr></thead><tbody><tr><th scope="row">Verified</th><td><span class="state-chip">satisfied</span></td><td>confirmed</td><td>The readback covers a matching delivery and links it to the captured action.</td></tr><tr><th scope="row">Unknown</th><td><span class="state-chip neutral">unknown</span></td><td>unknown</td><td>Unavailable readback does not support a success or failure conclusion.</td></tr><tr><th scope="row">Other actor</th><td><span class="state-chip">satisfied</span></td><td>other_actor</td><td>The requested state exists, but another actor produced the effect.</td></tr></tbody></table></div><p>The example hashes the bytes read from its fixture independently of the requested digest. Its application-owned <code>ArtifactVerifier</code> evaluates the contract; its <code>ArtifactTargetMatcher</code> can qualify matching through the separate explanation API.</p></section>
    <section id="reports"><span class="eyebrow">03 / ONE FILE, NO SERVER</span><h2>Inspect an offline report.</h2><p>A report is self-contained HTML: no JavaScript, external fonts, remote assets or network requests. It shows structural contract bounds, the timeline, responses, the reported assessment, readbacks, recorded state and origin, and an evidence graph.</p><p>Successive observations retain separate witnesses. Order, dependency, observation and origin links carry distinct labels; a graph edge does not establish counterfactual necessity.</p><div class="docs-callout"><strong>Rendering is a read-only presentation.</strong><p>It performs no verifier call, target matching, application action or replay. It presents captured verification and does not independently establish source truth. Assessment alignment remains unassessable in this renderer.</p></div><p>To start with the package’s bundled refund fixtures instead:</p>{demo}<p>Input traces are validated before the output is created. The CLI preserves the source and refuses an existing output file, including the input itself.</p></section>
    <section id="privacy"><span class="eyebrow">04 / CHOOSE WHAT YOU DISCLOSE</span><h2>Share a smaller surface.</h2><p>Default reports use local aliases and omit arbitrary captured values: payloads, rationales, source names, raw identifiers, paths, digests, predicates and error messages. Omitted fields are absent from the HTML, including attributes, comments and embedded data.</p><p>Timing, counts, enum statuses and relationships remain visible. Review these before sharing. This is deliberate field omission, not universal anonymization or personal-data detection.</p><details class="docs-details"><summary>Inspect all captured fields locally</summary><div><p><code>--include-details</code> explicitly includes the entire trace as escaped, inert text. This can expose sensitive information. Keep a detailed report private whenever its trace is private.</p>{detailed}</div></details><p>Retain the original trace and source evidence separately. A reduced presentation is not a substitute for the verification record. For a public bug report, provide a synthetic reproduction.</p></section>
    <section id="python-api"><span class="eyebrow">05 / COMPOSE WITH PYTHON</span><h2>Render without a service.</h2><p><code>render_report</code> returns HTML and writes no files. It accepts a validated <code>Trace</code> and an optional boolean <code>include_details</code> argument, which defaults to <code>False</code>.</p>{api}<p>The portable schema remains <code>0.1</code>. Package version and wire-schema version are separate; the version-1 core remains compatible.</p></section>
    <section id="integration"><span class="eyebrow">06 / YOUR DOMAIN, EXPLICITLY</span><h2>Connect your application.</h2><ol class="integration-list"><li><strong>Declare the contract before the action.</strong> Define matching state, deadline, persistence horizon and required count.</li><li><strong>Capture the action history.</strong> Retain dispatches, responses and the agent’s reported assessment.</li><li><strong>Obtain independent readback.</strong> Capture source, scope, completeness, watermark and effect-origin metadata from a read-only adapter.</li><li><strong>Implement your verifier.</strong> Interpret that domain’s evidence through the explicit <code>Verifier</code> interface.</li><li><strong>Qualify alignment when appropriate.</strong> Supply an application <code>TargetMatcher</code> to <code>explain(trace, target_matcher=...)</code>.</li></ol><p>The downloadable <a href="examples/artifact_delivery.py">artifact-delivery adapter</a> demonstrates both interfaces using only public APIs. Replace its fixture with an independently authenticated read adapter; do not copy the requested state into the readback.</p></section>
    <section id="boundaries"><span class="eyebrow">07 / WHAT THE RECORD CAN SUPPORT</span><h2>Keep uncertainty intact.</h2><p>Schema validation checks structure and identity linkage. Your application establishes source authentication, provider guarantees and the truth of supplied metadata. A report cannot supply those guarantees.</p><p><code>unknown</code>, <code>other_actor</code> and unassessable conclusions remain distinct. Missing readback is not a successful verification. Research replay interfaces carry their own assumptions; the package does not claim baseline superiority or improved live-model accuracy.</p><p>Platform validation is recorded for environments actually checked. A pure-Python wheel alone does not establish compatibility with every platform.</p></section>
    <section class="docs-next" id="help"><span class="eyebrow">KEEP BUILDING</span><h2>A clear next step.</h2><p><a href="support.html">Ask a question or report a reproducible bug</a>. Use the <a href="security.html">private security route</a> for vulnerabilities, and <a href="changelog.html">release notes</a> for publication status and platform checks.</p><a class="text-link" href="quickstart.zip" download>Download the synthetic quickstart <span aria-hidden="true">↓</span></a></section>
  </main>
</div>'''


def article(title: str, subtitle: str, body: str, label: str) -> str:
    return f'''<main class="docs-article section-shell" id="main"><div class="article-intro"><span class="eyebrow">{escape(label)}</span><h1>{title}</h1><p class="docs-lead">{subtitle}</p></div><div class="article-body">{body}</div><div class="article-return"><a class="text-link" href="docs.html">Back to the field guide <span aria-hidden="true">↗</span></a></div></main>'''


CSS = """/* Documentation: warm paper, ink and teal. No remote assets or scripts. */
.docs-header{min-height:99px;display:flex;align-items:center;justify-content:space-between;gap:28px;border-bottom:1px solid var(--line)}.docs-header>nav{display:flex;align-items:center;gap:25px;flex-wrap:wrap}.docs-header nav a{font-size:12px;text-decoration:none;padding:10px 0}.docs-header nav a[aria-current=page]{color:var(--teal);text-decoration:underline;text-underline-offset:7px}.docs-header .package-link{padding:10px 14px;border:1px solid var(--ink);margin-left:8px}.docs-header .package-link span{margin-left:12px}.docs-layout{display:grid;grid-template-columns:210px minmax(0,1fr);gap:clamp(40px,6vw,90px);padding-top:58px;padding-bottom:95px;max-width:1320px}.docs-sidebar{position:sticky;top:40px;align-self:start;padding-top:8px}.docs-sidebar .eyebrow{display:block;color:var(--teal);font-size:9px;letter-spacing:1.2px;margin-bottom:24px}.docs-sidebar nav{display:flex;flex-direction:column;align-items:flex-start;gap:17px}.docs-sidebar nav a{font-size:12px;text-decoration:none;line-height:1.5}.docs-sidebar nav a:hover{color:var(--teal);text-decoration:underline}.sidebar-download{display:block;padding-top:23px;margin-top:28px;border-top:1px solid var(--line);font-size:11px;font-weight:600;text-decoration:none;line-height:1.7}.sidebar-download>span{float:right;color:var(--teal);font-size:17px}.sidebar-download small{display:block;font-size:9px;font-weight:400;color:var(--muted);margin-top:6px;line-height:1.8}.docs-content{max-width:840px;min-width:0}.docs-hero .eyebrow,.article-intro .eyebrow{color:var(--teal);display:block;margin-bottom:20px}.docs-hero h1,.article-intro h1{font-size:clamp(52px,5.2vw,76px);line-height:1.04;letter-spacing:-.055em}.docs-lead{font-size:16px;line-height:1.85;color:#52645b;max-width:640px;margin-top:23px}.docs-prerequisites{display:flex;flex-wrap:wrap;gap:12px 20px;font-family:var(--mono);font-size:9px;color:var(--muted);margin-top:23px}.docs-prerequisites span+span::before{content:'·';padding-right:18px;color:var(--teal)}.docs-callout{border-left:2px solid var(--teal);background:#eaf0df;padding:20px 23px;margin-top:25px;margin-bottom:25px}.docs-callout strong{font-size:13px;line-height:1.6;font-weight:600}.docs-callout p{font-size:12px!important;margin-top:7px!important;color:#44594e!important}.release-callout{margin-top:35px;background:transparent;border:1px solid var(--line);border-left:2px solid var(--teal)}.docs-content section{scroll-margin-top:30px;border-top:1px solid var(--line);padding-top:35px;margin-top:45px}.docs-content section>.eyebrow{font-size:9px;display:block;color:var(--teal);margin-bottom:15px}.docs-content h2,.article-body h2{font-size:38px;letter-spacing:-.035em;line-height:1.12;margin-bottom:17px}.docs-content h3{font-family:var(--serif);font-size:24px;font-weight:400;letter-spacing:-.4px;line-height:1.3}.docs-content p,.article-body p,.article-body li{font-size:13px;line-height:1.9;color:#52645b;margin-top:14px}.docs-content p a,.article-body a{color:var(--teal-dark);font-weight:500}.docs-content p code,.docs-content li code,.article-body code{background:#e8ecdf;padding:2px 4px;color:var(--ink);overflow-wrap:anywhere;font-size:.9em}.guide-step{display:grid;grid-template-columns:26px minmax(0,1fr);gap:15px;margin-top:27px}.guide-step-number{width:25px;height:25px;border:1px solid #a7ba9f;border-radius:50%;display:grid;place-items:center;font-size:11px;color:var(--teal);margin-top:3px}.guide-step p{margin-top:8px}.small-text{font-size:11px!important}.code-block{background:var(--ink);color:#f3f3e7;margin-top:17px;margin-bottom:17px;min-width:0;position:relative;border:1px solid #142823}.code-label{display:block;font-family:var(--mono);font-size:8px;text-transform:uppercase;letter-spacing:1.5px;color:#c1d5bd;padding:13px 20px 0}.code-block pre{padding:12px 20px 19px;overflow:auto;font-family:var(--mono);font-size:11px;line-height:1.8;margin:0;tab-size:4}.code-block code{font-size:inherit;line-height:inherit;white-space:pre}.docs-table-wrap{overflow:auto;margin-top:24px;border:1px solid var(--line)}.docs-table-wrap table{border-collapse:collapse;text-align:left;width:100%;min-width:570px}.docs-table-wrap caption{text-align:left;font-size:10px;padding:14px 16px;color:var(--muted);font-family:var(--mono);line-height:1.7;border-bottom:1px solid var(--line)}.docs-table-wrap th,.docs-table-wrap td{padding:14px 16px;vertical-align:top;border-top:1px solid var(--line);font-size:11px;line-height:1.7}.docs-table-wrap thead th{background:#ebeedf;font-size:10px;font-weight:600;border-top:0}.docs-table-wrap tbody th{font-weight:500;white-space:nowrap}.docs-table-wrap td:last-child{color:#52645b;min-width:200px}.state-chip{display:inline-block;background:#e3edd7;border:1px solid #bad1ae;font-family:var(--mono);font-size:9px;color:var(--teal-dark);padding:1px 6px;white-space:nowrap}.state-chip.neutral{background:#e9e9df;color:#5c635b;border-color:#ccd0bf}.docs-details{border:1px solid #b7c6b0;margin-top:24px;background:#edf0e3}.docs-details summary{padding:17px 20px;cursor:pointer;font-size:12px;line-height:1.7;font-weight:600}.docs-details>div{padding:0 20px 5px;border-top:1px solid var(--line)}.integration-list{padding-left:20px;margin-top:23px}.integration-list li{padding-left:7px;margin-bottom:15px;color:#52645b;font-size:13px;line-height:1.9}.integration-list strong{color:var(--ink)}.docs-next{padding-bottom:10px}.docs-next .text-link{margin-top:18px}.docs-footer{padding-top:35px;padding-bottom:32px;border-top:1px solid var(--line);display:flex;flex-wrap:wrap;align-items:center;gap:20px 27px}.docs-footer>a{font-family:var(--serif);font-size:25px;text-decoration:none;letter-spacing:-.7px}.docs-footer>p{font-size:10px;max-width:220px;color:var(--muted);line-height:1.7}.docs-footer>nav{margin-left:auto;display:flex;flex-wrap:wrap;gap:19px}.docs-footer nav a{font-size:10px;text-decoration:none}.docs-footer nav a:hover{text-decoration:underline}.docs-footer small{display:block;flex-basis:100%;font-size:9px;color:var(--muted);margin-top:5px}.docs-article{max-width:1000px;padding-top:66px;padding-bottom:80px}.article-intro{padding-bottom:34px;border-bottom:1px solid var(--line)}.article-body{max-width:750px}.article-body h2{margin-top:37px;font-size:31px}.article-body ul{padding-left:21px;margin-top:20px}.article-body li{padding-left:4px;margin-top:8px}.article-body .support-grid{display:grid;grid-template-columns:1fr 1fr;gap:25px;margin-top:30px}.support-path{padding-top:20px;border-top:1px solid var(--line)}.support-path h2{margin-top:0;font-size:27px}.support-path .text-link{margin-top:15px;font-size:12px;gap:13px}.article-return{margin-top:42px;padding-top:23px;border-top:1px solid var(--line)}.article-return .text-link{font-size:12px}.contact-checklist{padding:20px 23px;background:#eaf0df;border-left:2px solid var(--teal);margin-top:28px}.contact-checklist h2{margin-top:0;font-size:25px}.contact-checklist ul{margin-bottom:0}.docs-content .guide-step .code-block{margin-bottom:0}
@media(min-width:1500px){.docs-layout{padding-inline:60px}}
@media(max-width:1000px){.docs-layout{gap:38px;grid-template-columns:180px minmax(0,1fr)}.docs-header>nav{gap:18px}.docs-header nav a{font-size:11px}.docs-content h2{font-size:34px}.docs-header .package-link{margin-left:0}.docs-footer>nav{margin-left:0;flex-basis:100%}}
@media(max-width:730px){.docs-header{padding-top:21px;padding-bottom:19px;min-height:0;display:block}.docs-header>nav{gap:9px 18px;margin-top:21px}.docs-header nav a{font-size:11px;padding:5px 0}.docs-header .package-link{border:0;padding:5px 0}.docs-header .package-link span{margin-left:3px}.docs-layout{display:block;padding-top:27px;padding-bottom:55px}.docs-sidebar{position:static;padding:0 0 24px;margin-bottom:30px;border-bottom:1px solid var(--line)}.docs-sidebar .eyebrow{margin-bottom:13px}.docs-sidebar nav{display:flex;flex-direction:row;gap:10px 17px;flex-wrap:wrap}.docs-sidebar nav a{font-size:10px}.sidebar-download{border:0;margin-top:14px;padding-top:0;font-size:10px;display:inline-block}.sidebar-download>span{float:none;margin-left:15px}.sidebar-download small{display:none}.docs-hero h1,.article-intro h1{font-size:53px}.docs-hero .eyebrow,.article-intro .eyebrow{font-size:9px;margin-bottom:17px}.docs-lead{font-size:14px;margin-top:18px}.docs-prerequisites{font-size:8px;gap:10px 14px;line-height:1.8;margin-top:18px}.docs-prerequisites span+span::before{padding-right:10px}.docs-callout{padding:17px 18px}.docs-callout p{font-size:11px!important}.docs-content section{padding-top:28px;margin-top:34px}.docs-content h2{font-size:32px}.docs-content p,.article-body p,.article-body li{font-size:12px}.docs-content h3{font-size:23px}.guide-step{gap:11px;grid-template-columns:23px minmax(0,1fr);margin-top:23px}.guide-step-number{width:23px;height:23px;font-size:10px}.code-label{padding-inline:15px;font-size:7px}.code-block pre{padding-inline:15px;font-size:10px}.docs-table-wrap caption{font-size:9px}.integration-list li{font-size:12px}.docs-details summary{padding:15px;font-size:11px}.docs-details>div{padding-inline:15px}.docs-article{padding-top:40px;padding-bottom:55px}.article-body h2{font-size:28px}.article-body .support-grid{grid-template-columns:1fr;gap:25px}.docs-footer{gap:17px 23px;padding-top:27px;padding-bottom:27px}.docs-footer>nav{gap:16px}.docs-footer nav a{font-size:9px}.docs-footer small{font-size:8px}.contact-checklist{padding:18px}.contact-checklist h2{font-size:23px}}
@media(max-width:380px){.docs-header>nav{gap:9px 14px}.docs-header nav a{font-size:10px}.docs-hero h1,.article-intro h1{font-size:46px}.docs-sidebar nav{gap:9px 14px}.docs-prerequisites{gap:8px 12px}.docs-prerequisites span+span::before{padding-right:8px}.docs-content h2{font-size:30px}.guide-step{gap:9px}.code-block pre{font-size:9px;padding-inline:12px}.code-label{padding-inline:12px}}
@media print{.docs-header,.docs-sidebar,.docs-footer,.article-return{display:none}.docs-layout,.docs-article{display:block;padding:0;max-width:none}.docs-content,.article-body{max-width:none}.docs-hero h1,.article-intro h1{font-size:42px}.code-block{break-inside:avoid;background:white;color:black;border-color:#bbb}.code-label{color:#333}.code-block pre{white-space:pre-wrap;overflow-wrap:anywhere}.docs-content section{break-inside:auto}.docs-callout{background:white}.docs-details>div{display:block}.docs-table-wrap{overflow:visible}.docs-table-wrap table{min-width:0}.docs-content h2{font-size:28px}.docs-site{background:white}}
"""


def platform_table(receipt_paths: list[Path]) -> str:
    """Publish only three bounded platform fields from successful 1.1 receipts.

    No executable paths, account names, complete receipt payloads or source
    locations are copied. Passing a receipt does not publish that JSON file.
    """
    rows = []
    wheel_hashes = set()
    for path in receipt_paths:
        record = json.loads(path.read_text(encoding="utf-8"))
        if (record.get("passed") is not True
                or record.get("isolated_imports") is not True
                or record.get("install", {}).get("version") != "1.1.0"):
            raise ValueError("Only successful isolated 1.1.0 installation receipts can be listed")
        digest = record.get("wheel", {}).get("sha256", "")
        if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError("Platform receipt must identify the checked wheel")
        wheel_hashes.add(digest)
        system, python, kernel = (record.get(key) for key in
                                  ("system", "python", "kernel_release"))
        if system not in {"Windows", "Linux", "Darwin"}:
            raise ValueError("Unsupported platform system in receipt")
        if not isinstance(python, str) or not re.fullmatch(r"3\.\d+\.\d+", python):
            raise ValueError("Platform receipt must contain an explicit Python version")
        if (not isinstance(kernel, str)
                or not re.fullmatch(r"[A-Za-z0-9 ._+()/#:-]{1,160}", kernel)):
            raise ValueError("Platform receipt has an unsupported kernel release")
        row = (system, python, kernel)
        if row not in rows:
            rows.append(row)
    if len(wheel_hashes) > 1:
        raise ValueError("Platform receipts must check the same reviewed wheel")
    if not rows:
        return ""
    rendered_rows = "".join("<tr>" + "".join(f"<td>{escape(value)}</td>" for value in row)
                            + "</tr>" for row in rows)
    return ('<h2>Installed 1.1.0 artifact checks</h2><p>These environments completed the '
            'same reviewed wheel’s isolated installation and offline integration checks. '
            'The table lists actual environments; it does not imply coverage of every '
            'Python or operating-system version.</p><div class="docs-table-wrap" '
            'tabindex="0" role="region" aria-label="Validated installation environments">'
            '<table><caption>Successful installed-wheel checks</caption><thead><tr>'
            '<th scope="col">System</th><th scope="col">Python</th>'
            '<th scope="col">Kernel release</th></tr></thead><tbody>'
            + rendered_rows + '</tbody></table></div>')


def build(*, published: bool = False, platform_receipts: list[Path] | None = None) -> None:
    # Only these public files can reach the website and example archive.
    community = ROOT / "community"
    dist = ROOT / "website" / "dist"
    source_examples = {name: (ROOT / "examples" / name).read_bytes() for name in EXAMPLES}
    quickstart = (community / "QUICKSTART.md").read_bytes()
    license_bytes = (community / "LICENSE").read_bytes()
    security = (community / "SECURITY.md").read_text(encoding="utf-8")
    changelog = (community / "CHANGELOG.md").read_text(encoding="utf-8")
    platforms = platform_table(platform_receipts or [])
    # Read the public community overview as a required, auditable input.
    overview = (community / "README.md").read_text(encoding="utf-8")
    if PUBLIC_REPOSITORY not in overview or SITE not in overview:
        raise ValueError("Public support overview does not match the selected destinations")
    if "MIT License" not in license_bytes.decode("utf-8"):
        raise ValueError("Quickstart must carry the public MIT license")
    (dist / "examples").mkdir(parents=True, exist_ok=True)
    (community / "examples").mkdir(parents=True, exist_ok=True)
    for name, data in source_examples.items():
        (dist / "examples" / name).write_bytes(data)
        (community / "examples" / name).write_bytes(data)
    (dist / "docs.css").write_text(CSS, encoding="utf-8", newline="\n")
    support = f'''<p>Questions and reproducible bug reports live in the <a href="{PUBLIC_REPOSITORY}">public community repository</a>. You do not need access to the private research repository to read the documentation or contribute a synthetic reproduction.</p><div class="support-grid"><section class="support-path"><h2>Something broke?</h2><p>Use the bug template for unexpected package behavior. Include a minimal synthetic trace, expected and actual behavior, and your environment.</p><a class="text-link" href="{PUBLIC_REPOSITORY}/issues/new/choose">Report a reproducible bug <span aria-hidden="true">↗</span></a></section><section class="support-path"><h2>Finding your way?</h2><p>Use the question template for integration and usage help. Start with the artifact-delivery quickstart and share the smallest example that explains your question.</p><a class="text-link" href="{PUBLIC_REPOSITORY}/issues/new/choose">Ask a question <span aria-hidden="true">↗</span></a></section></div><div class="contact-checklist"><h2>A useful report includes</h2><ul><li>Consequa-X version, Python version and operating system.</li><li>Reproduction steps and the smallest synthetic input.</li><li>The expected result and the actual error or conclusion.</li><li>Relevant sanitized output, with no customer or production data.</li></ul></div><h2>Keep private evidence private.</h2><p>Public issues require a GitHub account and are visible to everyone. Do not post credentials, exploit details, private traces or identifying customer data. Minimal-disclosure HTML still retains timing, counts and relationships; review it before sharing. Use a synthetic reproduction whenever possible.</p><p>Suspected vulnerabilities belong in <a href="security.html">private vulnerability reporting</a>, rather than a public issue. Maintainer help is best effort; no response deadline or long-term support period is promised.</p><h2>Source and distribution</h2><p>The research/source repository is private. The public community repository contains documentation, synthetic examples and issue templates. The <a href="https://pypi.org/project/consequa-x/">MIT-licensed Python wheel and source distribution</a> are public; the source distribution includes implementation, application examples, tests and documentation.</p>'''
    pages = {
        "docs": ("Documentation", "A five-minute offline artifact-delivery quickstart and the Consequa-X report API.", documentation(published=published)),
        "support": ("Support", "Public questions, synthetic bug reports and a private security route for Consequa-X.", article("A little context.<br>A <em>better answer.</em>", "Bring a small, reproducible example. Keep private captures out of public issues.", support, "COMMUNITY / HELP & SUPPORT")),
        "security": ("Security", "Report Consequa-X vulnerabilities privately and understand evidence trust boundaries.", article("Preserve the evidence.<br><em>Protect the people.</em>", "A private route for vulnerabilities, with clear boundaries for reports and application-owned evidence.", markdown_body(security), "SECURITY / RESPONSIBLE REPORTING")),
        "changelog": ("Changelog", "Consequa-X release status, compatibility and platform validation.", article("A record of<br><em>what changed.</em>", "Release status and compatibility claims, grounded in what has actually been checked.", markdown_body(changelog) + platforms, "RELEASES / PACKAGE HISTORY")),
    }
    for name, (title, description, body) in pages.items():
        (dist / f"{name}.html").write_text(page(title, description, body, name),
                                         encoding="utf-8", newline="\n")
    archive = {"README.md": quickstart, "LICENSE": license_bytes, **source_examples}
    with zipfile.ZipFile(dist / "quickstart.zip", "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9) as output:
        for name, data in sorted(archive.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 17, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            output.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    print("Built four documentation pages, their stylesheet, and the four-file quickstart archive.")
    print("Mirrored only the two explicitly allowlisted synthetic Python examples.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--published", action="store_true",
                        help="Declare 1.1.0 available only after verifying its public PyPI release")
    parser.add_argument("--platform-receipt", action="append", type=Path, default=[],
                        help="Successful isolated 1.1.0 installed-wheel receipt; repeat per environment")
    args = parser.parse_args()
    build(published=args.published, platform_receipts=args.platform_receipt)
