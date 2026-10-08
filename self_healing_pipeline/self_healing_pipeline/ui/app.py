"""
Self-Healing Recommendations - Streamlit UI.

    streamlit run ui/app.py            (or:  python main.py --ui)

Reads the pipeline's MongoDB output (recommendations, incidents, resource profiles) and the source logs.
The UI never executes anything against your cloud - actions are shown for a human to review.
"""
import json
import os
import sys

import altair as alt
import pandas as pd
import streamlit as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

from ui import data as D  # noqa: E402

st.set_page_config(page_title="Self-Healing Recommendations", page_icon="🛠️", layout="wide")

PAGES = ["Overview", "Incident detail", "Resource explorer", "Evaluation", "Pipeline", "Data dictionary"]
SEV_COLORS = alt.Scale(domain=["CRIT", "WARN"], range=["#d62728", "#ff9f1c"])


@st.cache_resource
def _client():
    return D.get_client()


def _naive(df: pd.DataFrame, cols) -> pd.DataFrame:
    df = df.copy()
    for c in cols:
        if c in df and not df[c].isna().all():
            df[c] = pd.to_datetime(df[c], utc=True).dt.tz_convert("UTC").dt.tz_localize(None)
    return df


def _go(incident_id: str):
    st.session_state["incident_id"] = incident_id
    st.session_state["nav"] = "Incident detail"


def _fmt_ts(x):
    return "-" if x is None or (isinstance(x, float) and pd.isna(x)) else str(x)[:16].replace("T", " ")


# ── connection ────────────────────────────────────────────────────────────────
db = D.get_db(_client())
err = D.ping(db)
if err:
    st.error("Cannot reach MongoDB.")
    st.code(f"{err}\n\nCheck MONGO_URI in .env (currently: {D.MONGO_URI}) and that mongod is running.")
    st.stop()

# ── sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.title("🛠️ Self-healing")
st.sidebar.caption("Recommendations only - nothing is executed automatically.")
st.sidebar.radio("Page", PAGES, key="nav")
if st.sidebar.button("↻ Refresh data"):
    st.rerun()
st.sidebar.caption(f"DB: `{D.MONGO_DB_NAME}`")
page = st.session_state["nav"]


# ── charts ────────────────────────────────────────────────────────────────────

def metric_chart(series, alerts, window, title, thresholds=()):
    if series.empty:
        st.caption(f"No data for {title}")
        return
    s = _naive(series, ["time"])
    layers = [alt.Chart(s).mark_line(color="#1f77b4").encode(
        x=alt.X("time:T", title=None), y=alt.Y("value:Q", title=title, scale=alt.Scale(zero=False)),
        tooltip=["time:T", alt.Tooltip("value:Q", format=",.2f")])]
    if window:
        w = _naive(pd.DataFrame([{"start": window[0], "end": window[1]}]), ["start", "end"])
        layers.insert(0, alt.Chart(w).mark_rect(opacity=0.10, color="#d62728").encode(x="start:T", x2="end:T"))
    if alerts is not None and not alerts.empty:
        a = _naive(alerts, ["fired", "resolved"])
        layers.append(alt.Chart(a).mark_rule(strokeDash=[4, 3], size=2).encode(
            x="fired:T", color=alt.Color("severity:N", scale=SEV_COLORS, legend=alt.Legend(title="alert fired")),
            tooltip=["rule", "severity", "fired:T", "resolved:T"]))
    for t in thresholds:
        layers.append(alt.Chart(pd.DataFrame({"y": [t]})).mark_rule(color="#888", strokeDash=[2, 2]).encode(y="y:Q"))
    st.altair_chart(alt.layer(*layers).properties(height=230, width="container"))


