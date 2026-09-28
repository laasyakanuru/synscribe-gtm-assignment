#!/usr/bin/env python3
"""
Synscribe MNC-Singapore segment funnel.

Deterministic where public data allows, explicit where it does not.

Subcommands
  download  Fetch the 27 ACRA "Information on Corporate Entities" CSVs from data.gov.sg
  profile   Print distinct entity types / statuses so you can confirm CONFIG values
  build     Run stages 1-6 and write one CSV per stage + funnel_report.md
  estimate  Read the hand-filled LinkedIn sample and output the company/people range
  outcomes  Reply rate and single-seat vs team asks, from 06_outbound_order.csv

Same inputs + same CONFIG + same seed  ->  same lists, same sample, same numbers.
"""
import argparse, glob, json, math, os, re, subprocess, sys, time
from datetime import date
import pandas as pd

# ---------------------------------------------------------------- CONFIG
CONFIG = {
    "acra_dir": "data/acra",
    "frame_csv": "data/frame.csv",
    "out_dir": "out",
    "seed": 20260928,
    # Random sample size per cell (source x industry group). 4 groups x 10 = 40 checks per source.
    "sample_per_cell": 10,
    # Confirm these with `python funnel.py profile` before `build`:
    "live_statuses": ["Live Company", "Live"],
    "local_company_types": ["Local Company"],
    "foreign_branch_types": ["Foreign Company Branch"],   # exact ACRA label (from profile)

    # Exclusion: companies that are not buyers (checked on primary AND secondary SSIC).
    # Verify prefixes against the SSIC 2025 tables.
    "exclude_ssic_prefixes": {
        "731": "Advertising",
        "732": "Market research",
        "84":  "Public administration",
        "85":  "Education",
        "94":  "Membership organisations",
    },

    # FILTER 1: no commercial activity in Singapore.
    # Removed if the PRIMARY SSIC starts with one of these, unless the SECONDARY SSIC is
    # a commercial activity (i.e. present and not itself in this list).
    "no_commercial_ssic_prefixes": {
        "642": "Holding companies",
        "643": "Trusts, funds and similar financial entities",
    },

    # FILTER 2: secretarial / nominee addresses.
    # An address = postal code + level + unit. Counted across ALL live entities in ACRA.
    # Entities at an address shared by more than this many live entities are removed.
    # `build` prints the distribution so you can set this from the data.
    "max_entities_per_address": 50,
    # Filter 2 is NOT applied to entities matched to data/frame.csv: many real multinationals
    # (e.g. Airwallex, Freshworks) register every Singapore entity at a corporate secretary's
    # address. Those are flagged in registered_at_secretarial_address instead, and real presence
    # is tested by the LinkedIn check (6+ marketers in Singapore). Unframed branches still get it.
    "secretarial_filter_applies_to_frame_matches": False,

    # TAG 3: industry group from primary SSIC (longest matching prefix wins).
    # SSIC mostly follows ISIC Rev. 4 at these levels. Verify against SSIC 2025.
    "industry_groups": {
        "Regulated": ["64", "65", "66", "86", "21", "325"],
        "Technical": ["62", "63", "582", "61", "26", "28", "72"],
        "High-trust": ["69", "702"],
    },

    # Aliases shorter than this, or single words, need a human look.
    "review_alias_min_len": 6,

    # ---- Frame verification (stage 2) ----
    # True: keep only entities verified against data/frame.csv. Foreign branches of companies
    # that are not in the frame are set aside in 02_unframed_branches.csv instead of kept.
    "require_frame_match": True,
    # An alias must start the entity name (after an optional "The"). Strict aliases, i.e.
    # those written "=Word" in the frame or single words of this length or shorter, also need
    # every other word in the entity name to be neutral (below) or part of the parent's names.
    "short_alias_strict_len": 3,
    "neutral_tokens": """singapore sg asia asian pacific apac south southeast east north west asean
        international global worldwide regional region holdings holding group corporation corp
        company co and the of branch office representative operations services service
        technologies technology tech solutions systems management trading marketing sales
        digital software cloud network networks data products brands consumer retail
        investments investment hub centre center research development innovation
        headquarters hq ventures global labs online""",
    # Legal-form words removed before matching. "singapore", "corporation" and "company" are
    # kept, unlike norm(), so "Singapore Airlines" or "Mitsubishi Corporation" still match.
    "match_legal_suffixes": r"\b(pte|private|ltd|limited|llp|inc|incorporated|plc|gmbh)\b",

    # ---- Research scope, LinkedIn checks and outbound ----
    # Only these size segments are researched and contacted. Large companies stay in
    # 04_candidate_companies.csv for reference but get no LinkedIn checks and no outreach.
    "research_segments": ["mid"],
    # Report cells and estimate cells within the research pool.
    "strata": ["industry_group"],
    # If the research pool is this size or smaller, every company goes into 05 (census).
    # If it is larger, 05 holds a seeded random sample of sample_per_cell per stratum instead.
    "census_max": 150,
    # Pre-screen of research companies against the mid-size definition, done before the
    # LinkedIn checks: pass / unsure / fail with a reason. Checks in 05 always override it.
    # Unchecked companies that fail the pre-screen count as not qualifying in the estimate.
    # Companies that FAIL the pre-screen are left out of 05 and 06 entirely (listed in
    # 05b_prescreen_excluded.csv). To bring one back, change its row in data/prescreen.csv.
    "prescreen_csv": "data/prescreen.csv",
    "midsize_definition": "200-5,000 employees worldwide, operating in at least two countries",
}

