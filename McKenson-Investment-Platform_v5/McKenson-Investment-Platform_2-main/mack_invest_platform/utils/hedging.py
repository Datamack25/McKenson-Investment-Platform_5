# utils/hedging.py  —  MAM v5.2 · Couvertures par produits dérivés proposées par le desk
"""
Le desk ne propose pas seulement des actifs « simples » : pour chaque exposition
importante du portefeuille (actions US, Nasdaq / tech, Europe, émergents, énergie,
matières premières, obligations longues), il calcule une couverture par options
qui compense une baisse du marché concerné.

* Le ratio de couverture dépend des facteurs macro du desk (stress, géopolitique,
  croissance, politique monétaire, énergie…) : plus le risque est élevé, plus la
  part protégée est grande.
* Stratégie : put de protection (volatilité normale) ou put spread (volatilité
  élevée, pour réduire le coût).
* L'investisseur décide : chaque couverture peut être acceptée ou retirée.
* Chaque couverture passe par les contrôles de conformité (utils.compliance) ;
  une couverture d'indice dont le nominal ne dépasse pas l'exposition protégée
  est traitée comme une « couverture », autorisée pour tous les profils.
"""
from __future__ import annotations

import math
from datetime import datetime

import numpy as np

from utils.options import bs_price, bs_greeks
from utils.option_strategies import round_strike, analyze

T_DAYS = 90             # échéance standard des couvertures
RATE = 0.04
MULT = 100              # options sur ETF : 100 titres par contrat

TECH = {"AAPL", "MSFT", "NVDA", "GOOGL", "GOOG", "META", "AMZN", "TSLA", "NFLX", "AMD", "INTC", "AVGO",
        "ORCL", "CRM", "ADBE", "QCOM", "QQQ", "XLK", "SOXX", "SMH", "PANX.PA", "ARKK"}
ENERGY_EQ = {"XOM", "CVX", "COP", "OXY", "SLB", "EOG", "XLE", "TTE.PA", "BP.L", "SHEL.L", "SHEL",
             "ENI.MI", "EQNR", "REP.MC"}
COMMODITY = {"USO", "BNO", "UNG", "CL=F", "BZ=F", "NG=F", "MCL=F", "DBC", "PDBC", "GSG", "DBA", "DBB"}

# Paniers d'exposition couvrables
BUCKETS = {
    "tech":      dict(label="Actions technologiques / Nasdaq", hedge="QQQ", vol=1.30, choc=-0.25,
                      risque="une baisse du Nasdaq (valeurs de croissance sensibles aux taux)"),
    "us":        dict(label="Actions américaines (S&P 500)", hedge="SPY", vol=1.00, choc=-0.20,
                      risque="une baisse du marché actions américain"),
    "europe":    dict(label="Actions européennes", hedge="VGK", vol=1.10, choc=-0.20,
                      risque="une baisse des actions européennes"),
    "em":        dict(label="Actions émergentes", hedge="EEM", vol=1.25, choc=-0.25,
                      risque="une baisse des marchés émergents (dollar fort, stress)"),
    "energie":   dict(label="Actions du secteur énergie", hedge="XLE", vol=1.50, choc=-0.30,
                      risque="un retournement du prix du pétrole et des valeurs pétrolières"),
    "matieres":  dict(label="Matières premières / pétrole", hedge="USO", vol=2.00, choc=-0.30,
                      risque="une chute du pétrole et des matières premières"),
    "taux":      dict(label="Obligations d'État longues", hedge="TLT", vol=0.90, choc=-0.12,
                      risque="une remontée des taux longs (inflation, banques centrales)"),
}

# Classes du desk (utils.advisor.CLASSES) → panier couvrable
CLASS_TO_BUCKET = {
    "Actions US": "us", "Actions Europe": "europe", "Actions Asie & émergents": "em",
    "Oblig. long terme": "taux", "Matières premières": "matieres",
}


# ══════════════════════════════════════════════════════════════════════════════
#  EXPOSITIONS
# ══════════════════════════════════════════════════════════════════════════════
def bucket_of(ticker: str) -> str | None:
    t = ticker.upper().strip()
    if t in ENERGY_EQ:
        return "energie"
    if t in COMMODITY or t.endswith("=F") and t not in ("GC=F", "SI=F"):
        return "matieres"
    if t in TECH:
        return "tech"
    try:
        from utils.advisor import classify_ticker
        return CLASS_TO_BUCKET.get(classify_ticker(t) or "")
    except Exception:
        return None