# ═════════════════════════════════ OVERVIEW ══════════════════════════════════
def page_overview():
    st.header("Overview")
    recs = D.load_recommendations(db)
    if not recs:
        st.info("No recommendations yet. Open the **Pipeline** page to load the dataset and run the pipeline.")
        return
    df = D.recs_frame(recs)
    c = st.columns(5)
    c[0].metric("Incidents", len(df))
    c[1].metric("Open", int((df.status == "open").sum()))
    c[2].metric("Open P1", int(((df.status == "open") & (df.priority == "P1")).sum()))
    c[3].metric("Resolved", int((df.status == "resolved").sum()))
    c[4].metric("Avg confidence", f"{df.confidence.mean():.0%}")

    with st.expander("Filters", expanded=True):
        f = st.columns(5)
        pri = f[0].multiselect("Priority", ["P1", "P2", "P3"], default=["P1", "P2", "P3"])
        cloud = f[1].multiselect("Cloud", sorted(df.cloud.unique()), default=sorted(df.cloud.unique()))
        status = f[2].multiselect("Status", ["open", "resolved"], default=["open", "resolved"])
        uc = f[3].multiselect("Use case", sorted(df["use case"].unique()))
        rc = f[4].multiselect("Root cause", sorted(df["root cause"].unique()))
        q = st.text_input("Search resource")
    v = df[df.priority.isin(pri) & df.cloud.isin(cloud) & df.status.isin(status)]
    if uc:
        v = v[v["use case"].isin(uc)]
    if rc:
        v = v[v["root cause"].isin(rc)]
    if q:
        v = v[v.resource.str.contains(q, case=False)]
    v = v.reset_index(drop=True)

    g = st.columns(3)
    for col, key, title in ((g[0], "root cause", "By root cause"), (g[1], "use case", "By use case"), (g[2], "cloud", "By cloud")):
        cnt = v[key].value_counts().rename_axis(key).reset_index(name="incidents")
        col.caption(title)
        if not cnt.empty:
            col.altair_chart(alt.Chart(cnt).mark_bar().encode(
                y=alt.Y(f"{key}:N", sort="-x", title=None), x=alt.X("incidents:Q", title=None),
                tooltip=[key, "incidents"]).properties(height=max(120, 26 * len(cnt)), width="container"))

    st.subheader(f"Incidents ({len(v)})")
    view = v.drop(columns=["id"]).copy()
    view["priority"] = view["priority"].map(D.PRIORITY_ICON)
    view["confidence"] = view["confidence"].map(lambda x: f"{x:.0%}")
    view["first alert"] = view["first alert"].dt.strftime("%Y-%m-%d %H:%M")
    view["resolved"] = pd.to_datetime(view["resolved"], utc=True).dt.strftime("%Y-%m-%d %H:%M").fillna("-")
    ev = st.dataframe(view, hide_index=True, on_select="rerun", selection_mode="single-row", key="ov_table")
    rows = ev.selection.rows if ev is not None else []
    if rows:
        st.button("Open selected incident →", on_click=_go, args=(v.loc[rows[0], "id"],), type="primary")
    else:
        st.caption("Select a row, then open it - or use the **Incident detail** page.")