# LinkedIn check columns, filled by hand in 05_linkedin_checks_TO_FILL.csv.
CHECK_COLS = ["linkedin_company_url", "linkedin_company_size", "c0_midsize_confirmed(y/n)",
              "c1_multinational_confirmed(y/n)", "c2_sg_marketing_count",
              "c3_leader_titles_count", "most_senior_sg_marketing_title", "business_model(B2B/B2C/Mixed)",
              "linkedin_industry", "fit_sg_or_apac_web_pages(y/n)", "fit_content_updated_90d(y/n)",
              "sg_leader_decides(y/n)", "excluded_on_review(y/n)", "checked_by", "check_date"]
CHECKS_FILE = "05_linkedin_checks_TO_FILL.csv"
OUTBOUND_FILE = "06_outbound_order.csv"


def passes_checks(d):
    """A company qualifies if it is confirmed mid-size and multinational, has 6+ marketers in
    Singapore and at least one marketing leader there, and was not excluded on review."""
    mkt = pd.to_numeric(d["c2_sg_marketing_count"], errors="coerce").fillna(0)
    lead = pd.to_numeric(d["c3_leader_titles_count"], errors="coerce").fillna(0)
    ok = ((d["c0_midsize_confirmed(y/n)"].str.lower() == "y")
          & (d["c1_multinational_confirmed(y/n)"].str.lower() == "y") & (mkt >= 6) & (lead >= 1)
          & (d["excluded_on_review(y/n)"].str.lower() != "y"))
    return ok, lead
COLS = ["uen", "entity_name", "entity_type_description", "entity_status_description",
        "primary_ssic_code", "secondary_ssic_code", "postal_code", "level_no", "unit_no"]
LEGAL_SUFFIXES = r"\b(pte|private|ltd|limited|llp|inc|corp|corporation|plc|ag|gmbh|bv|sa|nv|co|company|the|branch|singapore|s)\b"
# ------------------------------------------------------------------------


def norm(name: str) -> str:
    s = str(name).lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(LEGAL_SUFFIXES, " ", s)
    return re.sub(r"\s+", " ", s).strip()


# --------------------------------------------------------------- download
def _curl(url, out_path=None):
    """Fetch with the system curl (Cloudflare blocks Python's own HTTP client here).
    Uses DATA_GOV_SG_API_KEY from the environment if set."""
    cmd = ["curl", "-sS", "-L", "--fail-with-body", "--retry", "3", "--max-time", "600"]
    key = os.environ.get("DATA_GOV_SG_API_KEY")
    if key and "data.gov.sg" in url:
        cmd += ["-H", f"x-api-key: {key}"]
    if out_path:
        cmd += ["-o", out_path]
    r = subprocess.run(cmd + [url], capture_output=True)
    if r.returncode != 0:
        msg = (r.stdout[:400] or r.stderr[:400]).decode("utf-8", "replace")
        raise RuntimeError(f"curl failed for {url}\n{msg}")
    return r.stdout


def cmd_download(_):
    os.makedirs(CONFIG["acra_dir"], exist_ok=True)
    ids_file = os.path.join("data", "acra_dataset_ids.txt")
    if os.path.exists(ids_file):
        ids = [l.strip() for l in open(ids_file) if l.strip().startswith("d_")]
        print(f"Using {len(ids)} dataset IDs from {ids_file}")
    else:
        meta = json.loads(_curl("https://api-production.data.gov.sg/v2/public/api/collections/2/metadata"))
        ids = meta["data"]["collectionMetadata"]["childDatasets"]
    for i, d in enumerate(ids, 1):
        target = os.path.join(CONFIG["acra_dir"], f"{d}.csv")
        if os.path.exists(target) and os.path.getsize(target) > 0:
            print(f"[{i}/{len(ids)}] have {d}")
            continue
        base = f"https://api-open.data.gov.sg/v1/public/api/datasets/{d}"
        _curl(base + "/initiate-download")
        url = None
        for _ in range(40):
            url = json.loads(_curl(base + "/poll-download")).get("data", {}).get("url")
            if url:
                break
            time.sleep(3)
        if not url:
            sys.exit(f"No download URL for {d} after polling. Re-run; finished files are kept.")
        _curl(url, out_path=target)
        print(f"[{i}/{len(ids)}] saved {target} ({os.path.getsize(target)/1e6:.1f} MB)")
        time.sleep(2)
    with open(os.path.join(CONFIG["acra_dir"], "_downloaded_on.txt"), "w") as f:
        f.write(date.today().isoformat())
    print("done")


