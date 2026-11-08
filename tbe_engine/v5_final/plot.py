"""Plots for the report from one training run.

Run from connect6/tbe_engine:
    python3 -B v5_final/plot.py                      (latest run)
    python3 -B v5_final/plot.py v5_final/training_runs/run_...

Saves loss.png, weights.png and weights_bar.png in the run folder.
"""

import csv
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
run = Path(sys.argv[1]) if len(sys.argv) > 1 else sorted((HERE / 'training_runs').glob('run_*'))[-1]
FITTED = ['line_1', 'line_2', 'line_3', 'connectivity']
COLORS = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100']
INK, MUTED, GRID = '#1f1f1e', '#6b6a64', '#e4e3df'

plt.rcParams.update({'font.size': 10, 'axes.edgecolor': MUTED, 'axes.labelcolor': INK,
                     'xtick.color': MUTED, 'ytick.color': MUTED, 'axes.spines.top': False,
                     'axes.spines.right': False, 'axes.grid': True, 'grid.color': GRID,
                     'grid.linewidth': 0.8, 'legend.frameon': False})

rows = list(csv.DictReader(open(run / 'history.csv')))
result = json.load(open(run / 'result.json'))
learned = [r for r in rows if r['run'] == 'learned']
init = result.get('init', 'manual')                       # older runs: manual start
start = result.get('start_weights', result['manual_weights'])
start_val_loss = result.get('start_val_loss', result.get('manual_val_loss'))
epochs = [int(r['epoch']) for r in learned]

# 1. loss curves
fig, ax = plt.subplots(figsize=(7, 4))
ax.plot(epochs, [float(r['train_loss']) for r in learned], color=COLORS[0], lw=2, label='learned, train')
ax.plot(epochs, [float(r['val_loss']) for r in learned], color=COLORS[1], lw=2, label='learned, validation')
ax.axhline(start_val_loss, color=MUTED, lw=1.5, ls='--', label=f'{init} start weights, validation')
ax.axvline(result['best_epoch'], color=MUTED, lw=1, ls=':', label=f"best epoch ({result['best_epoch']})")
ax.set_xlabel('epoch')
ax.set_ylabel('logistic loss')
ax.set_title('Fitting the static evaluation to the teacher search', color=INK, loc='left')
ax.legend()
fig.tight_layout()
fig.savefig(run / 'loss.png', dpi=200)

# 2. weights during training (ratio to the manual value)
manual = result['manual_weights']
fig, ax = plt.subplots(figsize=(7, 4))
for name, color in zip(FITTED, COLORS):
    ax.plot(epochs, [float(r[name]) / manual[name] for r in learned], color=color, lw=2, label=name)
    if init != 'manual':
        ax.plot(0, start[name] / manual[name], 'o', color=color, ms=8)
ax.axhline(1, color=MUTED, lw=1.5, ls='--', label='manual (expert) = 1')
ax.set_xlabel('epoch')
ax.set_ylabel('learned / manual weight')
ax.set_title(f'Weights during training (start: {init})', color=INK, loc='left')
if init == 'manual':
    ax.legend()
else:
    ax.legend(loc='lower right', bbox_to_anchor=(1, 0.17))   # above the line_3 curve
fig.tight_layout()
fig.savefig(run / 'weights.png', dpi=200)

# 3. manual vs learned weights + control result
fig, ax = plt.subplots(figsize=(7, 4))
x = range(len(FITTED))
bars = [('manual (expert)', manual, MUTED), ('learned', result['learned_weights'], COLORS[0])]
if init != 'manual':
    bars.insert(0, (f'{init} start', start, COLORS[3]))
width = 0.8 / len(bars)
for j, (label, w, color) in enumerate(bars):
    offset = (j - (len(bars) - 1) / 2) * width
    ax.bar([i + offset for i in x], [w[n] for n in FITTED], width=width * 0.95, color=color, label=label)
    for i, n in enumerate(FITTED):
        ax.text(i + offset, w[n], f'{w[n]:g}', ha='center', va='bottom', color=INK, fontsize=8)
ax.set_xticks(list(x), FITTED)
ax.grid(axis='x', visible=False)
ax.set_ylabel('weight')
ax.set_title(f"Control vs {init} weights: learned {result['control_wins']}W {result['control_losses']}L "
             f"{result['control_draws']}D ({result['control_score']:.0%})", color=INK, loc='left')
ax.legend()
fig.tight_layout()
fig.savefig(run / 'weights_bar.png', dpi=200)

print('Saved loss.png, weights.png, weights_bar.png in', run)
