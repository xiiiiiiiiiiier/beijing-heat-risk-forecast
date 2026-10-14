# 本地复现说明

本轮代码与数据来自仓库提交 `0daab15d8813a4c52e88b708fd307b151e1d9b73`。所有命令在新的独立目录中运行，ERA5仅使用只读路径，不要把输出目录指向原数据目录。

## 直接检查交付

`修复后仓库`含完整修复后文件快照。对现有相同提交的独立Git副本，可运行 `git apply --check 顺义最小修复.patch` 后应用补丁。不要再次对已经修复的快照应用补丁。

## 从原提交重新计算

下面变量请填写实际解压后的路径。`$package`是包含此说明文件的交付目录。`$trial`是新的实验目录，不得使用桌面原数据目录。

```powershell
$package = 'C:\path\to\交付目录'
$trial = 'C:\path\to\新的实验目录'
$sample = 'C:\Users\11934\Desktop\qixiangshuju\era5_land_1991_06_jingjinji.nc'
New-Item -ItemType Directory -Force $trial | Out-Null
git clone https://github.com/xiiiiiiiiiiier/beijing-heat-risk-forecast "$trial\repo"
git -C "$trial\repo" checkout 0daab15d8813a4c52e88b708fd307b151e1d9b73
python -m venv "$trial\venv"
& "$trial\venv\Scripts\python.exe" -m pip install -r "$package\顺义修复证据包\code\requirements-reproduce.txt"

# 先仅应用构建检查及测试，保留原始源文件让审计脚本备份。
git -C "$trial\repo" apply --include=scripts/build_spatial.py --include=tests/test_shunyi_geometry.py --include=tests/fixtures/shunyi_original.geojson "$package\顺义最小修复.patch"
& "$trial\venv\Scripts\python.exe" "$package\顺义修复证据包\code\repair_audit.py" --repo "$trial\repo" --out "$trial\evidence"
& "$trial\venv\Scripts\python.exe" "$package\顺义修复证据包\code\diagnose_shunyi.py" --repo "$trial\repo" --out "$trial\evidence" --sample $sample --previous-results "$package\顺义修复证据包\provenance\previous_beijing_urban_results.json"
& "$trial\venv\Scripts\python.exe" "$package\顺义修复证据包\code\verify_build.py" --repo "$trial\repo" --target "$trial\fullbuild"
& "$trial\venv\Scripts\python.exe" "$package\顺义修复证据包\code\plot_geometry.py" --out "$trial\evidence"
Push-Location "$trial\repo"
& "$trial\venv\Scripts\python.exe" -m unittest discover -s tests -v
Pop-Location
```

`repair_audit.py`限制基线提交和原始源SHA256，并拒绝覆盖不相关源编辑；重复运行使用第一次保留的before文件。它只修110113并重建顺义、urban静态文件，不改天气预报数据。`diagnose_shunyi.py`中的所有试算都保存到指定证据目录，ERA5以 `h5py.File(...,'r')`读取并检验SHA256和修改时间。

此处锁定本次实际使用的科学库版本，避免不同GEOS/投影库版本导致复现差异；正式仓库依赖文件未改。`matplotlib`只用于示意图，Windows的Microsoft YaHei字体用于中文显示。核心几何和数值实验不依赖该字体。

证据包中的此前复现脚本用于说明已有口径，本轮应运行 `code/diagnose_shunyi.py`；此前脚本含上次工作目录路径，不能作为本轮运行入口。

固定UTC+8日分组是为了沿用已有诊断，未使用1991年历史夏令时日分组。诊断中顺义HI不是仓库正式输出；不要把ERA5权重或诊断CSV覆盖到IFS实时预报目录。
