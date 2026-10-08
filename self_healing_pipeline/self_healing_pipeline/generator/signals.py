"""
Signal synthesis: latent traffic -> per-metric hourly series -> scenario injections
-> burst-credit physics -> final hourly arrays in canonical units.

Canonical units (provider encoding happens later in docs.py):
    cpu          %  (0-100, of the whole VM)
    mem          %  used
    disk         %  used
    net_in/out   bytes per hour
    disk_write   bytes per hour
    credit       burst credit balance (count)
    sched_wait   seconds of vCPU scheduler wait per hour (GCP shared-core throttling)

Realism knobs: diurnal cycle (von-Mises bump), weekly seasonality (weekend dip),
slow growth trend, AR(1) multiplicative noise, weekly log-rotation sawtooth on disks,
release-cycle sawtooth on memory, and physically consistent credit accounting
(1 credit = 1 vCPU-minute at 100 %).  CPU, network, memory and disk_write are all
driven by one latent load so cross-metric correlation is genuine, not painted on.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .fleet import INSTANCE, ScenarioSpec

# ── tier behaviour ────────────────────────────────────────────────────────────
TIER = {
    #         cpu(c0,c1)  mem(m0,m1)  net_in    net_out   kappa peak weekend
    "web":    dict(cpu=(12, 22), mem=(50, 6), net_in=1.2e9, net_out=3.4e9, kappa=0.7, peak=15, weekend=0.70),
    "app":    dict(cpu=(14, 24), mem=(52, 5), net_in=8.0e8, net_out=6.0e8, kappa=0.6, peak=14, weekend=0.75),
    "worker": dict(cpu=(5, 10),  mem=(48, 3), net_in=1.5e8, net_out=1.0e8, kappa=0.9, peak=3,  weekend=0.95),
    "db":     dict(cpu=(10, 14), mem=(62, 3), net_in=4.0e8, net_out=5.0e8, kappa=0.4, peak=13, weekend=0.90),
}
DB_WRITE0 = 2.4e9          # bytes/hour baseline disk write on db tier
DB_DISK0 = 44.0            # % used at t0


def _ar1(rng, n, phi=0.7, sigma=0.06):
    e = rng.normal(0, sigma, n)
    x = np.zeros(n)
    for i in range(1, n):
        x[i] = phi * x[i - 1] + e[i]
    return x


def _diurnal(hour, peak, kappa):
    d = np.exp(kappa * (np.cos(2 * np.pi * (hour - peak) / 24.0) - 1.0))
    # normalise to mean 1 over a day
    grid = np.exp(kappa * (np.cos(2 * np.pi * (np.arange(24) - peak) / 24.0) - 1.0))
    return d / grid.mean()


@dataclass
class Bundle:
    n: int
    mult: np.ndarray
    net_in_x: np.ndarray
    net_out_x: np.ndarray
    cpu_add: np.ndarray
    cpu_force: np.ndarray            # NaN where unused
    mem_add: np.ndarray
    disk_add: np.ndarray
    disk_write_x: np.ndarray
    gaps: dict = field(default_factory=dict)      # role -> bool mask
    gc_cpu: float = 0.0
    cur: int = 0                                  # index of the scenario being applied
    windows: list = field(default_factory=list)  # ground-truth effect windows

    @classmethod
    def new(cls, n):
        return cls(n=n, mult=np.ones(n), net_in_x=np.ones(n), net_out_x=np.ones(n),
                   cpu_add=np.zeros(n), cpu_force=np.full(n, np.nan), mem_add=np.zeros(n),
                   disk_add=np.zeros(n), disk_write_x=np.ones(n))


# ── project-level latent traffic ─────────────────────────────────────────────

def latent_load(n, start_dow, tier, rng, phase_shift=0):
    p = TIER[tier]
    h = (np.arange(n) - phase_shift) % 24
    day = np.arange(n) // 24
    dow = (start_dow + day) % 7
    weekly = np.where(dow >= 5, p["weekend"], 1.0)
    weekly = np.where(dow == 6, p["weekend"] * 0.92, weekly)
    trend = 1.0 + 0.0015 * day
    noise = np.exp(_ar1(rng, n, 0.7, 0.055))
    return _diurnal(h, p["peak"], p["kappa"]) * weekly * trend * noise


# ── scenario injectors ───────────────────────────────────────────────────────

def _env(n, t0, ramp, hold, decay):
    """0..1 envelope: linear ramp up, flat hold, linear decay."""
    e = np.zeros(n)
    ramp, hold, decay = max(int(ramp), 0), int(hold), max(int(decay), 0)
    for i in range(ramp):
        if t0 + i < n:
            e[t0 + i] = (i + 1) / (ramp + 1)
    for i in range(hold):
        if 0 <= t0 + ramp + i < n:
            e[t0 + ramp + i] = 1.0
    for i in range(decay):
        j = t0 + ramp + hold + i
        if 0 <= j < n:
            e[j] = 1.0 - (i + 1) / (decay + 1)
    return e


def _win(b, kind, t0, t1, tail=10):
    b.windows.append(dict(kind=kind, start=int(t0), end=int(min(t1 + tail, b.n)), sidx=b.cur))


def sc_traffic_surge(b, sc, t0, ctx):
    p = sc.params
    env = _env(b.n, t0, p["ramp"], p["hold"], p["decay"])
    b.mult *= 1.0 + (p["factor"] - 1.0) * env
    _win(b, sc.kind, t0, t0 + p["ramp"] + p["hold"] + p["decay"])


def sc_downstream_surge(b, sc, t0, ctx):
    p = sc.params
    lag = ctx["lag"]
    env = _env(b.n, t0 + lag, p["ramp"], p["hold"], p["decay"])
    b.mult *= 1.0 + (p["factor"] - 1.0) * env
    _win(b, sc.kind, t0 + lag, t0 + lag + p["ramp"] + p["hold"] + p["decay"])


def sc_net_ingress_anomaly(b, sc, t0, ctx):
    p = sc.params
    b.net_in_x[t0:t0 + p["hold"]] *= p["factor"]
    b.cpu_add[t0:t0 + p["hold"]] += p["cpu_add"]
    _win(b, sc.kind, t0, t0 + p["hold"])


def sc_net_egress_anomaly(b, sc, t0, ctx):
    p = sc.params
    b.net_out_x[t0:t0 + p["hold"]] *= p["factor"]
    b.cpu_add[t0:t0 + p["hold"]] += p["cpu_add"]
    _win(b, sc.kind, t0, t0 + p["hold"])


def sc_net_traffic_loss(b, sc, t0, ctx):
    p = sc.params
    b.mult[t0:t0 + p["hold"]] *= p["residual"]
    _win(b, sc.kind, t0, t0 + p["hold"])


def sc_anomaly_no_alert(b, sc, t0, ctx):
    p = sc.params
    b.cpu_force[t0:t0 + p["hold"]] = p["level"]
    _win(b, sc.kind, t0, t0 + p["hold"], tail=2)


def sc_cpu_flapping(b, sc, t0, ctx):
    p = sc.params
    for i in range(p["hours"]):
        if t0 + i < b.n:
            b.cpu_force[t0 + i] = p["lo"] if i % 3 == 2 else p["hi"]
    _win(b, sc.kind, t0, t0 + p["hours"], tail=4)


def sc_transient_spike(b, sc, t0, ctx):
    p = sc.params
    b.cpu_force[t0:t0 + p["hold"]] = p["level"]
    _win(b, sc.kind, t0, t0 + p["hold"], tail=4)


def sc_cpu_runaway(b, sc, t0, ctx):
    p = sc.params
    b.cpu_force[t0:t0 + p["hold"]] = p["level"]
    _win(b, sc.kind, t0, t0 + p["hold"], tail=4)


def sc_recurring_batch(b, sc, t0, ctx):
    p = sc.params
    start_day = sc.day + ctx["day_offset"]
    for d in range(start_day, b.n // 24):
        if ctx["weekday_of"](d) == p["weekday"]:
            s = d * 24 + sc.hour
            b.cpu_force[s:s + p["hold"]] = p["level"]
            b.windows.append(dict(kind=sc.kind, start=int(s), end=int(min(s + p["hold"] + 6, b.n)),
                                  sidx=b.cur, episode=True))


def sc_memory_leak(b, sc, t0, ctx):
    p = sc.params
    end = (p["restart_day"] + ctx["day_offset"]) * 24 + p["restart_hour"]
    end = min(end, b.n)
    idx = np.arange(t0, end)
    b.mem_add[t0:end] += p["slope_per_day"] / 24.0 * (idx - t0)
    b.gc_cpu = max(b.gc_cpu, p["gc_cpu"])
    _win(b, sc.kind, t0, end, tail=8)


def sc_memory_step(b, sc, t0, ctx):
    p = sc.params
    end = min((p["rollback_day"] + ctx["day_offset"]) * 24 + p["rollback_hour"], b.n)
    b.mem_add[t0:end] += p["delta"]
    # one-hour ramp so hourly averages are not a perfect cliff
    b.mem_add[t0] -= p["delta"] * 0.35
    _win(b, sc.kind, t0, end, tail=8)


def sc_credit_exhaustion(b, sc, t0, ctx):
    p = sc.params
    end = min(t0 + p["days"] * 24, b.n)
    for d0 in range(t0, end, 24):
        b.cpu_add[d0 + 6:min(d0 + 22, b.n)] += p["extra_cpu"]
    _win(b, sc.kind, t0, end, tail=60)


def sc_disk_sudden_fill(b, sc, t0, ctx):
    p = sc.params
    end = min((p["cleanup_day"] + ctx["day_offset"]) * 24 + p["cleanup_hour"], b.n)
    over = p["over_hours"]
    for i in range(t0, end):
        b.disk_add[i] += p["jump"] * min(1.0, (i - t0 + 1) / over)
    b.disk_write_x[t0:t0 + over + 1] *= p["write_mult"]
    _win(b, sc.kind, t0, end, tail=8)


def sc_disk_log_growth(b, sc, t0, ctx):
    p = sc.params
    idx = np.arange(t0, b.n)
    b.disk_add[t0:] += p["slope_per_day"] / 24.0 * (idx - t0)
    b.disk_write_x[t0:] *= p["write_mult"]
    _win(b, sc.kind, t0, b.n, tail=0)


def sc_data_gap(b, sc, t0, ctx):
    p = sc.params
    for role in p["roles"]:
        m = b.gaps.setdefault(role, np.zeros(b.n, dtype=bool))
        m[t0:t0 + p["hours"]] = True
    _win(b, sc.kind, t0, t0 + p["hours"], tail=2)


SCENARIOS = {
    "traffic_surge": sc_traffic_surge,
    "downstream_surge": sc_downstream_surge,
    "net_ingress_anomaly": sc_net_ingress_anomaly,
    "net_egress_anomaly": sc_net_egress_anomaly,
    "net_traffic_loss": sc_net_traffic_loss,
    "anomaly_no_alert": sc_anomaly_no_alert,
    "cpu_flapping": sc_cpu_flapping,
    "transient_spike": sc_transient_spike,
    "cpu_runaway": sc_cpu_runaway,
    "recurring_batch": sc_recurring_batch,
    "memory_leak": sc_memory_leak,
    "memory_step": sc_memory_step,
    "credit_exhaustion": sc_credit_exhaustion,
    "disk_sudden_fill": sc_disk_sudden_fill,
    "disk_log_growth": sc_disk_log_growth,
    "data_gap": sc_data_gap,
}


# ── burst-credit physics ─────────────────────────────────────────────────────

def simulate_credits(demand_pct, vcpus, earn_per_hr, max_credits, init_frac=0.9):
    """Return (cpu_observed %, credit_balance_avg, unmet_pct)."""
    n = len(demand_pct)
    bal = max_credits * init_frac
    cpu_obs = np.zeros(n)
    credit = np.zeros(n)
    unmet = np.zeros(n)
    per_pct_hour = vcpus * 60.0 / 100.0          # credits consumed per hour per 1 % of total CPU
    for t in range(n):
        want = demand_pct[t] * per_pct_hour
        avail = bal + earn_per_hr
        used = min(want, avail)
        new_bal = min(max_credits, bal + earn_per_hr - used)
        cpu_obs[t] = used / per_pct_hour
        unmet[t] = (want - used) / per_pct_hour
        credit[t] = 0.5 * (bal + new_bal)
        bal = max(new_bal, 0.0)
    return cpu_obs, credit, unmet


# ── main entry point ─────────────────────────────────────────────────────────

def build_resource_series(
    provider, tier, instance_type, scenarios, roles, n_days, start_weekday,
    rng, web_latent, day_offset, lag_hours, weekday_of, apply_scenarios=True,
):
    """
    Return (arrays: role -> np.ndarray[n], windows: list[dict]).
    `web_latent` is the project's shared traffic signal (for web/app/db coupling).
    """
    n = n_days * 24
    p = TIER[tier]
    vcpus, mem_gb, earn, max_cred = INSTANCE[provider][instance_type]

    own = latent_load(n, start_weekday, tier, rng)
    if tier == "web":
        L = 0.7 * web_latent + 0.3 * own
    elif tier == "app":
        lagged = np.roll(web_latent, lag_hours)
        lagged[:lag_hours] = web_latent[:lag_hours]
        L = 0.75 * lagged + 0.25 * own
    elif tier == "db":
        sm = np.convolve(np.roll(web_latent, 2), np.ones(3) / 3, mode="same")
        L = 0.6 * sm + 0.4 * own
    else:
        L = own
    L = L / np.mean(L)

    b = Bundle.new(n)
    ctx = dict(lag=lag_hours, day_offset=day_offset, weekday_of=weekday_of)
    if apply_scenarios:
        for si, sc in enumerate(scenarios):
            b.cur = si
            day = sc.day + day_offset
            if sc.kind != "recurring_batch" and not (0 <= day < n_days - 1):
                continue
            SCENARIOS[sc.kind](b, sc, day * 24 + sc.hour, ctx)

    LM = L * b.mult
    hours = np.arange(n) % 24
    day_idx = np.arange(n) // 24

    # ---- memory (computed before cpu so GC pressure can feed back into cpu) ----
    m0, m1 = p["mem"]
    release_saw = 2.0 * ((day_idx % 14) / 14.0)              # deploy-cycle sawtooth
    mem = m0 + m1 * L * b.mult ** 0.2 + 0.03 * day_idx + release_saw + b.mem_add + rng.normal(0, 0.6, n)
    if b.gc_cpu > 0:
        b.cpu_add += b.gc_cpu * np.clip((mem - 85.0) / 8.0, 0.0, 1.0)

    # ---- cpu demand ----
    c0, c1 = p["cpu"]
    demand = c0 + c1 * LM + b.cpu_add + rng.normal(0, 1.1, n) + _ar1(rng, n, 0.6, 0.6)
    force = ~np.isnan(b.cpu_force)
    demand[force] = b.cpu_force[force] + rng.normal(0, 0.55, int(force.sum()))
    demand = np.clip(demand, 0.5, 100.0)

    arrays = {}
    burst = earn is not None
    if burst:
        cpu_obs, credit, unmet = simulate_credits(demand, vcpus, earn, max_cred)
        arrays["cpu"] = np.clip(cpu_obs, 0.3, 100.0)
        if "credit" in roles:
            arrays["credit"] = credit + rng.normal(0, 0.4, n) * (credit > 1)
            arrays["credit"] = np.clip(arrays["credit"], 0, max_cred)
        if "sched_wait" in roles:
            wait = 12.0 + unmet / 100.0 * vcpus * 3600.0 * 0.7
            arrays["sched_wait"] = np.clip(wait + rng.normal(0, 4.0, n), 0, None)
    else:
        arrays["cpu"] = demand

    arrays["mem"] = np.clip(mem, 3.0, 99.5)

    if "net_in" in roles:
        arrays["net_in"] = p["net_in"] * LM * b.net_in_x * np.exp(rng.normal(0, 0.07, n))
    if "net_out" in roles:
        arrays["net_out"] = p["net_out"] * LM * b.net_out_x * np.exp(rng.normal(0, 0.07, n))

    if "disk" in roles:
        weekly = np.zeros(n)
        for i in range(n):        # weekly logrotate sawtooth: +0.06/day, reset on Sunday 03:00
            wd = (start_weekday + i // 24) % 7
            weekly[i] = 0.06 * (((wd + 1) % 7) + (i % 24) / 24.0)
        disk = DB_DISK0 + 0.045 * day_idx + weekly + b.disk_add + rng.normal(0, 0.12, n)
        arrays["disk"] = np.clip(disk, 1.0, 99.8)
    if "disk_write" in roles:
        arrays["disk_write"] = DB_WRITE0 * LM * b.disk_write_x * np.exp(rng.normal(0, 0.09, n))

    for role, mask in b.gaps.items():
        if role in arrays:
            arrays[role] = arrays[role].astype(float)
            arrays[role][mask] = np.nan

    return {r: v for r, v in arrays.items() if r in roles or r in ("cpu", "mem")}, b.windows