# ---------------------------------------------------------------- loading
def load_acra() -> pd.DataFrame:
    files = sorted(glob.glob(os.path.join(CONFIG["acra_dir"], "*.csv")))
    if not files:
        sys.exit(f"No CSVs in {CONFIG['acra_dir']}. Run `download` first.")
    frames = []
    for f in files:
        head = pd.read_csv(f, nrows=0).columns
        use = [c for c in COLS if c in head]
        missing = set(COLS[:4]) - set(use)
        if missing:
            sys.exit(f"{f} is missing required columns {missing}")
        frames.append(pd.read_csv(f, usecols=use, dtype=str))
    df = pd.concat(frames, ignore_index=True).drop_duplicates("uen")
    for c in COLS:
        if c not in df:
            df[c] = ""
    return df.fillna("")


def cmd_profile(_):
    df = load_acra()
    print(f"rows: {len(df):,}\n")
    for c in ["entity_type_description", "entity_status_description"]:
        print(df[c].value_counts().head(25).to_string(), "\n")
    live = df[df.entity_status_description.isin(CONFIG["live_statuses"])
              & df.entity_type_description.isin(CONFIG["local_company_types"] + CONFIG["foreign_branch_types"])]
    print(f"Live local companies + foreign branches: {len(live):,}")
    for t, g in live.groupby("entity_type_description"):
        blank = (g.primary_ssic_code.str.strip() == "").mean()
        print(f"  {t}: {len(g):,} live, {blank:.1%} with blank primary SSIC")
    print("\nColumns found:", ", ".join(c for c in COLS if (df[c] != "").any()))


# ------------------------------------------------------------------ build
def _starts(code, prefixes):
    code = str(code).strip()
    return next((p for p in sorted(prefixes, key=len, reverse=True) if code and code.startswith(p)), None)


def exclusion_reason(row):
    for code in (row["primary_ssic_code"], row["secondary_ssic_code"]):
        p = _starts(code, CONFIG["exclude_ssic_prefixes"])
        if p:
            return f"Not a buyer: {CONFIG['exclude_ssic_prefixes'][p]} (SSIC {code})"
    return ""


def no_commercial_reason(row):
    ncp = CONFIG["no_commercial_ssic_prefixes"]
    p = _starts(row["primary_ssic_code"], ncp)
    if not p:
        return ""
    sec = str(row["secondary_ssic_code"]).strip()
    if sec and not _starts(sec, ncp):
        return ""          # has a commercial secondary activity -> keep
    return f"No commercial activity: {ncp[p]} (SSIC {row['primary_ssic_code']})"


def industry_group(code):
    best, best_len = "Other", 0
    for group, prefixes in CONFIG["industry_groups"].items():
        p = _starts(code, prefixes)
        if p and len(p) > best_len:
            best, best_len = group, len(p)
    return best


def address_key(df):
    lvl, unit = df.level_no.str.strip(), df.unit_no.str.strip()
    key = df.postal_code.str.strip() + "|" + lvl + "|" + unit
    # Without a level and unit we cannot tell a secretarial unit from a whole building.
    return key.where((lvl != "") & (unit != "") & (df.postal_code.str.strip() != ""), "")


def md_table(df):
    """Markdown table without needing the tabulate package."""
    df = df.reset_index() if df.index.name or not isinstance(df.index, pd.RangeIndex) else df
    head = "| " + " | ".join(map(str, df.columns)) + " |\n|" + "---|" * len(df.columns) + "\n"
    return head + "".join("| " + " | ".join(map(str, r)) + " |\n" for r in df.itertuples(index=False))


# ---------------------------------------------------------- frame verification
def mnorm(name: str) -> str:
    """Normalisation used for frame matching (lighter than norm())."""
    s = str(name).lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(CONFIG["match_legal_suffixes"], " ", s)
    return re.sub(r"\s+", " ", s).strip()


def load_frame():
    defaults = {"parent_name": "", "aliases": "", "hq_country": "", "frame_source": "", "mnc_basis": "",
                "global_tier": "n", "size_segment": "large", "listed_in_midsize_source": ""}
    if not os.path.exists(CONFIG["frame_csv"]):
        return pd.DataFrame(columns=list(defaults))
    fr = pd.read_csv(CONFIG["frame_csv"], dtype=str).fillna("")
    for c, d in defaults.items():
        if c not in fr.columns:
            fr[c] = d
        fr[c] = fr[c].where(fr[c] != "", d)
    return fr