def exposures_from_values(values: dict[str, float]) -> dict[str, dict]:
    """{ticker: valeur $} → {panier: {montant, lignes}}."""
    out: dict[str, dict] = {}
    for t, v in values.items():
        if not v or v <= 0:
            continue
        b = bucket_of(t)
        if b:
            e = out.setdefault(b, {"montant": 0.0, "lignes": []})
            e["montant"] += float(v)
            e["lignes"].append(t)
    return out


def exposures_from_allocation(weights, capital: float) -> dict[str, dict]:
    """Allocation du desk par classe (pd.Series) → expositions par panier."""
    from utils.advisor import CLASS_PROXY
    out: dict[str, dict] = {}
    for cls, w in weights.items():
        b = CLASS_TO_BUCKET.get(cls)
        if b and w > 0:
            e = out.setdefault(b, {"montant": 0.0, "lignes": []})
            e["montant"] += float(w) * capital
            e["lignes"].append(CLASS_PROXY.get(cls, cls))
    return out


# ══════════════════════════════════════════════════════════════════════════════
#  RISQUE PAR PANIER (à partir des facteurs du desk, échelle −2 … +2)
# ══════════════════════════════════════════════════════════════════════════════
def bucket_risk(bucket: str, f: dict) -> tuple[float, list[str]]:
    g = lambda k: float(f.get(k, 0.0) or 0.0)
    stress, geo, growth, mon = g("stress"), g("geopolitique"), g("croissance"), g("monetaire")
    infl, energy, dollar = g("inflation"), g("energie"), g("dollar")
    why = []
    if bucket in ("us", "tech", "europe", "em"):
        r = 0.5 * stress + 0.3 * geo - 0.4 * growth + 0.2 * mon
        if bucket == "tech":
            r += 0.3 * mon
            if mon > 0.3:
                why.append(f"politique monétaire restrictive ({mon:+.1f}) : les valeurs de croissance y sont très sensibles")
        if bucket == "europe":
            r += 0.2 * geo + 0.2 * energy
        if bucket == "em":
            r += 0.3 * dollar
            if dollar > 0.3:
                why.append(f"dollar fort ({dollar:+.1f}) : pénalise les émergents")
        if stress > 0.3:
            why.append(f"stress de marché élevé ({stress:+.1f})")
        if geo > 0.3:
            why.append(f"tensions géopolitiques ({geo:+.1f})")
        if growth < -0.2:
            why.append(f"croissance qui ralentit ({growth:+.1f})")
    elif bucket in ("energie", "matieres"):
        r = 0.4 * stress - 0.5 * growth + 0.3 * abs(energy) + 0.2 * geo
        if abs(energy) > 0.4:
            why.append(f"choc énergétique en cours ({energy:+.1f}) : risque de retournement brutal des prix")
        if growth < -0.2:
            why.append(f"ralentissement économique ({growth:+.1f}) : la demande d'énergie baisse")
        if stress > 0.3:
            why.append(f"stress de marché ({stress:+.1f})")
    else:  # taux longs
        r = 0.6 * infl + 0.5 * mon
        if infl > 0.3:
            why.append(f"pression inflationniste ({infl:+.1f})")
        if mon > 0.3:
            why.append(f"banques centrales restrictives ({mon:+.1f})")
    if not why:
        why.append("contexte calme : couverture d'assurance de base, facultative")
    return float(np.clip(r, -2, 2)), why


# ══════════════════════════════════════════════════════════════════════════════
#  PROPOSITIONS
# ══════════════════════════════════════════════════════════════════════════════
def _legs(strategy: str, spot: float, T: float, sigma: float, n: int) -> list[dict]:
    k1 = round_strike(spot * 0.95)
    legs = [{"type": "put", "qty": n, "K": k1, "premium": float(bs_price(spot, k1, T, RATE, sigma, "put"))}]
    if strategy == "Put spread":
        k2 = round_strike(spot * 0.85)
        if k2 >= k1:
            k2 = round_strike(k1 * 0.9)
        legs.append({"type": "put", "qty": -n, "K": k2, "premium": float(bs_price(spot, k2, T, RATE, sigma, "put"))})
    return legs


