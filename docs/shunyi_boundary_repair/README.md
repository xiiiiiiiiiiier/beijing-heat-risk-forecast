# 顺义边界修复与正式变量重算

- `report.md`：原始几何核查、方法比较及ERA5计算影响。
- `forecast_refresh.md`：用户追加授权后的北京12单元正式预报刷新、40输出文件及同输入权重影响。
- `evidence/`：修复前后、候选几何、ERA5逐格/逐时/逐日结果、日志与复算摘要。
- `evidence/正式预报更新/`：本次IFS逐格输入gzip、来源和摘要、逐列正式输出复算证据。
- `geometry_only.patch`：仅几何修复、权重和回归检查的补丁。

正式输出已刷新，禁止将ERA5诊断CSV覆盖IFS目录。仓库顺义正式输出是天气及AT/年龄风险；顺义HI仍为诊断。

从保存输入复核正式输出（在仓库根目录）：

```powershell
python scripts/audit_beijing_refresh.py --input docs/shunyi_boundary_repair/evidence/正式预报更新/forecast_20261014_192619.csv.gz --out work/forecast_audit
python -m scripts.validate_api_snapshot
python -m unittest discover -s tests -v
```

从最初固定基线复现几何和ERA5：在另一个新的副本checkout `0daab15d8813a4c52e88b708fd307b151e1d9b73`，使用本目录 `evidence/code/repair_audit.py --repo 新副本 --out 新证据目录`；接着使用 `diagnose_shunyi.py --repo 新副本 --out 新证据目录 --sample 原ERA5只读路径 --previous-results evidence/provenance/previous_beijing_urban_results.json`。两脚本包含原源摘要、版本、面积保持、权重及数值断言。科学依赖的实际版本见 `evidence/code/requirements-reproduce.txt`。

`reproduce.md`记录此前完整本地交付包的复现流程，其中`$package`指该交付包根目录，不是本目录。当前正式预报核查请使用仓库的 `scripts/audit_beijing_refresh.py`。

几何修复可以解除本次顺义区域计算障碍，没有证明地图位置精度或科研适用性全面通过；历史边界、海岸线、水域及独立界址精度不属于本轮范围。