def frame_match(s1, frame):
    """Match live entities to frame parents and verify each match.

    Returns (verified, review): one row per entity. `verified` holds entities whose name starts
    with a frame alias and passes the strict-alias check, assigned to exactly one parent
    (longest alias wins). Everything else that mentions an alias goes to `review` with a reason.
    """
    neutral = set(CONFIG["neutral_tokens"].split())
    alias_map, ptokens = {}, {}
    for _, f in frame.iterrows():
        toks = set(mnorm(f.parent_name).split())
        for raw in f.aliases.split(";"):   # aliases only: a parent name like "Wise" is too loose
            raw = raw.strip()
            if not raw:
                continue
            strict = raw.startswith("=")
            a = mnorm(raw.lstrip("="))
            if not a:
                continue
            toks |= set(a.split())
            strict = strict or (" " not in a and len(a) <= CONFIG["short_alias_strict_len"])
            entry = alias_map.setdefault(a, {})
            entry[f.parent_name] = entry.get(f.parent_name, False) or strict
        ptokens[f.parent_name] = toks
    if not alias_map:
        return pd.DataFrame(), pd.DataFrame()
    maxn = max(len(a.split()) for a in alias_map)

    ver, rev = [], []
    for i, m in zip(s1.index, s1["m"].values):
        tk = m.split()
        start = 1 if tk[:1] == ["the"] else 0
        passed, reasons = [], []
        for j in range(len(tk)):
            for n in range(1, maxn + 1):
                if j + n > len(tk):
                    break
                a = " ".join(tk[j:j + n])
                if a not in alias_map:
                    continue
                for parent, strict in alias_map[a].items():
                    if j != start:
                        if n > 1:   # single words mid-name are almost always unrelated
                            reasons.append((parent, a, "alias not at start of name"))
                        continue
                    rest = set(tk[:j] + tk[j + n:]) - neutral - ptokens[parent]
                    if strict and rest:
                        reasons.append((parent, a, "strict alias; other words: " + " ".join(sorted(rest))))
                        continue
                    passed.append((n, parent, a, strict))
        if passed:
            best = max(p[0] for p in passed)
            top = {p[1]: p for p in passed if p[0] == best}
            if len(top) == 1:
                n, parent, a, strict = next(iter(top.values()))
                ver.append({"idx": i, "parent_name": parent, "matched_alias": a, "strict_alias": strict})
                continue
            reasons = [(p, top[p][2], "ambiguous: " + " | ".join(sorted(top))) for p in sorted(top)]
        seen = set()
        for parent, a, why in reasons:
            if parent not in seen:
                seen.add(parent)
                rev.append({"idx": i, "parent_name": parent, "matched_alias": a, "review_reason": why})
    return pd.DataFrame(ver), pd.DataFrame(rev)


