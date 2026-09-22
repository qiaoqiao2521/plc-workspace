# Validation Workflow

> 2026-09-22：`FB_MainSequence` 的扫描语义修改先按 `validation/tests/README.md`
> 检查同源投影、编译后逐拍行为和形式结果。新入口 `run-semantic-modelcheck.py`
> 对失败/未知返回非零；下列历史门禁仍有审查记录的失效点，不能以退出 0 代替逻辑验收。
> v0.3 已实现持续 Enable 和分离的错误/诊断生命周期；参见项目 scan-contract.md。

## 开始前

先确认规格已经完成：

- `requirements`
- `state_machine`
- `fb_specs`

没规格，不进入检测层。

## Step 1. 检查环境

运行：

```powershell
powershell -ExecutionPolicy Bypass -File "E:\web\plc-workspace\validation\scripts\check-validation-env.ps1"
```

产物：

- `docs/artifacts/workflow/validation-env-check.json`

## Step 2. 初始化一个待验证项目

运行：

```powershell
powershell -ExecutionPolicy Bypass -File "E:\web\plc-workspace\validation\scripts\init-validation-project.ps1" -ProjectName "FB_MainSequence"
```

产物位置：

- `projects/FB_MainSequence/`

## Step 3. 填入 3 类输入

至少填：

1. `01_specs/requirements.md`
2. `01_specs/state_machine.md`
3. `01_specs/fb_specs.md`
4. `02_src/st/*.st`

## Step 4. 跑静态门禁

运行：

```powershell
powershell -ExecutionPolicy Bypass -File "E:\web\plc-workspace\validation\scripts\run-static-gate.ps1" -ProjectPath "E:\web\plc-workspace\projects\FB_MainSequence"
```

## Step 5. 跑状态机验证

运行：

```powershell
powershell -ExecutionPolicy Bypass -File "E:\web\plc-workspace\validation\scripts\run-modelcheck-gate.ps1" -ProjectPath "E:\web\plc-workspace\projects\FB_MainSequence"
```

## Step 6. 跑轻量冒烟

运行：

```powershell
powershell -ExecutionPolicy Bypass -File "E:\web\plc-workspace\validation\scripts\run-smoke-gate.ps1" -ProjectPath "E:\web\plc-workspace\projects\FB_MainSequence"
```

## Step 7. 回 TIA / PLCSIM

只有前三层都通过，才回 `TIA / PLCSIM` 做终验。

## 当前首批对象

先只做：

1. `FB_MainSequence`
2. `FB_LiftUnit`
3. `FB_ClampUnit`

## 通过标准

一个块至少满足：

1. 静态高危项为 0
2. 核心状态性质通过
3. 冒烟能跑一轮
4. 回 TIA 后接口映射正确