def propose_hedges(exposures: dict[str, dict], factors: dict, vix: float | None, nav: float,
                   prices: dict | None = None, min_weight: float = 0.05) -> list[dict]:
    """Une proposition de couverture par panier significatif (≥ min_weight de l'actif net)."""
    vix = float(vix) if vix is not None and np.isfinite(vix) else 18.0
    T = T_DAYS / 365.0
    out = []
    for b, e in sorted(exposures.items(), key=lambda kv: -kv[1]["montant"]):
        if nav <= 0 or e["montant"] / nav < min_weight:
            continue
        meta = dict(BUCKETS[b])
        risk, why = bucket_risk(b, factors)
        recommended = risk >= 0.25
        ratio = float(np.clip(0.30 + 0.20 * risk, 0.25, 0.75)) if recommended else 0.25
        calib = None
        try:  # paramètres calibrés sur l'historique, si un administrateur les a appliqués (v5.4)
            from utils.calibration import active_hedge, hedge_ratio_from_calibration
            calib = active_hedge(b)
        except Exception:
            calib = None
        if calib:
            if calib.get("vol_calibre"):
                meta["vol"] = float(calib["vol_calibre"])
            if calib.get("choc_calibre"):
                meta["choc"] = float(calib["choc_calibre"])
            if calib.get("predictif"):
                ratio, recommended = hedge_ratio_from_calibration(calib, risk)
                p_ = 1 / (1 + math.exp(-(calib["logit_a"] + calib["logit_b"] * risk)))
                why = why + [f"historique : probabilité d'une baisse de plus de {abs(calib['seuil_perte']):.0%} "
                             f"en 3 mois ≈ {p_:.0%} à ce niveau de risque (moyenne {calib['frequence']:.0%})"]
        sigma = float(np.clip(vix / 100 * meta["vol"], 0.08, 0.90))
        strategy = "Put spread" if vix >= 22 or sigma >= 0.35 else "Put de protection"
        und = meta["hedge"]
        spot = None
        if prices and und in prices:
            v = prices[und]
            spot = float(v[0] if isinstance(v, (list, tuple)) else v)
        if not spot:
            try:
                from utils.data import get_price
                spot = float(get_price(und))
            except Exception:
                spot = 100.0
        contract_value = spot * MULT
        n = int(math.floor(e["montant"] * ratio / contract_value))
        unit_legs = _legs(strategy, spot, T, sigma, 1)
        unit_cost = analyze(unit_legs, spot, MULT, T, RATE, sigma)["debit"]
        legs = _legs(strategy, spot, T, sigma, n) if n else []
        cost = unit_cost * n
        covered = n * contract_value
        # Scénario de baisse du marché concerné : ce que la couverture rapporte à l'échéance
        s_shock = spot * (1 + meta["choc"])
        payoff = sum(l["qty"] * MULT * max(l["K"] - s_shock, 0.0) for l in legs)
        loss = e["montant"] * meta["choc"]
        delta = sum(l["qty"] * MULT * bs_greeks(spot, l["K"], T, RATE, sigma, "put")["delta"] for l in legs)
        out.append(dict(
            cle=b, panier=meta["label"], sous_jacent=und, spot=spot, sigma=sigma,
            strategie=strategy, legs=legs, legs_unitaires=unit_legs,
            contrats=n, exposition=e["montant"], lignes=e["lignes"], ratio=ratio,
            couvert=covered, ratio_effectif=covered / e["montant"] if e["montant"] else 0.0,
            cout=cost, cout_pct=cost / nav if nav else 0.0, cout_contrat=unit_cost,
            valeur_contrat=contract_value, choc=meta["choc"], perte_sans=loss,
            gain_couverture=payoff, perte_avec=loss + payoff - cost,
            recommandee=recommended, risque=risk, pourquoi=why, protege_contre=meta["risque"],
            echeance=T_DAYS, delta=delta, calibree=bool(calib),
        ))
    return out