# ═══════════════════════════ INCIDENT DETAIL ═════════════════════════════════
def page_detail():
    st.header("Incident detail")
    recs = D.load_recommendations(db)
    if not recs:
        st.info("No recommendations yet.")
        return
    df = D.recs_frame(recs)
    ids = list(df["id"])
    label = {r.id: f"{D.PRIORITY_ICON[r.priority]} | {r['first alert']:%m-%d %H:%M} | {r.cloud} | {r.resource} | {r['root cause']} | {r.status}"
             for _, r in df.iterrows()}
    if st.session_state.get("incident_id") not in ids:
        st.session_state["incident_id"] = ids[0]
    iid = st.selectbox("Incident", ids, format_func=lambda i: label[i], key="incident_id")
    rec = next(r for r in recs if r["_id"] == iid)
    rc = rec["root_cause"]

    st.subheader(f"{D.PRIORITY_ICON[rec['priority']]}  {rec['title']}")
    st.caption(f"{rec['provider']} · {rec['resource_type']} · tier **{rec.get('tier')}** · app **{rec.get('app')}** · "
               f"{rec['use_case']} {rec['use_case_title']} · status **{rec['status']}** · priority reason: {rec['priority_reason']}")
    k = st.columns(5)
    k[0].metric("Root cause", rc["id"])
    k[1].metric("Confidence", f"{rc['confidence']:.0%}")
    k[2].metric("Source alerts", len(rec["alerts"]))
    k[3].metric("First alert", _fmt_ts(rec["first_alert_at"]))
    k[4].metric("Resolved", _fmt_ts(rec.get("resolved_at")))
    st.info(rec["summary"])

    t_diag, t_alerts, t_act, t_stats, t_hist = st.tabs(
        ["Diagnosis", "Alerts & correlation", "Actions", "Statistics & trends", "History"])

    with t_diag:
        ex = rec["explanation"]
        st.markdown("#### Explanation")
        for key, title in (("why_this_cause", "Why this cause"), ("what_to_do", "What to do"),
                           ("what_to_watch", "What to watch"), ("confidence_note", "Confidence")):
            st.markdown(f"**{title}.** {ex['sections'].get(key, '')}")
        st.caption(f"explanation source: **{ex['source']}** ({ex['note']}). Decisions come from the rule-based analysis; "
                   "the LLM only words the explanation.")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"#### Evidence for **{rc['id']}**")
            st.markdown("\n".join(f"- ✅ {e}" for e in rc["evidence"]) or "_none_")
            if rc["counter_evidence"]:
                st.markdown("**Facts that do not fit perfectly**")
                st.markdown("\n".join(f"- ⚠️ {e}" for e in rc["counter_evidence"]))
        with c2:
            st.markdown("#### Hypotheses considered")
            h = D.hypotheses_frame(rec)
            st.altair_chart(alt.Chart(h).mark_bar().encode(
                y=alt.Y("cause:N", sort="-x", title=None), x=alt.X("score:Q", scale=alt.Scale(domain=[0, 1])),
                color=alt.condition(alt.datum.cause == rc["id"], alt.value("#2ca02c"), alt.value("#9aa0a6")),
                tooltip=["cause", "score"]).properties(height=170, width="container"))
            for a in rc["alternatives"]:
                st.caption(f"~ {a}")
        with st.expander("How the confidence was computed"):
            st.json(rc["confidence_parts"])

        st.markdown("#### Metrics around the incident")
        win = D.incident_window(rec)
        alerting = set(rec["correlation"]["intra_resource"]["alerting_metrics"])
        shown = 0
        for nm in D.native_metrics(db, rec["resource_id"]):
            series, alerts, canon = D.metric_series(db, rec["resource_id"], nm, *win)
            if canon in alerting and shown < 4:
                thr = sorted({a["threshold"] for a in rec["alerts"] if a["metric"] == canon and a["condition_type"] == "static"
                              and a["threshold"] is not None})
                metric_chart(series, alerts, (D.as_utc(rec["first_alert_at"]), D.as_utc(rec.get("resolved_at")) or D.as_utc(rec["last_alert_at"])),
                             canon, thr)
                shown += 1
        if not shown:
            st.caption("Source logs not available in this database - only the analysis is shown.")

    with t_alerts:
        st.markdown("#### Source alerts")
        af = D.alerts_frame(rec)
        st.dataframe(af, hide_index=True)
        corr = rec["correlation"]
        st.markdown("#### Correlation")
        st.write(corr["summary"] or "No correlated alerts on other resources.")
        ir = corr["intra_resource"]
        c = st.columns(3)
        c[0].markdown("**Alerting metrics**\n\n" + (", ".join(ir["alerting_metrics"]) or "-"))
        c[1].markdown("**Quiet metrics**\n\n" + (", ".join(ir["quiet_metrics"]) or "-"))
        c[2].markdown("**Deviating without alert**\n\n" + (", ".join(ir["deviating_without_alert"]) or "-"))
        for name, key in (("Upstream", "upstream"), ("Same-tier peers", "same_tier_peers"), ("Downstream", "downstream")):
            if corr[key]:
                st.markdown(f"**{name}**")
                st.dataframe(pd.DataFrame(corr[key]), hide_index=True)
        if corr["domain_rules"]:
            st.markdown("**Domain rules matched**")
            st.json(corr["domain_rules"])
        tl = D.timeline_frame(rec)
        if not tl.empty:
            st.markdown("**Alert timeline across correlated resources**")
            st.dataframe(tl, hide_index=True)

    with t_act:
        st.warning("These are recommendations for a human to review and approve. Nothing is executed automatically.")
        if rec["do_not_do"]:
            st.error("**Do NOT**\n\n" + "\n".join(f"- {d}" for d in rec["do_not_do"]))
        for phase, title in (("now", "Now (first minutes)"), ("fix", "Fix (hours to a day)"), ("prevent", "Prevent (follow-up)")):
            acts = [a for a in rec["actions"] if a["phase"] == phase]
            if not acts:
                continue
            st.markdown(f"#### {title}")
            for a in acts:
                flag = " · ⚠️ disruptive" if a["disruptive"] else ""
                with st.expander(f"{a['title']}  ({a['kind']}){flag}", expanded=(phase == "now")):
                    st.write(a["detail"])
                    if a["expected_effect"]:
                        st.caption(f"Expected effect: {a['expected_effect']}")
                    for cmd in a["commands"]:
                        st.caption(f"{'🔧 changes the system' if cmd['mutating'] else '🔍 read-only'} - {cmd['purpose']}")
                        st.code(cmd["command"], language="bash")
        st.success(f"**Verify:** {rec['verification']}")
        r = rec["risk_if_ignored"]
        st.markdown(f"**If ignored** - 1 h: {r['1h']}  \n24 h: {r['24h']}  \n7 d: {r['7d']}")

    with t_stats:
        tr = D.trends_frame(rec)
        if not tr.empty:
            st.markdown("#### Trends (seasonality-aware)")
            st.dataframe(tr, hide_index=True)
        ms = rec["statistics"]["metrics"]
        if ms:
            st.markdown("#### Metric statistics on the incident day")
            st.dataframe(pd.DataFrame(ms).T.reset_index(names="metric"), hide_index=True)
        if rec.get("ml"):
            m = rec["ml"]
            st.markdown(f"#### Light ML (Isolation Forest, {m['model_level']} model, n={m['training_samples']})")
            st.write(f"anomaly score **{m['anomaly_score']:.2f}** - flagged unusual: **{m['is_anomaly']}**")
        else:
            st.caption("ML model not trained yet for this resource (needs more history).")

    with t_hist:
        st.markdown("#### Revisions")
        st.dataframe(pd.DataFrame(rec["revisions"]), hide_index=True)
        with st.expander("Raw recommendation document"):
            st.json(json.loads(json.dumps(rec, default=str)))


