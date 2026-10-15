# utils/ml_engine.py  —  MAM v5 · Machine learning appliqué aux marchés
"""
Pipeline d'apprentissage :

1. Caractéristiques par actif (momentum, volatilité, techniques, bêta) +
   facteurs macro communs (VIX, courbe, taux, dollar, pétrole, cuivre/or,
   crédit, tendance S&P 500).
2. Cibles : rendement à 21 jours ouvrés (≈ 1 mois) et probabilité de hausse.
3. Modèles : ensemble Gradient Boosting (non linéaire) + régression logistique
   (linéaire, régularisée) ; validation walk-forward avec purge de 21 jours
   (aucune fuite d'information future).
4. Détection du régime de marché par mélange gaussien (GMM) sur les facteurs
   macro, avec noms de régimes interprétables.
5. Recommandations par actif + facteurs explicatifs.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.mixture import GaussianMixture
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from utils.market_intel import ASSET_CLASSES, asset_class, macro_features

warnings.filterwarnings("ignore", category=RuntimeWarning)

HORIZON = 21          # jours ouvrés
SAMPLE_EVERY = 5      # échantillonnage hebdomadaire (réduit l'autocorrélation)

FEATURE_LABELS = {
    "mom_5": "Momentum 1 semaine", "mom_21": "Momentum 1 mois", "mom_63": "Momentum 3 mois",
    "mom_126": "Momentum 6 mois", "mom_12_1": "Momentum 12-1 mois",
    "vol_21": "Volatilité 1 mois", "vol_63": "Volatilité 3 mois", "vol_ratio": "Accélération de la volatilité",
    "rsi": "RSI 14", "macd": "MACD (normalisé)", "dist_50": "Écart à la moyenne 50 j",
    "dist_200": "Écart à la moyenne 200 j", "dd_63": "Drawdown 3 mois", "beta": "Bêta vs S&P 500",
    "skew": "Asymétrie des rendements",
    "vix": "Niveau du VIX", "vix_chg_21": "Variation du VIX", "vix_z": "VIX vs sa moyenne",
    "curve": "Pente de la courbe des taux", "rate_chg_63": "Variation du taux 10 ans",
    "dxy_63": "Dollar (3 mois)", "oil_63": "Pétrole (3 mois)", "gold_63": "Or (3 mois)",
    "copper_gold_63": "Ratio cuivre/or", "credit_63": "Crédit HY vs Treasuries",
    "spy_trend": "Tendance S&P 500", "spy_ret_63": "Performance S&P 500 3 mois",
    "spy_vol_63": "Volatilité S&P 500", "cls": "Classe d'actif",
}

FEATURE_FAMILY = {
    **{k: "Momentum" for k in ("mom_5", "mom_21", "mom_63", "mom_126", "mom_12_1")},
    **{k: "Volatilité & risque" for k in ("vol_21", "vol_63", "vol_ratio", "dd_63", "beta", "skew")},
    **{k: "Technique" for k in ("rsi", "macd", "dist_50", "dist_200")},
    **{k: "Sentiment de marché" for k in ("vix", "vix_chg_21", "vix_z", "credit_63")},
    **{k: "Taux & monnaie" for k in ("curve", "rate_chg_63", "dxy_63")},
    **{k: "Matières premières" for k in ("oil_63", "gold_63", "copper_gold_63")},
    **{k: "Cycle actions" for k in ("spy_trend", "spy_ret_63", "spy_vol_63")},
    "cls": "Classe d'actif",
}

ASSET_FEATS = ["mom_5", "mom_21", "mom_63", "mom_126", "mom_12_1", "vol_21", "vol_63",
               "vol_ratio", "rsi", "macd", "dist_50", "dist_200", "dd_63", "beta", "skew"]
MACRO_FEATS = ["vix", "vix_chg_21", "vix_z", "curve", "rate_chg_63", "dxy_63", "oil_63",
               "gold_63", "copper_gold_63", "credit_63", "spy_trend", "spy_ret_63", "spy_vol_63"]
ALL_FEATS = ASSET_FEATS + MACRO_FEATS + ["cls"]


# ══════════════════════════════════════════════════════════════════════════════
#  FEATURES
# ══════════════════════════════════════════════════════════════════════════════

def _rsi(px: pd.Series, n: int = 14) -> pd.Series:
    d = px.diff()
    g = d.clip(lower=0).ewm(com=n - 1, min_periods=n).mean()
    l = (-d).clip(lower=0).ewm(com=n - 1, min_periods=n).mean()
    return 100 - 100 / (1 + g / l.replace(0, np.nan))


def asset_features(px: pd.Series, mkt: pd.Series | None) -> pd.DataFrame:
    px = px.astype(float)
    r = px.pct_change(fill_method=None)
    f = pd.DataFrame(index=px.index)
    for n in (5, 21, 63, 126):
        f[f"mom_{n}"] = px.pct_change(n, fill_method=None)
    f["mom_12_1"] = px.shift(21) / px.shift(252) - 1
    f["vol_21"] = r.rolling(21).std() * np.sqrt(252)
    f["vol_63"] = r.rolling(63).std() * np.sqrt(252)
    f["vol_ratio"] = f["vol_21"] / f["vol_63"]
    f["rsi"] = _rsi(px)
    ema12, ema26 = px.ewm(span=12, adjust=False).mean(), px.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    f["macd"] = (macd - macd.ewm(span=9, adjust=False).mean()) / px
    f["dist_50"] = px / px.rolling(50).mean() - 1
    f["dist_200"] = px / px.rolling(200, min_periods=120).mean() - 1
    f["dd_63"] = px / px.rolling(63).max() - 1
    if mkt is not None:
        mr = mkt.pct_change(fill_method=None)
        f["beta"] = r.rolling(63).cov(mr) / mr.rolling(63).var()
    else:
        f["beta"] = np.nan
    f["skew"] = r.rolling(63).skew()
    return f


def build_panel(prices: pd.DataFrame, macro: pd.DataFrame) -> pd.DataFrame:
    """Panel long (date, ticker) avec features, cibles et classe d'actif."""
    mf = macro_features(macro, prices)
    mkt = prices["SPY"] if "SPY" in prices else None
    frames = []
    for t in prices.columns:
        px = prices[t].dropna()
        if len(px) < 300:
            continue
        f = asset_features(px, mkt.reindex(px.index) if mkt is not None else None)
        f = f.join(mf[MACRO_FEATS], how="left")
        f["cls"] = ASSET_CLASSES.index(asset_class(t)) if asset_class(t) in ASSET_CLASSES else 0
        fwd = px.shift(-HORIZON) / px - 1
        f["y_ret"] = fwd
        f["ticker"] = t
        f["date"] = f.index
        frames.append(f.iloc[252:])  # attendre un an d'historique pour les features longues
    if not frames:
        return pd.DataFrame()
    panel = pd.concat(frames, ignore_index=True)
    panel = panel.replace([np.inf, -np.inf], np.nan)
    return panel