# ══════════════════════════════════════════════════════════════════════════════
#  EXÉCUTION (avec contrôles de conformité)
# ══════════════════════════════════════════════════════════════════════════════
def _existing_hedge(port: dict, h: dict) -> list[dict]:
    """Lignes d'options vivantes de la couverture du même panier (même sous-jacent)."""
    from utils.options import remaining_days
    lab = f"Couverture {h['panier']}"
    return [o for o in port.get("options", []) or []
            if str(o.get("strategy", "")).startswith(lab) and o.get("ticker") == h["sous_jacent"]
            and int(o.get("n_contracts", 0)) > 0 and remaining_days(o) > 0]


def execute_hedge(port: dict, h: dict, tag: str = "Hedge Fund Agent") -> str:
    """Met la couverture du panier au niveau recommandé. Renvoie '' si c'est fait, sinon la raison.

    v5.5 : la recommandation donne le NOMBRE TOTAL de contrats visé pour le panier. Si une couverture
    existe déjà, on AJUSTE la ligne existante (achat du complément, ou revente de l'excédent en commençant
    par les lignes les plus récentes) au lieu d'ajouter une ligne en double. Le détail est placé dans
    h["ajustement"]."""
    from utils.compliance import Decision, log_decision, pre_trade_options
    from utils.options import book_option, consolidate_options, remaining_days
    consolidate_options(port)                          # fusionne d'éventuelles lignes identiques déjà en double
    existing = _existing_hedge(port, h)
    target = int(h["contrats"])
    now_dt = datetime.now()
    now = now_dt.strftime("%Y-%m-%d %H:%M")
    sid = f"H{now_dt:%H%M%S}{h['cle'][:3].upper()}"
    label = f"Couverture {h['panier']} ({h['strategie']})"

    if not existing:                                   # ── première couverture du panier ──
        if target <= 0:
            return (f"{h['panier']} : exposition trop faible pour un contrat "
                    f"(1 contrat {h['sous_jacent']} ≈ ${h['valeur_contrat']:,.0f})")
        dec, a = pre_trade_options(port, h["sous_jacent"], h["legs"], spot=h["spot"], mult=MULT,
                                   T_days=h["echeance"], r=RATE, sigma=h["sigma"],
                                   hedge_exposure=h["exposition"])
        log_decision(dec, port, h["sous_jacent"], f"COUVERTURE {h['strategie']}", target,
                     a["net_premium"], executed=dec.allowed, note=f"{tag} — {h['panier']}")
        if not dec.allowed:
            return f"{h['panier']} bloquée — " + "; ".join(f"[{c.code}] {c.title}" for c in dec.blocks)
        for l in h["legs"]:
            buy = l["qty"] > 0
            k = abs(int(l["qty"]))
            tot = l["premium"] * k * MULT
            book_option(port, {
                "date": now, "ticker": h["sous_jacent"], "type": "put", "action": "BUY" if buy else "SELL",
                "strike": round(l["K"], 4), "maturity_days": h["echeance"], "sigma": round(h["sigma"] * 100, 2),
                "n_contracts": k, "contract_mult": MULT, "premium": round(l["premium"], 6),
                "total_premium": round(tot, 2), "spot_at_entry": round(h["spot"], 4), "currency": "USD",
                "strategy": label, "strategy_id": sid})
            port["cash"] = port.get("cash", 0.0) + (-tot if buy else tot)
        port.setdefault("trades", []).append({
            "date": now, "ticker": f"{h['sous_jacent']} {h['strategie']}", "action": "COUVERTURE OPTIONS",
            "qty": target, "price": round(a["net_premium"] / max(target * MULT, 1), 6),
            "total": round(a["net_premium"], 2), "source": tag, "conformite": "contrôlé"})
        h["ajustement"] = f"{h['panier']} : nouvelle couverture de {target} contrat(s) {h['sous_jacent']}"
        return ""

    # ── une couverture existe : on ajuste les lignes existantes ──────────────────
    longs = [o for o in existing if str(o.get("action", "BUY")).upper() == "BUY"]
    shorts = [o for o in existing if str(o.get("action", "BUY")).upper() == "SELL"]
    n_old = sum(int(o["n_contracts"]) for o in longs)
    diff = target - n_old
    if diff == 0:
        h["ajustement"] = f"{h['panier']} : couverture déjà au niveau recommandé ({n_old} contrat(s)), aucun ordre"
        return ""
    spot, sigma = float(h["spot"]), float(h["sigma"])

    def _px(o):
        T = max(remaining_days(o), 1.0) / 365.0
        return float(bs_price(spot, float(o["strike"]), T, RATE, sigma, "put"))

    def _leg(o, qty_abs, action):
        p = _px(o)
        return p, {"date": now, "ticker": o["ticker"], "type": "put", "action": action, "strike": o["strike"],
                   "maturity_days": max(int(round(remaining_days(o))), 1), "sigma": round(sigma * 100, 2),
                   "n_contracts": int(qty_abs), "contract_mult": MULT, "premium": round(p, 6),
                   "total_premium": round(p * qty_abs * MULT, 2), "spot_at_entry": round(spot, 4),
                   "currency": "USD", "strategy": o.get("strategy", label), "strategy_id": o.get("strategy_id", sid)}

    cash_flow = 0.0
    if diff > 0:                                       # ── renforcer la ligne existante (échéance la plus longue) ──
        base = max(longs, key=remaining_days) if longs else None
        if base is None:
            return f"{h['panier']} : structure de couverture inattendue (aucune jambe acheteuse)"
        plan = [(base, diff, "BUY")]
        if shorts:                                     # put spread : la jambe vendue suit
            plan.append((max(shorts, key=remaining_days), diff, "SELL"))
        legs_chk = [{"type": "put", "qty": q if a_ == "BUY" else -q, "K": float(o["strike"]), "premium": _px(o)}
                    for o, q, a_ in plan]
        dec, a = pre_trade_options(port, h["sous_jacent"], legs_chk, spot=spot, mult=MULT,
                                   T_days=max(int(remaining_days(base)), 1), r=RATE, sigma=sigma,
                                   hedge_exposure=h["exposition"])
        log_decision(dec, port, h["sous_jacent"], f"RENFORCEMENT COUVERTURE {h['strategie']}", diff,
                     a["net_premium"], executed=dec.allowed, note=f"{tag} — {h['panier']}")
        if not dec.allowed:
            return f"{h['panier']} bloquée — " + "; ".join(f"[{c.code}] {c.title}" for c in dec.blocks)
        for o, q, act in plan:
            p, leg = _leg(o, q, act)
            book_option(port, leg)
            cash_flow += (-1 if act == "BUY" else 1) * p * q * MULT
        verb = "renforcée"
    else:                                              # ── réduire : revente de l'excédent, lignes récentes d'abord ──
        def _reduce(lines, qty, close_action):
            nonlocal cash_flow
            for o in sorted(lines, key=lambda x: str(x.get("date", "")), reverse=True):
                if qty <= 0:
                    break
                q = min(qty, int(o["n_contracts"]))
                p, leg = _leg(o, q, close_action)
                book_option(port, leg)
                cash_flow += (1 if close_action == "SELL" else -1) * p * q * MULT
                qty -= q
        _reduce(longs, -diff, "SELL")                  # revente des puts achetés
        if shorts:
            _reduce(shorts, -diff, "BUY")              # rachat des puts vendus (put spread)
        dec = Decision("option")                       # réduction de risque : pas de contrôle bloquant
        log_decision(dec, port, h["sous_jacent"], f"RÉDUCTION COUVERTURE {h['strategie']}", -diff, cash_flow,
                     executed=True, note=f"{tag} — {h['panier']}")
        verb = "réduite"
    port["cash"] = port.get("cash", 0.0) + cash_flow
    port.setdefault("trades", []).append({
        "date": now, "ticker": f"{h['sous_jacent']} {h['strategie']}", "action": "AJUSTEMENT COUVERTURE",
        "qty": diff, "price": round(abs(cash_flow) / max(abs(diff) * MULT, 1), 6),
        "total": round(-cash_flow, 2), "source": tag, "conformite": "contrôlé"})
    h["ajustement"] = f"{h['panier']} : couverture {verb} de {n_old} à {target} contrat(s) {h['sous_jacent']}"
    return ""
