# Calibration data

Drop your labeled audience outcomes here as `.json` (array) or `.jsonl` (one per
line). Each record joins to a local report by `reportId` (the report folder
name under `userData/garuda/reports/`), or by `sourceName` / `youtubeVideoId`.

```json
[
  {
    "reportId": "1699999999999-my_video_mp4",
    "youtubeVideoId": "abc123",
    "avgViewDurationPct": 44.5,
    "ctr": 6.1,
    "views": 12000,
    "impressions": 90000,
    "retention": [
      { "tFrac": 0.0, "retentionPct": 100 },
      { "tFrac": 0.05, "retentionPct": 78 },
      { "tFrac": 0.5, "retentionPct": 41 }
    ]
  }
]
```

Then train:

```bash
python -m garuda_analyze.calibration.train \
  --data packages/analysis/garuda_analyze/calibration/data \
  --reports "<userData>/garuda/reports" \
  --out packages/analysis/garuda_analyze/calibration/model
```

Once `model/model.joblib` + `model/model.json` exist, every new report gets a
`predictions` block (avg view duration, CTR, retention curve) with 10/90%
confidence intervals; otherwise the engine keeps its heuristic retention curve.
`avgViewDurationPct` and `ctr` are percentages (0..100); `retention[].tFrac` is
0..1 of the video, `retentionPct` is 0..100.
```