# ══════════════════════════════════════════════════════════════════════════════
#  MODÈLES
# ══════════════════════════════════════════════════════════════════════════════

def _make_models():
    clf = HistGradientBoostingClassifier(max_iter=160, learning_rate=0.05, max_depth=4,
                                         min_samples_leaf=40, l2_regularization=1.0,
                                         categorical_features=[len(ALL_FEATS) - 1],
                                         random_state=0)
    reg = HistGradientBoostingRegressor(max_iter=160, learning_rate=0.05, max_depth=3,
                                        min_samples_leaf=60, l2_regularization=1.0,
                                        loss="absolute_error",
                                        categorical_features=[len(ALL_FEATS) - 1],
                                        random_state=0)
    lin = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                        LogisticRegression(C=0.05, max_iter=500))
    return clf, reg, lin


class MarketModel:
    """Ensemble entraîné ; prédit P(hausse à 1 mois) et rendement attendu à 1 mois."""

    def __init__(self):
        self.clf, self.reg, self.lin = _make_models()
        self.fitted = False
        self.feat_mean = None
        self.feat_std = None
        self.feat_corr = None

    def fit(self, train: pd.DataFrame) -> "MarketModel":
        tr = train.dropna(subset=["y_ret"])
        tr = tr.iloc[::1]
        X = tr[ALL_FEATS].astype(float).values
        y_ret = tr["y_ret"].clip(tr["y_ret"].quantile(.01), tr["y_ret"].quantile(.99)).values
        y_up = (tr["y_ret"].values > 0).astype(int)
        if len(np.unique(y_up)) < 2 or len(tr) < 200:
            return self
        self.clf.fit(X, y_up)
        self.reg.fit(X, y_ret)
        self.lin.fit(X[:, :-1], y_up)
        num = tr[ALL_FEATS[:-1]].astype(float)
        self.feat_mean = num.mean()
        self.feat_std = num.std().replace(0, np.nan)
        self.feat_corr = num.corrwith(pd.Series(y_ret, index=num.index), method="spearman").fillna(0)
        self.fitted = True
        return self

    def predict(self, X_df: pd.DataFrame) -> pd.DataFrame:
        X = X_df[ALL_FEATS].astype(float).values
        p1 = self.clf.predict_proba(X)[:, 1]
        p2 = self.lin.predict_proba(X[:, :-1])[:, 1]
        p = 0.6 * p1 + 0.4 * p2
        er = self.reg.predict(X)
        return pd.DataFrame({"p_up": p, "exp_ret": er}, index=X_df.index)