def cmd_build(_):
    out = CONFIG["out_dir"]; os.makedirs(out, exist_ok=True)
    acra = load_acra()
    counts = [("0. ACRA register, all entities", len(acra))]

    # Address density across every live entity in ACRA (for filter 2)
    live_all = acra[acra.entity_status_description.isin(CONFIG["live_statuses"])].copy()
    live_all["addr"] = address_key(live_all)
    addr_counts = live_all[live_all.addr != ""].addr.value_counts()
    if addr_counts.empty:
        print("WARNING: no postal_code/level_no/unit_no values found -> filter 2 cannot run. "
              "Check the address column names with `profile`.\n")

    # Stage 1: live local companies + foreign branches
    types = CONFIG["local_company_types"] + CONFIG["foreign_branch_types"]
    s1 = acra[acra.entity_status_description.isin(CONFIG["live_statuses"])
              & acra.entity_type_description.isin(types)].copy()
    s1["name_norm"] = s1.entity_name.map(norm)
    s1["addr"] = address_key(s1)
    s1["entities_at_address"] = s1.addr.map(addr_counts).fillna(0).astype(int)
    s1.to_csv(f"{out}/01_live_companies.csv", index=False)
    counts.append(("1. Live local companies + foreign branches", len(s1)))

    # Stage 2a: frame match, verified
    frame = load_frame()
    if frame.empty:
        print("WARNING: data/frame.csv is missing or empty -> stage 2a finds nothing.\n")
    s1["m"] = s1.entity_name.map(mnorm)
    ver, rev = frame_match(s1, frame)
    fcols = frame.set_index("parent_name")
    if not rev.empty:
        r = s1.loc[rev.idx, ["uen", "entity_name", "entity_type_description", "primary_ssic_code"]].reset_index(drop=True)
        r = pd.concat([r, rev.drop(columns="idx").reset_index(drop=True)], axis=1)
        r = r[~r.uen.isin(s1.loc[ver.idx, "uen"] if not ver.empty else [])]
        r.sort_values(["parent_name", "entity_name"]).to_csv(f"{out}/02_frame_review.csv", index=False)
    n_review = 0 if rev.empty else int(rev.idx.nunique() - rev.idx.isin(ver.idx if not ver.empty else []).sum())

    # Parent qualifies as a multinational present in Singapore if it has at least one verified
    # live entity AND (it is headquartered outside Singapore OR the frame gives an mnc_basis).
    status = {}
    found = set(ver.parent_name) if not ver.empty else set()
    in_review = set(rev.parent_name) if not rev.empty else set()
    for p, f in fcols.iterrows():
        sg_hq = str(f.hq_country).strip().lower() == "singapore"
        if p not in found:
            status[p] = "review matches only" if p in in_review else "not found in ACRA"
        elif sg_hq and not str(f.mnc_basis).strip():
            status[p] = "Singapore HQ, no mnc_basis given"
        else:
            status[p] = "qualified"
    fp = frame.assign(status=frame.parent_name.map(status),
                      verified_entities=frame.parent_name.map(ver.parent_name.value_counts() if not ver.empty else {}).fillna(0).astype(int))
    fp.to_csv(f"{out}/02_frame_parents.csv", index=False)
    qualified = {p for p, st in status.items() if st == "qualified"}

    if not ver.empty:
        ver = ver[ver.parent_name.isin(qualified)]
        matched = s1.loc[ver.idx].copy()
        matched["source"] = "frame_match"
        matched["parent_name"] = ver.parent_name.values
        matched["matched_alias"] = ver.matched_alias.values
        matched["needs_review"] = ver.strict_alias.values
        matched["hq_country"] = matched.parent_name.map(fcols.hq_country)
        matched["frame_source"] = matched.parent_name.map(fcols.frame_source)
        for c in ["global_tier", "size_segment", "mnc_basis"]:
            matched[c] = matched.parent_name.map(fcols[c])
    else:
        matched = pd.DataFrame(columns=list(s1.columns) + ["source", "parent_name", "matched_alias",
                                                          "needs_review", "hq_country", "frame_source"])

    # Stage 2b: foreign branches not matched to the frame
    br = s1[s1.entity_type_description.isin(CONFIG["foreign_branch_types"]) & ~s1.uen.isin(matched.uen)].copy()
    br["source"], br["parent_name"], br["hq_country"], br["needs_review"] = "foreign_branch", br.name_norm, "Foreign (branch)", False
    br["global_tier"], br["size_segment"], br["mnc_basis"] = "n", "unclassified", ""
    if CONFIG["require_frame_match"]:
        br.drop(columns="m").to_csv(f"{out}/02_unframed_branches.csv", index=False)
        s2 = matched.copy()
    else:
        s2 = pd.concat([matched, br], ignore_index=True)
    s2 = s2.drop(columns="m", errors="ignore")
    s2.to_csv(f"{out}/02_multinational_entities.csv", index=False)
    counts.append(("2a. Frame parents (data/frame.csv)", len(frame)))
    counts.append(("    qualified: MNC with a verified live Singapore entity", len(qualified)))
    for st in ["not found in ACRA", "review matches only", "Singapore HQ, no mnc_basis given"]:
        counts.append((f"    {st}", sum(v == st for v in status.values())))
    counts.append(("    verified entities of qualified parents", len(matched)))
    counts.append(("    entities sent to 02_frame_review.csv", n_review))
    counts.append(("2b. Foreign branches not in the frame" +
                   (" (set aside: require_frame_match)" if CONFIG["require_frame_match"] else " (kept)"), len(br)))
    counts.append(("2. Multinational entities carried forward", len(s2)))

    # Stage 3: exclusions and filters, applied in order; first reason wins
    s2["removed_reason"] = s2.apply(exclusion_reason, axis=1)
    counts.append(("3a. After not-a-buyer exclusions", int((s2.removed_reason == "").sum())))

    m = s2.removed_reason == ""
    s2.loc[m, "removed_reason"] = s2[m].apply(no_commercial_reason, axis=1)
    counts.append(("3b. After filter 1 (no commercial activity)", int((s2.removed_reason == "").sum())))

    s2["registered_at_secretarial_address"] = s2.entities_at_address.astype(int) > CONFIG["max_entities_per_address"]
    m = (s2.removed_reason == "") & s2.registered_at_secretarial_address
    if not CONFIG["secretarial_filter_applies_to_frame_matches"]:
        m &= s2.source != "frame_match"
    s2.loc[m, "removed_reason"] = s2.loc[m, "entities_at_address"].map(
        lambda n: f"Secretarial address: {n} live entities share this unit")
    counts.append(("3c. After filter 2 (secretarial address; frame matches only flagged)", int((s2.removed_reason == "").sum())))

    s2[s2.removed_reason != ""].to_csv(f"{out}/03_removed.csv", index=False)
    s3 = s2[s2.removed_reason == ""].copy()
    s3["industry_group"] = s3.primary_ssic_code.map(industry_group)

    # Stage 4: one row per company group
    s4 = (s3.groupby(["parent_name", "source"], as_index=False)
            .agg(hq_country=("hq_country", "first"),
                 industry_group=("industry_group", "first"),
                 sg_entities=("entity_name", lambda x: " | ".join(sorted(set(x)))),
                 sg_uens=("uen", lambda x: " | ".join(sorted(set(x)))),
                 primary_ssic=("primary_ssic_code", "first"),
                 needs_review=("needs_review", "max"),
                 all_entities_at_secretarial_address=("registered_at_secretarial_address", "min"),
                 global_tier=("global_tier", "first"),
                 size_segment=("size_segment", "first"),
                 mnc_basis=("mnc_basis", "first"))
            .sort_values(["size_segment", "industry_group", "parent_name"]))
    s4["hq_tag"] = s4.hq_country.map(lambda c: "Singapore HQ" if str(c).strip().lower() == "singapore" else "Foreign HQ")
    s4.to_csv(f"{out}/04_candidate_companies.csv", index=False)
    counts.append(("4. Candidate companies (one row per group)", len(s4)))
    counts.append(("   of which flagged for name-match review", int(s4.needs_review.sum())))
    for seg, n in s4.size_segment.value_counts().items():
        counts.append((f"   size segment: {seg}", int(n)))
    counts.append(("   global tier (Forbes Global 2000 or proxy)", int((s4.global_tier == "y").sum())))

    # Stage 5: LinkedIn checks, research segments only (census, or a sample if the pool is large)
    pool = s4[s4.size_segment.isin(CONFIG["research_segments"])]
    counts.append(("   out of scope (not researched): " + ", ".join(
        sorted(set(s4.size_segment) - set(CONFIG["research_segments"]))), int(len(s4) - len(pool))))
    chk = build_checks(pool, out)
    n_fail = int(pool.parent_name.isin(load_prescreen().query("prescreen == 'fail'").parent_name).sum())
    counts.append(("   removed by prescreen (05b_prescreen_excluded.csv)", n_fail))
    counts.append((f"5. LinkedIn checks ({chk.selected_by.iloc[0] if len(chk) else 'none'})", len(chk)))
    for v, n in chk.prescreen.replace("", "(none)").value_counts().items():
        counts.append((f"   prescreen: {v}", int(n)))

    # Stage 6: outbound list, derived from the checks
    ob = build_outbound(chk, out)
    for g, n in ob.status.value_counts().sort_index().items():
        counts.append((f"6. Outbound: {g}", int(n)))

    # Report
    acra_date_f = os.path.join(CONFIG["acra_dir"], "_downloaded_on.txt")
    acra_date = open(acra_date_f).read().strip() if os.path.exists(acra_date_f) else "unknown"
    cand_addr = s2.entities_at_address
    q = cand_addr.quantile([.5, .75, .9, .95, .99]).round().astype(int).to_dict()
    bands = pd.cut(cand_addr, [-1, 1, 5, 20, 50, 100, 500, 10**9],
                   labels=["0-1", "2-5", "6-20", "21-50", "51-100", "101-500", "500+"]).value_counts().sort_index()
    cells = s4.groupby(["size_segment", "industry_group"]).size().rename("companies").reset_index()
    top_removed = s2[s2.removed_reason != ""].removed_reason.str.replace(r"\s*\(.*|: \d+.*", "", regex=True).value_counts()
    with open(f"{out}/funnel_report.md", "w") as f:
        f.write(f"# Funnel report\n\nRun: {date.today()} · ACRA data downloaded: {acra_date} · seed: {CONFIG['seed']}\n\n")
        f.write("| Stage | Count |\n|---|---|\n" + "".join(f"| {k} | {v:,} |\n" for k, v in counts))
        f.write("\n## Candidates by cell\n\n" + md_table(cells) + "\n")
        f.write("\n## Removed, by reason\n\n" + md_table(top_removed.rename_axis("reason").to_frame("entities")) + "\n")
        f.write("\n## Filter 2 check: live entities sharing each multinational entity's address\n\n")
        f.write(f"Threshold: > {CONFIG['max_entities_per_address']} removed. "
                f"Percentiles (p50/p75/p90/p95/p99): {list(q.values())}\n\n")
        f.write(md_table(bands.rename_axis("live entities at address").to_frame("multinational entities")) + "\n")
    print(open(f"{out}/funnel_report.md").read())


