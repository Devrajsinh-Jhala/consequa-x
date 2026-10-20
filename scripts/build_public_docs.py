"""Build explicitly allowlisted public docs and deterministic synthetic examples.

This authoring tool has no runtime dependencies. It never scans the repository
for publication candidates: every input and output is named below. Run it again
after editing the public documentation sources or the three example modules.
"""

import argparse
from html import escape
import json
from pathlib import Path
import re
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_REPOSITORY = "https://github.com/Devrajsinh-Jhala/consequa-x"
SITE = "https://consequa-x.onrender.com"
RELEASE = "2.1.2"
EXAMPLES = ("agent_loop_sqlite.py", "artifact_delivery.py", "report_quickstart.py")


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
            target = {"QUICKSTART.md": "docs.html", "docs/quickstart.md": "docs.html",
                      "SECURITY.md": "security.html", "CHANGELOG.md": "changelog.html",
                      "docs/release-notes.md": "changelog.html"}.get(target, target)
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
  <meta name="theme-color" content="#0b0d10">
  <meta name="description" content="{escape(description, quote=True)}">
  <title>{escape(title)} — ConseqaX</title>
  <link rel="icon" type="image/svg+xml" href="favicon.svg?v=20261018-ui5">
  <link rel="stylesheet" href="styles.css?v=20261018-ui5">
  <link rel="stylesheet" href="docs.css?v=20261018-ui5">
</head>
<body class="docs-site">
  <a class="skip-link" href="#main">Skip to content</a>
  <header class="docs-header section-shell">
    <a class="wordmark" href="index.html" aria-label="ConseqaX home"><svg class="brand-symbol" viewBox="0 0 32 32" fill="none" aria-hidden="true"><path d="M6 23 16 5h10L16 23H6Z" fill="currentColor"/><path d="m8 28 3-5h10l5-9h5L23 28H8Z" fill="currentColor" opacity=".5"/></svg><span>conseqa<span class="brand-x">×</span></span></a>
    <nav aria-label="Main navigation">{navigation}<a class="package-link" href="https://pypi.org/project/consequa-x/">Python package <span aria-hidden="true">↗</span></a></nav>
  </header>
  {body}
  <footer class="docs-footer section-shell"><a href="index.html">conseqa<span class="brand-x">×</span></a><p>Evidence-aware explanation of consequential agent actions.</p><nav aria-label="Footer">{navigation}<a href="{PUBLIC_REPOSITORY}">GitHub <span aria-hidden="true">↗</span></a></nav><small>© 2026 Devrajsinh Jhala · MIT licensed package</small></footer>
