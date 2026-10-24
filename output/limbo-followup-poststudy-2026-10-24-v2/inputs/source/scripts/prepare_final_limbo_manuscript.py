"""Stage a complete proposed manuscript from the sealed official LIMBO analysis.

This preparation step copies existing figures; it creates no PDF and does not
compile, run a model, evaluate a native task, mutate Git, or modify the working
paper. The lead reviews the staged sources before applying and building them.
Missing/error dispositions remain in the 96-slot denominator. Document visual
QA and publication remain separate from this data-validated preparation.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import shutil


ROOT = Path(__file__).resolve().parents[1]
ARMS = ("vanilla", "sdk_retry3", "guard", "conseqax_guard")
LABELS = ("Vanilla", "SDK retry", "Native guard", "ConseqaX guard")
BASE_SOURCES = ("paper/conseqax-research.tex", "paper/conseqax-research.md",
    "paper/recovery-study-results.tex", "paper/recovery-availability-results.tex",
    "paper/limbo-native-methods.tex")
OLD_FIGURES = ("recovery-method-overview", "recovery-family-primary-contrasts",
               "recovery-availability-grid")
NEW_FIGURES = ("limbo-outcomes", "limbo-stratification", "limbo-costs")
METHOD_FIGURE = "limbo-native-methods"
METHOD_CAPTION = ("Native public-information boundary and four matched conditions. "
    "The package arm preserves the supplied strong guard while consuming actual SDK receipts. "
    "Only public reports enter the receipt path; targets, faults, ledgers and native grades "
    "remain evaluator-only. Offline replay checks behavior and receipt mappings, not an "
    "independently operated service or SDK re-execution.")
TAU = ("An earlier excluded airline development check used the native environment at "
    "revision 96a3ef92329baf908ffe9dfe188cea34e8701d2a. Its unwrapped execution returned "
    "12 model completions and five tool calls but native reward 0 (DB 0; communication 1 "
    "was vacuous). Two guarded checks timed out at 600- and 1,200-second request limits, "
    "respectively, with no returned native grade and no SDK receipt. Their grades remain "
    "unavailable; they are excluded development evidence rather than paired comparative "
    "results. No official airline matrix was collected. Full original traces, partial "
    "failure audits and the historical manuscript retain these limitations.")


def helper(root):
    path = root / "scripts/build_final_limbo_paper.py"
    specification = importlib.util.spec_from_file_location("conseqax_paper_preparation_checks", path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def escape(text):
    replacements = {"&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
        "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
        "\\": r"\textbackslash{}"}
    return "".join(replacements.get(character, character) for character in text)


def replace_paragraph(body, prefix, replacement):
    paragraphs = re.split(r"\n\s*\n", body.strip())
    positions = [index for index, paragraph in enumerate(paragraphs)
                 if re.sub(r"\s+", " ", paragraph).startswith(prefix)]
    if len(positions) != 1:
        raise ValueError("Expected exactly one baseline paragraph: " + prefix)
    paragraphs[positions[0]] = replacement
    return "\n\n".join(paragraphs)


def tex_sections(text):
    matches = list(re.finditer(r"^\\section\{([^{}]+)\}", text, re.M))
    result = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else text.index(r"\section*{AI Assistance")
        result[match.group(1)] = text[match.end():end].strip()
    return result


def markdown_sections(text):
    matches = list(re.finditer(r"^## (\d+)\. ([^\n]+)\n", text, re.M))
    result = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else text.index("## AI Assistance")
        result[match.group(2)] = text[match.end():end].strip()
    return result


def outcome_values(result):
    arms = result["arms"]
    package = arms["conseqax_guard"]
    return {"available": sum(arms[arm]["audited_grade_available"] for arm in ARMS),
        "errors": sum(arms[arm]["audited_native_error_returns"] for arm in ARMS),
        "normal": sum(arms[arm]["execution_success"] for arm in ARMS),
        "receipts": package["costs"]["receipt_count"]["observed_total"],
        "receipt_episodes": package["receipt_episodes_with_at_least_one"],
        "package_graded": package["audited_grade_available"]}


def abstract(result, earlier):
    value = outcome_values(result)
    outcomes = "; ".join(f"{label} {result['arms'][arm]['endpoints']['TS']['true_audited']}/"
        f"{result['arms'][arm]['endpoints']['EOS']['true_audited']}" for arm, label in zip(ARMS, LABELS))
    return ("A timed-out tool call can leave an agent uncertain whether an operation failed or will "
        "commit later. ConseqaX binds explicit contracts and readback witnesses to separate state, "
        "action-origin and unknown conclusions. We evaluate its conditional recovery and reporting "
        "behavior in two controlled studies and an externally authored native fault benchmark. "
        "Study A retains 15,360 SQLite worlds from 24 authored cases: readback policies safely recover "
        "14/24 cases versus 8/24 for response-driven retry, matching a strong reference. Repeated "
        "seeds add no recorded-metric diversity. Polling adds no coverage there. Study B retains "
        "960 worlds: polling increases correct-state yield from 3/192 to 81/192 at 741 versus "
        "192 reads; the reference shares this gain and physical outcomes are identical. The native "
        "LIMBO comparison covers 12 base instances, 24 clean/fault conditions and four arms. "
        f"The original interrupted cohort retains {outcome_values(earlier['result'])['available']}/96 "
        "audited grades and every unavailable disposition. A separately frozen runtime follow-up "
        "on the same instances retains another 96 planned slots; cohorts are not pooled. "
        f"Independent replay establishes {value['available']}/96 follow-up grades, "
        f"including {value['errors']} native error returns after settlement. All-planned TS/EOS "
        f"success counts, each out of 24, are {outcomes}. The SDK condition emits "
        f"{value['receipts']} audited receipts in {value['receipt_episodes']}/24 episodes while "
        "preserving the supplied strong guard. Native EOS has domain-specific accounting and is "
        "not a universal exactly-once guarantee. Study A's postcollection packaging deviation "
        "remains disclosed. These finite results characterize protocol conformance and coverage, "
        "outcome and resource tradeoffs; they establish neither a new recovery algorithm nor "
        "task-population superiority or transfer to independently operated services.")


def introduction(body, is_tex):
    q6 = ("Q6: Under native ambiguous-commit faults, how do all-planned task/effect outcomes, "
        "failures and actual work differ among vanilla dispatch, transparent retry, the supplied "
        "strong guard and its receipt-preserving SDK integration?")
    if is_tex:
        q6 = q6.replace("Q6:", r"\textbf{Q6:}", 1)
        section_reference = r"Sections~\ref{sec:limbo} and~\ref{sec:limbo-results}"
    else:
        q6 = q6.replace("Q6:", "**Q6:**", 1)
        section_reference = "Sections 6 and 7"
    body = replace_paragraph(body, "The research questions are falsifiable.",
        next(paragraph for paragraph in re.split(r"\n\s*\n", body.strip())
             if re.sub(r"\s+", " ", paragraph).startswith("The research questions are falsifiable."))
        + " " + q6)
    contribution = ("The contributions are an executable evidence protocol, a controlled evaluation "
        "of recovery/reporting boundaries and a native external fault-benchmark integration with "
        "audited first-attempt accounting. The controlled reference uses separate arithmetic but "
        "shares application transitions; its agreement supports conformance. The external SDK arm "
        "deliberately preserves an established strong guard, so it does not introduce a new recovery "
        "algorithm. Provenance changes only reporting in the controlled shared-transition comparison. "
        "The native experiment and actual results in " + section_reference + " retain 96 planned "
        "slots per cohort on the same 12 base instances, including the original interrupted cohort "
        "and the separately frozen follow-up. Neither repeated "
        "seeds nor repeated arms create independently sampled tasks.")
    return replace_paragraph(body, "The contribution is", contribution)


def related(body, is_tex):
    if is_tex:
        references = r"\cite{appworld,toolsandbox,taubench}"
        transfer = r"\cite{tau3tasks,tau3eval}"
        limbo = r"\cite{limbo,limbosource}"
    else:
        references, transfer, limbo = "[12]–[14]", "[15], [16]", "[6], [20]"
    paragraph = ("AppWorld, ToolSandbox and tau-bench evaluate stateful agent interaction and world "
        f"outcomes {references}. Earlier model-free transfer used maintained retail/airline tools "
        f"and native DB evaluation {transfer}; reference-action replay is not an autonomous score. "
        f"Our external experiment uses LIMBO's authored tasks, native faults and unchanged grader {limbo}, "
        "retaining its supplied strong guard as a comparator. The receipt arm tests protocol "
        "integration under that same recovery law. The native grade and independently replayed "
        "effect history extend the controlled evaluation while remaining simulated evidence from "
        "one local quantized model.")
    return replace_paragraph(body, "AppWorld, ToolSandbox", paragraph)


def protocol_scope(body):
    opening = ("This section specifies the temporal record contract and application recovery law "
        "evaluated in controlled Studies A and B. The external LIMBO condition instead uses the "
        "benchmark's own guard and a custom current-public-report verifier; it does not apply this "
        "controller or the temporal RecordVerifier to native reports.")
    return opening + "\n\n" + body.replace("The present evaluator scores", "The controlled-study evaluator scores")


def supporting(body, is_tex):
    citation = r"\cite{artifact}" if is_tex else "[7]"
    paragraph = (f"Studies A and B use selected ConseqaX 2.1.1 recording, contract, observation and "
        f"built-in record-verification paths {citation}, together with explicit application polling "
        "and safety-gate code. The native LIMBO arm instead uses a custom verifier over current "
        "public reports; it does not exercise the temporal RecordVerifier. These studies do not "
        "evaluate the public blocking polling helper, composite/multiple-source verification, "
        "OpenTelemetry, unrelated SDK integrations or the full release surface. Historical 1.1.0 "
        "results and 2.0 migration retain their original versions; byte-identical numerical modules "
        "alone do not establish end-to-end version equivalence.")
    body = replace_paragraph(body, "The new experiment uses", paragraph)
    return body + "\n\n" + (escape(TAU) if is_tex else TAU)


def limitations(body, result, earlier):
    value = outcome_values(result)
    replacement = ("The external native study exercises ambiguous commits in authored LIMBO tasks "
        "with unchanged service semantics and native grading. It remains one 4B quantized local "
        "model, one declared seed, one base instance per template and one compatible assigned fault "
        "per template, rather than an exhaustive fault cross-product or a task-population sample. "
        "The follow-up condition was frozen after observing partial original results and repairing "
        "runtime paths after host migration; it is not an unseen replication or a replacement of "
        "the original. Both full 96-slot cohorts are retained separately on the same 12 instances. "
        f"The original has {outcome_values(earlier['result'])['available']}/96 audited grades. "
        f"Follow-up native grades are available in {value['available']}/96 planned slots, including "
        f"{value['errors']} audited error returns after settlement; unavailable grades do not become "
        "semantic failures. The guard comparison uses the same control law; descriptive outcome "
        "agreement is not population equivalence. Native status/upsert duplicate accounting and "
        "target-scoped exact-state checks limit exactly-once interpretations. Serial host wall time, "
        "cache and shared load do not isolate SDK overhead. Independently operated service validation, "
        "broader model/task sampling and external replication remain outside these findings.")
    return replace_paragraph(body, "The pending native comparison", replacement)


def conclusion(result, earlier, is_tex):
    value = outcome_values(result)
    outcomes = "; ".join(f"{label} TS/EOS "
        f"{result['arms'][arm]['endpoints']['TS']['true_audited']}/24 and "
        f"{result['arms'][arm]['endpoints']['EOS']['true_audited']}/24" for arm, label in zip(ARMS, LABELS))
    first = ("ConseqaX exposes inspectable boundaries between acknowledgements, admitted evidence, "
        "temporal state, operation-linked origin and explicitly unknown conclusions. The controlled "
        "studies show when polling improves report yield at additional cost and when it adds no "
        "benefit; the equally informed reference shares its gains. The 12-instance external native follow-up "
        f"matrix retains all 96 planned dispositions and {value['available']}/96 audited grades: "
        f"{outcomes}. Its SDK condition emits {value['receipts']} audited receipts in "
        f"{value['receipt_episodes']}/24 planned episodes while preserving the supplied strong guard. "
        f"The original interrupted cohort retains {outcome_values(earlier['result'])['available']}/96 "
        "audited grades and every unknown disposition separately; the same 12 instances are reused. "
        "These finite findings support an executable protocol and observed integration/coverage/cost "
        "tradeoffs rather than algorithmic superiority or universal exactly-once execution.")
    second = ("All three experiments retain the 2.1.1 package pin; the 2.1.2 distribution was released "
        "on 20 October 2026. The accompanying artifact binds protocols, exact source/runtime/wheel "
        "identities, planned schedules, dispositions, saved evidence, audits, analysis and deviations. "
        "The public repository is https://github.com/Devrajsinh-Jhala/consequa-x. A DOI-backed "
        "immutable archive has not been established. Historical replay, model, transfer and migration "
        "evidence retains its original targets and versions. No real payment or production-service "
        "write is part of these experiments.")
    if is_tex:
        second = escape(second).replace("https://github.com/Devrajsinh-Jhala/consequa-x",
            r"\url{https://github.com/Devrajsinh-Jhala/consequa-x}")
        second += r" The evaluated and later release records are cited separately \cite{artifact,currentrelease}."
        return escape(first) + "\n\n" + second
    return first + "\n\n" + second + " The evaluated and later releases are cited separately [7], [19]."


def figure_tex(name, caption, label):
    return (r"\begin{figure*}[t]" + "\n" + r"\centering" + "\n"
        + rf"\includegraphics[width=\textwidth,height=0.67\textheight,keepaspectratio]{{{name}.pdf}}" + "\n"
        + "\\caption{" + escape(caption) + "}\n\\label{" + label + "}\n"
        + r"\end{figure*}" + "\n")


def final_methods(original, protocol, commit, protocol_binding, earlier):
    text = "\n".join(line for line in original.splitlines() if not line.lstrip().startswith("%"))
    replacements = {"The prospective schedule selects": "The frozen schedule selected",
        "Four arms yield": "Four arms defined", "Rotating arm order balances": "Rotating arm order balanced",
        "Prospective native comparison.": "Frozen native comparison.",
        "The official comparison is designed to test this declared\nconformance with autonomous model proposals.":
            "The external comparison retained this declared\ncontrol law under autonomous model proposals.",
        "The candidate runtime uses": "The frozen runtime used",
        "The frozen artifact must bind": "The frozen artifact binds",
        "The candidate configuration is": "The frozen configuration was",
        "The prospective shared ceilings are": "The frozen shared ceilings were",
        "The prospective primary numerator counts": "The registered primary numerator counts",
        "Analysis must retain all planned slots and report": "Analysis retained all planned slots and reports"}
    for before, after in replacements.items():
        if before not in text:
            raise ValueError("Prepared methods template changed: " + before)
        text = text.replace(before, after)
    version = protocol["execution_condition"]["ollama_version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Final methods require the explicit follow-up runtime version")
    text = re.sub(r"version 0\.40\.(?:6|8)", "version " + version, text)
    if "version " + version not in text:
        raise ValueError("Final methods must describe the verified follow-up runtime")
    text = text.replace(r"\texttt{qwen3:4b-instruct-2507-q4\_K\_M}",
                        r"\texttt{\seqsplit{qwen3:4b-instruct-2507-q4\_K\_M}}")
    text = text.replace(r"\href{https://ollama.com/library/qwen3:4b-instruct-2507-q4_K_M}{Ollama}",
                        r"Ollama \cite{ollamaqwen}")
    limits = protocol["limits"]
    expected = {"max_requests": 16, "max_output_tokens": 512, "request_timeout_s": 1200,
        "episode_timeout_s": 7200, "work": {"execute": 96, "verify": 64, "wait": 64,
                                                    "total_wait_seconds": 172800}}
    if limits != expected or protocol["seed"] != 1701:
        raise ValueError("Frozen limits differ from the reviewed final methods template")
    if any(slot["spec"]["max_tool_calls"] != 16 for slot in protocol["schedule"]):
        raise ValueError("Frozen proposal cap differs from the final methods template")
    if protocol["runtime_binding"]["context_tokens"] != 8192 or protocol["runtime_binding"]["parallel_slots"] != 1:
        raise ValueError("Frozen context configuration differs from the final methods template")
    if protocol["environment"]["distributions"]["consequa-x"] != "2.1.1":
        raise ValueError("The proposed paper evaluates package 2.1.1 only")
    provenance = ("The complete schedule, execution sources, native implementation, wheel and runtime "
        "identities for the separately declared follow-up were published before its generation at protocol commit "
        + r"\texttt{\seqsplit{" + commit + "}}. The protocol SHA-256 is "
        + r"\texttt{\seqsplit{" + protocol_binding["sha256"] + "}}. "
        "All 96 planned follow-up dispositions are retained, including errors and unavailable grades. "
        "Source, model and resource bindings are part of the accompanying audit-linked artifact.")
    original_available = outcome_values(earlier["result"])["available"]
    provenance += (" The original cohort at protocol commit "
        + r"\texttt{\seqsplit{" + earlier["result"]["inputs"]["protocol_commit"] + "}}"
        + f" was interrupted after {original_available}/96 native grades became available. "
        "Its original final collector seal and process terminal are unavailable. A separately dated "
        "postcollection preservation archive binds copied original bytes; replay reconstructs only "
        "available sealed child returns. The remaining dispositions stay unknown, including the "
        "interrupted child and every unstarted slot. No original exit status or interruption cause "
        "is invented. Both 96-slot cohorts remain in the paper and artifact.")
    provenance += (" The host migration required explicit runtime-path repairs, a new private runtime "
        "binding and a change from Ollama 0.40.8 to " + escape(version) + ". The follow-up was declared "
        "after access to the partial original data. It reuses the same weights, frozen scientific "
        "sources, task indices, fault assignments, arm order, control settings, limits and analysis. "
        "It is a distinct runtime condition, not a resume, successful-slot replacement or independently "
        "sampled replication. Its within-world contrasts are primary; cross-cohort outcomes and costs "
        "are descriptive and never pooled. The two planned cohorts still contain only 12 unique base instances.")
    position = text.index(r"\subsection{Benchmark")
    text = text[:position] + provenance + "\n\n" + text[position:]
    position = text.index(r"\subsection{Actual SDK")
    text = text[:position] + figure_tex(METHOD_FIGURE, METHOD_CAPTION, "fig:limbo-methods") + "\n" + text[position:]
    return text.strip() + "\n"


def harm_table(result, is_tex):
    keys = ("dup_executed", "dup_live", "dup_compensated", "collateral_records", "extraneous_writes", "n_effects")
    rows = [[label, value["audited_grade_available"], *[value["native_effects"][key]["observed_total"] for key in keys]]
            for arm, label in zip(ARMS, LABELS) for value in (result["arms"][arm],)]
    caption = ("Observed native effect totals from graded slots only. Graded is the availability denominator, "
        "not a success count; unavailable effects are unquantified. Compensated is the native derived "
        "duplicate difference, not a count of compensation calls. Native domain qualifications apply.")
    if not is_tex:
        return ("| Arm | Graded | Dup. executed | Dup. live | Compensated | Collateral | Extraneous | Effects |\n"
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |\n"
            + "\n".join("| " + " | ".join(map(str, row)) + " |" for row in rows) + "\n\n" + caption)
    return (r"\begin{table*}[t]" + "\n\\caption{" + escape(caption) + "}\n"
        + r"\label{tab:limbo-effects}\centering\small" + "\n"
        + r"\begin{tabular}{lrrrrrrr}\toprule" + "\n"
        + r"Arm & Graded & Dup. executed & Dup. live & Compensated & Collateral & Extraneous & Effects \\"
        + "\n\\midrule\n" + "\n".join(" & ".join(map(str, row)) + r" \\" for row in rows)
        + "\n" + r"\bottomrule\end{tabular}\end{table*}" + "\n")


def cohort_disclosures(result, earlier):
    original = earlier["result"]
    counts = []
    for label, value in (("Original interrupted cohort", original), ("Follow-up cohort", result)):
        dispositions = Counter()
        for arm in ARMS:
            dispositions.update(value["arms"][arm]["dispositions"])
        counts.append(label + ": " + "; ".join(f"{name} {count}" for name, count in sorted(dispositions.items())) + ".")
    values = outcome_values(original)
    original_endpoints = "; ".join(f"{label} TS/EOS "
        f"{original['arms'][arm]['endpoints']['TS']['true_audited']}/24 and "
        f"{original['arms'][arm]['endpoints']['EOS']['true_audited']}/24" for arm, label in zip(ARMS, LABELS))
    return ("The original interrupted cohort retains its full 96-slot denominator: "
        f"{values['available']} independently replayed grades, {values['errors']} native error returns "
        f"among those grades, and {96 - values['available']} unavailable grades. Its all-planned counts "
        f"are {original_endpoints}. The original collector's final seal is unavailable; its audit binds "
        "a later copy-only preservation archive and does not manufacture missing terminal evidence. "
        "The separately published follow-up is the primary runtime condition below. Both cohorts reuse "
        "the same 12 base instances and 24 condition definitions; they are not pooled or counted as "
        "192 independent tasks. " + " ".join(counts))


def native_results(result, analysis, is_tex, earlier):
    paragraphs = (analysis / "narrative.md").read_text(encoding="utf-8").strip().split("\n\n")
    if len(paragraphs) != 7:
        raise ValueError("Frozen analysis narrative shape changed")
    selected = [paragraphs[index] for index in (0, 2, 3, 5)]
    secondary = "; ".join(f"{label}: clean-success "
        f"{result['arms'][arm]['endpoints']['clean_success']['true_audited']}/24 and exact-state "
        f"{result['arms'][arm]['endpoints']['exact_state']['true_audited']}/24"
        for arm, label in zip(ARMS, LABELS))
    secondary = "Secondary native endpoint counts were " + secondary + ". Missing grades do not count as true; exact-state checks target counts only."
    known_input = sum(result["arms"][arm]["usage"]["input_tokens"]["observed_token_total"] for arm in ARMS)
    known_output = sum(result["arms"][arm]["usage"]["output_tokens"]["observed_token_total"] for arm in ARMS)
    unknown_input = sum(result["arms"][arm]["usage"]["input_tokens"]["unknown_invocations_among_audited_rows"] for arm in ARMS)
    unknown_output = sum(result["arms"][arm]["usage"]["output_tokens"]["unknown_invocations_among_audited_rows"] for arm in ARMS)
    usage = (f"Across slots with complete audited accounting, journals retain {known_input} known input "
        f"tokens and {known_output} known output tokens, with {unknown_input} invocations lacking input "
        f"usage and {unknown_output} lacking output usage. These are observed totals, not complete "
        "usage for slots without accounting. Cached input is already included in input totals. "
        "The artifact reports per-arm counts, assigned-fault/template/domain strata, paired contrasts "
        "and missingness without population significance or equivalence claims.")
    captions = {"limbo-outcomes": "Native TS/EOS true, false and unavailable grades over all 24 planned slots per arm. Error returns with audited settled grades remain physically assessable.",
        "limbo-stratification": "Native EOS true over all planned slots by base template and assigned fault. Unavailable grades remain marked. Strata are finite and descriptive; fault triggering is not an inclusion rule.",
        "limbo-costs": "Observed execute, public verification and model-dispatch totals from complete audited rows. Missing-row work is unquantified. Boundary attempts are not physical effect counts or isolated SDK overhead."}
    disclosure = cohort_disclosures(result, earlier)
    if is_tex:
        first = (r"\section{External Native Results}\label{sec:limbo-results}" + "\n\n"
            + escape(disclosure) + "\n\n" + r"\input{limbo-cohort-accounting.tex}" + "\n\n"
            + escape(selected[0]) + "\n\n" + r"\begin{table}[t]" + "\n"
            + r"\caption{All-planned native results. Graded means an independently replayed native grade; it includes native error returns after settlement. Missing is not an invented semantic zero.}"
            + "\n" + r"\label{tab:limbo-results}\centering\small\setlength{\tabcolsep}{3pt}" + "\n"
            + r"\input{limbo-results-table.tex}" + "\n" + r"\end{table}" + "\n\n")
        return (first + "\n\n".join(escape(paragraph) for paragraph in selected[1:] + [secondary, usage])
            + "\n\n" + harm_table(result, True) + "\n"
            + "\n".join(figure_tex(name, captions[name], "fig:" + name) for name in NEW_FIGURES))
    table = ["| Arm | Planned | Graded | TS true | EOS true | Missing |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for arm, label in zip(ARMS, LABELS):
        value = result["arms"][arm]
        table.append(f"| {label} | 24 | {value['audited_grade_available']} | "
            f"{value['endpoints']['TS']['true_audited']} | {value['endpoints']['EOS']['true_audited']} | {value['grade_unavailable']} |")
    cohorts = ["| Cohort | Arm | Planned | Started | Graded | Error returns | Unavailable | TS | EOS |",
               "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for cohort, source in (("Original interrupted", earlier["result"]), ("Follow-up", result)):
        for arm, label in zip(ARMS, LABELS):
            value = source["arms"][arm]
            cohorts.append("| " + " | ".join(map(str, (cohort, label, 24, value["started"],
                value["audited_grade_available"], value["audited_native_error_returns"],
                value["grade_unavailable"], value["endpoints"]["TS"]["true_audited"],
                value["endpoints"]["EOS"]["true_audited"]))) + " |")
    return ("## 7. External Native Results\n\n" + disclosure + "\n\n" + "\n".join(cohorts)
        + "\n\n" + selected[0] + "\n\n" + "\n".join(table)
        + "\n\n" + "\n\n".join(selected[1:] + [secondary, usage]) + "\n\n" + harm_table(result, False)
        + "\n\n" + "\n\n".join(f"![{captions[name]}](figures/{name}.svg)" for name in NEW_FIGURES))


NEW_REFERENCES = (
    ("limbosource", r"J. Li, ``LIMBO: Benchmark code, harness adapters and episode traces,'' MIT software, commit \texttt{\seqsplit{2db09fba22a0572a70639162a808906409f612a8}}, 2026. [Online]. Available: \url{https://github.com/jaxblack/limbo-bench/tree/2db09fba22a0572a70639162a808906409f612a8}",
     "J. Li. *LIMBO: Benchmark code, harness adapters and episode traces*. MIT software, commit `2db09fba22a0572a70639162a808906409f612a8`, 2026. [Pinned author source](https://github.com/jaxblack/limbo-bench/tree/2db09fba22a0572a70639162a808906409f612a8)."),
    ("qwenmodel", r"Qwen Team, ``Qwen3-4B-Instruct-2507,'' official model card, Apache 2.0. [Online]. Available: \url{https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507}",
     "Qwen Team. *Qwen3-4B-Instruct-2507*. Official model card, Apache 2.0. [Model card](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507)."),
    ("ollamaqwen", r"Ollama, ``qwen3:4b-instruct-2507-q4\_K\_M,'' Q4\_K\_M model distribution. [Online]. Available: \url{https://ollama.com/library/qwen3:4b-instruct-2507-q4_K_M}",
     "Ollama. *qwen3:4b-instruct-2507-q4_K_M*. Exact Q4_K_M model distribution; actual bytes are pinned in the runtime binding. [Distribution tag](https://ollama.com/library/qwen3:4b-instruct-2507-q4_K_M)."),
    ("ollamaruntime", r"Ollama, ``Ollama,'' software vers. 0.40.8 and 0.40.10. Exact evaluated executable bytes are bound separately by cohort. [Online]. Available: \url{https://github.com/ollama/ollama/releases}",
     "Ollama. *Ollama*, software versions 0.40.8 and 0.40.10. Exact evaluated executable bytes are bound separately by cohort. [Official releases](https://github.com/ollama/ollama/releases)."),
)


def methods_markdown(tex, bibliography_keys):
    text = tex
    text = re.sub(r"\\begin\{table\}.*?\\end\{table\}",
        "| Arm | Execution rule |\n| --- | --- |\n"
        "| Vanilla | Unchanged native direct dispatch. |\n"
        "| SDK retry | Unchanged native rule: up to three retries after the initial retryable failure. |\n"
        "| Native guard | Unchanged strong key/verification/suppression rule. |\n"
        "| ConseqaX guard | The same guard consuming actual SDK receipt statuses. |", text, flags=re.S)
    text = re.sub(r"\\begin\{figure\*\}.*?\\end\{figure\*\}",
        lambda _match: f"![{METHOD_CAPTION}](figures/{METHOD_FIGURE}.svg)", text, flags=re.S)
    text = re.sub(r"\\section\{([^{}]+)\}", r"## 6. \1", text)
    count = 0
    def subsection(match):
        nonlocal count
        count += 1
        return f"### 6.{count} {match.group(1)}"
    text = re.sub(r"\\subsection\{([^{}]+)\}", subsection, text)
    text = re.sub(r"\\label\{[^{}]+\}", "", text)
    text = re.sub(r"\\texttt\{\\seqsplit\{([^{}]+)\}\}", r"`\1`", text)
    text = re.sub(r"\\texttt\{([^{}]+)\}", r"`\1`", text)
    text = re.sub(r"\\cite\{([^{}]+)\}", lambda match: ", ".join(
        f"[{bibliography_keys.index(key) + 1}]" for key in match.group(1).split(",")), text)
    text = text.replace(r"\_", "_").replace(r"\&", "&").replace(r"\%", "%")
    if re.search(r"\\(?:begin|end|texttt|seqsplit|cite|href|section|subsection)\b", text):
        raise ValueError("Unsupported TeX remains in the mirrored methods")
    return text.strip()


def assemble(tex, md, methods, result, analysis, earlier):
    sections = tex_sections(tex)
    readable = markdown_sections(md)
    required = ("Introduction", "Related Work and Positioning", "Evidence and Recovery Protocol",
        "Frozen Closed-Loop Study", "Recovery Results", "Supporting Evidence and Version Boundaries",
        "Discussion and Limitations", "Conclusion and Artifact Availability")
    if any(name not in sections or name not in readable for name in required):
        raise ValueError("Current manuscript section structure changed; review the preparation template")
    preamble = tex[:tex.index(r"\begin{abstract}")]
    if "Independent Researcher" not in preamble or "IEEEtran" not in preamble:
        raise ValueError("Expected generic IEEE independent-researcher manuscript")
    abstract_text = abstract(result, earlier)
    intro = introduction(sections["Introduction"], True)
    related_text = related(sections["Related Work and Positioning"], True)
    support = supporting(sections["Supporting Evidence and Version Boundaries"], True)
    discussion = limitations(sections["Discussion and Limitations"], result, earlier)
    keyword = re.search(r"\\begin\{IEEEkeywords\}.*?\\end\{IEEEkeywords\}", tex, re.S).group(0)
    body = preamble + "\\begin{abstract}\n" + escape(abstract_text) + "\n\\end{abstract}\n" + keyword + "\n\n"
    for name, text in (("Introduction", intro), ("Related Work and Positioning", related_text),
        ("Evidence and Recovery Protocol", protocol_scope(sections["Evidence and Recovery Protocol"])),
        ("Frozen Closed-Loop Study", sections["Frozen Closed-Loop Study"]),
        ("Recovery Results", r"\input{recovery-study-results.tex}")):
        body += "\\section{" + name + "}\n\n" + text + "\n\n"
    body += r"\input{limbo-native-methods.tex}" + "\n" + r"\input{limbo-native-results.tex}" + "\n\n"
    for name, text in (("Supporting Evidence and Version Boundaries", support),
        ("Discussion and Limitations", discussion), ("Conclusion and Artifact Availability", conclusion(result, earlier, True))):
        body += "\\section{" + name + "}\n\n" + text + "\n\n"
    tail = tex[tex.index(r"\section*{AI Assistance"):]
    if len(re.findall(r"\\bibitem\{([^{}]+)\}", tail)) != 19:
        raise ValueError("Baseline bibliography changed; review Markdown citation numbering")
    if any(r"\bibitem{" + key + "}" in tail for key, _tex, _md in NEW_REFERENCES):
        raise ValueError("Final bibliography already contains proposed keys; review rather than duplicate")
    additions = "\n".join(r"\bibitem{" + key + "}\n" + entry for key, entry, _md in NEW_REFERENCES) + "\n"
    body += tail.replace(r"\end{thebibliography}", additions + r"\end{thebibliography}")
    bibliography_keys = re.findall(r"\\bibitem\{([^{}]+)\}", body)
    md_intro = introduction(readable["Introduction"], False)
    md_related = related(readable["Related Work and Positioning"], False)
    md_support = supporting(readable["Supporting Evidence and Version Boundaries"], False)
    md_discussion = limitations(readable["Discussion and Limitations"], result, earlier)
    readable_body = ("# ConseqaX: An Evidence Protocol for Recovering Ambiguous Agent Actions\n\n"
        "Devrajsinh Jhala\n\nIndependent Researcher\n\n"
        "Generic IEEE manuscript reporting controlled and externally authored simulator studies. "
        "No venue or acceptance is asserted.\n\n## Abstract\n\n" + abstract_text + "\n\n"
        "**Index terms:** agent systems, outcome verification, recovery, idempotency, evidence provenance, uncertainty\n\n")
    for number, name, text in ((1, "Introduction", md_intro), (2, "Related Work and Positioning", md_related),
        (3, "Evidence and Recovery Protocol", protocol_scope(readable["Evidence and Recovery Protocol"])),
        (4, "Frozen Closed-Loop Study", readable["Frozen Closed-Loop Study"]),
        (5, "Recovery Results", readable["Recovery Results"])):
        readable_body += f"## {number}. {name}\n\n{text}\n\n"
    readable_body += methods_markdown(methods, bibliography_keys) + "\n\n" + native_results(result, analysis, False, earlier) + "\n\n"
    for number, name, text in ((8, "Supporting Evidence and Version Boundaries", md_support),
        (9, "Discussion and Limitations", md_discussion), (10, "Conclusion and Artifact Availability", conclusion(result, earlier, False))):
        readable_body += f"## {number}. {name}\n\n{text}\n\n"
    md_tail = md[md.index("## AI Assistance"):].rstrip()
    md_tail = md_tail.replace("current MIT Python distribution, 2.1.2", "MIT Python distribution, 2.1.2")
    readable_body += md_tail + "\n" + "\n".join(f"{20 + index}. {entry}" for index, (_key, _tex, entry) in enumerate(NEW_REFERENCES)) + "\n"
    return body, readable_body


def reject_stale(text):
    patterns = (r"\bTODO\b", r"\bTBD\b", r"pending native comparison", r"prospective external comparison",
        r"Native Integration and Prospective External Pilot", r"48 planned trajectories",
        r"12 distinct airline task IDs", r"native-four-arm-methods", r"native-external-validation\.tex",
        r"The next fault-focused validation should", r"The prospective (?:schedule|shared ceilings|primary numerator)",
        r"official comparison is designed to", r"candidate runtime", r"candidate configuration",
        r"completed autonomous benchmark evaluation\s+is asserted")
    for pattern in patterns:
        if re.search(pattern, text, re.I):
            raise ValueError("Stale/provisional manuscript text remains: " + pattern)


def prepare(args):
    root = ROOT
    b = helper(root)
    helper_path = root / "scripts/build_final_limbo_paper.py"
    code_bindings = {str(Path(__file__).resolve()): b.binding(Path(__file__)),
                     str(helper_path): b.binding(helper_path)}
    commit = b.exact_commit(args.protocol_commit, "--protocol-commit")
    analysis, protocol, output = args.analysis.resolve(), args.protocol.resolve(), args.output.resolve()
    b.require(not output.exists(), "Refuse an existing staging directory")
    b.require(not output.is_relative_to(analysis) and not analysis.is_relative_to(output),
              "Staging must not overlap the sealed analysis")
    b.require(protocol.is_relative_to(root), "Protocol must belong to this repository")
    interrupted_commit = b.exact_commit(args.interrupted_protocol_commit, "--interrupted-protocol-commit")
    interrupted_analysis, interrupted_protocol = args.interrupted_analysis.resolve(), args.interrupted_protocol.resolve()
    b.require(interrupted_protocol.is_relative_to(root), "Original protocol must belong to this repository")
    checked, earlier = b.validate_cohorts(root, analysis, protocol, commit,
        interrupted_analysis, interrupted_protocol, interrupted_commit, commit)
    result, frozen = checked["result"], checked["protocol"]
    source_names = list(BASE_SOURCES)
    for stem in OLD_FIGURES + (METHOD_FIGURE,):
        for extension in ("pdf", "svg", "png"):
            name = f"paper/figures/{stem}.{extension}"
            if (root / name).is_file():
                source_names.append(name)
            elif extension == "pdf" or stem == METHOD_FIGURE:
                raise ValueError("Missing existing bound figure: " + name)
    for extension in ("pdf", "svg", "png"):
        b.committed_file(root, f"paper/figures/{METHOD_FIGURE}.{extension}", commit)
    originals = {name: (root / name).read_bytes() for name in source_names}
    original_bindings = {name: b.byte_binding(data) for name, data in originals.items()}
    methods = final_methods(originals["paper/limbo-native-methods.tex"].decode("utf-8"), frozen, commit,
                            b.binding(protocol), earlier)
    paper_tex, paper_md = assemble(originals["paper/conseqax-research.tex"].decode("utf-8"),
        originals["paper/conseqax-research.md"].decode("utf-8"), methods, result, analysis, earlier)
    result_tex = native_results(result, analysis, True, earlier)
    for text in (paper_tex, paper_md, methods, result_tex):
        reject_stale(text)
    output.mkdir(parents=True, exist_ok=False)
    paper = output / "paper"
    (paper / "figures").mkdir(parents=True)
    for name, data in originals.items():
        target = output / "inputs/source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        if name.startswith("paper/figures/") or name.endswith(("recovery-study-results.tex", "recovery-availability-results.tex")):
            destination = output / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
    for name, text in (("conseqax-research.tex", paper_tex), ("conseqax-research.md", paper_md),
                        ("limbo-native-methods.tex", methods), ("limbo-native-results.tex", result_tex)):
        (paper / name).write_text(text, encoding="utf-8", newline="\n")
    shutil.copyfile(analysis / "results.tex", paper / "limbo-results-table.tex")
    (paper / "limbo-cohort-accounting.tex").write_text(b.cohort_accounting_tex(checked, earlier),
        encoding="utf-8", newline="\n")
    for stem in NEW_FIGURES:
        for extension in ("pdf", "svg", "png"):
            shutil.copyfile(analysis / f"{stem}.{extension}", paper / "figures" / f"{stem}.{extension}")
    shutil.copytree(analysis, output / "inputs/analysis")
    shutil.copytree(interrupted_analysis, output / "inputs/interrupted-analysis")
    shutil.copyfile(protocol, output / "inputs/protocol.json")
    shutil.copyfile(interrupted_protocol, output / "inputs/interrupted-protocol.json")
    for path in (Path(__file__).resolve(), root / "scripts/build_final_limbo_paper.py"):
        shutil.copyfile(path, output / "inputs" / (path.stem + ".source.py"))
    names, edges = b.discover_sources(output)
    b.validate_paper_assets(output, names, analysis)
    b.require(b.check_manifest(analysis) == checked["sealed"]
              and b.check_manifest(output / "inputs/analysis") == checked["sealed"],
              "Sealed analysis changed during preparation/copy")
    b.require(b.check_manifest(interrupted_analysis) == earlier["sealed"]
              and b.check_manifest(output / "inputs/interrupted-analysis") == earlier["sealed"],
              "Original interrupted analysis changed during preparation/copy")
    b.require(b.binding(protocol) == checked["audit"]["protocol"]
              and b.binding(output / "inputs/protocol.json") == checked["audit"]["protocol"],
              "Protocol changed during preparation/copy")
    b.require(b.binding(interrupted_protocol) == earlier["audit"]["protocol"]
              and b.binding(output / "inputs/interrupted-protocol.json") == earlier["audit"]["protocol"],
              "Original protocol changed during preparation/copy")
    b.require(all((root / name).read_bytes() == data for name, data in originals.items()),
              "Baseline source changed during preparation")
    b.require(all(b.binding(Path(name)) == expected for name, expected in code_bindings.items()),
              "Preparation/checking code changed during preparation")
    b.require(b.binding(root / "scripts/analyze_limbo_external_benchmark.py") == checked["analyzer_binding"],
              "Frozen analyzer changed during preparation")
    for extension in ("pdf", "svg", "png"):
        name = f"paper/figures/{METHOD_FIGURE}.{extension}"
        b.require(b.committed_file(root, name, commit) == original_bindings[name],
                  "Published methods figure changed during preparation")
    values = outcome_values(result)
    dispositions = dict(sorted(Counter(row["status"] for row in checked["audit"]["rows"]).items()))
    b.write_json(output / "preparation-receipt.json", {"schema": "conseqax-final-paper-preparation-v1",
        "status": "REVIEW_PENDING",
        "prepared_utc": datetime.now(timezone.utc).isoformat(), "protocol_commit": commit,
        "protocol": b.binding(protocol), "analysis_manifest": checked["sealed"]["manifest"],
        "analysis_values_recomputed": True, "planned_slots": 96, "base_instances": 12,
        "interrupted_cohort": {"protocol_commit": interrupted_commit,
            "protocol": b.binding(interrupted_protocol), "analysis_manifest": earlier["sealed"]["manifest"],
            "planned_slots": 96, "grade_available": outcome_values(earlier["result"])["available"],
            "dispositions": dict(sorted(Counter(row["status"] for row in earlier["audit"]["rows"]).items()))},
        "both_cohorts_retained_separately": True, "cohorts_pooled": False,
        "native_grade_available": values["available"], "native_error_returns": values["errors"],
        "receipt_count": values["receipts"], "receipt_episodes": values["receipt_episodes"],
        "dispositions": dispositions, "source_inputs": original_bindings,
        "proposed_manuscript_files": {name: b.binding(output / name) for name in names},
        "dependency_edges": edges, "preparer": code_bindings[str(Path(__file__).resolve())],
        "validation_helper": code_bindings[str(helper_path)],
        "current_working_paper_modified": False, "new_pdf_created": False,
        "new_model_calls": 0, "new_native_evaluations": 0, "human_labels": 0,
        "visual_review_pending": True, "proposed_sources_require_lead_review": True,
        "all_tasks_successful_or_conference_acceptance_is_not_asserted": True})
    (output / "README.md").write_text(
        "# Proposed final ConseqaX manuscript\n\n"
        "The paper/ folder is a complete proposed TeX and readable manuscript derived from "
        "the sealed passed follow-up 96-slot native analysis, the separately retained original "
        "interrupted 96-slot cohort and Studies A/B. Both native cohorts reuse the same 12 base "
        "instances; they are not pooled and do not create independently sampled tasks. "
        "The working paper was not modified. Existing figures were copied; no new PDF, model "
        "call, native evaluation, human label or Git mutation was performed by preparation.\n\n"
        "Review the proposed sources, actual counts, assumptions and figure captions before "
        "applying the paper/ files to the repository. Commit the reviewed sources, then use "
        "build_final_limbo_paper.py with an exact source commit to compile and render them. "
        "Compilation and every-page visual QA remain pending; this preparation receipt is "
        "not a claim of final document quality, universal exactly-once execution or venue acceptance.\n\n"
        "inputs/ preserves the original paper sources, sealed analysis, exact protocol and "
        "preparation/checking code. The final artifact retains error/missing denominators and "
        "the audit's SDK/tokenizer/service-verification scope limits.\n", encoding="utf-8", newline="\n")
    b.write_json(output / "manifest.json", {path.relative_to(output).as_posix(): b.binding(path)
        for path in sorted(output.rglob("*")) if path.is_file()})
    b.check_manifest(output)
    return {"output": str(output), "proposed_paper": str(paper / "conseqax-research.tex"),
        "protocol_commit": commit, "planned_slots": 96, "native_grade_available": values["available"],
        "status": "REVIEW_PENDING", "visual_review_pending": True, "current_working_paper_modified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", required=True, type=Path)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--protocol-commit", required=True)
    parser.add_argument("--interrupted-analysis", required=True, type=Path)
    parser.add_argument("--interrupted-protocol", required=True, type=Path)
    parser.add_argument("--interrupted-protocol-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args), sort_keys=True))


if __name__ == "__main__":
    main()
