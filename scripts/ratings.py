#!/usr/bin/env python3
"""
ratings.py — strength-rating engines fit on the international-results corpus.

Two complementary engines:

  (1) DixonColes  — a time-decayed, ridge-regularized bivariate-Poisson goals
      model (Dixon & Coles 1997). Each team gets an ATTACK and a DEFENCE rating;
      globals are a baseline (c), a home-advantage (gamma) applied only at
      non-neutral venues, and the low-score dependence parameter (rho).
      This is the GENERATIVE model used to sample scorelines in the Monte Carlo.

  (2) Elo        — a chronological World-Football-Elo system (margin-of-victory
      and match-importance aware). Used as a complementary rating, a model
      feature, and a calibration baseline.

Fitting uses numpy + scipy only. Attack/defence are estimated by ridge-penalised
weighted Poisson MLE (convex, analytic gradient -> L-BFGS-B); rho is then fit by
1-D search on the Dixon-Coles low-score correction. This two-stage scheme
reproduces the full DC model while staying fast and numerically robust.
"""
import numpy as np
from scipy.optimize import minimize, minimize_scalar
import datetime, math

# tournament importance weights (World-Football-Elo style) for Elo K and also
# used as a multiplicative weight on the Poisson likelihood (competitive > friendly)
TOURN_WEIGHT = {
    "FIFA World Cup": 1.00, "FIFA World Cup qualification": 0.85,
    "UEFA Euro": 0.90, "UEFA Euro qualification": 0.70,
    "Copa América": 0.90, "African Cup of Nations": 0.85, "AFC Asian Cup": 0.80,
    "Gold Cup": 0.70, "CONCACAF Nations League": 0.65, "UEFA Nations League": 0.80,
    "Confederations Cup": 0.85, "FIFA Series": 0.45,
    "Friendly": 0.40,
}
def tourn_weight(name):
    if name in TOURN_WEIGHT: return TOURN_WEIGHT[name]
    n = name.lower()
    if "qualification" in n: return 0.80
    if "friendly" in n: return 0.40
    if "cup" in n or "championship" in n or "nations league" in n: return 0.75
    return 0.60


def _to_days(date_str):
    y, m, d = map(int, date_str.split("-"))
    return datetime.date(y, m, d).toordinal()