# ═══════════════════════════ RESOURCE EXPLORER ═══════════════════════════════
def page_resources():
    st.header("Resource explorer")
    rs = D.resources(db)
    if rs.empty:
        st.info("No resources yet - run the pipeline first.")
        return
    c = st.columns(3)
    cloud = c[0].selectbox("Cloud", sorted(rs.cloud.dropna().unique()))
    sub = rs[rs.cloud == cloud]
    name = c[1].selectbox("Resource", list(sub.name))
    row = sub[sub.name == name].iloc[0]
    metrics = D.native_metrics(db, row.resource_id)
    if not metrics:
        st.warning("The source log collection has no documents for this resource.")
        return
    nm = c[2].selectbox("Metric", metrics)
    days = st.slider("Days shown (ending at the latest data)", 7, 90, 30)
    series, alerts, canon = D.metric_series(db, row.resource_id, nm)
    if series.empty:
        st.info("No data")
        return
    end = series["time"].max()
    start = end - pd.Timedelta(days=days)
    s = series[series.time >= start]
    a = alerts[alerts.fired >= start] if not alerts.empty else alerts
    st.caption(f"tier **{row.tier}** · app **{row.app}** · canonical metric **{canon}**")
    metric_chart(s, a, None, canon or nm)
    if not a.empty:
        st.markdown("**Alerts in range**")
        st.dataframe(a, hide_index=True)
    recs = [r for r in D.load_recommendations(db) if r["resource_id"] == row.resource_id]
    if recs:
        st.markdown("**Incidents on this resource**")
        st.dataframe(D.recs_frame(recs).drop(columns=["id"]), hide_index=True)
    else:
        st.caption("No incidents recorded for this resource.")


