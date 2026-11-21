"""Báo cáo Phase 6 bằng tiếng Việt, chỉ dùng kết quả đã thực thi trong state."""

from __future__ import annotations

import hashlib
from pathlib import Path
import platform

import matplotlib
import numpy as np
import pandas as pd
import scipy
import sklearn
import xgboost

from scripts.prepare_training_features import FEATURES, ROOT
from scripts.training.train_models import MODEL_NAMES, _table
from scripts.training.tune_models import canonical_params
from .feature_analysis import FEATURE_GROUPS, GROUP_NAMES
from .error_analysis import DISAGREEMENT_THRESHOLD, LARGE_ERROR_THRESHOLD, SMALL_SAMPLE_THRESHOLD


DEFINITIONS = {
    "is_home": "1 = Home, 0 = Away; lấy từ venue.",
    "matches_seen": "Số trận đã quan sát trước hiện trận, trong stint các mùa La Liga liên tiếp của đội.",
    "short_history": "1 khi matches_seen < 5; bao gồm 0–4 trận, không chỉ 0 trận.",
    "xg_avg5": "Trung bình xg của tối đa 5 trận trước; tấn công theo xG.",
    "xga_avg5": "Trung bình xga của tối đa 5 trận trước; xG đối thủ tạo ra.",
    "gf_avg5": "Trung bình bàn ghi được của tối đa 5 trận trước.",
    "ga_avg5": "Trung bình bàn thua của tối đa 5 trận trước.",
    "shot_avg5": "Trung bình tổng cú sút sh của tối đa 5 trận trước.",
    "sot_avg5": "Trung bình cú sút trúng đích sot của tối đa 5 trận trước.",
    "opponent_xg_avg5": "xg_avg5 của đối thủ, ghép từ phía còn lại cùng match_id.",
    "opponent_xga_avg5": "xga_avg5 của đối thủ, ghép từ phía còn lại cùng match_id.",
    "opponent_matches_seen": "Số trận lịch sử trước đó của đối thủ trong stint tương ứng.",
    "opponent_short_history": "1 khi opponent_matches_seen < 5.",
}


def result_observations(tables: dict) -> list[str]:
    """Diễn giải có số liệu, không suy luận nhân quả hoặc tự chọn lại features."""
    importance = tables["permutation_summary.csv"]
    errors = tables["error_analysis.csv"]
    lines = ["### Các điểm quan sát từ bảng và biểu đồ", ""]
    for model in ("Linear Regression", "XGBoost"):
        leaders = importance.loc[importance.model.eq(model)].nlargest(3, "mean_importance_mae")
        text = "; ".join(f"{r.feature} ({r.mean_importance_mae:+.6f})" for r in leaders.itertuples(index=False))
        lines += [f"- {model}: ba features có mean Permutation Importance lớn nhất là {text}."]
    lines += ["", "Trong các kết quả này, có thể so sánh trực tiếp mức reliance của LR vào số trận lịch sử đối thủ với reliance của XGBoost vào thông tin xGA đối thủ và cú sút. Đây là mô tả perturbation từng cột; không đồng nhất với tổng đóng góp của một nhóm, vì Ablation cho phép model học bù từ những cột giữ lại.", ""]
    for model in ("Linear Regression", "XGBoost"):
        seasons = errors.loc[errors.model.eq(model) & errors.dimension.eq("season")]
        best = seasons.loc[seasons.mae.idxmin()]
        worst = seasons.loc[seasons.mae.idxmax()]
        home = errors.loc[errors.model.eq(model) & errors.dimension.eq("venue") & errors.group.eq("Home")].iloc[0]
        away = errors.loc[errors.model.eq(model) & errors.dimension.eq("venue") & errors.group.eq("Away")].iloc[0]
        overall = errors.loc[errors.model.eq(model) & errors.dimension.eq("overall")].iloc[0]
        lines += [f"- {model}: MAE mùa thấp nhất ở season={best.group} ({best.mae:.6f}), cao nhất ở season={worst.group} ({worst.mae:.6f}). Home MAE={home.mae:.6f}, Mean Residual={home.mean_residual:+.6f}; Away MAE={away.mae:.6f}, Mean Residual={away.mean_residual:+.6f} (mỗi phía n={home.n_observations}). Residual gộp={overall.mean_residual:+.6f} có thể che các chiều sai lệch khác nhau khi điều kiện hóa theo xG thực tế."]
        zero = errors.loc[errors.model.eq(model) & errors.dimension.eq("team_history") & errors.group.eq("zero")].iloc[0]
        long = errors.loc[errors.model.eq(model) & errors.dimension.eq("team_history") & errors.group.eq("five_or_more")].iloc[0]
        lines += [f"- {model}: nhóm đội có 0 trận lịch sử có n={zero.n_observations}, MAE={zero.mae:.6f}; nhóm ≥5 trận có n={long.n_observations}, MAE={long.mae:.6f}. Không mặc định rằng nhóm ít lịch sử luôn có sai số cao hơn, cũng không suy ra ưu thế từ nhóm n rất nhỏ."]
    lines += ["", "Các kết quả này không đủ giải thích nhân quả cho khác biệt Home/Away hoặc giữa mùa. Scatter và bảng actual_xg cho thấy cần phân biệt sai lệch tổng thể với sai lệch có điều kiện; không dùng các nhóm hậu kiểm để thay model hoặc tạo feature mới.", ""]
    return lines