# --------------------------------------------------------------- checks + outbound
TRACK_COLS = ["contact_name", "contact_title", "sent_date", "replied(y/n)", "reply_date",
              "ask_type(single_seat/team_training/other)", "notes"]
CARRY_COLS = ["c2_sg_marketing_count", "c3_leader_titles_count", "most_senior_sg_marketing_title",
              "sg_leader_decides(y/n)", "linkedin_company_url"]


def _merge_saved(df, path, cols):
    """Copy hand-entered columns from an earlier version of `path`, matched on parent_name."""
    for c in cols:
        df[c] = ""
    if os.path.exists(path):
        old = pd.read_csv(path, dtype=str).fillna("")
        if "parent_name" in old.columns:
            old = old.drop_duplicates("parent_name").set_index("parent_name")
            for c in cols:
                if c in old.columns:
                    df[c] = df.parent_name.map(old[c]).fillna("")
    return df


def load_prescreen():
    cols = ["prescreen", "prescreen_reason", "prescreen_basis"]
    if not os.path.exists(CONFIG["prescreen_csv"]):
        return pd.DataFrame(columns=["parent_name"] + cols)
    ps = pd.read_csv(CONFIG["prescreen_csv"], dtype=str).fillna("")
    ps["prescreen"] = ps.prescreen.str.strip().str.lower()
    return ps.drop_duplicates("parent_name")[["parent_name"] + cols]