# ═══════════════════════════════ EVALUATION ══════════════════════════════════
def page_eval():
    st.header("Evaluation against ground truth")
    gt_path = os.path.join(ROOT, "data", "ground_truth.json")
    if not os.path.exists(gt_path):
        st.info("`data/ground_truth.json` not found (it ships with the synthetic dataset).")
        return
    st.caption("Ground truth comes from the synthetic generator: it checks the pipeline's logic, "
               "not accuracy on production data.")
    if st.button("Run evaluation", type="primary"):
        import evaluate
        st.session_state["eval"] = evaluate.evaluate(db, json.load(open(gt_path)))
    res = st.session_state.get("eval")
    if not res:
        return
    s = res["summary"]
    c = st.columns(5)
    c[0].metric("Recall", s["detection_recall"])
    c[1].metric("Root-cause accuracy", s["rca_accuracy"])
    c[2].metric("Silent negatives", f"{s['negatives_correctly_silent']}/{s['negatives']}")
    c[3].metric("Precision", s["precision"])
    c[4].metric("Unexplained recs", s["unexplained_recommendations"])
    c = st.columns(2)
    c[0].write("By use case"); c[0].json(res["by_use_case"])
    c[1].write("By cloud"); c[1].json(res["by_provider"])
    rows = pd.DataFrame(res["rows"])
    rows["result"] = rows["correct"].map({True: "✅", False: "❌"})
    st.dataframe(rows[["result", "gt", "provider", "use_case", "expected", "got", "confidence", "priority"]], hide_index=True)


# ═════════════════════════════════ PIPELINE ══════════════════════════════════
def page_pipeline():
    st.header("Pipeline")
    st.dataframe(pd.DataFrame(D.counts(db).items(), columns=["collection", "documents"]), hide_index=True)
    st.markdown("**1. Load the synthetic dataset** (replaces the source collection)")
    if st.button("Load dataset into MongoDB"):
        with st.spinner("loading..."):
            code, out = D.run_command(D.load_command())
        (st.success if code == 0 else st.error)(out[-800:])
    st.markdown("**2. Run the pipeline** (replays the logs oldest-first in day batches; ~1-2 min)")
    c = st.columns(2)
    reset = c[0].checkbox("Reset derived collections first", value=True)
    llm = c[1].checkbox("Use LLM (Ollama) for explanations", value=False)
    if st.button("Run pipeline", type="primary"):
        with st.spinner("running the pipeline..."):
            code, out = D.run_command(D.pipeline_command(reset, llm))
        (st.success if code == 0 else st.error)("finished" if code == 0 else "failed")
        st.code(out[-4000:])
    st.caption("Command line equivalents: `python tools/load_dataset.py --drop` · `python main.py --reset --no-llm`")


# ═══════════════════════════════ DATA DICTIONARY ═════════════════════════════
def page_dict():
    st.header("Data dictionary")
    p = os.path.join(ROOT, "docs", "FIELDS.md")
    st.markdown(open(p, encoding="utf-8").read() if os.path.exists(p) else "docs/FIELDS.md not found")


{"Overview": page_overview, "Incident detail": page_detail, "Resource explorer": page_resources,
 "Evaluation": page_eval, "Pipeline": page_pipeline, "Data dictionary": page_dict}[page]()
