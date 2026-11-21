"""Biểu đồ khoa học từ bảng thực nghiệm đã kiểm chứng, dùng backend không GUI."""

from __future__ import annotations

from pathlib import Path
import hashlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from scripts.training.train_models import MODEL_NAMES, csv_bytes
from .feature_analysis import FEATURE_GROUPS


COLORS = dict(zip(MODEL_NAMES, ["#777777", "#2878B5", "#D67B23", "#32936F", "#C44E52"]))
GROUP_LABELS = ["G1\nSân nhà", "G2\nxG lịch sử", "G3\nBàn thắng", "G4\nCú sút", "G5\nĐối thủ", "G6\nLịch sử"]
HISTORY_LABELS = ["0 trận", "1–4 trận", "≥5 trận"]
DPI = 220


def generate_figures(tables: dict[str, pd.DataFrame], output_dir: Path) -> list[dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "savefig.facecolor": "white"})
    audits = []

    def save(fig, name, source, count, explanation):
        path = output_dir / name
        fig.savefig(path, dpi=DPI, bbox_inches="tight")
        audits.append(dict(file=name, dpi=DPI, plotted_values=count, source_sha256=hashlib.sha256(csv_bytes(source)).hexdigest(),
                           validation=explanation, output_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        plt.close(fig)

    ablation = tables["ablation_summary.csv"]
    models = list(MODEL_NAMES[1:])
    matrix = ablation.pivot(index="model", columns="removed_group", values="mean_delta_mae").loc[models, list(FEATURE_GROUPS)].to_numpy()
    fig, ax = plt.subplots(figsize=(11.5, 4.8), layout="constrained")
    maximum = max(float(np.abs(matrix).max()), 0.001)
    chart = ax.imshow(matrix, cmap="RdBu_r", vmin=-maximum, vmax=maximum, aspect="auto")
    np.testing.assert_array_equal(chart.get_array(), matrix)
    ax.set_xticks(range(6), GROUP_LABELS)
    ax.set_yticks(range(4), models)
    for i in range(4):
        for j in range(6):
            ax.text(j, i, f"{matrix[i, j]:+.3f}", ha="center", va="center",
                    color="white" if abs(matrix[i, j]) > maximum * 0.55 else "black")
    fig.colorbar(chart, ax=ax, label="ΔMAE (xG): bỏ nhóm − full-feature")
    ax.set_title("Ablation nhóm — Development Validation\nTrung bình ba fold; Δ dương nghĩa là lỗi tăng khi bỏ nhóm")
    save(fig, "ablation_delta_mae.png", ablation, matrix.size, "Ô heatmap khớp chính xác mean_delta_mae.")

    importance = tables["permutation_summary.csv"]
    fig, axes = plt.subplots(2, 2, figsize=(15, 11), layout="constrained")
    for ax, model in zip(axes.flat, models):
        data = importance.loc[importance.model.eq(model)].sort_values("mean_importance_mae")
        bars = ax.barh(data.feature, data.mean_importance_mae, xerr=data.std_between_folds,
                       color=COLORS[model], alpha=0.85, capsize=2)
        np.testing.assert_array_equal([bar.get_width() for bar in bars], data.mean_importance_mae)
        ax.axvline(0, color="black", linewidth=0.7)
        ax.set_title(model)
        ax.set_xlabel("MAE sau hoán vị − MAE gốc (xG)")
    fig.suptitle("Permutation Importance — Development Validation\n10 lần/fold; thanh sai số là SD của ba mean-fold (ddof=0), không phải khoảng tin cậy", fontsize=13)
    save(fig, "permutation_importance.png", importance, len(importance), "Chiều rộng cột khớp mean_importance_mae; xerr dùng std_between_folds.")

    predictions = tables["validation_predictions.csv"]
    maximum = float(max(predictions.actual_xg.max(), predictions.predicted_xg.max())) * 1.04
    fig, axes = plt.subplots(2, 3, figsize=(13.5, 8.5), layout="constrained", sharex=True, sharey=True)
    for ax, model in zip(axes.flat, MODEL_NAMES):
        data = predictions.loc[predictions.model.eq(model)]
        chart = ax.scatter(data.actual_xg, data.predicted_xg, s=9, alpha=0.22, color=COLORS[model], edgecolors="none")
        np.testing.assert_array_equal(chart.get_offsets(), data[["actual_xg", "predicted_xg"]].to_numpy())
        ax.plot([0, maximum], [0, maximum], color="black", linestyle="--", linewidth=0.8)
        ax.set(xlim=(0, maximum), ylim=(0, maximum), xlabel="xG thực tế", ylabel="xG dự báo",
               title=f"{model}\nn={len(data)} bản ghi, {data.match_id.nunique()} trận")
    axes.flat[-1].axis("off")
    fig.suptitle("xG thực tế và dự báo — Development Validation 2021–2023", fontsize=13)
    save(fig, "actual_vs_predicted.png", predictions, len(predictions) * 2, "Mọi tọa độ scatter khớp actual_xg/predicted_xg; không lấy mẫu bớt bản ghi.")

    fig, axes = plt.subplots(2, 3, figsize=(13.5, 8), layout="constrained", sharex=True, sharey=True)
    bins = np.linspace(float(predictions.residual.min()), float(predictions.residual.max()), 51)
    for ax, model in zip(axes.flat, MODEL_NAMES):
        values = predictions.loc[predictions.model.eq(model), "residual"]
        counts, _, _ = ax.hist(values, bins=bins, color=COLORS[model], alpha=0.85)
        np.testing.assert_array_equal(counts, np.histogram(values, bins=bins)[0])
        ax.axvline(0, color="black", linestyle="--", linewidth=0.8)
        ax.set(title=model, xlabel="Residual = dự báo − thực tế (xG)", ylabel="Số bản ghi")
    axes.flat[-1].axis("off")
    fig.suptitle("Phân phối residual — Development Validation\nDương: dự báo cao; âm: dự báo thấp", fontsize=13)
    save(fig, "residual_distribution.png", predictions, len(predictions), "Tần số histogram khớp np.histogram với cùng bin ở mọi model.")

    errors = tables["error_analysis.csv"]

    def grouped_chart(dimension, groups, labels, title, name):
        data = errors.loc[errors.dimension.eq(dimension)]
        fig, ax = plt.subplots(figsize=(11, 5.2), layout="constrained")
        x = np.arange(len(groups))
        for i, model in enumerate(MODEL_NAMES):
            group = data.loc[data.model.eq(model)].set_index("group").loc[groups]
            bars = ax.bar(x + (i - 2) * 0.15, group.mae, width=0.145, label=model, color=COLORS[model])
            np.testing.assert_array_equal([bar.get_height() for bar in bars], group.mae)
        counts = data.loc[data.model.eq(MODEL_NAMES[0])].set_index("group").loc[groups, "n_observations"]
        ax.set_xticks(x, [f"{label}\nn={int(n)} / model" for label, n in zip(labels, counts)])
        ax.set_ylabel("MAE (xG)")
        ax.set_title(title + "\nDevelopment Validation; n là số bản ghi đội–trận")
        ax.legend(ncol=3, fontsize=9)
        ax.set_ylim(0, float(data.mae.max()) * 1.28)
        save(fig, name, data, len(data), "Chiều cao mọi cột khớp MAE và số quan sát của subgroup đã xuất.")

    grouped_chart("season", ["2021", "2022", "2023"], ["2021–2022", "2022–2023", "2023–2024"],
                  "MAE theo mùa Validation", "mae_by_season.png")
    grouped_chart("actual_xg", ["xg_lt_1", "xg_1_to_2", "xg_ge_2"], ["xG < 1", "1 ≤ xG < 2", "xG ≥ 2"],
                  "MAE theo xG thực tế — chỉ dùng phân tích sau trận", "mae_by_actual_xg.png")

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.6), layout="constrained", sharey=True)
    sources = []
    groups = ["zero", "one_to_four", "five_or_more"]
    for ax, dimension, label in zip(axes, ["team_history", "opponent_history"], ["Đội đang xét", "Đối thủ"]):
        data = errors.loc[errors.dimension.eq(dimension)]
        sources.append(data)
        x = np.arange(3)
        for i, model in enumerate(MODEL_NAMES):
            group = data.loc[data.model.eq(model)].set_index("group").loc[groups]
            bars = ax.bar(x + (i - 2) * 0.15, group.mae, width=0.145, color=COLORS[model], label=model)
            np.testing.assert_array_equal([bar.get_height() for bar in bars], group.mae)
        counts = data.loc[data.model.eq(MODEL_NAMES[0])].set_index("group").loc[groups, "n_observations"]
        ax.set_xticks(x, [f"{label}\nn={int(n)} / model" for label, n in zip(HISTORY_LABELS, counts)])
        ax.set_title(label)
        ax.set_ylabel("MAE (xG)")
    axes[0].legend(ncol=1, fontsize=8)
    fig.suptitle("Sai số theo mức độ có dữ liệu lịch sử — Development Validation\nNhóm n < 30 chỉ có ý nghĩa mô tả, cần tránh khái quát mạnh", fontsize=12)
    source = pd.concat(sources, ignore_index=True)
    save(fig, "mae_by_history.png", source, len(source), "Cột MAE và nhãn n của hai nhóm lịch sử khớp bảng error_analysis.")
    return audits
