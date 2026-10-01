# SCL 模块化模板（FC/FB）+ OB1(LAD) 集成思路

目标：逻辑块可脱离真实 DI/DO/AI/AO 使用；物理地址只出现在 “I/O mapping” 层。

## 1) 推荐的块分层

1) `FC_IO_Map`：读取实际输入标签/地址 → 组装成结构化输入（例如 `UDT_IO_In`），并将结构化输出写回实际输出标签/地址\
2) `FB_<Logic>`：纯逻辑（状态机/联锁/报警/控制），只处理结构化接口\
3) `FC_<Math/Util>`：缩放、限幅、滤波、报警阈值计算等纯函数

## 2) 变量区含义（必须说清楚给用户）

- `VAR_INPUT`：输入形参（只读）
- `VAR_OUTPUT`：输出形参（写出给调用方）
- `VAR_IN_OUT`：引用传递（调用方传入变量，块内可读写）
- `VAR_STAT`：**仅 FB** 存储区（静态变量/内部状态），存入**实例 DB**
- `VAR_TEMP`：临时变量（不保存、不可保持）

> 生成方案时要明确：你用的是 `Input/Output/InOut/Static/Temp` 哪一种，以及是否依赖实例 DB。

## 3) UDT（接口类型）建议

在 “PLC data types” 创建 UDT（示意）：

- `UDT_IO_In`：所有 DI/AI（结构化输入）
- `UDT_IO_Out`：所有 DO/AO（结构化输出/命令）
- `UDT_Cmd` / `UDT_Status`：控制命令与状态（手自动、复位、报警、运行状态）

UDT 好处：逻辑块可复用，后续改点位只动映射层。

## 4) FC 模板：I/O 映射（示意）

> 这是唯一允许触碰真实标签/地址的地方。逻辑块内不要出现 `%I/%Q/%IW/%QW`。

```scl
FUNCTION "FC_IO_Map" : Void
{ S7_Optimized_Access := 'TRUE' }
VAR_INPUT
    DI_Start      : Bool;    // 示例：用符号化标签，不直接写 %I0.0
    AI_Pressure_Raw: Int;    // 示例：原始 AI
END_VAR
VAR_IN_OUT
    IO_In  : "UDT_IO_In";
    IO_Out : "UDT_IO_Out";
END_VAR
VAR_TEMP
    pressure_bar : Real;
END_VAR
BEGIN
    // 输入映射
    IO_In.Start := DI_Start;

    // 模拟量缩放：根据项目约定替换（NORM_X/SCALE_X 或自定义）
    // pressure_bar := SCALE_X(NORM_X(AI_Pressure_Raw, 0, 27648), 0.0, 10.0);
    pressure_bar := INT_TO_REAL(AI_Pressure_Raw); // 占位：务必按真实量程改
    IO_In.Pressure_bar := pressure_bar;

    // 输出映射（示意：把结构化命令写回实际输出标签）
    // DO_Motor := IO_Out.MotorOnCmd;
END_FUNCTION
```

## 5) FB 模板：可复用逻辑（示意）

> 用 FB 承载“需要记忆”的逻辑（锁存、步进、定时、故障状态）。状态放 `VAR_STAT`，自动落在实例 DB。

```scl
FUNCTION_BLOCK "FB_Controller"
{ S7_Optimized_Access := 'TRUE' }
VAR_INPUT
    Cmd   : "UDT_Cmd";
    IO_In : "UDT_IO_In";
END_VAR
VAR_OUTPUT
    IO_Out : "UDT_IO_Out";
    Sts    : "UDT_Status";
END_VAR
VAR_STAT
    isRunning : Bool;
END_VAR
BEGIN
    IF Cmd.Reset THEN
        isRunning := FALSE;
    ELSIF Cmd.Start AND IO_In.PermitRun THEN
        isRunning := TRUE;
    ELSIF Cmd.Stop THEN
        isRunning := FALSE;
    END_IF;

    IO_Out.MotorOnCmd := isRunning;
    Sts.Running := isRunning;
END_FUNCTION_BLOCK
```

## 6) OB1/Main（LAD）组织方式（描述模板）

要求：OB1 用 LAD，方便在线监视；逻辑放在 SCL 块。

建议 OB1 网络顺序（每步一张 Network）：

1) Network 1：调用 `FC_IO_Map`（把实际点位 → `IO_In`，并将 `IO_Out` 写回实际输出）\
2) Network 2：调用 `FB_Controller`（实例 DB 自动生成，例如 `"FB_Controller_DB"`）\
3) Network 3：报警/联锁汇总（可选，仍建议用 SCL 块）\

关键提醒：

- 把 FB 拖入 OB1(LAD) 的调用口，会提示生成实例 DB；实例 DB 是保存 `VAR_STAT` 的地方。
- OB1 中的块调用必须把**形参对应实参**接好（例如 `IO_In := DB_IO.IO_In` / `Cmd := DB_Cmd` 等）。