def build_report(state: dict, error: str | None = None) -> str:
    tables = state.get("tables", {})
    lines = ["# Phân tích đóng góp features và sai số dự báo xG La Liga", "",
        "## 1. Bối cảnh và mục tiêu Phase 6", "",
        "Phân tích bốn Regression models đã tuning ở Phase 5 bằng Group Ablation, Permutation Importance và Error Analysis trên Development Validation. Historical Baseline giữ nguyên làm benchmark. Không tuning lại, không Feature Selection, SHAP, Final Test, tạo Final Model hoặc triển khai website.", "",
        "## 2. Kiểm tra repository và kết quả Phase 5", "",
        "Đã đọc preprocessing, schema normalized CSV, scripts chuẩn hóa/chuẩn bị features, cross_validation.py, train_models.py, tune_models.py, requirements, các CSV/JSON Phase 4–5, reports Phase 3–5 và tests hiện có. Tái sử dụng APIs và hàm metric/hash; không cần hoặc tìm Final Features.docx.", ""]
    if "selected" in state:
        selected = state["selected"]
        lines += _table(pd.DataFrame([dict(model=name, mean_validation_mae=data["mean_validation_mae"],
            mean_validation_rmse=data["mean_validation_rmse"], best_params=canonical_params(data["best_params"]))
            for name, data in selected["models"].items()]))
    lines += ["", "Các cấu hình được đọc trực tiếp best_params.json; fixed_parameters được so với model_templates() hiện có trước khi clone/set_params. Kiểm tra SHA-256 nguồn, feature order, clipping và ddof; không hard-code tham số đã chọn. Không chỉnh sửa kết quả hoặc báo cáo Phase 5 để ép khớp.", "",
        "## 3. Định nghĩa 13 features và Feature Engineering", "",
        "Nguồn xác minh là data/preprocess_laliga.py, các hằng số của module hiện có và dataset. Rolling theo team/stint sử dụng shift(1), window=5, min_periods=1, loại hiện trận khỏi lịch sử. Stint bắt đầu lại khi gap giữa các mùa quan sát >1, không phải ngưỡng 300 ngày. matches_seen là cumcount và short_history kiểm tra <5.", "",
        "| Thứ tự | Feature | Ý nghĩa đã đối chiếu |", "|---|---|---|"]
    lines += [f"| {i} | `{feature}` | {DEFINITIONS[feature]} |" for i, feature in enumerate(FEATURES, 1)]
    lines += ["", "**sh là tổng cú sút; sot là cú sút trúng đích.** ROLLING_MAP ánh xạ sh→shot_avg5 và sot→sot_avg5 riêng biệt; đã kiểm tra sh≥sot và số dòng hai giá trị khác nhau trên Development. Kiểm tra số học hỗ trợ tính nhất quán của schema, không tự nó chứng minh ngữ nghĩa ngoài định nghĩa dự án.", "",
        "## 4. Dữ liệu, target, metadata và Final Test", ""]
    if "dataset_shape" in state:
        development = state["development"]
        lines += [f"Dataset nguồn: {state['dataset_shape'][0]} dòng × {state['dataset_shape'][1]} cột, {state['source_matches']} trận. Development: {len(development.frame)} bản ghi, season 2019–2023. Validation của ba fold: {sum(len(f.validation_indices) for f in development.folds)} bản ghi/model, tương ứng {sum(len(f.validation_indices) for f in development.folds) // 2} trận/model.", ""]
    lines += ["Target y=xg. season, date, round, match_id, team, opponent, venue chỉ dùng chia tập/audit/phân tích; is_home đồng thời là feature hợp lệ và biến phân nhóm. gf, ga, sh, sot, xga và xg hiện trận không xuất hiện trong X. Không dùng actual_xg groups làm feature hoặc điều chỉnh model.", "",
        "Season 2024 và 2025 chỉ được đọc khi kiểm tra schema/toàn vẹn nguồn; bị loại trước prepare_features của Development và mọi thí nghiệm, scoring, Ablation, Permutation, Error Analysis. Không fit model toàn bộ Development.", "",
        "## 5. Cross-Validation và Median Imputation", ""]
    if "development" in state:
        lines += _table(pd.DataFrame([dict(fold=f.fold, train_seasons=";".join(map(str, f.spec.train_seasons)),
            validation_season=f.spec.validation_season, train_samples=len(f.train_indices), validation_samples=len(f.validation_indices),
            train_end=f.train_end, validation_start=f.validation_start, validation_end=f.validation_end)
            for f in state["development"].folds]))
    lines += ["", "Giữ nguyên Expanding Window Phase 4/5; splitter kiểm tra mùa, ngày, cặp trận và không giao match_id. X/y/metadata giữ đúng thứ tự với indices iloc của Development. prepare_features() khôi phục đúng Fixed Prior về NaN; mỗi full-feature reference có Pipeline/preprocessor/estimator mới, chỉ fit trên Train. Tám median được đối chiếu riêng từ Train, năm features còn lại và mọi ô hợp lệ giữ nguyên. Không có dataset impute toàn cục.", "",
        "Đánh giá theo dự báo tuần tự trước trận: trận đã kết thúc trước đó trong cùng mùa Validation được phép cung cấp lịch sử có sẵn; không dùng hiện trận hoặc trận tương lai. Không giả định dự báo đồng thời cả mùa. Tác vụ đọc/kiểm chứng logic Feature Engineering chứ không tái tính rolling.", "",
        "## 6. Tái tạo full-feature trước phân tích", ""]
    if "full_feature_results.csv" in tables:
        full = tables["full_feature_results.csv"]
        lines += _table(full.loc[:, ["model", "fold", "train_samples", "validation_samples", "mae", "rmse", "phase5_hash_matches"]])
        lines += ["", "Đối chiếu đủ 15 dòng với overfitting_diagnostics.csv, configuration_stage=after: MAE/RMSE khớp atol=1e-12, rtol=0 và hash dự báo khớp chính xác. Hash là SHA-256 của dự báo sau clipping dưới dạng float64 little-endian. Tất cả reference được tái tạo và đối chiếu trước khi bắt đầu Ablation/Permutation.", "",
                  "12 fitted full-feature estimators được giữ trong bộ nhớ cho Permutation. Baseline lấy xg_avg5 từ cùng preprocessor đã fit Train của một reference trong fold; không fit Regression, không Ablation hoặc Permutation baseline."]
    lines += ["", "## 7. Sáu nhóm và Leave-One-Group-Out Ablation", "", "| Nhóm | Tên | Features bị bỏ |", "|---|---|---|"]
    lines += [f"| {group} | {GROUP_NAMES[group]} | {', '.join(features)} |" for group, features in FEATURE_GROUPS.items()]
    lines += ["", "Mỗi lần bỏ đúng một nhóm, clone estimator mới giữ nguyên hyperparameters Phase 5, fit Train và dự báo Validation bằng các cột còn lại đúng thứ tự. Đầu tiên preprocess cả 13 features bằng preprocessor đã fit Train, rồi mới chọn cột cho estimator; không sửa HistoryMedianImputer.", "",
        "**G6:** matches_seen/opponent_matches_seen vẫn dùng để xác minh và khôi phục prior trước imputation. Bỏ G6 chỉ loại bốn cột khỏi estimator, không loại mọi vai trò gián tiếp của thông tin lịch sử trong preprocessing.", "",
        "ΔMAE=ablated_mae−full_mae, ΔRMSE tương tự. Δ dương nghĩa là bỏ nhóm làm lỗi tăng; Δ âm nghĩa là giảm lỗi trong thí nghiệm này. Không retune sau bỏ nhóm, không diễn giải Δ là tác động nhân quả hoặc tự động loại feature khi Δ nhỏ/âm.", ""]
    if "ablation_results.csv" in tables:
        lines += ["### Kết quả từng fold — đủ 72 lượt fit", ""]
        lines += _table(tables["ablation_results.csv"].loc[:, ["model", "fold", "removed_group", "n_features", "full_mae", "ablated_mae", "delta_mae", "full_rmse", "ablated_rmse", "delta_rmse"]])
        lines += ["", "### Tổng hợp ba fold (ddof=0)", ""]
        lines += _table(tables["ablation_summary.csv"].loc[:, ["model", "removed_group", "mean_delta_mae", "std_delta_mae", "mean_delta_rmse", "std_delta_rmse", "positive_delta_folds"]])
    lines += ["", "## 8. Permutation Importance", "",
        "Dùng sklearn.inspection.permutation_importance trên X_validation sau preprocessing. Mỗi full estimator giữ nguyên, không fit lại; chỉ một cột hoán vị mỗi lượt, target và ma trận gốc được kiểm tra không đổi. n_repeats=10, random_state=42, n_jobs=1. Dùng scorer âm gọi evaluate_predictions() để clip trước MAE; importance_mae=permuted_mae−original_mae.", "",
        "Lưu 1.560 repetition riêng. Thư viện còn chấm 12 baseline nguyên bản; kiểm chứng tái lập thực nghiệm chạy lại 130 perturbations và 1 baseline ở reference đầu với cùng seed, không thêm model fit. Seed 42 khởi tạo chuỗi RNG, không hiểu repetition thứ r là seed=42+r.", "",
        "permutation_fold_summary.csv có mean/SD qua 10 repetition trong mỗi fold. permutation_summary.csv lấy trung bình ba mean-fold và SD giữa ba mean-fold (ddof=0), đồng thời lưu mean SD trong-fold. Thanh sai số trên hình là biến động giữa mùa/fold, không phải khoảng tin cậy.", ""]
    if "permutation_summary.csv" in tables:
        lines += ["### Kết quả tổng hợp 13 features cho bốn model", ""]
        lines += _table(tables["permutation_summary.csv"].loc[:, ["model", "feature", "mean_importance_mae", "std_between_folds", "mean_std_within_fold", "positive_importance_folds"]])
        lines += ["", "### Mean importance theo từng fold", ""]
        pivot = tables["permutation_fold_summary.csv"].pivot(index=["model", "feature"], columns="fold", values="mean_importance_mae").rename(columns={1: "fold_1", 2: "fold_2", 3: "fold_3"}).reset_index()
        lines += _table(pivot)
    lines += ["", "## 9. Kết hợp Ablation và Permutation", "",
        "Ablation bỏ nhóm và huấn luyện lại nên model có thể bù bằng các features còn lại. Permutation giữ nguyên model nhưng gây nhiễu một feature khi đánh giá. Hai đại lượng khác nhau; không cộng importance của các cột để coi như Delta của nhóm.", ""]
    if "ablation_summary.csv" in tables:
        ablation, importance = tables["ablation_summary.csv"], tables["permutation_summary.csv"]
        lookup = {feature: group for group, features in FEATURE_GROUPS.items() for feature in features}
        for model in MODEL_NAMES[1:]:
            a = ablation.loc[ablation.model.eq(model)].sort_values("mean_delta_mae", ascending=False).iloc[0]
            p = importance.loc[importance.model.eq(model)].sort_values("mean_importance_mae", ascending=False).iloc[0]
            lines += [f"- **{model}:** nhóm có ΔMAE lớn nhất là {a.removed_group} ({a.mean_delta_mae:+.6f}; dương ở {a.positive_delta_folds}/3 fold). Feature có mean permutation importance lớn nhất là {p.feature}, thuộc {lookup[p.feature]} ({p.mean_importance_mae:+.6f}; dương ở {p.positive_importance_folds}/3 fold)."]
        lines += ["", "### Đối chiếu Linear Regression và XGBoost", ""]
        a = ablation.loc[ablation.model.isin(["Linear Regression", "XGBoost"])].pivot(index="removed_group", columns="model", values="mean_delta_mae").reset_index()
        p = importance.loc[importance.model.isin(["Linear Regression", "XGBoost"])].pivot(index="feature", columns="model", values="mean_importance_mae").reset_index()
        lines += _table(a) + [""] + _table(p)
    lines += ["", "Các biến tấn công xg_avg5, gf_avg5, shot_avg5, sot_avg5 có thể chia sẻ thông tin; low importance không chứng minh vô dụng. matches_seen/short_history có quan hệ xác định; hoán vị độc lập có thể tạo tổ hợp không thực tế. Hai bản ghi cùng trận có liên quan, nhưng permutation cột độc lập có thể phá tính nhất quán Home/Away. Kết quả là model reliance dưới perturbation đã chọn, không phải quan hệ nhân quả. Chưa đo hoặc tách hoàn toàn tác động tương quan. Không thực hiện Feature Selection/SHAP.", "",
        "## 10. Error Analysis — đơn vị, công thức và quy tắc", "",
        "validation_predictions.csv chỉ chứa Validation 2021–2023, gồm metadata yêu cầu và source_row (index dòng nguồn bắt đầu từ 0; dòng CSV vật lý = source_row+2). residual=predicted−actual; absolute_error=abs(residual); squared_error=residual². Dương là overprediction, âm là underprediction. Mỗi model có 2.280 đội–trận/1.140 trận; 11.400 dòng tổng không có nghĩa 11.400 trận độc lập.", "",
        "error_analysis.csv luôn là thống kê subgroup gộp các bản ghi Validation, tách dimension/group/scope rõ ràng; season riêng tương ứng đúng một fold. MAE/RMSE tính bằng metric dùng chung. Dispersion gồm residual_std và absolute_error_std, ddof=0; thêm median, p90 và max Absolute Error. RMSE gộp các quan sát không đồng nhất với trung bình RMSE của ba fold; bảng CV dùng mean-fold, bảng subgroup dùng pooled observations.", "",
        f"Quy tắc chẩn đoán cố định trước xem kết quả: sai số lớn ≥{LARGE_ERROR_THRESHOLD} xG; chênh dự báo LR/XGBoost lớn ≥{DISAGREEMENT_THRESHOLD} xG; subgroup n<{SMALL_SAMPLE_THRESHOLD} được đánh dấu mẫu nhỏ; chọn 15 lỗi tuyệt đối cao nhất/model cùng cực trị over/under nếu chưa nằm trong top 15. Các ngưỡng này chỉ để mô tả, không dùng chọn hoặc điều chỉnh model.", ""]
    if "error_analysis.csv" in tables:
        errors = tables["error_analysis.csv"]
        columns = ["model", "group", "n_observations", "n_matches", "mae", "rmse", "mean_residual", "median_absolute_error", "residual_std"]
        for section, dimension, explanation in [
            ("11. Sai số theo mùa", "season", "Ba mùa chỉ cho thấy biến động Development Validation; không đủ kết luận xu hướng dài hạn."),
            ("12. Sai số Home/Away", "venue", "Khác biệt sai số và residual không chứng minh home advantage có tác động nhân quả."),
            ("13. Sai số theo xG thực tế", "actual_xg", "Nhóm cố định: xg_lt_1 (<1), xg_1_to_2 (1≤xG<2), xg_ge_2 (≥2). Chỉ phân tích sau trận; việc nhóm theo target có hiệu ứng điều kiện hóa, không phải features trước trận."),
            ("14. Sai số theo lịch sử đội", "team_history", "zero=0 trận, one_to_four=1–4, five_or_more=≥5. short_history bao gồm cả zero và one_to_four."),
            ("15. Sai số theo lịch sử đối thủ", "opponent_history", "Áp dụng cùng ranh giới; n nhỏ không hỗ trợ khái quát mạnh.")]:
            subset = errors.loc[errors.dimension.eq(dimension)]
            lines += [f"## {section}", "", explanation, ""] + _table(subset.loc[:, columns + ["small_sample"]]) + [""]
            if dimension == "actual_xg":
                for model in ("Linear Regression", "XGBoost"):
                    for level in ("xg_lt_1", "xg_ge_2"):
                        value = subset.loc[subset.model.eq(model) & subset.group.eq(level)].iloc[0]
                        lines += [f"- {model}, {level}: n={value.n_observations}, Mean Residual={value.mean_residual:+.6f}, MAE={value.mae:.6f}. Dấu residual mô tả chiều sai lệch trong nhóm đã quan sát, không tự giải thích nguyên nhân."]
            if dimension in ("team_history", "opponent_history"):
                small = subset.loc[subset.small_sample]
                lines += ["", f"Có {len(small)} subgroup model/nhóm với n<30 trong bảng này. Các nhóm không có hoặc có ít lịch sử cần được xem thận trọng; không dùng sai số nhóm nhỏ làm căn cứ retune."]
        lines += ["", "## 16. Sai số theo Matchweek", ""]
        week = errors.loc[errors.dimension.eq("matchweek")].copy()
        if not week.empty:
            week["matchweek"] = week.group.astype(int)
            matrix = week.pivot(index="matchweek", columns="model", values="mae").loc[:, list(MODEL_NAMES)].reset_index()
            n = week.loc[week.model.eq(MODEL_NAMES[0])].set_index("matchweek").n_observations
            matrix.insert(1, "n_per_model", matrix.matchweek.map(n))
            lines += ["Round được parse đầy đủ theo mẫu Matchweek N, N∈[1,38]; bảng sắp theo số nguyên, không theo chuỗi. Không đưa round vào X.", ""] + _table(matrix)
        else:
            lines += ["Không chuyển đổi round đáng tin cậy; đã bỏ riêng phân tích Matchweek và ghi cảnh báo, không tự tạo thứ tự."]
    if "notable_errors.csv" in tables:
        cases = tables["notable_errors.csv"]
        lines += ["", "## 17. Các trường hợp sai số lớn", "",
            "Chọn theo quy tắc giống nhau cho mọi model: top 15 Absolute Error, thêm cực trị over/under nếu chưa có. Giữ từng bản ghi duy nhất/model; không chọn ví dụ nhằm ưu ái model. Chỉ mô tả từ metadata/xG/dự báo hiện có, không đoán thẻ đỏ, chiến thuật hoặc diễn biến khi không có bằng chứng.", ""]
        cols = ["fold", "date", "match_id", "team", "opponent", "is_home", "actual_xg", "predicted_xg", "residual", "absolute_error", "largest_overprediction", "largest_underprediction"]
        for model in MODEL_NAMES:
            rows = cases.loc[cases.model.eq(model)]
            lines += [f"### {model}: {len(rows)} trường hợp", ""] + _table(rows.loc[:, cols]) + [""]
        lines += ["## 18. Hai phía cùng trận và sai số chung nhiều model", ""]
        matches, cross = tables["match_error_analysis.csv"], tables["cross_model_errors.csv"]
        counts = matches.groupby("model", as_index=False).agg(matches=("match_id", "size"), both_large=("both_large_errors", "sum"))
        lines += _table(counts)
        top_matches = matches.loc[matches.both_large_errors].sort_values(["model", "min_team_absolute_error", "sum_absolute_error"],
            ascending=[True, False, False], kind="stable").groupby("model", sort=False).head(3)
        lines += ["", "Các trận có lỗi cả hai phía lớn nhất theo min(Absolute Error Home, Away), tối đa 3/model:", ""]
        lines += _table(top_matches.loc[:, ["model", "fold", "date", "match_id", "home_team", "away_team", "home_actual_xg", "away_actual_xg", "home_predicted_xg", "away_predicted_xg", "home_absolute_error", "away_absolute_error"]])
        multiple = cross.loc[cross.multiple_regressors_large]
        both_sides = cross.groupby("match_id").multiple_regressors_large.sum().eq(2).sum()
        lines += ["", f"Có {len(multiple)} đội–trận ({multiple.match_id.nunique()} trận phân biệt) có ít nhất hai trong bốn Regression models sai số ≥1 xG. {int(cross.all_regressors_large.sum())} đội–trận có cả bốn model cùng sai số lớn; {int(both_sides)} trận có cả hai phía đều thuộc nhóm nhiều-model-sai-lớn. Benchmark được hiển thị trong cross_model_errors.csv nhưng không tính vào số bốn regressors.", ""]
        selected = multiple.sort_values(["regression_models_large", "mean_regressor_absolute_error", "match_id"], ascending=[False, False, True], kind="stable").head(10)
        lines += _table(selected.loc[:, ["fold", "date", "match_id", "team", "opponent", "actual_xg", "regression_models_large", "mean_regressor_absolute_error", "linear_regression_predicted_xg", "xgboost_predicted_xg"]])
        lines += ["", "## 19. Chênh lệch dự báo Linear Regression và XGBoost", "",
                  f"Có {int(cross.large_disagreement.sum())} đội–trận có |prediction_LR−prediction_XGB|≥{DISAGREEMENT_THRESHOLD} xG. Bảng là 10 chênh lệch lớn nhất theo quy tắc cố định; không dùng để điều chỉnh hoặc chọn model.", ""]
        disagree = cross.sort_values(["lr_xgb_prediction_difference", "match_id", "team"], ascending=[False, True, True], kind="stable").head(10)
        lines += _table(disagree.loc[:, ["fold", "date", "match_id", "team", "opponent", "actual_xg", "linear_regression_predicted_xg", "xgboost_predicted_xg", "linear_regression_absolute_error", "xgboost_absolute_error", "lr_xgb_prediction_difference"]])
    lines += ["", "## 20. Biểu đồ học thuật", ""]
    for figure in state.get("figures", []):
        lines += [f"### {figure['file']}", "", f"![{figure['file']}](../outputs/figures/phase6/{figure['file']})", "",
                  f"{figure['validation']} PNG {figure['dpi']} dpi; dữ liệu chỉ thuộc Development Validation.", ""]
    lines += ["Hình Ablation so sánh delta với mốc 0; Permutation hiển thị cả importance âm và SD giữa fold. Scatter dùng toàn bộ quan sát/model và đường y=x; histogram dùng cùng bins và dấu residual rõ ràng. Các hình MAE theo mùa, actual xG và lịch sử ghi số quan sát; nhóm actual xG chỉ là hậu kiểm. Không dùng các hình làm lý do tự đổi pipeline 13 features.", "",
        "## 21. Giới hạn diễn giải và model-selection bias", "",
        "Cấu hình Phase 5 được chọn bằng chính ba mùa Validation này; Phase 6 tiếp tục phân tích chúng nên đây là development-stage diagnostics, không phải đánh giá độc lập sau chọn hay Final Test. Sai số thấp hơn khi bỏ một nhóm chỉ là giả thuyết cho nghiên cứu sau, không tự tạo feature set mới. Ba mùa không đủ suy ra xu hướng dài hạn hoặc ý nghĩa thống kê.", "",
        "Ablation và Permutation không đo cùng đại lượng và không phải tác động nhân quả. Tương quan features, mối liên hệ xác định của counters/flags, hai phía cùng trận và kích thước subgroup nhỏ giới hạn cách hiểu. Không có dữ liệu sự kiện/chiến thuật để giải thích nhân quả các ca lớn. Phân nhóm theo target là mô tả hậu nghiệm và có hiệu ứng điều kiện hóa; không được chuyển thành feature trước trận.", "",
        "## 22. Kiểm thử, kiểm chứng và tái lập", ""]
    lines += _table(pd.DataFrame([(name, "Đạt" if passed else "Không đạt", detail) for name, passed, detail in state["checks"]],
                                columns=["Kiểm chứng", "Kết quả", "Bằng chứng"]))
    if "tests" in state:
        tests = state["tests"]
        lines += ["", f"Tests thực tế: {tests['run']} đã chạy; failures={tests['failures']}, errors={tests['errors']}, skipped={tests['skipped']}.", "",
                  "```text", tests["log"].strip(), "```", "",
                  "Các unit tests Phase 5 có GridSearch nhỏ cho Linear Regression để kiểm tra cơ chế; đây là regression tests, không chạy lại full search 79 cấu hình và không thay hyperparameters/đầu ra Phase 5. Fixtures Phase 6 và hình trong tests nằm ở thư mục tạm, tách khỏi thí nghiệm thật."]
    lines += ["", "Tái lập thực nghiệm: 15 full-feature/benchmark prediction hashes khớp Phase 5, mọi reference giữ seed và params. Permutation đầu tiên chạy lại đủ 130 perturbations cùng seed và khớp từng repetition chính xác. Không tuyên bố đã chạy lại toàn bộ Ablation hoặc toàn bộ Permutation lần hai. Tất cả CSV được đọc lại theo schema và đối chiếu số thực atol/rtol=1e-14; manifest JSON được đọc lại và kiểm chứng. Biểu đồ tự đối chiếu giá trị với bảng dùng vẽ.", "",
        "## 23. Ngân sách, môi trường và lệnh chạy", "",
        "Thí nghiệm chính: 12 fit full Regression + 72 fit ablated = **84 Regression fits**. Permutation: **1.560 perturbation prediction evaluations**, cộng 12 baseline scores nội bộ thư viện; kiểm chứng lại một reference thêm 130 perturbations và 1 baseline score, không refit. Unit-test fits không tính vào ngân sách chính. Baseline không train Regression và tái sử dụng preprocessing của fold.", "",
        f"Python {platform.python_version()}; NumPy {np.__version__}; Pandas {pd.__version__}; SciPy {scipy.__version__}; scikit-learn {sklearn.__version__}; XGBoost {xgboost.__version__}; Matplotlib {matplotlib.__version__}. Không cài dependency mới; scripts/evaluation/requirements.txt bổ sung Matplotlib trên các pins training hiện có.", "",
        "Lệnh đã thực thi:", "", "```powershell", ".\\.venv\\Scripts\\python.exe -m unittest discover -s tests -p test_evaluation.py -v",
        ".\\.venv\\Scripts\\python.exe -m scripts.evaluation.analyze_models", "```", "",
        "CLI chạy tests Phase 4/5/6 trước, rồi reproduction, Ablation, Permutation, Error Analysis, xuất bảng, hình và báo cáo này. Không gọi CLI training/tuning trước đây. Figure backend Agg không cần mở cửa sổ GUI.", ""]
    if "elapsed_seconds" in state:
        lines += [f"Thời gian CLI thực tế: {state['elapsed_seconds']:.2f} giây, gồm tests và xuất hình.", ""]
    lines += ["## 24. File bàn giao và bảo toàn repository", "",
        "Mã mới trong scripts/evaluation/: analyze_models.py điều phối; feature_analysis.py xử lý Ablation/Permutation; error_analysis.py xử lý sai số; visualizations.py vẽ; reporting.py tạo báo cáo; __init__.py và requirements.txt. Tests mới duy nhất tests/test_evaluation.py. Không thay shared modules cũ.", "",
        "Các bảng riêng theo đơn vị: full_feature_results.csv (model-fold); ablation_results.csv (model-fold-group), ablation_summary.csv (model-group); permutation_importance.csv (model-fold-feature-repeat), permutation_fold_summary.csv (model-fold-feature), permutation_summary.csv (model-feature); validation_predictions.csv (model-đội–trận); error_analysis.csv (model-subgroup); notable_errors.csv (case duy nhất/model); match_error_analysis.csv (model-trận); cross_model_errors.csv (đội–trận đối chiếu model). Không trộn records và summaries trong cùng schema. analysis_manifest.json ghi features/groups, params nguồn, SHA-256, folds, seeds, ngưỡng chẩn đoán, phiên bản, schema bảng và figure/data hashes.", "",
        "| File có sẵn | SHA-256 trước | Sau thực thi |", "|---|---|---|"]
    for path, digest in state["protected"].items():
        same = path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == digest
        lines.append(f"| `{path.relative_to(ROOT).as_posix()}` | `{digest}` | {'Giữ nguyên' if same else 'Không khớp'} |")
    if state.get("output_hashes"):
        lines += ["", "### SHA-256 các bảng xuất", ""]
        lines += _table(pd.DataFrame([dict(file=name, sha256=digest) for name, digest in state["output_hashes"].items()]))
    lines += ["", "## 25. Vấn đề đã xử lý, cảnh báo và giới hạn còn lại", "",
        "Lần chạy thử tests Phase 6 đầu phát hiện một lỗi ở kiểm chứng round-trip CSV: fixture chỉ có một fold nên Pandas tự suy luận nhãn folds='1' thành số. Đã sửa hàm đọc lại để dùng schema của các cột string và lưu schema vào manifest. Đây là lỗi của kiểm chứng nhãn trên dữ liệu test tạm, không phải lỗi dataset hoặc metrics thực nghiệm. Sau sửa đã chạy lại tests; chỉ kết quả pass được xác nhận trong log mới nhất ở trên.", ""]
    if state["warnings"]:
        lines += [f"- {message}" for message in dict.fromkeys(state["warnings"])]
    else:
        lines += ["Không ghi nhận cảnh báo trong thí nghiệm đã hoàn tất."]
    if error:
        lines += ["", "**Phase 6 chưa hoàn tất.**", "", "```text", error, "```", "",
                  "Chỉ kiểm chứng và kết quả xuất hiện ở trên đã được xác nhận. Không tự sửa dataset hoặc đổi cấu hình Phase 5; cần giải quyết lỗi trước khi kết luận hoàn thành."]
    else:
        lines += ["Không có lỗi chưa giải quyết chặn hoàn thành trong phạm vi Phase 6. Các giới hạn phương pháp ở mục 21 vẫn áp dụng."]
    lines += ["", "## 26. Tài liệu phương pháp", "",
        "Permutation của fitted estimator và giới hạn khi features tương quan: [hướng dẫn scikit-learn](https://scikit-learn.org/stable/modules/permutation_importance.html). Cấu hình API: [permutation_importance](https://scikit-learn.org/stable/modules/generated/sklearn.inspection.permutation_importance.html). Các định nghĩa features dựa hoàn toàn vào code/schema/reports dự án, không phụ thuộc tài liệu ngoài.", "",
        "## 27. Kết luận và đề xuất Phase 7", ""]
    if error:
        lines += ["Chưa thể xác nhận hoàn thành; xem lỗi và phần thí nghiệm còn thiếu."]
    else:
        lines += ["Đã tái tạo mô hình khớp Phase 5, hoàn tất đủ sáu nhóm Ablation, 13 Permutation features với 10 repeats, Error Analysis và bộ Validation predictions có truy vết; bảng, hình và tests đã được kiểm chứng. Findings về features hoặc sai số là mô tả trên Development Validation, không phải kết luận Final Test hoặc bằng chứng nhân quả.", "",
                  "Phase 7 có thể lập kế hoạch kiểm chứng độc lập các giả thuyết về nhóm thông tin, sai số cực trị và độ bền qua thời gian, với phạm vi riêng được phê duyệt. Chưa chọn/fit Final Model, chưa Feature Selection, chưa đánh giá Final Test hoặc triển khai. Dừng sau Phase 6."]
    text = "\n".join(lines) + "\n"
    if "error_analysis.csv" in tables:
        text = text.replace("## 21. Giới hạn diễn giải và model-selection bias",
                            "\n".join(result_observations(tables)) + "\n## 21. Giới hạn diễn giải và model-selection bias")
    return text