PRESCREEN_ORDER = {"pass": 0, "unsure": 1, "": 1, "fail": 2}


def build_checks(pool, out):
    """05: every research-segment company (census), or a seeded sample per stratum if the pool is
    larger than census_max. Anything already typed in is kept across rebuilds."""
    if len(pool) <= CONFIG["census_max"]:
        sel, how = pool.copy(), "census"
    else:
        sel = pd.concat([g.sample(n=min(CONFIG["sample_per_cell"], len(g)), random_state=CONFIG["seed"])
                         for _, g in pool.groupby(CONFIG["strata"])])
        how = "sample"
    sel = sel.assign(selected_by=how).merge(load_prescreen(), on="parent_name", how="left").fillna("")
    sel[sel.prescreen == "fail"][["parent_name", "prescreen_reason", "prescreen_basis", "hq_country",
                                  "industry_group", "sg_entities"]].to_csv(f"{out}/05b_prescreen_excluded.csv", index=False)
    sel = sel[sel.prescreen != "fail"]
    sel["_p"] = sel.prescreen.map(PRESCREEN_ORDER).fillna(1)
    sel = sel.sort_values(["_p", "industry_group", "parent_name"]).drop(columns="_p")
    cols = ["parent_name", "prescreen", "prescreen_reason", "prescreen_basis", "selected_by",
            "size_segment", "hq_country", "hq_tag", "industry_group", "sg_entities", "needs_review", "mnc_basis"]
    sel = _merge_saved(sel[cols].copy(), f"{out}/{CHECKS_FILE}", CHECK_COLS)
    sel.to_csv(f"{out}/{CHECKS_FILE}", index=False)
    return sel


def build_outbound(chk, out):
    """06: the companies from 05, with their check result, in contact order.

    status: ready (passed checks) / not yet checked / excluded (failed checks).
    Order: ready first; within it, Singapore leader decides first, then Singapore HQ, then a
    seeded random order. Outreach columns are kept across rebuilds.
    """
    ob = chk[["parent_name", "prescreen", "prescreen_reason", "size_segment", "hq_country", "hq_tag",
              "industry_group", "sg_entities"] + CARRY_COLS + ["check_date"]].copy()
    passed, _ = passes_checks(chk)
    checked = chk.check_date != ""
    ob["status"] = ["1 ready: passed checks" if c and p else "3 excluded: failed checks" if c
                    else "2 not yet checked" for c, p in zip(checked, passed)]
    ob = _merge_saved(ob, f"{out}/{OUTBOUND_FILE}", TRACK_COLS)
    ob["_lead"] = (ob["sg_leader_decides(y/n)"].str.lower() != "y").astype(int)
    ob["_sg"] = (ob.hq_tag != "Singapore HQ").astype(int)
    ob["_r"] = ob.sample(frac=1, random_state=CONFIG["seed"]).assign(_r=range(len(ob)))["_r"].reindex(ob.index)
    ob["_p"] = ob.prescreen.map(PRESCREEN_ORDER).fillna(1)
    ob = ob.sort_values(["status", "_p", "_lead", "_sg", "_r"]).drop(columns=["_p", "_lead", "_sg", "_r"])
    ob = ob[["status"] + [c for c in ob.columns if c != "status"]]
    ob.insert(0, "outbound_rank", range(1, len(ob) + 1))
    ob.to_csv(f"{out}/{OUTBOUND_FILE}", index=False)
    return ob


