"""
T5 graphical abstract v1.

A 16:9 schematic that compresses the full convergence narrative into a single
image, mirroring the four-step framework of Cao et al. Nature 2026
(PerturbFate, "different perturbations -> common state -> common program ->
key nodes") but expressed in macroecological language.

Layout (top to bottom):
    Top    : 4-node narrative arc (A diverse biomes -> B shared scaling -> C
             shared mechanism -> D K is the leverage point)
    Middle : 3 evidence rails aligned to the 4 nodes
                rail 1 Primary EMP atlas (26,181 samples / 15 EMPO-3 biomes)
                rail 2 Falsification (4 nulls; 3 rejected, Shoemaker boundary)
                rail 3 Replication (curatedMG shotgun, iHMP longitudinal,
                       Tara Oceans)
    Bottom : 2 deliverables
                left  Theoretical: hierarchical universality, beta_global
                      = 1.95 [1.91, 1.99]
                right Translational: K-shift as readout for disease,
                      disturbance, habitat perturbation

Output:
    figures/T5_graphical_abstract.png
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle, Rectangle
from matplotlib.lines import Line2D

ROOT = Path("/Users/ynh83/Desktop/T5_Macroecology")
FIGS = ROOT / "figures"
FIGS.mkdir(exist_ok=True)

NATURE_STYLE = Path("/Users/ynh83/Desktop/Epi-Protocols/04152026 Microbiome-Epi Protocols/scripts/shared")
sys.path.insert(0, str(NATURE_STYLE))
from nature_style import apply_nature_style, BIOME_COLORS, DECISION_COLORS

apply_nature_style()

# Narrative-arc gradient: grey (raw biomes) -> orange (shared mechanism) ->
# red (leverage point), echoing wildtype -> reprogrammed -> intervention
NODE_COLORS = ["#8C8C8C", "#F4A261", "#E76F51", "#B5374B"]
NODE_LABELS = [
    "A   15 EMPO-3 biomes",
    "B   Shared Taylor backbone\n($\\beta \\approx 2$)",
    "C   Stochastic-logistic\n+ Gamma AFD",
    "D   K is the leverage\npoint",
]
NODE_SUBLABELS = [
    "gut, skin, soil, sediment,\nsaline / fresh water, aerosol,\nplant rhizosphere",
    r"15/15 biomes pass $R^2 \geq 0.80$" + "\n" + r"$\beta \in [1.82, 2.07]$, CV = 3.9%",
    r"$\beta_{global}$ = 1.950" + "\n" + "95% HDI [1.909, 1.992]\n95% taxa Gamma-dominated",
    r"$\alpha$ ($\approx \log K$) absorbs habitat," + "\n"
    r"disease, and time;" + "\n" + r"$\beta$ stays invariant",
]


def draw_node(ax: plt.Axes, x: float, y: float, color: str,
              label: str, sublabel: str, radius: float = 0.072) -> None:
    circ = Circle((x, y), radius, color=color, zorder=4,
                  alpha=0.9, ec="white", linewidth=2)
    ax.add_patch(circ)
    ax.text(x, y, label.split()[0], color="white", fontsize=18,
            fontweight="bold", ha="center", va="center", zorder=5)
    ax.text(x, y - radius - 0.020, "\n".join(label.split("   ")[1:]),
            ha="center", va="top", fontsize=11.5, fontweight="bold",
            color="#222")
    ax.text(x, y - radius - 0.095, sublabel, ha="center", va="top",
            fontsize=9.0, color="#444")


def draw_arrow(ax: plt.Axes, x0: float, x1: float, y: float,
               color: str = "#666") -> None:
    arr = FancyArrowPatch((x0, y), (x1, y),
                          arrowstyle="-|>,head_length=10,head_width=6",
                          color=color, linewidth=2.4, zorder=2,
                          shrinkA=22, shrinkB=22)
    ax.add_patch(arr)


def draw_rail(ax: plt.Axes, y: float, label: str,
              hits: list[tuple[float, str, str]],
              icon_color: str = "#444") -> None:
    """One horizontal evidence rail.
    hits: list of (x_center, short_text, dot_color); each is one icon on the rail.
    """
    ax.plot([0.06, 0.96], [y, y], color="#cccccc", linewidth=1.0, zorder=1)
    ax.text(0.045, y, label, ha="right", va="center", fontsize=10.5,
            fontweight="bold", color=icon_color)
    for x, txt, c in hits:
        ax.scatter([x], [y], s=190, color=c, edgecolor="white",
                   linewidth=1.2, zorder=3)
        ax.text(x, y - 0.030, txt, ha="center", va="top", fontsize=8.8,
                color="#222")


def draw_biome_strip(ax: plt.Axes, x_center: float, y: float,
                     width: float = 0.085, height: float = 0.022) -> None:
    """A small horizontal strip showing the 15 biome colors."""
    keys = [
        "Animal corpus", "Animal distal gut", "Animal proximal gut",
        "Animal secretion", "Animal surface",
        "Plant rhizosphere", "Plant surface",
        "Aerosol (non-saline)",
        "Sediment (non-saline)", "Sediment (saline)",
        "Soil (non-saline)",
        "Surface (non-saline)", "Surface (saline)",
        "Water (non-saline)", "Water (saline)",
    ]
    n = len(keys)
    cw = width / n
    x0 = x_center - width / 2
    for i, k in enumerate(keys):
        rect = Rectangle((x0 + i * cw, y - height / 2), cw, height,
                         facecolor=BIOME_COLORS.get(k, "#888"),
                         edgecolor="none")
        ax.add_patch(rect)


def draw_collapse_icon(ax: plt.Axes, x: float, y: float,
                       size: float = 0.07) -> None:
    rng = np.random.default_rng(7)
    xs = rng.uniform(-1, 1, 80) * size * 0.9
    ys = 1.0 * xs + rng.normal(0, size * 0.18, 80)
    ax.scatter(x + xs, y + ys, s=4, color="#444", alpha=0.55, zorder=3)
    line_x = np.linspace(-size * 0.95, size * 0.95, 30)
    ax.plot(x + line_x, y + 1.0 * line_x, color=NODE_COLORS[1],
            linewidth=1.4, zorder=4)


def draw_gamma_icon(ax: plt.Axes, x: float, y: float, size: float = 0.06) -> None:
    t = np.linspace(0.05, 4, 80)
    pdf = (t ** 1.5) * np.exp(-t)
    pdf = pdf / pdf.max() * size
    xs = np.linspace(-size, size, 80)
    ax.plot(x + xs, y + pdf - size * 0.5, color=NODE_COLORS[2],
            linewidth=1.4, zorder=4)


def draw_target_icon(ax: plt.Axes, x: float, y: float, size: float = 0.05) -> None:
    for r, c in zip([1.0, 0.66, 0.33], ["#B5374B", "#E76F51", "#F4A261"]):
        circ = Circle((x, y), size * r, facecolor=c, edgecolor="white",
                       linewidth=1.0, zorder=4)
        ax.add_patch(circ)
    ax.scatter([x], [y], s=12, color="white", zorder=5)


def main() -> None:
    fig = plt.figure(figsize=(16, 9))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # ---- Title strip ----
    fig.text(0.5, 0.965,
             "Convergent Taylor scaling links planetary microbiomes through "
             "a habitat-modulated carrying-capacity axis",
             ha="center", va="top", fontsize=18, fontweight="bold",
             color="#1B1B1B")
    fig.text(0.5, 0.928,
             "Different perturbations  $\\rightarrow$  common state  "
             "$\\rightarrow$  common program  $\\rightarrow$  leverage node",
             ha="center", va="top", fontsize=12.5, color="#555",
             fontstyle="italic")

    # ---- Top: narrative arc ----
    arc_y = 0.78
    node_xs = [0.16, 0.40, 0.64, 0.88]
    for i, (x, c, lbl, sub) in enumerate(zip(
            node_xs, NODE_COLORS, NODE_LABELS, NODE_SUBLABELS)):
        draw_node(ax, x, arc_y, c, lbl, sub)
    for i in range(len(node_xs) - 1):
        draw_arrow(ax, node_xs[i], node_xs[i + 1], arc_y,
                    color="#666")

    # Per-node mini icons (above each node, top-right of circle)
    icon_y = arc_y + 0.085
    draw_biome_strip(ax, node_xs[0], icon_y)
    draw_collapse_icon(ax, node_xs[1], icon_y, size=0.045)
    draw_gamma_icon(ax, node_xs[2], icon_y, size=0.055)
    draw_target_icon(ax, node_xs[3], icon_y, size=0.038)

    # ---- Middle: 3 evidence rails ----
    rail_top = 0.46
    rail_dy = 0.075

    draw_rail(
        ax, rail_top, "Primary  EMP",
        [
            (node_xs[0], "26,181 samples\n317,314 ASVs", "#3C5488"),
            (node_xs[1], "universal collapse\n$\\beta$ = 1.966", "#3C5488"),
            (node_xs[2], "Bayesian hierarchical\n$\\beta_{global}$ = 1.950", "#3C5488"),
            (node_xs[3], "K ridge: H = 3542,\np < 2e$-$308", "#3C5488"),
        ],
        icon_color="#3C5488",
    )

    draw_rail(
        ax, rail_top - rail_dy, "Falsification",
        [
            (node_xs[1], "Hubbell  z = 13.5", "#E64B35"),
            ((node_xs[1] + node_xs[2]) / 2, "Fisher  z = 24.8", "#E64B35"),
            (node_xs[2], "Preston  z = 11.9", "#E64B35"),
            ((node_xs[2] + node_xs[3]) / 2,
             "Shoemaker boundary\nz = 2.88, p = 0.011",
             DECISION_COLORS["marginal"]),
        ],
        icon_color="#E64B35",
    )

    draw_rail(
        ax, rail_top - 2 * rail_dy, "Replication",
        [
            (node_xs[1], "curatedMG  9 cohorts\n$\\Delta$BIC = +23.4", "#00A087"),
            (node_xs[2], "iHMP IBDMDB\n108 subjects, 3 time bins", "#00A087"),
            (node_xs[3], "Tara Oceans\nP0 / P1", "#00A087"),
        ],
        icon_color="#00A087",
    )

    # Vertical connectors (light) from rails up to corresponding node
    for x in node_xs:
        ax.plot([x, x], [rail_top - 2 * rail_dy - 0.012,
                          arc_y - 0.072],
                color="#dddddd", linewidth=0.8, linestyle="-", zorder=0)

    # ---- Bottom: deliverables ----
    bottom_y = 0.13
    box_h = 0.18
    # left box
    left = FancyBboxPatch((0.05, bottom_y - box_h / 2), 0.43, box_h,
                          boxstyle="round,pad=0.012,rounding_size=0.012",
                          facecolor="#F1F4F8", edgecolor="#3C5488",
                          linewidth=1.5, zorder=1)
    ax.add_patch(left)
    ax.text(0.265, bottom_y + box_h / 2 - 0.020,
            "Theoretical deliverable",
            ha="center", va="top", fontsize=14.5, fontweight="bold",
            color="#3C5488")
    ax.text(0.265, bottom_y - 0.025,
            "Hierarchical universality\n"
            "$\\beta$ shared, $\\alpha$ ($\\approx \\log K$) habitat-modulated\n"
            "H5 falsifies 3/4 nulls; Shoemaker boundary rules out\n"
            "neutral-only, log-series, and lognormal generators",
            ha="center", va="center", fontsize=12.5, color="#222")

    # right box
    right = FancyBboxPatch((0.52, bottom_y - box_h / 2), 0.43, box_h,
                           boxstyle="round,pad=0.012,rounding_size=0.012",
                           facecolor="#FFF3EE", edgecolor="#B5374B",
                           linewidth=1.5, zorder=1)
    ax.add_patch(right)
    ax.text(0.735, bottom_y + box_h / 2 - 0.020,
            "Translational deliverable",
            ha="center", va="top", fontsize=14.5, fontweight="bold",
            color="#B5374B")
    ax.text(0.735, bottom_y - 0.025,
            "K-shift as a generalizable readout for\n"
            "disease (IBDMDB UC / CD), disturbance,\n"
            "habitat perturbation, and longitudinal drift\n"
            "($\\beta$ stays invariant; intervene on $\\alpha$ / K)",
            ha="center", va="center", fontsize=12.5, color="#222")

    # ---- Footer ----
    fig.text(0.5, 0.018,
             "T5 Macroecology  $\\cdot$  EMP release 1 deblur, 26,181 samples, "
             "15 EMPO-3 biomes  $\\cdot$  Bayesian hierarchical + 4 nulls + "
             "cross-platform replication",
             ha="center", va="bottom", fontsize=9.0, color="#777")

    out = FIGS / "T5_graphical_abstract.png"
    fig.savefig(out, dpi=400)
    plt.close(fig)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
