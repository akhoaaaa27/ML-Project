"""Một báo cáo tiếng Việt từ kết quả Phase 7 thực tế, không chọn lại model."""

import json
import pandas as pd
from scripts.prepare_training_features import ROOT
from scripts.training.train_models import _table, MODEL_NAMES
from .feature_analysis import require


def write_report(tables, protocol, manifest, path):
    metrics=tables["final_test_metrics.csv"]
    diagnostics=tables["final_test_diagnostics.csv"]
    errors=tables["final_test_error_analysis.csv"]
    cross=tables["final_test_cross_model_errors.csv"]
    matches=tables["final_test_match_errors.csv"]
    notable=tables["final_test_notable_errors.csv"]
    bootstrap=tables["bootstrap_results.csv"]
    phase6=pd.read_csv(ROOT/"outputs/evaluation/error_analysis.csv",keep_default_na=False)
    phase6_cross=pd.read_csv(ROOT/"outputs/evaluation/cross_model_errors.csv",keep_default_na=False)
    lines=["# Đánh giá mô hình xG La Liga trên các tập Test độc lập theo thời gian", ""]
    def section(number,title,text=""):
        lines.extend([f"## {number}. {title}","",text,""])
    def table(frame): lines.extend([*_table(frame),""])
    def groups(dimension):
        group=errors.loc[errors.dimension.eq(dimension)].copy()
        if dimension=="matchweek": group=group.assign(week=group.group.astype(int)).sort_values(["test_split","week","model"]).drop(columns="week")
        return group[["test_split","model","group","n_observations","n_matches","mae","rmse","mean_residual","small_sample"]]

    section(1,"Bối cảnh và mục tiêu","Dự án dự báo xG trước trận La Liga đã hoàn tất Phase 1–6 bằng Development. Phase 7 lần đầu đánh giá hiệu năng trên mùa 2024 và phần đầu mùa 2025 đã được bảo vệ. Mục tiêu là kiểm tra khả năng khái quát theo thời gian, so sánh Baseline, phân tích sai số và định lượng bất định; không điều chỉnh thiết kế theo Test.")
    section(2,"Nguyên tắc đánh giá độc lập","Tất cả quyết định mô hình, 13 features, preprocessing, clipping, chỉ số, các ngưỡng sai số và so sánh bootstrap được xác định từ trước khi chấm điểm Test. Hai Test có vai trò riêng và không gộp thành một chỉ số chính. Thứ hạng quan sát chỉ mô tả mẫu Test, không thay thế Primary Candidate và không tạo quyết định Final Model.")
    section(3,"Protocol đóng băng trước đánh giá",f"Lệnh `prepare` hoàn tất trước lệnh `evaluate`; bước đầu chỉ kiểm tra cấu trúc/toàn vẹn và đọc quyết định Development. `evaluate` đòi hỏi protocol đã tồn tại và so sánh toàn bộ nội dung, SHA nguồn, cấu hình và tham chiếu trước fit/predict/score. Protocol không bị ghi đè. Nếu đã có manifest hoàn tất, CLI chặn đánh giá lại để tránh vô tình retrain.\n\nProtocol: [`evaluation_protocol.json`](../outputs/final_test/evaluation_protocol.json). SHA-256: `{manifest['evaluation_protocol_sha256']}`. Đã xác minh nguyên trạng sau đánh giá. Bootstrap đã cố định năm so sánh, 2.000 lần lặp, seed 42, ngưỡng percentile 2,5/97,5 và phương pháp quantile `linear`. Các khoảng là khoảng biên, không hiệu chỉnh nhiều so sánh.")
    section(4,"Kiểm tra repository và kết quả kế thừa","Đã đọc Feature Engineering, chuẩn hóa số, API khôi phục prior/median, splitter, training/tuning, cấu hình Phase 5, phân tích Phase 6, dependencies, báo cáo Phase 3–6 và kiểm thử cũ. Tái sử dụng `load_dataset`, `prepare_features`, `build_pipeline`, `load_selected_models`, `evaluate_predictions`, các hàm phân tích sai số và `export_tables`. Tham chiếu CV lấy đúng `outputs/tuning/tuning_summary.csv`, các cột `mean_validation_*_after`. Baseline không có estimator hoặc hyperparameter giả.")
    table(pd.DataFrame([dict(model=n,**v) for n,v in protocol["development_cv"].items()]))
    section(5,"Dữ liệu và ranh giới Development/Test","Nguồn thực tế: 4.700 bản ghi đội–trận, 2.350 trận, 26 cột. Ba phần không giao source rows hoặc match_id; mỗi trận đủ đúng một Home, một Away, cùng ngày và mùa. Không random split. `season=2024` tương ứng mùa 2024–2025, `season=2025` tương ứng phần đầu mùa 2025–2026.")
    table(pd.DataFrame([dict(partition=k,**v) for k,v in protocol["partitions"].items()]))
    section(6,"Khả dụng lịch sử và độ phân giải thời gian",f"Nguồn FE dùng `shift(1).rolling(5,min_periods=1)` trong team/stint; reset khi khoảng mùa >1. Audit đối chiếu chỉ đọc {protocol['temporal_audit']['rolling_values_checked']:,} giá trị với công thức hiện có, không tạo lại/ghi đè rolling. Dung sai `5.1e-9` được xác định trước Test metrics từ độ làm tròn CSV gốc: `5/3 → 1,666666667`, `46/3 → 15,33333333`; Phase 2 chỉ đổi dấu thập phân. Sai khác lớn nhất thực tế `{protocol['temporal_audit']['max_absolute_difference']:.12g}`. Đối chiếu counters và opponent features giữ nguyên logic cũ.\n\nKhông có trường hợp cùng đội có hai trận khác nhau cùng ngày. Mọi bản ghi trong cửa sổ lịch sử có ngày nhỏ hơn ngày dự báo. Dataset chỉ xác nhận độ phân giải ngày; chưa xác nhận giờ khai cuộc/múi giờ, vì vậy không khẳng định kiểm soát đến kickoff. Các trận đã hoàn tất trước đó trong mùa Test được phép làm lịch sử; đây là cập nhật thông tin sẵn có, không phải cập nhật trọng số. Không phát hiện vi phạm thời gian theo độ phân giải hiện có. Nếu audit thất bại, mã dừng, không tự sửa hay loại dòng.")
    section(7,"Huấn luyện cố định một lần","Bốn regressors và bốn preprocessors mới được fit đúng một lần trên toàn bộ 3.800 dòng Development. Toàn bộ fit hoàn tất trước đánh giá hai Test. Cùng fitted objects được giữ trong bộ nhớ để predict Main và Supplemental; sau đó lặp inference kiểm tra chính xác, không fit lại. Không có fit/fit_transform/partial_fit trên Test, không train giữa hai Test và không serialize model. Đếm fit trong manifest được đối chiếu kiểm thử spy; không phải log bao phủ mọi thao tác Python ngoài chương trình.")
    table(pd.DataFrame([dict(model=n,estimator_fit_calls=v["estimator_fit_calls"],imputer_fit_calls=v["imputer_fit_calls"],n_fit_records=v["n_fit_records"]) for n,v in manifest["training"].items()]))
    section(8,"Median Imputation và chống rò rỉ","`prepare_features` khôi phục đúng prior đã xác minh về NaN khi số trận lịch sử bằng 0; không thay giá trị hợp lệ tình cờ bằng prior, không coi short_history là thiếu toàn bộ lịch sử. Tám median chỉ học trên Development và đối chiếu phép tính median độc lập; năm cột passthrough giữ nguyên. X, y, metadata giữ index và đúng thứ tự 13 cột; target, date, team, round, match_id và thống kê hiện tại không thuộc X. Sau transform, mọi số hữu hạn, không đổi ô hợp lệ. Test shift nhân tạo +1.000.000 xác nhận median không đổi.")
    table(pd.DataFrame([dict(feature=f,development_median=manifest["training"]["Linear Regression"]["medians"][f]) for f in protocol["imputation"]["imputed_columns"]]))
    lines.extend(["Thứ tự X:","","```text",", ".join(protocol["features"]),"```",""])
    section(9,"Cấu hình năm phương pháp","Đọc trực tiếp selected/fixed parameters trong Phase 5, xác minh dataset SHA và toàn bộ fixed parameters với estimator templates, không tuning lại. Các seed cố định giữ nguyên. Baseline lấy `xg_avg5` đã transform bằng preprocessor Development của LR; không có bước fit Baseline độc lập.")
    table(pd.DataFrame([dict(model=n,best_params=json.dumps(v["best_params"],sort_keys=True)) for n,v in protocol["selected_models"].items()]))
    lines.extend(["Toàn bộ effective parameters gồm fixed parameters (giá trị `nan` là biểu diễn JSON của missing marker, không phải feature NaN sau transform):","","```json",json.dumps(protocol["effective_estimator_parameters"],ensure_ascii=False,indent=2),"```",""])
    section(10,"Primary Candidate và Main Challenger","Linear Regression được chỉ định Primary Candidate do MAE Development CV nhỏ nhất; XGBoost là Main Challenger. Hai vai trò được đóng băng trước Test. Mọi thứ hạng Test sau đây là quan sát thực nghiệm, không tự động chọn mô hình khác hoặc công bố Final Model.")
    for number,split,title in [(11,"main_final_test","Kết quả Main Final Test mùa 2024"),(12,"supplemental_test","Kết quả Supplemental Test mùa 2025")]:
        group=metrics.loc[metrics.test_split.eq(split)].sort_values("observed_mae_rank")
        winner=group.iloc[0]
        section(number,title,f"Bảng độc lập cho `{split}`. MAE thấp nhất quan sát: **{winner['model']}**, `{winner.mae:.6f}` xG; đây là thứ hạng mô tả, LR vẫn là Primary Candidate.")
        table(group[["model","designation","n_observations","n_matches","mae","rmse","observed_mae_rank"]])
    section(13,"Quy ước metric và chẩn đoán","Tất cả dự báo được clip `maximum(0,raw_prediction)` trước mọi metric. MAE = trung bình |prediction−actual|; RMSE = căn trung bình bình phương. Residual = prediction−actual, dương là dự báo cao, âm là dự báo thấp. `residual_std` dùng ddof=0; đây là độ phân tán residual, không phải khoảng tin cậy. CSV dự báo giữ cả raw_prediction để kiểm toán số âm.")
    table(diagnostics.drop(columns="prediction_sha256"))
    section(14,"Cải thiện so với Historical Baseline","Cải thiện tuyệt đối = MAE Baseline − MAE model; phần trăm = 100 × cải thiện / MAE Baseline, tính riêng từng Test. Giá trị dương là tốt hơn Baseline; Baseline có cải thiện 0 theo định nghĩa.")
    table(metrics[["test_split","model","baseline_mae_improvement","baseline_mae_improvement_percent"]])
    section(15,"Development CV so với Test","Tham chiếu là trung bình số học metric của ba validation folds, không phải RMSE trên residual gộp. Chênh lệch Test − CV dương nghĩa là sai số tăng. Các mô hình Development từng fold có ít dữ liệu train hơn mô hình fit toàn bộ Development ở đây, nên chênh lệch còn chịu ảnh hưởng cỡ train và phân phối theo mùa.")
    table(metrics[["test_split","model","development_cv_mean_fold_mae","mae","mae_minus_development_cv","development_cv_mean_fold_rmse","rmse","rmse_minus_development_cv"]])
    for split,g in metrics.groupby("test_split",sort=False):
        lines.extend([f"`{split}`: {int(g.mae_minus_development_cv.gt(0).sum())}/{len(g)} phương pháp có MAE cao hơn Development CV; {int(g.rmse_minus_development_cv.gt(0).sum())}/{len(g)} có RMSE cao hơn. Đây là kết quả trên từng mẫu theo thời gian, không chứng minh hiệu năng cải thiện lâu dài.",""])
    section(16,"Phương pháp Paired Bootstrap","Mỗi Test dùng danh sách match_id sắp tăng riêng; lấy có hoàn lại số trận bằng cỡ Test bằng `default_rng(42)`, 2.000 lần. Giữ đủ hai phía và số lần xuất hiện của trận; lấy trung bình sai số hai phía rồi lấy trung bình các trận có multiplicity tương đương MAE trên toàn bộ 2×n records lấy mẫu. Năm so sánh trong cùng Test dùng đúng cùng draw indices; không lấy mẫu từng đội–trận riêng, không deduplicate. ΔMAE = MAE_A − MAE_B, âm có lợi cho A. Khoảng percentile 2,5/97,5 dùng `linear`. Lưu tóm tắt, đủ 20.000 delta và hash draw indices để replay; không gộp hai mùa.")
    section(17,"Kết quả bootstrap và khoảng 95%","Khoảng hoàn toàn âm cho thấy ưu thế MAE của A trong bootstrap trên mẫu này; khoảng chứa 0 chưa tách rõ hai phương pháp theo thủ tục đã định. Khoảng không chứng minh một model luôn thắng ở tương lai và không được dùng để đổi Primary Candidate.")
    table(bootstrap)
    for row in bootstrap.loc[bootstrap.comparison_id.isin(["lr_minus_baseline","lr_minus_xgb"])].itertuples():
        interpretation="chứa 0, chưa tách rõ chênh MAE" if row.interval_contains_zero else "hoàn toàn âm, có lợi cho LR trong mẫu bootstrap này" if row.ci_upper<0 else "hoàn toàn dương, bất lợi cho LR trong mẫu bootstrap này"
        lines.extend([f"`{row.test_split}` · {row.model_a} − {row.model_b}: khoảng `[{row.ci_lower:.6f}, {row.ci_upper:.6f}]` {interpretation}.",""])
    section(18,"Sai số Home và Away","Mỗi Test được phân tích riêng. Số bản ghi và số trận được báo cho từng subgroup; cùng một trận có thể thuộc cả hai nhóm venue qua hai phía.")
    table(groups("venue"))
    section(19,"Sai số theo mức xG thực tế","Ngưỡng cố định từ Phase 6: xG <1; 1≤xG<2; xG≥2. Actual xG chỉ dùng phân nhóm hậu kiểm, tuyệt đối không đưa vào X. Các nhóm n<30 được đánh dấu small_sample.")
    table(groups("actual_xg"))
    section(20,"Sai số theo độ dài lịch sử","Tách lịch sử đội và đối thủ: 0, 1–4, ≥5 trận. Bảng chỉ có nhóm thực sự tồn tại; không tạo metric giả cho nhóm rỗng. Nhóm không xuất hiện không đủ bằng chứng để kết luận độ bền ở tình huống đó.")
    for dimension in ["team_history","opponent_history"]:
        lines.extend([f"**{dimension}**",""]); table(groups(dimension))
        for split in ["main_final_test","supplemental_test"]:
            available=set(errors.loc[errors.dimension.eq(dimension)&errors.test_split.eq(split),"group"])
            lines.extend([f"`{split}` không có nhóm: {', '.join(sorted({'zero','one_to_four','five_or_more'}-available)) or 'không' }.",""])
    section(21,"Sai số theo vòng đấu","`Matchweek N` được parse và kiểm tra 1–38, sắp theo số. Dưới đây là LR và XGBoost; CSV `final_test_error_analysis.csv` chứa đủ năm phương pháp. Mỗi vòng chỉ có tối đa 20 bản ghi nên mọi nhóm vòng đấu đều nhỏ theo ngưỡng 30; không suy luận chắc chắn từ vòng có MAE cực trị.")
    table(groups("matchweek").loc[lambda f:f.model.isin(["Linear Regression","XGBoost"])])
    section(22,"Các sai số lớn và bất đồng dự báo","Giữ nguyên ngưỡng absolute_error≥1,0 xG; bất đồng |LR−XGB|≥0,5; top 15 theo lỗi tuyệt đối mỗi model/split cùng cực trị over/under, deduplicate nguồn. `final_test_notable_errors.csv` giữ toàn bộ các ca được chọn; bảng match-level giữ đủ cả hai phía và cờ both_large_errors; bảng cross-model dùng đơn vị đội–trận để đếm cả bốn regressors sai lớn.")
    summary=[]
    for split,g in cross.groupby("test_split",sort=False):
        summary.append(dict(test_split=split,n_team_records=len(g),multiple_regressors_large=int(g.multiple_regressors_large.sum()),
            all_four_large=int(g.all_regressors_large.sum()),lr_xgb_large_disagreement=int(g.large_disagreement.sum()),
            mean_abs_lr_xgb_prediction_difference=float(g.lr_xgb_prediction_difference.mean())))
    table(pd.DataFrame(summary))
    lines.extend(["Các ca cả bốn regressors cùng sai lớn (tối đa 5 mỗi Test, theo lỗi trung bình giảm dần):",""])
    table(cross.loc[cross.all_regressors_large].sort_values("mean_regressor_absolute_error",ascending=False).groupby("test_split",sort=False).head(5)[[
        "test_split","date","match_id","team","opponent","actual_xg","linear_regression_predicted_xg",
        "decision_tree_predicted_xg","random_forest_predicted_xg","xgboost_predicted_xg","mean_regressor_absolute_error"]])
    table(matches.groupby(["test_split","model"]).agg(n_matches=("match_id","size"),both_sides_large=("both_large_errors","sum")).reset_index())
    lines.extend(["Cực trị over/under thực tế của từng model và Test:",""])
    extreme=notable.loc[notable.largest_overprediction|notable.largest_underprediction]
    table(extreme[["test_split","model","source_row","date","match_id","team","opponent","actual_xg","predicted_xg","residual","largest_overprediction","largest_underprediction"]])
    lines.extend(["Các ca LR có lỗi tuyệt đối lớn nhất (5 mỗi Test):",""])
    table(notable.loc[notable.model.eq("Linear Regression")&notable.top_absolute_error].sort_values("absolute_error",ascending=False).groupby("test_split",sort=False).head(5)[["test_split","source_row","date","match_id","team","opponent","actual_xg","predicted_xg","absolute_error"]])
    lines.extend(["Các trận có lỗi lớn cả hai phía ở LR (tối đa 5 mỗi Test):",""])
    table(matches.loc[matches.model.eq("Linear Regression")&matches.both_large_errors].sort_values("sum_absolute_error",ascending=False).groupby("test_split",sort=False).head(5)[["test_split","match_id","date","home_team","away_team","home_actual_xg","away_actual_xg","home_predicted_xg","away_predicted_xg","sum_absolute_error"]])
    section(23,"Hình thực nghiệm và diễn giải","Bảy hình dùng trực tiếp CSV kết quả: so sánh CV/Main, hai Test theo MAE/RMSE, scatter thực tế/dự báo, histogram residual, nhóm venue, nhóm actual xG, histogram bootstrap. Kiểm tra trực tiếp bar heights, scatter offsets, histogram bins và percentile với bảng nguồn. Scatter có đường y=x; residual bên âm là dự báo thấp; bootstrap có đường 0 và delta quan sát. Hai Test luôn giữ nhãn/cỡ mẫu riêng; ảnh Phase 6 không bị thay đổi.")
    for figure in manifest["figures"]:
        filename=figure["path"].replace("\\","/").rsplit("/",1)[-1]
        lines.extend([f"![{filename}](../outputs/figures/phase7/{filename})",""])
    section(24,"Đối chiếu các phát hiện Phase 6 với Test","Bảng dưới đối chiếu định lượng cùng định nghĩa subgroup với Validation gộp Phase 6. Không coi kết quả vài subgroup ít mẫu là quy luật mới hoặc dùng để đề xuất feature đã kiểm chứng trên Test.")
    pattern=[]
    for model in MODEL_NAMES:
        old=phase6.loc[phase6.model.eq(model)]
        old_home=float(old.loc[old.dimension.eq("venue")&old.group.eq("Home"),"mae"].iloc[0])
        old_away=float(old.loc[old.dimension.eq("venue")&old.group.eq("Away"),"mae"].iloc[0])
        for split in ["main_final_test","supplemental_test"]:
            now=errors.loc[errors.model.eq(model)&errors.test_split.eq(split)]
            venue=now.loc[now.dimension.eq("venue")].set_index("group")
            actual=now.loc[now.dimension.eq("actual_xg")].set_index("group")
            pattern.append(dict(model=model,test_split=split,phase6_home_minus_away=old_home-old_away,
                test_home_minus_away=float(venue.loc["Home","mae"]-venue.loc["Away","mae"]),
                home_mae_higher=bool(venue.loc["Home","mae"]>venue.loc["Away","mae"]),
                high_xg_group_largest_mae=bool(actual.mae.idxmax()=="xg_ge_2"),
                high_xg_n=int(actual.loc["xg_ge_2","n_observations"]) if "xg_ge_2" in actual.index else 0))
    table(pd.DataFrame(pattern))
    for split in ["main_final_test","supplemental_test"]:
        selected=[r for r in pattern if r["test_split"]==split]
        g=cross.loc[cross.test_split.eq(split)]
        high_n=selected[0]["high_xg_n"]
        lines.extend([f"`{split}`: {sum(r['home_mae_higher'] for r in selected)}/5 phương pháp lặp lại mẫu Home MAE cao hơn Away; {sum(r['high_xg_group_largest_mae'] for r in selected)}/5 có MAE cao nhất ở nhóm xG≥2 (n={high_n}). Nhóm xG cao {'dưới ngưỡng 30 nên chỉ mô tả, chưa đủ để kết luận ổn định' if high_n<30 else 'vượt ngưỡng cảnh báo mẫu nhỏ, nhưng vẫn là phân tích hậu kiểm'}. Cả bốn regressors cùng sai lớn ở {int(g.all_regressors_large.sum())}/{len(g)} bản ghi ({100*g.all_regressors_large.mean():.2f}%).",""])
    lines.extend([f"Phase 6 ghi nhận {int(phase6_cross.all_regressors_large.sum())}/{len(phase6_cross)} đội–trận mà cả bốn regressors sai ≥1 xG. So sánh số Test ở mục 22; cỡ mẫu khác nhau nên không đồng nhất số đếm với tỷ lệ. Các ca chung cho bốn model vẫn phản ánh hạn chế của bộ dự báo trung bình trước trận, không chứng minh một nguyên nhân chiến thuật cụ thể.",""])
    section(25,"Linear Regression và XGBoost","Hai model được so sánh theo vai trò đã định từ Development. Dưới đây là chênh MAE và khoảng bootstrap thực tế. Khoảng chứa 0 cần giữ mức kết luận thận trọng; bất đồng trên từng dự báo ở mục 22 không đồng nghĩa chênh hiệu năng tổng thể. XGBoost có thể có RMSE tốt hơn ngay khi MAE cao hơn vì hai metric nhấn mạnh sai số khác nhau.")
    table(bootstrap.loc[bootstrap.comparison_id.eq("lr_minus_xgb")])
    section(26,"Thiên lệch lựa chọn và giới hạn CV","CV dùng để tìm hyperparameters và so sánh models; điểm tốt nhất sau tìm kiếm có thể lạc quan vì tái sử dụng Validation. Split theo mùa giảm rò rỉ thời gian nhưng không loại bỏ selection bias hoặc distribution shift. Phase 6 phân tích lặp trên Development cũng không phải bằng chứng độc lập. Test hiện đã được mở; mọi thay đổi kiến trúc/feature hoặc lựa chọn Final Model dựa trên kết quả ở đây đều là quyết định sau Test và phải ghi rõ, cần một tập độc lập mới cho tuyên bố xác nhận tiếp theo.")
    section(27,"Giới hạn Supplemental và bootstrap","Supplemental chỉ 70 trận đầu mùa, không đại diện trọn mùa 2025–2026. Bootstrap theo trận giữ phụ thuộc Home/Away nhưng không xử lý đầy đủ phụ thuộc giữa các trận cùng đội, tự tương quan thời gian hoặc shift giữa mùa. Seed 42 được khởi tạo riêng cho mỗi Test, các danh sách trận khác nhau và không trộn hai tập. Khoảng 95% là percentile biên trên mẫu quan sát, chưa hiệu chỉnh năm so sánh; không phải xác suất thắng tương lai, prediction interval hay khoảng hiệu năng ở mọi mùa.")
    section(28,"Các kiểm thử đã thực thi",f"Chạy thực tế **{manifest['tests']['run']} tests**, failures={manifest['tests']['failures']}, errors={manifest['tests']['errors']}, skipped={manifest['tests']['skipped']}. Bao gồm 44 tests Phase 4–6 và 18 tests Phase 7. Fixtures Phase 7 chỉ dùng Development/nhân tạo; nhãn mùa Test giả trong kiểm thử cơ chế không phải kết quả Test thật. Không chạy lại toàn bộ Phase 5 search. Kiểm tra bổ sung trong luồng thực nghiệm xác minh schema, fit lineage, medians, alignment, pairs, clipping, metrics, bootstrap replay và nguyên trạng file.")
    lines.extend(["```text",manifest["tests"]["log"].strip(),"```",""])
    section(29,"Tái lập và toàn vẹn",f"Dataset SHA-256 `{manifest['dataset_sha256']}`.\n\nBest parameters SHA-256 `{manifest['best_params_sha256']}`.\n\nProtocol SHA-256 `{manifest['evaluation_protocol_sha256']}`.\n\nInference lặp bằng chính fitted objects cho kết quả chính xác từng giá trị; không thực hiện fit độc lập lần hai. Đã đọc lại {manifest['readback']['csv_files']} CSV bằng csv chuẩn và float Python để xác minh round-trip 17 chữ số, schema, nguồn dòng, clipping/errors và tính lại metrics; replay bootstrap khớp toàn bộ deltas/khoảng. Manifest giữ prediction hashes, draw hashes, hashes CSV/hình/nguồn và snapshot file được bảo vệ. CSV staging được tạo trực tiếp trong thư mục đích để kế thừa ACL, tránh lỗi NoPermissions do di chuyển từ thư mục tạm riêng. Đọc lại thành công trong tiến trình hiện tại; việc mở bằng VS Code/Excel của phiên người dùng không được giả nhận là đã kiểm thử tương tác.")
    table(pd.DataFrame([dict(file=k,sha256=v) for k,v in manifest["csv_sha256"].items()]))
    section(30,"Môi trường và lệnh thực thi",f"Python thực tế: `{manifest['environment']['python']}`. Dùng dependencies sẵn có của môi trường `.venv`, yêu cầu từ training/evaluation requirements; không thêm dependency mới.")
    table(pd.DataFrame([dict(package=k,version=v) for k,v in manifest["environment"]["packages"].items()]))
    lines.extend(["```powershell",r'.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v',
        ".\\.venv\\Scripts\\python.exe -m scripts.evaluation.final_test prepare",
        ".\\.venv\\Scripts\\python.exe -m scripts.evaluation.final_test evaluate","```",""])
    section(31,"File mới, tái sử dụng và bảo toàn","Thêm `scripts/evaluation/final_test.py`, `bootstrap_analysis.py`, `final_test_visualizations.py`, `final_test_reporting.py`, `tests/test_final_test.py`, thư mục `outputs/final_test/`, hình `outputs/figures/phase7/` và đúng báo cáo này. Các bảng bổ sung có vai trò riêng: subgroup, ca nổi bật, cặp trận, đối chiếu model và bootstrap replicates để kiểm toán.\n\nChỉnh tối thiểu `error_analysis.py`: tách `build_prediction_records` dùng chung; wrapper Validation vẫn kiểm tra fold/mùa cũ; ba hàm tổng hợp nhận `partition_column` mặc định `fold`, mặc định schema và hành vi Phase 6 không đổi. Đã chạy regression tests và kiểm thử đối chiếu hai giao diện. Không sửa splitter/RESERVED_SEASONS, Feature Engineering, chuẩn hóa, imputer, cấu hình tuning hoặc datasets. Snapshot xác minh nguyên trạng toàn bộ kết quả/báo cáo Phase 1–6; không commit/push.")
    section(32,"Vấn đề còn lại và phạm vi kiểm chứng","Không có lỗi chặn trong lần thực nghiệm hoàn tất. Chưa có kickoff timestamp đã xác minh. Nhóm zero-history thực tế chỉ 3 bản ghi và nhóm 1–4 trận chỉ 12 bản ghi mỗi Test; không đủ kết luận độ bền riêng cho các nhóm này. Kiểm chứng tái lập giới hạn ở inference cùng fitted objects, bootstrap và đọc lại kết quả, không phải fit độc lập lần hai hoặc kiểm thử trên mọi hệ điều hành. Không suy diễn nguồn gốc causal của sai số. Kết quả Test không được dùng sửa params/features/ngưỡng. Kiểm thử mock/synthetic đã có lỗi fixture ngày nhuận và sai số làm tròn quá chặt trong lúc phát triển; đã sửa trước khi đóng băng protocol và trước mọi Test metric, không đổi quyết định sau Test.\n\nSau thực nghiệm chỉ sửa trình bày: chuẩn hóa dấu phân cách đường dẫn ảnh Windows trong báo cáo và bổ sung diễn giải định lượng từ các CSV đã xuất. Không đổi protocol, mã quyết định đánh giá, dự báo, metrics, bootstrap, hình hoặc fit model. Manifest ghi hash nguồn tại thực nghiệm và các cập nhật tài liệu để phân biệt hai thời điểm.")
    section(33,"Kết luận Phase 7","Đã thực thi quy trình fit một lần trên Development, đánh giá hai Test bằng đúng cấu hình Phase 5 và đủ năm phương pháp. Kết quả thực tế, chênh CV/Baseline, các khoảng bootstrap và ca sai số được lưu đầy đủ; vai trò Primary LR và Challenger XGBoost giữ nguyên. Hoàn thành phạm vi đánh giá, không công bố Final Model qua thứ hạng Test.")
    for split in ["main_final_test","supplemental_test"]:
        lr=metrics.loc[metrics.test_split.eq(split)&metrics.model.eq("Linear Regression")].iloc[0]
        ci=bootstrap.loc[bootstrap.test_split.eq(split)&bootstrap.comparison_id.eq("lr_minus_xgb")].iloc[0]
        lines.extend([f"`{split}`: LR MAE `{lr.mae:.6f}`, RMSE `{lr.rmse:.6f}`; cải thiện MAE Baseline `{lr.baseline_mae_improvement_percent:.2f}%`; ΔMAE LR−XGB `{ci.observed_delta_mae:.6f}`, khoảng 95% `[{ci.ci_lower:.6f}, {ci.ci_upper:.6f}]`.",""])
    section(34,"Khuyến nghị cho Phase 8 khi được yêu cầu","Khi người dùng cho phép, có thể xây dựng Final Model Pipeline theo quy trình và vai trò đã đóng băng, lưu metadata/schema/preprocessing nhất quán và kiểm toán nguồn gốc quyết định. Nếu thay đổi quyết định vì Test, phải ghi rõ tính chất sau Test và lập kế hoạch xác nhận độc lập mới. Báo cáo này không thực hiện serialization, rolling retraining, SHAP, Streamlit, website, deployment hay tài liệu nộp cuối kỳ. Dừng ở Phase 7.")
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text("\n".join(lines),encoding="utf-8")