def walk_forward(panel: pd.DataFrame, n_folds: int = 5) -> dict:
    """Validation chronologique avec purge ; renvoie métriques hors-échantillon."""
    data = panel.dropna(subset=["y_ret"]).copy()
    dates = np.sort(data["date"].unique())
    data = data[data["date"].isin(dates[::SAMPLE_EVERY])]
    dates = np.sort(data["date"].unique())
    if len(dates) < 120:
        return {"ok": False}
    start = int(len(dates) * 0.4)
    edges = np.linspace(start, len(dates), n_folds + 1).astype(int)
    preds = []
    last_model, last_test = None, None
    purge = HORIZON // SAMPLE_EVERY + 1
    for k in range(n_folds):
        te_dates = dates[edges[k]:edges[k + 1]]
        tr_dates = dates[:max(0, edges[k] - purge)]
        if len(te_dates) == 0 or len(tr_dates) < 60:
            continue
        tr = data[data["date"].isin(tr_dates)]
        te = data[data["date"].isin(te_dates)]
        m = MarketModel().fit(tr)
        if not m.fitted:
            continue
        p = m.predict(te)
        preds.append(te[["date", "ticker", "y_ret"]].join(p))
        last_model, last_test = m, te
    if not preds:
        return {"ok": False}
    oos = pd.concat(preds)
    y = (oos["y_ret"] > 0).astype(int)
    acc = float(((oos["p_up"] > 0.5).astype(int) == y).mean())
    base = float(max(y.mean(), 1 - y.mean()))
    try:
        auc = float(roc_auc_score(y, oos["p_up"]))
    except Exception:
        auc = 0.5
    # IC : corrélation de rang transversale, moyenne par date
    ics, spreads = [], []
    for _, g in oos.groupby("date"):
        if len(g) >= 5:
            ic = g["exp_ret"].rank().corr(g["y_ret"].rank())
            if ic == ic:
                ics.append(ic)
            q = g["exp_ret"].quantile([.2, .8])
            top = g[g["exp_ret"] >= q.iloc[1]]["y_ret"].mean()
            bot = g[g["exp_ret"] <= q.iloc[0]]["y_ret"].mean()
            spreads.append(top - bot)
    ic_mean = float(np.mean(ics)) if ics else 0.0
    ic_t = float(ic_mean / (np.std(ics) / np.sqrt(len(ics)))) if len(ics) > 2 and np.std(ics) > 0 else 0.0
    spread = float(np.mean(spreads)) if spreads else 0.0
    # Importance des variables (permutation sur le dernier pli, échantillonné)
    importance = _permutation_importance(last_model, last_test)
    return {"ok": True, "accuracy": acc, "baseline": base, "auc": auc, "ic": ic_mean,
            "ic_t": ic_t, "ls_spread_month": spread, "n_obs": int(len(oos)),
            "oos": oos, "importance": importance,
            "period": (pd.Timestamp(oos["date"].min()), pd.Timestamp(oos["date"].max()))}