def cmd_outcomes(_):
    """Reply rate and single-seat vs team asks, from the outreach columns in 06."""
    out = CONFIG["out_dir"]
    ob = pd.read_csv(f"{out}/{OUTBOUND_FILE}", dtype=str).fillna("")
    sent = ob[ob.sent_date != ""]
    if sent.empty:
        sys.exit(f"No rows with sent_date yet in {OUTBOUND_FILE}.")
    ask = "ask_type(single_seat/team_training/other)"
    sent = sent.assign(all="all")
    lines = []
    for col in ["all", "sg_leader_decides(y/n)", "hq_tag", "industry_group"]:
        lines += [f"## By {col}", "",
                  "| " + col + " | Sent | Replied | Reply rate (95% CI) | Replies stating ask | Single seat | Single-seat share (95% CI) |",
                  "|---|---|---|---|---|---|---|"]
        for g, d in sent.groupby(col):
            n, k = len(d), int((d["replied(y/n)"].str.lower() == "y").sum())
            lo, hi = wilson(k, n)
            r = d[(d["replied(y/n)"].str.lower() == "y") & (d[ask] != "")]
            m, s1 = len(r), int((r[ask].str.lower() == "single_seat").sum())
            slo, shi = wilson(s1, m) if m else (0, 1)
            share = f"{s1/m:.0%} ({slo:.0%}–{shi:.0%})" if m else "–"
            lines.append(f"| {g or '(blank)'} | {n} | {k} | {k/n:.0%} ({lo:.0%}–{hi:.0%}) | {m} | {s1} | {share} |")
        lines.append("")
    lines.append("Intervals are Wilson 95%. Overlapping intervals mean the difference is not yet clear.")
    txt = "\n".join(lines)
    open(f"{out}/outcomes.md", "w").write(f"# Outbound outcomes ({date.today()})\n\n" + txt + "\n")
    print(txt)


# --------------------------------------------------------------- estimate
def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0, c - h), min(1, c + h))


def cmd_estimate(_):
    """Mid-size MNCs in Singapore that pass the checks, and their marketing leaders."""
    out = CONFIG["out_dir"]
    s4 = pd.read_csv(f"{out}/04_candidate_companies.csv", dtype=str).fillna("")
    chk = pd.read_csv(f"{out}/{CHECKS_FILE}", dtype=str).fillna("")
    pool = s4[s4.size_segment.isin(CONFIG["research_segments"])]
    ps = load_prescreen()
    pre_fail = set(ps[ps.prescreen == "fail"].parent_name) - set(chk[chk.check_date != ""].parent_name)
    done = chk[chk.check_date != ""]
    if done.empty:
        sys.exit(f"No checked rows yet. Fill {CHECKS_FILE} first.")
    passed, lead = passes_checks(done)
    done = done.assign(passed=passed, leaders=lead)
    st = CONFIG["strata"]
    lines = ["| " + " | ".join(st) + " | Pool | Checked | Passed | Removed by prescreen | Pass rate (95% CI) | Companies |",
             "|" + "---|" * (len(st) + 6)]
    lo_tot = hi_tot = 0.0
    for key, pdf in pool.groupby(st):
        key = key if isinstance(key, tuple) else (key,)
        d = done[done.parent_name.isin(pdf.parent_name)]
        n_pool, k, n = len(pdf), int(d.passed.sum()), len(d)
        n_pf = int(pdf.parent_name.isin(pre_fail).sum())
        lo, hi = wilson(k, n) if n else (0.0, 1.0)
        # Checked companies are known; unchecked pre-screen fails count as not qualifying;
        # only the remaining unchecked companies are estimated.
        rest = n_pool - n - n_pf
        c_lo, c_hi = k + lo * rest, k + hi * rest
        lo_tot += c_lo; hi_tot += c_hi
        rate = f"{k/n:.0%} ({lo:.0%}–{hi:.0%})" if n else "not checked (0–100%)"
        lines.append("| " + " | ".join(key) + f" | {n_pool:,} | {n} | {k} | {n_pf} | {rate} | {c_lo:,.0f}–{c_hi:,.0f} |")
    pl = done[done.passed].leaders
    lmin, lmean, lmax = (pl.min(), pl.mean(), pl.max()) if len(pl) else (0, 0, 0)
    ppl_known = pl.sum()
    lines += ["", f"**Mid-size MNC companies: {lo_tot:,.0f}–{hi_tot:,.0f}**",
              f"**People (leader-titled marketers): {lo_tot*lmean:,.0f}–{hi_tot*lmean:,.0f}** "
              f"({ppl_known:.0f} counted at checked companies; mean {lmean:.1f} per passing company, observed {lmin:.0f}–{lmax:.0f})",
              "", "Mid-size definition: " + CONFIG["midsize_definition"] + ".",
              "", "Scope: " + ", ".join(CONFIG["research_segments"]) + " companies in data/frame.csv with a verified live "
              "Singapore entity, after filters 1–2. Large companies are out of scope. Mid-size multinationals "
              "missing from the frame are not counted, so this is a lower bound for the segment."]
    txt = "\n".join(lines)
    open(f"{out}/estimate.md", "w").write(f"# Estimate ({date.today()})\n\n" + txt + "\n")
    print(txt)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["download", "profile", "build", "estimate", "outcomes"])
    a = ap.parse_args()
    {"download": cmd_download, "profile": cmd_profile, "build": cmd_build, "estimate": cmd_estimate,
     "outcomes": cmd_outcomes}[a.cmd](a)
