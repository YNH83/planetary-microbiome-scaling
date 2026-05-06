"""
T5 Macroecology research concept cartoon (ZH+EN bilingual), v2 layout.

Design intent (mirrors ID-MED12 v2 cartoon):
    Top    :  4 column headers (A 不同擾動 / B 共同狀態 / C 共同程序 / D 關鍵節點)
    Mid-top:  one icon + 1-line cue per column (no overlap with arrow)
    Middle :  convergence arrow strip with single label (no overlap with icons)
    Lower  :  3 evidence pillars (Pillar 1 / 2 / 3) with 4 cells each
    Bottom :  Theoretical deliverable + Translational deliverable (K-shift)

Compared to v1 the layout adds vertical breathing room, enlarges fonts,
removes the cramped 4-step arrow under the cue strip, and replaces it with
a clear convergence strip between cue and pillars.
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle
from matplotlib import rcParams

rcParams["font.family"] = ["Hiragino Sans TC", "Hiragino Sans GB",
                           "Heiti TC", "Arial Unicode MS", "Helvetica"]
rcParams["axes.unicode_minus"] = False

ROOT = Path("/Users/ynh83/Desktop/T5_Macroecology")
FIGS = ROOT / "figures"
FIGS.mkdir(exist_ok=True)

NODE_COLORS = ["#384B5E", "#3C5488", "#F4A261", "#E76F51", "#B5374B"]
PILLAR_FILL = ["#E8EEF5", "#FFF1E8", "#E9F5EE"]
PILLAR_EDGE = ["#3C5488", "#E76F51", "#00A087"]


def header_box(ax, x, y, w, h, color, title_zh, title_en):
    box = FancyBboxPatch((x, y), w, h,
                         boxstyle="round,pad=0.005,rounding_size=0.012",
                         facecolor=color, edgecolor="white", linewidth=1.6)
    ax.add_patch(box)
    ax.text(x + w / 2, y + h * 0.62, title_zh, ha="center", va="center",
            color="white", fontsize=14, fontweight="bold")
    ax.text(x + w / 2, y + h * 0.27, title_en, ha="center", va="center",
            color="white", fontsize=9.5, style="italic")


def pillar_row(ax, y, h, fill, edge, label_zh, label_en, sub, cells):
    """A faint background bar with a 4-cell row inside.

    The first 0.10 of the canvas width is reserved for the pillar label
    (Chinese title + English subtitle); the remaining 0.86 is split into
    4 equal cells.
    """
    ax.add_patch(Rectangle((0.04, y), 0.92, h,
                           facecolor=fill, edgecolor=edge, linewidth=1.0,
                           alpha=0.85))
    label_x = 0.052
    ax.text(label_x, y + h * 0.72, label_zh, ha="left", va="center",
            fontsize=11, fontweight="bold", color=edge)
    ax.text(label_x, y + h * 0.45, label_en, ha="left", va="center",
            fontsize=8.5, color=edge, style="italic")
    ax.text(label_x, y + h * 0.20, sub, ha="left", va="center",
            fontsize=7.8, color="#444")

    cell_x0 = 0.16
    cell_w = (0.96 - cell_x0) / 4
    for i, txt in enumerate(cells):
        cx = cell_x0 + i * cell_w
        ax.add_patch(FancyBboxPatch((cx + 0.005, y + 0.012),
                                     cell_w - 0.014, h - 0.024,
                                     boxstyle="round,pad=0.003,rounding_size=0.008",
                                     facecolor="white", edgecolor=edge,
                                     linewidth=0.9))
        ax.text(cx + cell_w / 2, y + h / 2, txt, ha="center", va="center",
                fontsize=8.4, color="#1B1B1B", linespacing=1.32)


def biome_strip(ax, x, y, w, h):
    biomes = [
        "#7B5BA8", "#8E4582", "#A85FA8", "#B47BB6", "#C4A1C8",
        "#5C8A3A", "#83AE57",
        "#9CB7C8",
        "#7A5C3D", "#A07B53",
        "#9B6F3A",
        "#C7B594", "#D8C8A6",
        "#3C7DB1", "#1F4E79",
    ]
    cw = w / len(biomes)
    for i, c in enumerate(biomes):
        ax.add_patch(Rectangle((x + i * cw, y), cw, h,
                               facecolor=c, edgecolor="white", linewidth=0.4))


def taylor_mini(ax, x, y, w, h):
    rng = np.random.default_rng(11)
    xs = rng.uniform(0, 1, 35)
    ys = 2.0 * xs + rng.normal(0, 0.07, 35)
    ax.scatter(x + xs * w, y + ys * h * 0.55, s=5, color="#222", alpha=0.6)
    grid = np.linspace(0, 1, 30)
    ax.plot(x + grid * w, y + 2.0 * grid * h * 0.55, color="#E76F51",
            linewidth=1.4)


def gamma_mini(ax, x, y, w, h):
    t = np.linspace(0.05, 4, 80)
    pdf = (t ** 1.5) * np.exp(-t)
    pdf = pdf / pdf.max()
    xs = np.linspace(0, 1, 80)
    ax.plot(x + xs * w, y + pdf * h * 0.85, color="#E76F51", linewidth=1.5)
    ax.fill_between(x + xs * w, y, y + pdf * h * 0.85,
                    color="#E76F51", alpha=0.22)


def k_target(ax, x, y, r):
    for radius, c in zip([1.0, 0.66, 0.33], ["#B5374B", "#E76F51", "#F4A261"]):
        ax.add_patch(plt.Circle((x, y), r * radius, facecolor=c,
                                edgecolor="white", linewidth=0.8))
    ax.scatter([x], [y], s=10, color="white")


def main():
    fig = plt.figure(figsize=(16, 11.5))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # ---- Title strip ----
    fig.text(0.5, 0.965,
             "T5 Macroecology 研究架構：四步收斂 × 三支柱證據 × K 槓桿轉譯",
             ha="center", va="top", fontsize=15.5, fontweight="bold")
    fig.text(0.5, 0.940,
             "Convergent Taylor scaling links planetary microbiomes through "
             "a habitat-modulated carrying-capacity (K) axis",
             ha="center", va="top", fontsize=10.5, color="#444",
             style="italic")

    # ---- Header row ----
    head_y = 0.855
    head_h = 0.062
    col_w = 0.218
    col_x0 = 0.045
    col_gap = 0.012
    headers = [
        ("A. 不同擾動",       "Different perturbations"),
        ("B. 共同狀態",       "Common state"),
        ("C. 共同程序",       "Common program"),
        ("D. 關鍵槓桿節點",   "Key leverage node"),
    ]
    centres = []
    for i, (zh, en) in enumerate(headers):
        x = col_x0 + i * (col_w + col_gap)
        header_box(ax, x, head_y, col_w, head_h, NODE_COLORS[i + 1], zh, en)
        centres.append(x + col_w / 2)

    # ---- Cue strip (vertical stack inside each column: title / icon / anchor) ----
    cue_strip_h = 0.110
    cue_y = head_y - 0.014 - cue_strip_h
    for cx in centres:
        ax.add_patch(Rectangle((cx - col_w / 2 + 0.005, cue_y),
                                col_w - 0.01, cue_strip_h,
                                facecolor="#FAFAF7", edgecolor="#E0E0E0",
                                linewidth=0.6))

    title_y = cue_y + cue_strip_h - 0.018
    icon_y = cue_y + cue_strip_h * 0.50
    anchor_y = cue_y + 0.014

    # A column: biome strip + 2 short lines
    biome_w = col_w - 0.05
    ax.text(centres[0], title_y, "15 EMPO-3 biomes",
            ha="center", va="top", fontsize=9.5, fontweight="bold",
            color="#1B1B1B")
    biome_strip(ax, centres[0] - biome_w / 2, icon_y - 0.010,
                biome_w, 0.020)
    ax.text(centres[0], anchor_y,
            "gut · skin · soil · water\nsediment · air · plant",
            ha="center", va="bottom", fontsize=8.0, color="#444",
            linespacing=1.3)

    # B column: Taylor schematic + key equation
    ax.text(centres[1], title_y,
            r"$\log_{10}\mathrm{var} = \beta\,\log_{10}\mathrm{mean}$",
            ha="center", va="top", fontsize=9.5, fontweight="bold",
            color="#1B1B1B")
    taylor_mini(ax, centres[1] - 0.045, icon_y - 0.012,
                w=0.090, h=0.033)
    ax.text(centres[1], anchor_y,
            r"universal $\beta$ = 1.966 (EMP)",
            ha="center", va="bottom", fontsize=9.0, color="#B5374B",
            fontweight="bold")

    # C column: Gamma AFD curve + steady-state relation
    ax.text(centres[2], title_y,
            "stochastic-logistic + Gamma AFD",
            ha="center", va="top", fontsize=9.5, fontweight="bold",
            color="#1B1B1B")
    gamma_mini(ax, centres[2] - 0.045, icon_y - 0.012, w=0.090, h=0.033)
    ax.text(centres[2], anchor_y,
            r"$\langle x \rangle \approx K,\;\;\mathrm{var}(x) \approx \sigma^2 K^2$",
            ha="center", va="bottom", fontsize=8.5, color="#444")

    # D column: K target + leverage description
    ax.text(centres[3], title_y,
            r"$\alpha \approx \log K$ absorbs difference",
            ha="center", va="top", fontsize=9.5, fontweight="bold",
            color="#1B1B1B")
    k_target(ax, centres[3], icon_y, r=0.022)
    ax.text(centres[3], anchor_y,
            r"habitat / disease / time → K," "\n" r"$\beta$ stays invariant",
            ha="center", va="bottom", fontsize=8.5, color="#444",
            linespacing=1.3)

    # ---- Convergence arrow strip (between cue and pillars) ----
    arrow_y = cue_y - 0.030
    for i in range(3):
        arr = FancyArrowPatch((centres[i] + 0.03, arrow_y),
                              (centres[i + 1] - 0.03, arrow_y),
                              arrowstyle="-|>,head_length=12,head_width=7",
                              color=NODE_COLORS[1 + i], linewidth=2.2)
        ax.add_patch(arr)
    ax.text(0.5, arrow_y - 0.026,
            "四步收斂 (four-step convergence)：不同擾動 → 共同狀態 → "
            "共同程序 → 關鍵節點",
            ha="center", va="top", fontsize=9.5, color="#444",
            style="italic")

    # ---- 3 evidence pillars ----
    pillar_y0 = 0.485
    pillar_h = 0.085
    gap = 0.012
    pillar_y1 = pillar_y0 - (pillar_h + gap)
    pillar_y2 = pillar_y1 - (pillar_h + gap)

    pillar_row(
        ax, pillar_y0, pillar_h, PILLAR_FILL[0], PILLAR_EDGE[0],
        "支柱 1", "Pillar 1", "Primary atlas",
        [
            "EMP release 1 deblur 90 bp\n26,181 samples\n317,314 ASVs\n15 EMPO-3 biomes",
            "per-biome Taylor 15/15 PASS\n$R^2 \\geq 0.80$\n$\\beta\\in[1.82,\\,2.07]$\nuniversal $\\beta$ = 1.966",
            "Bayesian hierarchical\n(PyMC NUTS)\n$\\beta_{global}$ = 1.950\n95% HDI [1.909, 1.992]",
            "K ridge across 15 biomes\nKruskal H = 3,542\np $\\ll$ 1e$-$300\n$\\beta$ CV = 3.9%",
        ],
    )

    pillar_row(
        ax, pillar_y1, pillar_h, PILLAR_FILL[1], PILLAR_EDGE[1],
        "支柱 2", "Pillar 2", "Falsification",
        [
            "Earth-scale invariance\nrules out single-biome\nartefact / sampling bias",
            "Hubbell neutral drift\n(Etienne 2005)\nz = 13.5\n→ REJECT",
            "Fisher log-series  z = 24.8\nPreston lognormal  z = 11.9\n→ both REJECTED",
            "Shoemaker 2017\nlognormal-neutral\nz = 2.88, p = 0.011\n→ stochastic-logistic family",
        ],
    )

    pillar_row(
        ax, pillar_y2, pillar_h, PILLAR_FILL[2], PILLAR_EDGE[2],
        "支柱 3", "Pillar 3", "Replication",
        [
            "shotgun $\\neq$ 16S replicate\n→ technology-independent",
            "curatedMG v3.18.0\n9 cohorts, 4,702 stool\n$\\Delta$BIC = +23.4\n→ DECISIVE",
            "iHMP IBDMDB\n108 longitudinal subjects\n3 time bins\n$\\beta\\in[1.5,\\,2.0]$",
            "Tara Oceans P0 / P1\nfunctional-layer KEGG KO\nexploratory cross-domain",
        ],
    )

    # ---- Bottom deliverables ----
    bot_y = 0.06
    bot_h = 0.155
    box_left = FancyBboxPatch((0.04, bot_y), 0.45, bot_h,
                              boxstyle="round,pad=0.005,rounding_size=0.012",
                              facecolor="#F1F4F8", edgecolor="#3C5488",
                              linewidth=1.5)
    ax.add_patch(box_left)
    ax.text(0.265, bot_y + bot_h - 0.014,
            "理論交付  Theoretical deliverable",
            ha="center", va="top", fontsize=11, fontweight="bold",
            color="#3C5488")
    ax.text(0.058, bot_y + bot_h * 0.42,
            "•  Hierarchical universality (PSIS-LOO 拒絕 complete-pooling,\n"
            "   $\\Delta$ELPD = +38.6, SE 10.8)\n"
            "•  4-step convergence: 不同擾動 → 共享 $\\beta$ → 共同程序 → K 軸\n"
            "•  Host vs free-living: t = 0.41, p = 0.69 ($\\beta$ no difference)\n"
            "•  $\\beta$ 偏離 [1.85, 2.05] = QC 警示 (內建測序品質檢查)",
            ha="left", va="center", fontsize=8.4, color="#1B1B1B",
            linespacing=1.55)

    box_right = FancyBboxPatch((0.51, bot_y), 0.45, bot_h,
                               boxstyle="round,pad=0.005,rounding_size=0.012",
                               facecolor="#FFF3EE", edgecolor="#B5374B",
                               linewidth=1.5)
    ax.add_patch(box_right)
    ax.text(0.735, bot_y + bot_h - 0.014,
            "臨床轉譯  Translational deliverable: K-shift index",
            ha="center", va="top", fontsize=11, fontweight="bold",
            color="#B5374B")
    ax.text(0.528, bot_y + bot_h * 0.42,
            "•  IBD relapse early-warning: dD/dt 在症狀前 2 至 4 週上升\n"
            "•  CRC triage: cosine sim($K_p$, $K_{CRC}$) > 0.85 → colonoscopy\n"
            "•  PD-1 immunotherapy: $\\log K$ Akkermansia / Ruminococcaceae\n"
            "•  FMT efficacy: 4 週後 sim($K_{patient}$, $K_{donor}$) < 0.7 → fail\n"
            "•  Antibiotic / metformin: K landscape collapse vs K fingerprint",
            ha="left", va="center", fontsize=8.4, color="#1B1B1B",
            linespacing=1.55)

    # ---- Footer ----
    fig.text(0.5, 0.018,
             "Provenance:  EMP release 1 (Thompson 2017 Nature)  ·  "
             "curatedMG v3.18.0 (Pasolli 2017 Nat Methods)  ·  "
             "iHMP IBDMDB (Lloyd-Price 2019 Nature)  ·  "
             "Tara Oceans (Sunagawa 2015 Science).    "
             "Theory:  Grilli 2020 Nat Commun.    "
             "Convergence framing:  Cao et al. Nature 2026 PerturbFate analogue.",
             ha="center", va="bottom", fontsize=7.4, color="#666")

    out = FIGS / "T5_research_cartoon_v1.png"
    fig.savefig(out, dpi=300)
    plt.close(fig)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