def _permutation_importance(model: MarketModel | None, test: pd.DataFrame | None,
                            n_rep: int = 3, max_rows: int = 2500) -> pd.Series:
    if model is None or test is None or len(test) < 50:
        return pd.Series(dtype=float)
    te = test.sample(min(max_rows, len(test)), random_state=0)
    y = (te["y_ret"] > 0).astype(int).values
    if len(np.unique(y)) < 2:
        return pd.Series(dtype=float)
    base = roc_auc_score(y, model.predict(te)["p_up"])
    rng = np.random.default_rng(0)
    out = {}
    for f in ALL_FEATS:
        drops = []
        for _ in range(n_rep):
            tmp = te.copy()
            tmp[f] = rng.permutation(tmp[f].values)
            drops.append(base - roc_auc_score(y, model.predict(tmp)["p_up"]))
        out[f] = float(np.mean(drops))
    s = pd.Series(out).clip(lower=0)
    if s.sum() > 0:
        s = s / s.sum()
    return s.sort_values(ascending=False)


# ══════════════════════════════════════════════════════════════════════════════
#  RÉGIMES DE MARCHÉ
# ══════════════════════════════════════════════════════════════════════════════

REGIME_NAMES = ["Crise / Risk-off", "Ralentissement", "Reprise", "Expansion / Risk-on"]
REGIME_COLORS = {"Crise / Risk-off": "#ff3b6b", "Ralentissement": "#ff8c00",
                 "Reprise": "#ffd700", "Expansion / Risk-on": "#00ff88"}
REGIME_TEXT = {
    "Crise / Risk-off": "Volatilité élevée, actions en baisse, écartement du crédit : priorité à la "
                        "préservation du capital (obligations d'État, or, monétaire).",
    "Ralentissement": "Momentum qui s'essouffle et signaux macro mitigés : réduire le bêta, "
                      "privilégier qualité, défensives et duration modérée.",
    "Reprise": "Volatilité qui reflue après un stress, crédit qui se normalise : réintroduire "
               "progressivement le risque (cycliques, small caps, émergents).",
    "Expansion / Risk-on": "Tendance haussière, volatilité basse, crédit porteur : surpondérer les "
                           "actions et actifs de croissance, garder une couverture légère.",
}
_REG_FEATS = ["spy_ret_63", "spy_vol_63", "vix_z", "credit_63", "curve", "spy_trend"]