</body>
</html>
'''


def documentation(*, published: bool = False) -> str:
    release_status = (
        f'<strong>Version {RELEASE} is available.</strong><p>Install the verified '
        f'<a href="https://pypi.org/project/consequa-x/{RELEASE}/">{RELEASE} release from PyPI</a>. '
        '<a href="changelog.html">Read release notes and the actual platform checks.</a></p>'
        if published else
        f'<strong>{RELEASE} is being prepared.</strong><p>The capture API below belongs '
        f'to {RELEASE}. Check the <a href="https://pypi.org/project/consequa-x/">published version '
        'on PyPI</a> before installing a pinned release. <a href="changelog.html">Read '
        'release status and validated platforms.</a></p>'
    )
    installation = code(f"python -m pip install consequa-x=={RELEASE}\nconsequa-x --version")
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
    agent_loop = code("python agent_loop_sqlite.py --mode timeout_after_commit --output agent-run")
    return f'''<div class="docs-layout section-shell">
  <aside class="docs-sidebar" aria-label="On this page"><span class="eyebrow">THE FIELD GUIDE</span><nav><a href="#quickstart">Five-minute quickstart</a><a href="#read-the-evidence">Read the evidence</a><a href="#reports">Offline reports</a><a href="#privacy">Disclosure &amp; sharing</a><a href="#python-api">Python API</a><a href="#integration">Connect your application</a><a href="#boundaries">Trust boundaries</a><a href="#help">Get help</a></nav><a class="sidebar-download" href="quickstart.zip" download>Download the examples <span aria-hidden="true">↓</span><small>Three Python files · synthetic data · MIT</small></a></aside>
  <main class="docs-content" id="main">
    <div class="docs-hero"><span class="eyebrow">DOCUMENTATION / VERSION 2.1</span><h1>From a trace<br>to a <em>clear account.</em></h1><p class="docs-lead">Create your first offline report, read what the evidence supports, and capture your own agent’s tool calls.</p><div class="docs-prerequisites"><span>Python 3.11 or newer</span><span>No API key</span><span>No required runtime dependencies</span></div></div>
    <div class="docs-callout release-callout">{release_status}</div>
    <section id="quickstart"><span class="eyebrow">01 / YOUR FIRST FIVE MINUTES</span><h2>Make the evidence visible.</h2><p>This example performs no delivery or payment. It reads synthetic artifact-store fixtures using the public package APIs.</p>
      <div class="guide-step"><span class="guide-step-number" aria-hidden="true">1</span><div><h3>Install the package.</h3><p>Use Python 3.11 or newer.</p>{installation}</div></div>
      <div class="guide-step"><span class="guide-step-number" aria-hidden="true">2</span><div><h3>Get the two example files.</h3><p><a href="quickstart.zip" download>Download the quickstart archive</a> and extract it. Keep <code>artifact_delivery.py</code> and <code>report_quickstart.py</code> in the same folder. The archive includes its README and MIT license.</p><p class="small-text">Prefer reading first? <a href="examples/artifact_delivery.py">View the artifact adapter</a> or <a href="examples/report_quickstart.py">view the report example</a>.</p></div></div>
      <div class="guide-step"><span class="guide-step-number" aria-hidden="true">3</span><div><h3>Generate three captured examples.</h3><p>Open a terminal in the extracted folder, then use a new output directory:</p>{run_example}<p>Open <code>my-first-capture/verified.html</code> in your browser. Compare <code>unknown.html</code> and <code>other-actor.html</code>. Each report has a separate original JSON trace.</p></div></div>
      <div class="guide-step"><span class="guide-step-number" aria-hidden="true">4</span><div><h3>Render a saved trace again.</h3>{render}<p>The destination must be new. If the console command is not on your PATH, replace <code>consequa-x</code> with <code>python -m consequa_x</code>.</p></div></div>
    </section>
    <section id="read-the-evidence"><span class="eyebrow">02 / THREE DISTINCT CONCLUSIONS</span><h2>State and origin stay separate.</h2><p>A timeout describes a tool response. It cannot by itself determine the requested outcome.</p><div class="docs-table-wrap" tabindex="0" role="region" aria-label="Synthetic example outcomes"><table><caption>What the artifact-delivery fixtures establish</caption><thead><tr><th scope="col">Example</th><th scope="col">Verified state</th><th scope="col">Effect origin</th><th scope="col">Interpretation</th></tr></thead><tbody><tr><th scope="row">Verified</th><td><span class="state-chip">satisfied</span></td><td>confirmed</td><td>The readback covers a matching delivery and links it to the captured action.</td></tr><tr><th scope="row">Unknown</th><td><span class="state-chip neutral">unknown</span></td><td>unknown</td><td>Unavailable readback does not support a success or failure conclusion.</td></tr><tr><th scope="row">Other actor</th><td><span class="state-chip">satisfied</span></td><td>other_actor</td><td>The requested state exists, but another actor produced the effect.</td></tr></tbody></table></div><p>The example hashes the bytes read from its fixture independently of the requested digest. Its application-owned <code>ArtifactVerifier</code> evaluates the contract and records which revisions match the target, so <code>explain</code> can judge the agent&#8217;s report without any artifact-specific logic.</p></section>
    <section id="reports"><span class="eyebrow">03 / ONE FILE, NO SERVER</span><h2>Inspect an offline report.</h2><p>A report is self-contained HTML: no JavaScript, external fonts, remote assets or network requests. It shows structural contract bounds, the timeline, responses, the reported assessment, readbacks, recorded state and origin, and an evidence graph.</p><p>Successive observations retain separate witnesses. Order, dependency, observation and origin links carry distinct labels; a graph edge does not establish counterfactual necessity.</p><div class="docs-callout"><strong>Rendering is a read-only presentation.</strong><p>It performs no verifier call, target matching, application action or replay. It presents captured verification and does not independently establish source truth. Each action&#8217;s assessment alignment and diagnosis codes are computed from the recorded receipts.</p></div><p>To start with the package’s bundled refund fixtures instead:</p>{demo}<p>Input traces are validated before the output is created. The CLI preserves the source and refuses an existing output file, including the input itself.</p></section>
    <section id="privacy"><span class="eyebrow">04 / CHOOSE WHAT YOU DISCLOSE</span><h2>Share a smaller surface.</h2><p>Default reports use local aliases and omit arbitrary captured values: payloads, rationales, source names, raw identifiers, paths, digests, predicates and error messages. Omitted fields are absent from the HTML, including attributes, comments and embedded data.</p><p>Timing, counts, enum statuses and relationships remain visible. Review these before sharing. This is deliberate field omission, not universal anonymization or personal-data detection.</p><details class="docs-details"><summary>Inspect all captured fields locally</summary><div><p><code>--include-details</code> explicitly includes the entire trace as escaped, inert text. This can expose sensitive information. Keep a detailed report private whenever its trace is private.</p>{detailed}</div></details><p>Retain the original trace and source evidence separately. A reduced presentation is not a substitute for the verification record. For a public bug report, provide a synthetic reproduction.</p></section>
    <section id="python-api"><span class="eyebrow">05 / COMPOSE WITH PYTHON</span><h2>Render without a service.</h2><p><code>render_report</code> returns HTML and writes no files. It accepts a validated <code>Trace</code> and an optional boolean <code>include_details</code> argument, which defaults to <code>False</code>.</p>{api}<p>The portable schema is <code>1.0</code>: several actions per trace, a declared time base, and read-only records. Package version and wire-schema version are separate. Convert traces saved by 1.x with <code>consequa-x migrate</code>.</p></section>
    <section id="integration"><span class="eyebrow">06 / YOUR DOMAIN, EXPLICITLY</span><h2>Connect your application.</h2><ol class="integration-list"><li><strong>Declare the contract before the action.</strong> Define matching state, deadline, persistence horizon and required count; <code>TraceRecorder.register</code> returns that action&#8217;s <code>ActionCapture</code>.</li><li><strong>Capture the action as it runs.</strong> Wrap each tool call in <code>capture.attempt()</code>, <code>capture_tool</code> or <code>acall</code>, and record the agent&#8217;s assessment exactly as it was stated. A run can register several actions.</li><li><strong>Obtain independent readback.</strong> Query your system of record through a separate read-only path, with source, scope, completeness, watermark and effect-origin metadata; <code>poll_readback</code> re-reads a lagging source.</li><li><strong>Verify it.</strong> Use the built-in <code>RecordVerifier</code> for rows, orders or tickets, or implement the explicit <code>Verifier</code> interface for another domain. The receipt records which effects match the target, and any domain findings. An outcome with several required effects is one <code>all_of</code> or <code>any_of</code> contract, checked part by part by <code>CompositeVerifier</code> with one readback per source.</li><li><strong>Explain and act.</strong> <code>explain(trace)</code> judges each action from its receipts; <code>retry_advice</code> says whether a retry would duplicate an effect.</li><li><strong>Or let your framework report its tool calls.</strong> Optional extras record calls from the OpenAI Agents SDK (<code>consequential_tool</code>), LangChain (<code>ConsequaCallbackHandler</code>) and the Claude Agent SDK (<code>consequa_hooks</code>) for the calls you mark as consequential. <code>consequa-x otel-export</code> writes a trace as OpenTelemetry spans.</li></ol><p>The downloadable <a href="examples/agent_loop_sqlite.py">SQLite agent loop</a> runs a scripted support agent against a real local database, captures it with <code>TraceRecorder</code> and checks the refund with <code>RecordVerifier</code>. Its other modes are <code>other_actor</code> and <code>stale_readback</code>. No money moves; the refund is a row in a local file.</p>{agent_loop}<p>The <a href="examples/artifact_delivery.py">artifact-delivery adapter</a> implements a verifier by hand. In your application, read back through an independently authenticated adapter; do not copy the requested state into the readback.</p></section>
    <section id="boundaries"><span class="eyebrow">07 / WHAT THE RECORD CAN SUPPORT</span><h2>Keep uncertainty intact.</h2><p>Schema validation checks structure and identity linkage. Your application establishes source authentication, provider guarantees and the truth of supplied metadata. A report cannot supply those guarantees.</p><p><code>unknown</code>, <code>other_actor</code> and unassessable conclusions remain distinct. Missing readback is not a successful verification. Research replay interfaces carry their own assumptions; the package does not claim baseline superiority or improved live-model accuracy.</p><p>Platform validation is recorded for environments actually checked. A pure-Python wheel alone does not establish compatibility with every platform.</p></section>
    <section class="docs-next" id="help"><span class="eyebrow">KEEP BUILDING</span><h2>A clear next step.</h2><p><a href="support.html">Ask a question or report a reproducible bug</a>. Use the <a href="security.html">private security route</a> for vulnerabilities, and <a href="changelog.html">release notes</a> for publication status and platform checks.</p><a class="text-link" href="quickstart.zip" download>Download the synthetic quickstart <span aria-hidden="true">↓</span></a></section>
  </main>