# ============================================================== Dixon-Coles
class DixonColes:
    def __init__(self, half_life_years=2.0, ridge=2.0, ref_date="2026-06-13", prior=None):
        self.half_life_years = half_life_years
        self.ridge = ridge
        self.ref = _to_days(ref_date)
        self.teams = []; self.idx = {}
        self.c = 0.0; self.gamma = 0.25; self.rho = -0.05
        self.atk = None; self.dfn = None
        # prior: optional dict team -> prior strength z (anchors atk & dfn toward
        # an externally-validated value; improves cross-confederation calibration).
        self.prior = prior or {}
        self.atk_prior = None; self.dfn_prior = None

    def _prep(self, rows, canon):
        teams = sorted(set([canon(r["home_team"]) for r in rows] +
                           [canon(r["away_team"]) for r in rows]))
        teams = [t for t in teams if t is not None]
        self.teams = teams; self.idx = {t: i for i, t in enumerate(teams)}
        H, A, X, Y, W, NEU = [], [], [], [], [], []
        lam = math.log(2) / (self.half_life_years * 365.25)
        for r in rows:
            h = canon(r["home_team"]); a = canon(r["away_team"])
            if h is None or a is None or h == a: continue
            H.append(self.idx[h]); A.append(self.idx[a])
            X.append(r["hs"]); Y.append(r["as"])
            age = self.ref - _to_days(r["date"])
            w = math.exp(-lam * age) * tourn_weight(r["tournament"])
            W.append(w); NEU.append(0.0 if r["neutral"] else 1.0)
        self.H = np.array(H); self.A = np.array(A)
        self.X = np.array(X, float); self.Y = np.array(Y, float)
        self.W = np.array(W); self.HOME = np.array(NEU)
        self.n_teams = len(teams)
        # prior anchor per team (half the strength goes to attack, half to defence)
        self.atk_prior = np.array([0.5*self.prior.get(t, 0.0) for t in teams])
        self.dfn_prior = np.array([0.5*self.prior.get(t, 0.0) for t in teams])

    def _unpack(self, p):
        n = self.n_teams
        atk = p[:n]; dfn = p[n:2*n]; c = p[2*n]; gamma = p[2*n+1]
        return atk, dfn, c, gamma

    def _nll_grad(self, p):
        """Ridge-penalised weighted Poisson negative log-lik + analytic gradient.
        (Low-score rho correction handled separately afterward.)"""
        n = self.n_teams
        atk, dfn, c, gamma = self._unpack(p)
        loglam = c + atk[self.H] - dfn[self.A] + gamma * self.HOME
        lognu  = c + atk[self.A] - dfn[self.H]
        lam = np.exp(loglam); nu = np.exp(lognu)
        # NLL (drop constant factorials); add ridge on atk & dfn
        da = atk - self.atk_prior; dd = dfn - self.dfn_prior
        ll = self.W * (self.X * loglam - lam + self.Y * lognu - nu)
        nll = -ll.sum() + self.ridge * (da @ da + dd @ dd)
        # gradients
        rh = self.W * (self.X - lam)   # d/d loglam
        ra = self.W * (self.Y - nu)    # d/d lognu
        g_atk = np.zeros(n); g_dfn = np.zeros(n)
        np.add.at(g_atk, self.H, rh); np.add.at(g_atk, self.A, ra)
        np.add.at(g_dfn, self.A, -rh); np.add.at(g_dfn, self.H, -ra)
        g_atk = -g_atk + 2*self.ridge*da
        g_dfn = -g_dfn + 2*self.ridge*dd
        g_c = -(rh.sum() + ra.sum())
        g_gamma = -(rh * self.HOME).sum()
        grad = np.concatenate([g_atk, g_dfn, [g_c, g_gamma]])
        return nll, grad

    @staticmethod
    def _tau(x, y, lam, nu, rho):
        # Dixon-Coles low-score dependence correction
        t = np.ones_like(lam)
        m00 = (x == 0) & (y == 0); m01 = (x == 0) & (y == 1)
        m10 = (x == 1) & (y == 0); m11 = (x == 1) & (y == 1)
        t = np.where(m00, 1 - lam*nu*rho, t)
        t = np.where(m01, 1 + lam*rho, t)
        t = np.where(m10, 1 + nu*rho, t)
        t = np.where(m11, 1 - rho, t)
        return t

    def _fit_rho(self):
        atk, dfn = self.atk, self.dfn
        loglam = self.c + atk[self.H] - dfn[self.A] + self.gamma*self.HOME
        lognu  = self.c + atk[self.A] - dfn[self.H]
        lam = np.exp(loglam); nu = np.exp(lognu)
        def nll(rho):
            tau = self._tau(self.X, self.Y, lam, nu, rho)
            tau = np.clip(tau, 1e-9, None)
            return -(self.W * np.log(tau)).sum()
        res = minimize_scalar(nll, bounds=(-0.2, 0.2), method="bounded")
        self.rho = float(res.x)

    def fit(self, rows, canon, verbose=True):
        self._prep(rows, canon)
        n = self.n_teams
        p0 = np.concatenate([np.zeros(2*n), [0.0, 0.25]])
        res = minimize(self._nll_grad, p0, jac=True, method="L-BFGS-B",
                       options={"maxiter": 500, "ftol": 1e-10})
        atk, dfn, c, gamma = self._unpack(res.x)
        if not self.prior:
            # mean-centre for interpretability (ridge-toward-0 already pins scale)
            self.atk = atk - atk.mean(); self.dfn = dfn - dfn.mean()
            self.c = c + atk.mean() - dfn.mean()
        else:
            # prior fixes the location; keep raw fitted values
            self.atk = atk; self.dfn = dfn; self.c = c
        self.gamma = gamma
        self._fit_rho()
        if verbose:
            print(f"  DixonColes fit: teams={n} | c={self.c:.3f} gamma(home)={self.gamma:.3f} "
                  f"rho={self.rho:.3f} | conv={res.success} nll={res.fun:.1f}")
        return self

    def expected_goals(self, home, away, home_adv=0.0):
        """lambda(home), nu(away). home_adv: 1.0 host in own country, 0 neutral."""
        i, j = self.idx[home], self.idx[away]
        lam = math.exp(self.c + self.atk[i] - self.dfn[j] + self.gamma*home_adv)
        nu  = math.exp(self.c + self.atk[j] - self.dfn[i])
        return lam, nu

    def score_matrix(self, home, away, home_adv=0.0, maxg=10):
        lam, nu = self.expected_goals(home, away, home_adv)
        gx = np.arange(maxg+1)
        px = np.exp(-lam) * lam**gx / np.array([math.factorial(k) for k in gx])
        py = np.exp(-nu) * nu**gx / np.array([math.factorial(k) for k in gx])
        M = np.outer(px, py)
        # apply DC correction to the four low-score cells
        for (x, y) in [(0,0),(0,1),(1,0),(1,1)]:
            M[x, y] *= self._tau(np.array([x]), np.array([y]),
                                 np.array([lam]), np.array([nu]), self.rho)[0]
        M /= M.sum()
        return M, lam, nu

    def wdl(self, home, away, home_adv=0.0, maxg=10):
        M, lam, nu = self.score_matrix(home, away, home_adv, maxg)
        pH = np.tril(M, -1).sum(); pD = np.trace(M); pA = np.triu(M, 1).sum()
        return pH, pD, pA, lam, nu


# ============================================================== Elo
def compute_elo(rows, canon, base=1500.0, K0=40.0, ref_sort=True):
    """Chronological World-Football-Elo. Returns final rating per team and a
    snapshot dict of pre-match ratings keyed by (date,home,away) for features."""
    R = {}
    pre = {}
    rows_sorted = sorted(rows, key=lambda r: r["date"]) if ref_sort else rows
    for r in rows_sorted:
        h = canon(r["home_team"]); a = canon(r["away_team"])
        if h is None or a is None or h == a: continue
        Rh = R.get(h, base); Ra = R.get(a, base)
        hadv = 0.0 if r["neutral"] else 65.0   # home-field ~65 Elo pts
        We = 1.0 / (1.0 + 10 ** ((Ra - (Rh + hadv)) / 400.0))
        x, y = r["hs"], r["as"]
        if x > y: Sh = 1.0
        elif x == y: Sh = 0.5
        else: Sh = 0.0
        gd = abs(x - y)
        gmult = 1.0 if gd <= 1 else (1.5 if gd == 2 else (1.75 + (gd-3)/8.0))
        K = K0 * tourn_weight(r["tournament"]) * gmult
        pre[(r["date"], r["home_team"], r["away_team"])] = (Rh, Ra)
        R[h] = Rh + K * (Sh - We)
        R[a] = Ra + K * ((1 - Sh) - (1 - We))
    return R, pre