def detect_regimes(mf: pd.DataFrame, n_states: int = 4) -> dict:
    """Mélange gaussien sur les facteurs macro ; noms attribués par score de risque."""
    X = mf[_REG_FEATS].dropna()
    X = X[X.index.dayofweek < 5]
    if len(X) < 150:
        return {"ok": False}
    mu, sd = X.mean(), X.std().replace(0, 1)
    Z = (X - mu) / sd
    gmm = GaussianMixture(n_components=n_states, covariance_type="full", random_state=0,
                          n_init=3, reg_covar=1e-3).fit(Z.values)
    proba = pd.DataFrame(gmm.predict_proba(Z.values), index=X.index)
    # score de « risk-on » de chaque composante
    cent = pd.DataFrame(gmm.means_, columns=_REG_FEATS)
    score = (cent["spy_ret_63"] - cent["spy_vol_63"] - cent["vix_z"] + cent["credit_63"]
             + 0.5 * cent["spy_trend"])
    order = score.sort_values().index.tolist()
    names = {comp: REGIME_NAMES[min(i * len(REGIME_NAMES) // n_states, len(REGIME_NAMES) - 1)]
             for i, comp in enumerate(order)}
    proba.columns = [names[c] for c in proba.columns]
    proba = proba.T.groupby(level=0).sum().T.reindex(columns=REGIME_NAMES, fill_value=0.0)
    smooth = proba.rolling(5, min_periods=1).mean()
    label = smooth.idxmax(axis=1)
    cur = smooth.iloc[-1]
    last = mf.dropna(subset=["rate_chg_63"]).iloc[-1] if mf["rate_chg_63"].notna().any() else mf.iloc[-1]
    infl = bool((last.get("rate_chg_63", 0) or 0) > 0.35 and (last.get("oil_63", 0) or 0) > 0.08)
    profile = pd.DataFrame({
        n: (X.loc[label == n].mean() if (label == n).any() else pd.Series(np.nan, index=_REG_FEATS))
        for n in REGIME_NAMES}).T
    return {"ok": True, "proba": smooth, "label": label, "current": str(cur.idxmax()),
            "current_proba": cur, "inflation_flag": infl, "profile": profile,
            "model": gmm, "scaler": (mu, sd), "names": names}


def regime_at(mf: pd.DataFrame, date) -> tuple[str, bool]:
    """Régime calculé uniquement avec les données disponibles à `date` (pour le backtest)."""
    sub = mf.loc[:date]
    r = detect_regimes(sub)
    if not r.get("ok"):
        return "Ralentissement", False
    return r["current"], r["inflation_flag"]


# ══════════════════════════════════════════════════════════════════════════════
#  PIPELINE COMPLET + RECOMMANDATIONS
# ══════════════════════════════════════════════════════════════════════════════

def latest_rows(panel: pd.DataFrame) -> pd.DataFrame:
    return panel.sort_values("date").groupby("ticker").tail(1).set_index("ticker")


def signal_label(p: float, er: float) -> tuple[str, str]:
    if p >= 0.58 and er > 0:
        return "SURPONDÉRER", "#00ff88"
    if p >= 0.53 and er > -0.002:
        return "RENFORCER", "#7cf0b5"
    if p <= 0.42 and er < 0:
        return "SOUS-PONDÉRER", "#ff3b6b"
    if p <= 0.47:
        return "ALLÉGER", "#ff8c00"
    return "NEUTRE", "#94a3b8"


def explain_row(model: MarketModel, row: pd.Series, importance: pd.Series, k: int = 3) -> tuple[list, list]:
    """Facteurs qui poussent la prévision à la hausse / à la baisse (approximation locale)."""
    if model.feat_mean is None:
        return [], []
    feats = [f for f in ALL_FEATS[:-1]]
    z = ((row[feats].astype(float) - model.feat_mean[feats]) / model.feat_std[feats]).fillna(0).clip(-3, 3)
    imp = importance.reindex(feats).fillna(importance.mean() if len(importance) else 0.02) + 1e-3
    contrib = z * np.sign(model.feat_corr[feats]) * imp

    def pick(sign):
        out = []
        for group, n in ((ASSET_FEATS, k - 1), (MACRO_FEATS, 1)):
            c = contrib[group].sort_values(ascending=(sign < 0))
            out += [FEATURE_LABELS.get(f, f) for f, v in c.items() if v * sign > 0][:n]
        return out
    return pick(1), pick(-1)


def run_pipeline(prices: pd.DataFrame, macro: pd.DataFrame) -> dict:
    """Entraîne, valide et produit les signaux courants pour tous les actifs."""
    panel = build_panel(prices, macro)
    if panel.empty:
        return {"ok": False, "error": "historique insuffisant"}
    mf = macro_features(macro, prices)
    val = walk_forward(panel)
    train = panel.dropna(subset=["y_ret"])
    dates = np.sort(train["date"].unique())
    train = train[train["date"].isin(dates[::SAMPLE_EVERY])]
    model = MarketModel().fit(train)
    if not model.fitted:
        return {"ok": False, "error": "modèle non entraînable (données insuffisantes)"}
    last = latest_rows(panel)
    pred = model.predict(last)
    importance = val.get("importance", pd.Series(dtype=float)) if val.get("ok") else pd.Series(dtype=float)
    rows = []
    for t, r in last.iterrows():
        p, er = float(pred.loc[t, "p_up"]), float(pred.loc[t, "exp_ret"])
        lab, col = signal_label(p, er)
        up, dn = explain_row(model, r, importance)
        rows.append({"ticker": t, "classe": asset_class(t), "p_up": p, "exp_ret_1m": er,
                     "exp_ret_ann": float(np.clip(er * 12, -0.6, 0.8)),
                     "vol": float(r.get("vol_63", np.nan)), "mom_63": float(r.get("mom_63", np.nan)),
                     "signal": lab, "color": col, "drivers_up": up, "drivers_down": dn,
                     "date": pd.Timestamp(r["date"])})
    signals = pd.DataFrame(rows).set_index("ticker").sort_values("p_up", ascending=False)
    regimes = detect_regimes(mf)
    return {"ok": True, "signals": signals, "validation": val, "regimes": regimes,
            "model": model, "panel": panel, "macro_feats": mf}


def confidence_from_validation(val: dict) -> float:
    """Confiance globale du modèle (0.05–0.4) déduite de l'AUC et de l'IC hors-échantillon."""
    if not val or not val.get("ok"):
        return 0.1
    auc_part = max(0.0, val["auc"] - 0.5) * 4          # AUC 0.60 -> 0.4
    ic_part = max(0.0, val["ic"]) * 4                   # IC 0.05 -> 0.2
    return float(np.clip(0.06 + auc_part + ic_part, 0.05, 0.4))