</div>'''


def article(title: str, subtitle: str, body: str, label: str) -> str:
    return f'''<main class="docs-article section-shell" id="main"><div class="article-intro"><span class="eyebrow">{escape(label)}</span><h1>{title}</h1><p class="docs-lead">{subtitle}</p></div><div class="article-body">{body}</div><div class="article-return"><a class="text-link" href="docs.html">Back to the field guide <span aria-hidden="true">↗</span></a></div></main>'''


CSS = """/* Documentation: graphite, clear typography and electric-lime wayfinding.
   Self-contained styles; all behavior remains native HTML. */
.docs-site {
  --docs-bg: #0b0d10;
  --docs-panel: #12161c;
  --docs-line: #272d36;
  --docs-text: #f1f3f5;
  --docs-muted: #a9b0bc;
  --docs-accent: #c9f36a;
  --docs-mono: var(--font-mono, "Cascadia Code", "SFMono-Regular", Consolas, monospace);
  background: var(--docs-bg);
  color: var(--docs-text);
  font-family: var(--font-body, Arial, sans-serif);
  -webkit-font-smoothing: antialiased;
}
.docs-site a { text-underline-offset: 4px; }
.docs-site :focus-visible { outline: 2px solid var(--docs-accent); outline-offset: 5px; }
.docs-header {
  min-height: 92px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 28px;
  border-bottom: 1px solid var(--docs-line);
}
.docs-header .wordmark { display: inline-flex; align-items: center; gap: 10px; font-size: 24px; letter-spacing: -.9px; font-weight: 700; text-decoration: none; color: var(--docs-text); white-space: nowrap; }
.docs-header .brand-symbol { width: 29px; height: 29px; color: var(--docs-accent); flex: 0 0 auto; }
.docs-header .brand-x, .docs-footer .brand-x { color: var(--docs-accent); }
.docs-header > nav { display: flex; align-items: center; gap: 5px; flex-wrap: wrap; }
.docs-header nav a { font-size: 13px; text-decoration: none; padding: 10px 12px; min-height: 44px; display: inline-flex; align-items: center; border-radius: 7px; color: var(--docs-muted); transition: color .18s, background .18s; }
.docs-header nav a:hover { color: var(--docs-text); background: #1a2028; }
.docs-header nav a[aria-current=page] { color: var(--docs-accent); background: #c9f36a0c; }
.docs-header .package-link { padding: 10px 14px; border: 1px solid var(--docs-line); margin-left: 12px; color: var(--docs-text); }
.docs-header .package-link span { margin-left: 10px; color: var(--docs-accent); }
.docs-layout { display: grid; grid-template-columns: 218px minmax(0,1fr); gap: clamp(44px,6vw,88px); padding-top: 64px; padding-bottom: 112px; max-width: 1280px; }
.docs-sidebar { position: sticky; top: 34px; align-self: start; padding-top: 5px; }
.docs-sidebar .eyebrow { display: block; color: #757f8e; font-family: var(--docs-mono); font-size: 10px; font-weight: 500; letter-spacing: 1.5px; margin: 0 0 20px 13px; }
.docs-sidebar nav { display: flex; flex-direction: column; align-items: stretch; gap: 3px; border-left: 1px solid var(--docs-line); }
.docs-sidebar nav a { font-size: 13px; text-decoration: none; line-height: 1.6; color: var(--docs-muted); padding: 9px 12px; min-height: 44px; border-radius: 0 7px 7px 0; margin-left: -1px; border-left: 1px solid transparent; transition: color .18s, background .18s, border-color .18s; }
.docs-sidebar nav a:hover, .docs-sidebar nav a:focus-visible { color: var(--docs-accent); background: #c9f36a09; border-left-color: var(--docs-accent); }
.sidebar-download { display: block; padding: 18px 15px; margin-top: 30px; border: 1px solid var(--docs-line); border-radius: 10px; background: var(--docs-panel); font-size: 12px; font-weight: 600; color: var(--docs-text); text-decoration: none; line-height: 1.7; }
.sidebar-download:hover { border-color: #66794a; }
.sidebar-download > span { float: right; color: var(--docs-accent); font-size: 16px; }
.sidebar-download small { display: block; font-size: 10px; font-weight: 400; color: var(--docs-muted); margin-top: 7px; line-height: 1.7; }
.docs-content { max-width: 820px; min-width: 0; }
.docs-hero .eyebrow, .article-intro .eyebrow { color: var(--docs-accent); display: block; font-family: var(--docs-mono); font-size: 10px; font-weight: 500; letter-spacing: 1.1px; margin-bottom: 24px; }
.docs-hero h1, .article-intro h1 { margin: 0; font-family: var(--font-body, Arial, sans-serif); font-size: clamp(48px,4.5vw,68px); line-height: 1.04; font-weight: 600; letter-spacing: -.065em; color: var(--docs-text); }
.docs-hero h1 em, .article-intro h1 em { font-style: normal; color: var(--docs-accent); }
.docs-lead { font-size: 17px; line-height: 1.8; color: var(--docs-muted); max-width: 640px; margin-top: 24px; }
.docs-prerequisites { display: flex; flex-wrap: wrap; gap: 8px; font-family: var(--docs-mono); font-size: 10px; color: #a8b0bc; margin-top: 25px; }
.docs-prerequisites span { padding: 7px 10px; border: 1px solid var(--docs-line); border-radius: 5px; background: var(--docs-panel); }
.docs-callout { border: 1px solid #3d482c; border-left: 3px solid var(--docs-accent); border-radius: 0 10px 10px 0; background: #c9f36a06; padding: 22px 25px; margin-top: 25px; margin-bottom: 25px; }
.docs-callout strong { font-size: 14px; line-height: 1.6; font-weight: 600; color: var(--docs-text); }
.docs-callout p { font-size: 13px !important; margin-top: 8px !important; color: #b8c1ae !important; }
.release-callout { margin-top: 36px; }
.docs-content section { scroll-margin-top: 34px; border-top: 1px solid var(--docs-line); padding-top: 43px; margin-top: 52px; }
.docs-content section > .eyebrow { font-size: 10px; font-family: var(--docs-mono); letter-spacing: 1.2px; display: block; color: #87928c; margin-bottom: 17px; }
.docs-content h2, .article-body h2 { font-family: var(--font-body, Arial, sans-serif); color: var(--docs-text); font-size: 34px; font-weight: 600; letter-spacing: -.045em; line-height: 1.15; margin-bottom: 18px; }
.docs-content h3 { font-family: var(--font-body, Arial, sans-serif); color: var(--docs-text); font-size: 21px; font-weight: 600; letter-spacing: -.5px; line-height: 1.35; margin: 0; }
.docs-content p, .article-body p, .article-body li { font-size: 15px; line-height: 1.9; color: var(--docs-muted); margin-top: 15px; }
.docs-content p a, .article-body a { color: var(--docs-accent); font-weight: 500; text-decoration-color: #c9f36a55; }
.docs-content p a:hover, .article-body a:hover { text-decoration-color: var(--docs-accent); }
.docs-content p code, .docs-content li code, .article-body code { background: #1d232c; border: 1px solid #2b323c; border-radius: 4px; padding: 2px 5px; color: #dbe2eb; overflow-wrap: anywhere; font-family: var(--docs-mono); font-size: .85em; }
.guide-step { display: grid; grid-template-columns: 30px minmax(0,1fr); gap: 17px; margin-top: 33px; }
.guide-step-number { width: 29px; height: 29px; border: 1px solid #3c482d; background: #c9f36a08; border-radius: 8px; display: grid; place-items: center; font-family: var(--docs-mono); font-size: 12px; color: var(--docs-accent); margin-top: 1px; }
.guide-step p { margin-top: 10px; }
.small-text { font-size: 12px !important; }
.code-block { background: #101419; color: #dce7d1; margin-top: 20px; margin-bottom: 20px; min-width: 0; position: relative; border: 1px solid #2b333c; border-radius: 10px; overflow: hidden; }
.code-label { display: block; font-family: var(--docs-mono); font-size: 9px; text-transform: uppercase; letter-spacing: 1.1px; color: #83917b; padding: 13px 19px 12px; border-bottom: 1px solid #242c34; background: #151a20; }
.code-label::before { content: "›_"; color: var(--docs-accent); letter-spacing: 0; padding-right: 9px; font-weight: 600; }
.code-block pre { padding: 18px 20px 20px; overflow: auto; font-family: var(--docs-mono); font-size: 12px; line-height: 1.85; margin: 0; tab-size: 4; }
.code-block code { font-family: inherit; font-size: inherit; line-height: inherit; white-space: pre; background: transparent; color: inherit; padding: 0; border: 0; }
.docs-table-wrap { overflow: auto; margin-top: 26px; border: 1px solid var(--docs-line); border-radius: 10px; background: #101419; }
.docs-table-wrap table { border-collapse: collapse; text-align: left; width: 100%; min-width: 570px; }
.docs-table-wrap caption { text-align: left; font-size: 11px; padding: 17px 18px; color: var(--docs-muted); font-family: var(--docs-mono); line-height: 1.7; border-bottom: 1px solid var(--docs-line); }
.docs-table-wrap th, .docs-table-wrap td { padding: 17px 18px; vertical-align: top; border-top: 1px solid var(--docs-line); font-size: 12px; line-height: 1.8; color: #c7ced7; }
.docs-table-wrap thead th { background: #181d24; color: #a5afbc; font-family: var(--docs-mono); font-size: 10px; font-weight: 500; letter-spacing: .3px; border-top: 0; }
.docs-table-wrap tbody th { font-weight: 600; white-space: nowrap; color: var(--docs-text); }
.docs-table-wrap td:last-child { color: var(--docs-muted); min-width: 200px; }
.state-chip { display: inline-block; background: #c9f36a0a; border: 1px solid #465334; border-radius: 4px; font-family: var(--docs-mono); font-size: 10px; color: var(--docs-accent); padding: 2px 7px; white-space: nowrap; }
.state-chip.neutral { background: #20252d; color: #b9c2ce; border-color: #363e4a; }
.docs-details { border: 1px solid var(--docs-line); border-radius: 10px; margin-top: 27px; background: var(--docs-panel); overflow: hidden; }
.docs-details summary { padding: 18px 22px; cursor: pointer; font-size: 14px; line-height: 1.7; font-weight: 500; color: var(--docs-text); }
.docs-details summary::marker { color: var(--docs-accent); }
.docs-details[open] summary { background: #171d23; }
.docs-details > div { padding: 0 22px 6px; border-top: 1px solid var(--docs-line); }
.integration-list { padding-left: 22px; margin-top: 26px; }
.integration-list li { padding-left: 8px; margin-bottom: 18px; color: var(--docs-muted); font-size: 15px; line-height: 1.9; }
.integration-list li::marker { color: var(--docs-accent); font-family: var(--docs-mono); font-size: 12px; }
.integration-list strong { color: var(--docs-text); font-weight: 500; }
.docs-next { padding-bottom: 10px; }
.docs-next .text-link { margin-top: 22px; color: var(--docs-accent); }
.docs-footer { padding-top: 36px; padding-bottom: 32px; border-top: 1px solid var(--docs-line); display: flex; flex-wrap: wrap; align-items: center; gap: 20px 27px; }
.docs-footer > a { font-family: var(--font-body, Arial, sans-serif); font-size: 25px; font-weight: 600; text-decoration: none; color: var(--docs-text); letter-spacing: -.9px; }
.docs-footer > p { font-size: 12px; max-width: 260px; color: var(--docs-muted); line-height: 1.7; }
.docs-footer > nav { margin-left: auto; display: flex; flex-wrap: wrap; gap: 17px; }
.docs-footer nav a { font-size: 12px; text-decoration: none; color: #b8c2d0; min-height: 44px; display: inline-flex; align-items: center; }
.docs-footer nav a:hover { color: var(--docs-accent); }
.docs-footer small { display: block; flex-basis: 100%; font-size: 11px; color: #a1aebe; margin-top: 7px; }
.docs-article { max-width: 1080px; padding-top: 76px; padding-bottom: 100px; }
.article-intro { padding-bottom: 38px; border-bottom: 1px solid var(--docs-line); }
.article-body { max-width: 810px; }
.article-body h2 { margin-top: 43px; font-size: 29px; }
.article-body ul { padding-left: 22px; margin-top: 21px; }
.article-body li { padding-left: 5px; margin-top: 10px; }
.article-body li::marker { color: #7d9760; }
.article-body .support-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 34px; }
.support-path { padding: 25px; border: 1px solid var(--docs-line); background: var(--docs-panel); border-radius: 12px; }
.support-path h2 { margin-top: 0; font-size: 25px; }
.support-path p { font-size: 14px; }
.support-path .text-link { margin-top: 19px; font-size: 12px; gap: 13px; }
.article-return { margin-top: 48px; padding-top: 25px; border-top: 1px solid var(--docs-line); }
.article-return .text-link { font-size: 13px; color: var(--docs-accent); }
.contact-checklist { padding: 25px 28px; background: #c9f36a06; border: 1px solid #39452b; border-radius: 12px; margin-top: 30px; }
.contact-checklist h2 { margin-top: 0; font-size: 25px; }
.contact-checklist ul { margin-bottom: 0; }
.docs-content .guide-step .code-block { margin-bottom: 0; }
@media (min-width:1500px) {
  .docs-layout { padding-inline: 48px; }
}
@media (max-width:1050px) {
  .docs-layout { gap: 40px; grid-template-columns: 190px minmax(0,1fr); }
  .docs-header > nav { gap: 2px; }
  .docs-header nav a { font-size: 12px; padding-inline: 9px; }
  .docs-header .package-link { margin-left: 4px; }
  .docs-content h2 { font-size: 31px; }
  .docs-footer > nav { margin-left: 0; flex-basis: 100%; }
}
@media (max-width:760px) {
  .docs-header { padding-top: 22px; padding-bottom: 18px; min-height: 0; display: block; }
  .docs-header .wordmark { font-size: 24px; }
  .docs-header > nav { gap: 5px; margin-top: 18px; margin-left: -8px; }
  .docs-header nav a { font-size: 12px; padding: 8px; }
  .docs-header .package-link { margin-left: 0; padding: 7px 8px; }
  .docs-header .package-link span { margin-left: 5px; }
  .docs-layout { display: flex; flex-direction: column; padding-top: 28px; padding-bottom: 65px; gap: 0; }
  .docs-sidebar { position: static; padding: 0 0 25px; margin-bottom: 36px; border-bottom: 1px solid var(--docs-line); width: 100%; }
  .docs-sidebar .eyebrow { margin: 0 0 13px; font-size: 9px; }
  .docs-sidebar nav { flex-direction: row; gap: 5px; flex-wrap: wrap; border: 0; }
  .docs-sidebar nav a { font-size: 12px; padding: 9px 10px; min-height: 44px; display: inline-flex; align-items: center; border-radius: 6px; border: 1px solid var(--docs-line); margin: 0; background: var(--docs-panel); }
  .sidebar-download { margin-top: 15px; padding: 11px 13px; font-size: 11px; max-width: 270px; }
  .sidebar-download small { font-size: 9px; margin-top: 3px; }
  .docs-hero h1, .article-intro h1 { font-size: clamp(40px,8.4vw,57px); letter-spacing: -.055em; }
  .docs-hero .eyebrow, .article-intro .eyebrow { font-size: 9px; margin-bottom: 20px; }
  .docs-lead { font-size: 15px; line-height: 1.8; margin-top: 21px; }
  .docs-prerequisites { font-size: 9px; gap: 6px; margin-top: 22px; }
  .docs-prerequisites span { padding: 6px 8px; }
  .docs-callout { padding: 19px 18px; }
  .docs-callout strong { font-size: 13px; }
  .docs-callout p { font-size: 12px !important; }
  .docs-content section { padding-top: 33px; margin-top: 39px; }
  .docs-content section > .eyebrow { font-size: 9px; line-height: 1.6; }
  .docs-content h2 { font-size: 29px; }
  .docs-content p, .article-body p, .article-body li, .integration-list li { font-size: 14px; }
  .docs-content h3 { font-size: 20px; }
  .guide-step { gap: 12px; grid-template-columns: 26px minmax(0,1fr); margin-top: 29px; }
  .guide-step-number { width: 26px; height: 26px; font-size: 11px; }
  .code-label { padding: 11px 15px; font-size: 8px; }
  .code-block pre { padding: 15px 15px 17px; font-size: 11px; }
  .docs-table-wrap caption { font-size: 10px; padding: 14px 15px; }
  .docs-table-wrap th, .docs-table-wrap td { padding: 14px 15px; }
  .docs-details summary { padding: 16px; font-size: 13px; }
  .docs-details > div { padding-inline: 16px; }
  .docs-article { padding-top: 46px; padding-bottom: 65px; }
  .article-body h2 { font-size: 27px; }
  .article-body .support-grid { grid-template-columns: 1fr; gap: 14px; }
  .support-path { padding: 23px; }
  .docs-footer { gap: 17px 23px; padding-top: 29px; padding-bottom: 29px; }
  .docs-footer > nav { gap: 15px 19px; }
  .docs-footer nav a { font-size: 12px; }
  .docs-footer small { font-size: 11px; line-height: 1.7; }
  .contact-checklist { padding: 21px; }
  .contact-checklist h2 { font-size: 23px; }
}
@media (max-width:380px) {
  .docs-header > nav { gap: 3px; }
  .docs-header nav a { font-size: 12px; padding-inline: 7px; }
  .docs-hero h1, .article-intro h1 { font-size: 39px; }
  .docs-content h2 { font-size: 27px; }
  .guide-step { gap: 10px; grid-template-columns: 24px minmax(0,1fr); }
  .guide-step-number { width: 24px; height: 24px; }
  .code-block pre { font-size: 10px; padding-inline: 12px; }
  .code-label { padding-inline: 12px; }
}
@media print {
  .docs-site { background: white; color: #111; --docs-text: #111; --docs-muted: #333; --docs-line: #bbb; --docs-accent: #244217; }
  .docs-header, .docs-sidebar, .docs-footer, .article-return { display: none; }
  .docs-layout, .docs-article { display: block; padding: 0; max-width: none; }
  .docs-content, .article-body { max-width: none; }
  .docs-hero h1, .article-intro h1 { font-size: 42px; }
  .docs-content h2 { font-size: 28px; }
  .code-block { break-inside: avoid; background: white; color: black; border-color: #bbb; }
  .code-label { color: #333; background: #eee; }
  .code-block pre, .code-block code { white-space: pre-wrap; overflow-wrap: anywhere; }
  .docs-content section { break-inside: auto; }
  .docs-callout, .contact-checklist, .support-path, .docs-prerequisites span, .docs-details { background: white; border-color: #999; }
  .docs-callout p { color: #333 !important; }
  .docs-content p code, .docs-content li code, .article-body code { background: #eee; color: #111; border-color: #ccc; }
  .docs-details > div { display: block; }
  .docs-table-wrap { overflow: visible; background: white; border-color: #bbb; }
  .docs-table-wrap table { min-width: 0; }
  .docs-table-wrap th, .docs-table-wrap td { color: #222; }
  .docs-table-wrap thead th { background: #eee; }
  .state-chip, .state-chip.neutral { background: white; color: #222; border-color: #999; }
}
"""


def platform_table(receipt_paths: list[Path]) -> str:
    """Publish only three bounded platform fields from successful release receipts.

    No executable paths, account names, complete receipt payloads or source
    locations are copied. Passing a receipt does not publish that JSON file.
    """
    rows = []
    wheel_hashes = set()
    for path in receipt_paths:
        record = json.loads(path.read_text(encoding="utf-8"))
        if (record.get("passed") is not True
                or record.get("isolated_imports") is not True
                or record.get("install", {}).get("version") != RELEASE):
            raise ValueError(f"Only successful isolated {RELEASE} installation receipts can be listed")
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
    return (f'<h2>Installed {RELEASE} artifact checks</h2><p>These environments completed the '
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
    dist = ROOT / "website" / "dist"
    source_examples = {name: (ROOT / "examples" / name).read_bytes() for name in EXAMPLES}
    quickstart = (ROOT / "docs" / "quickstart.md").read_bytes()
    license_bytes = (ROOT / "LICENSE").read_bytes()
    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    changelog = (ROOT / "docs" / "release-notes.md").read_text(encoding="utf-8")
    platforms = platform_table(platform_receipts or [])
    # The public README must name the same repository and site as these pages.
    overview = (ROOT / "README.md").read_text(encoding="utf-8")
    if PUBLIC_REPOSITORY not in overview or SITE not in overview:
        raise ValueError("Public support overview does not match the selected destinations")
    if "MIT License" not in license_bytes.decode("utf-8"):
        raise ValueError("Quickstart must carry the public MIT license")
    (dist / "examples").mkdir(parents=True, exist_ok=True)
    for name, data in source_examples.items():
        (dist / "examples" / name).write_bytes(data)
    (dist / "docs.css").write_text(CSS, encoding="utf-8", newline="\n")
    support = f'''<p>Questions and reproducible bug reports live in the <a href="{PUBLIC_REPOSITORY}">public GitHub repository</a>, alongside the source, documentation and examples.</p><div class="support-grid"><section class="support-path"><h2>Something broke?</h2><p>Use the bug template for unexpected package behavior. Include a minimal synthetic trace, expected and actual behavior, and your environment.</p><a class="text-link" href="{PUBLIC_REPOSITORY}/issues/new/choose">Report a reproducible bug <span aria-hidden="true">↗</span></a></section><section class="support-path"><h2>Finding your way?</h2><p>Use the question template for integration and usage help. Start with the artifact-delivery quickstart and share the smallest example that explains your question.</p><a class="text-link" href="{PUBLIC_REPOSITORY}/issues/new/choose">Ask a question <span aria-hidden="true">↗</span></a></section></div><div class="contact-checklist"><h2>A useful report includes</h2><ul><li>ConseqaX version, Python version and operating system.</li><li>Reproduction steps and the smallest synthetic input.</li><li>The expected result and the actual error or conclusion.</li><li>Relevant sanitized output, with no customer or production data.</li></ul></div><h2>Keep private evidence private.</h2><p>Public issues require a GitHub account and are visible to everyone. Do not post credentials, exploit details, private traces or identifying customer data. Minimal-disclosure HTML still retains timing, counts and relationships; review it before sharing. Use a synthetic reproduction whenever possible.</p><p>Suspected vulnerabilities belong in <a href="security.html">private vulnerability reporting</a>, rather than a public issue. Maintainer help is best effort; no response deadline or long-term support period is promised.</p><h2>Source and distribution</h2><p>The <a href="{PUBLIC_REPOSITORY}">source repository</a> is public under the MIT license, including the implementation, tests, documentation, examples and research records. The <a href="https://pypi.org/project/consequa-x/">Python wheel and source distribution</a> are published on PyPI.</p>'''
    pages = {
        "docs": ("Documentation", "A five-minute offline artifact-delivery quickstart and the ConseqaX report API.", documentation(published=published)),
        "support": ("Support", "Public questions, synthetic bug reports and a private security route for ConseqaX.", article("A little context.<br>A <em>better answer.</em>", "Bring a small, reproducible example. Keep private captures out of public issues.", support, "COMMUNITY / HELP & SUPPORT")),
        "security": ("Security", "Report ConseqaX vulnerabilities privately and understand evidence trust boundaries.", article("Preserve the evidence.<br><em>Protect the people.</em>", "A private route for vulnerabilities, with clear boundaries for reports and application-owned evidence.", markdown_body(security), "SECURITY / RESPONSIBLE REPORTING")),
        "changelog": ("Changelog", "ConseqaX release status, compatibility and platform validation.", article("A record of<br><em>what changed.</em>", "Release status and compatibility claims, grounded in what has actually been checked.", markdown_body(changelog) + platforms, "RELEASES / PACKAGE HISTORY")),
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
    print("Built four documentation pages, their stylesheet, and the five-file quickstart archive.")
    print("Mirrored only the three explicitly allowlisted synthetic Python examples.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--published", action="store_true",
                        help=f"Declare {RELEASE} available only after verifying its public PyPI release")
    parser.add_argument("--platform-receipt", action="append", type=Path, default=[],
                        help=f"Successful isolated {RELEASE} installed-wheel receipt; repeat per environment")
    args = parser.parse_args()
    build(published=args.published, platform_receipts=args.platform_receipt)
