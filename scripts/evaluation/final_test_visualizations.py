"""Hình Phase 7 từ các bảng đã kiểm chứng; không fit model hoặc đọc lại target nguồn."""

import hashlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from scripts.prepare_training_features import ROOT
from scripts.training.train_models import MODEL_NAMES
from .feature_analysis import require

FIGURE_DIR = ROOT/"outputs/figures/phase7"
LABELS = {"Historical Baseline":"Baseline", "Linear Regression":"LR", "Decision Tree":"DT", "Random Forest":"RF", "XGBoost":"XGB"}
COLORS = ["#757575", "#1675ad", "#d89124", "#439b65", "#a45395"]
SPLITS = ["main_final_test", "supplemental_test"]
TITLES = {SPLITS[0]:"Main 2024 · 760 bản ghi / 380 trận", SPLITS[1]:"Supplemental 2025 · 140 bản ghi / 70 trận"}


def generate_figures(tables, output_dir=FIGURE_DIR):
    output_dir.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size":9, "axes.spines.top":False, "axes.spines.right":False})
    metrics = tables["final_test_metrics.csv"]
    predictions = tables["final_test_predictions.csv"]
    errors = tables["final_test_error_analysis.csv"]
    bootstrap = tables["bootstrap_results.csv"]
    replicates = tables["bootstrap_replicates.csv"]
    artifacts = []
    def save(fig, name, inputs, checks):
        fig.tight_layout()
        path = output_dir/name
        fig.savefig(path, dpi=180, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        artifacts.append(dict(path=str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(), input_tables=inputs, verified_values=checks))
    def check_bars(bars, values):
        np.testing.assert_array_equal([b.get_height() for b in bars], np.asarray(values))
    x = np.arange(5)
    labels = [LABELS[n] for n in MODEL_NAMES]
    main = metrics.loc[metrics.test_split.eq(SPLITS[0])].set_index("model").loc[list(MODEL_NAMES)]
    fig,ax = plt.subplots(figsize=(9,4))
    a = ax.bar(x-.18,main.development_cv_mean_fold_mae,.36,label="Development CV · trung bình 3 fold",color="#9bbbd0")
    b = ax.bar(x+.18,main.mae,.36,label=TITLES[SPLITS[0]],color=COLORS)
    check_bars(a,main.development_cv_mean_fold_mae); check_bars(b,main.mae)
    ax.set(xticks=x,xticklabels=labels,ylabel="MAE (xG / bản ghi)",title="Development CV và Main Final Test")
    ax.legend(fontsize=8)
    save(fig,"development_vs_main.png",["final_test_metrics.csv"],"10 bar heights = CV mean-fold MAE / Main MAE")

    fig,axes = plt.subplots(1,2,figsize=(12,4))
    for ax,metric in zip(axes,["mae","rmse"]):
        for i,split in enumerate(SPLITS):
            group = metrics.loc[metrics.test_split.eq(split)].set_index("model").loc[list(MODEL_NAMES)]
            bars = ax.bar(x+(-.18 if i==0 else .18),group[metric],.36,label=TITLES[split],color=COLORS,alpha=1 if i==0 else .42)
            check_bars(bars,group[metric])
        ax.set(xticks=x,xticklabels=labels,ylabel=f"{metric.upper()} (xG / bản ghi)",title=f"Hai Test độc lập · {metric.upper()}")
        ax.legend(fontsize=7)
    save(fig,"main_vs_supplemental_metrics.png",["final_test_metrics.csv"],"20 bar heights = separate split MAE/RMSE")

    fig,axes = plt.subplots(2,5,figsize=(16,6.7))
    for i,split in enumerate(SPLITS):
        for j,model in enumerate(MODEL_NAMES):
            ax = axes[i,j]
            group = predictions.loc[predictions.test_split.eq(split)&predictions.model.eq(model)]
            scatter = ax.scatter(group.actual_xg,group.predicted_xg,s=9,alpha=.35,color=COLORS[j])
            np.testing.assert_array_equal(np.asarray(scatter.get_offsets()), group[["actual_xg","predicted_xg"]].to_numpy())
            lim = max(group.actual_xg.max(),group.predicted_xg.max())+.1
            ax.plot([0,lim],[0,lim],"--",lw=.8,color="#444444")
            ax.set(xlabel="xG thực tế",ylabel="xG dự báo",title=f"{LABELS[model]} · {'Main 2024' if i==0 else 'Supp. 2025'} · n={len(group)}")
    fig.suptitle("Thực tế và dự báo sau clipping",y=1.02)
    save(fig,"actual_vs_predicted.png",["final_test_predictions.csv"],"4500 plotted points = actual/predicted pairs")

    fig,axes = plt.subplots(2,5,figsize=(16,6.7))
    edges = np.linspace(min(-1,predictions.residual.min()),max(1,predictions.residual.max()),30)
    for i,split in enumerate(SPLITS):
        for j,model in enumerate(MODEL_NAMES):
            ax=axes[i,j]; group=predictions.loc[predictions.test_split.eq(split)&predictions.model.eq(model)]
            counts,_,_=ax.hist(group.residual,bins=edges,color=COLORS[j],alpha=.8)
            np.testing.assert_array_equal(counts,np.histogram(group.residual,bins=edges)[0])
            require(int(sum(counts)) == len(group),"Histogram thiếu residual.")
            ax.axvline(0,color="#444444",ls="--",lw=.8)
            ax.set(xlabel="Residual = dự báo − thực tế (xG)",ylabel="Số bản ghi",title=f"{LABELS[model]} · {'Main 2024' if i==0 else 'Supp. 2025'} · n={len(group)}")
    save(fig,"residual_distribution.png",["final_test_predictions.csv"],"histogram bins verified against numpy, all 4500 residuals")

    for dimension, groups, names, filename, title in (
        ("venue",["Home","Away"],["Home","Away"],"venue_mae.png","MAE theo sân thi đấu"),
        ("actual_xg",["xg_lt_1","xg_1_to_2","xg_ge_2"],["xG < 1","1 ≤ xG < 2","xG ≥ 2"],"actual_xg_groups_mae.png","MAE theo xG thực tế · chỉ phân tích sau trận")):
        fig,axes=plt.subplots(1,2,figsize=(13,4.6))
        width=.72/len(groups)
        for ax,split in zip(axes,SPLITS):
            subset=errors.loc[errors.test_split.eq(split)&errors.dimension.eq(dimension)]
            for i,(group,name) in enumerate(zip(groups,names)):
                if not subset.group.eq(group).any():
                    continue  # Nhóm rỗng: không dựng metric giả.
                ordered=subset.loc[subset.group.eq(group)].set_index("model").loc[list(MODEL_NAMES)]
                bars=ax.bar(x+(i-(len(groups)-1)/2)*width,ordered.mae,width,label=f"{name} · n={ordered.n_observations.iloc[0]}",alpha=1-i*.22,color=COLORS)
                check_bars(bars,ordered.mae)
            ax.set(xticks=x,xticklabels=labels,ylabel="MAE (xG / bản ghi)",title=TITLES[split])
            ax.legend(fontsize=8)
        fig.suptitle(title,y=1.02)
        save(fig,filename,["final_test_error_analysis.csv"],"all subgroup bars verified; subgroup n shown")

    comparisons=bootstrap.comparison_id.unique()
    fig,axes=plt.subplots(2,len(comparisons),figsize=(17,7))
    for i,split in enumerate(SPLITS):
        for j,comparison in enumerate(comparisons):
            ax=axes[i,j]
            values=replicates.loc[replicates.test_split.eq(split)&replicates.comparison_id.eq(comparison),"delta_mae"]
            row=bootstrap.loc[bootstrap.test_split.eq(split)&bootstrap.comparison_id.eq(comparison)].iloc[0]
            counts,edges,_=ax.hist(values,bins=32,color="#1675ad",alpha=.75)
            np.testing.assert_array_equal(counts,np.histogram(values,bins=edges)[0])
            require(sum(counts)==2000,"Histogram bootstrap thiếu repetitions.")
            np.testing.assert_array_equal([row.ci_lower,row.ci_upper],np.quantile(values,[.025,.975],method="linear"))
            ax.axvspan(row.ci_lower,row.ci_upper,color="#79b6a0",alpha=.2,label="Khoảng 95%")
            ax.axvline(0,color="#333333",ls="--",lw=.8)
            ax.axvline(row.observed_delta_mae,color="#a44335",lw=1,label="Delta quan sát")
            ax.set(xlabel="ΔMAE = A − B (xG)",ylabel="Số lần lặp",title=f"{LABELS[row.model_a]} − {LABELS[row.model_b]}\n{'Main 2024 · 380' if i==0 else 'Supp. 2025 · 70'} trận · B=2000")
            ax.legend(fontsize=7)
    save(fig,"bootstrap_delta_mae.png",["bootstrap_results.csv","bootstrap_replicates.csv"],"all 20000 replicates and 10 percentile intervals verified")
    return artifacts
