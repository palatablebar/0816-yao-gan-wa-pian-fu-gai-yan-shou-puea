# 遥感瓦片覆盖验收规则登记

- 规模：中型

## 功能模块

| 模块 | 动作 | 接口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 样例采信 | 预览并定位坏行 | `POST /api/stages/intake` | `app/intake/service.py` | `tests/test_intake.py` |
| M2 范围裁切 | 检查领域约束 | `POST /api/stages/prepare` | `app/modules/prepare.py` | `tests/test_prepare.py` |
| M3 覆盖归并 | 查看业务计算结果 | `POST /api/stages/calculate` | `app/modules/calculate.py` | `tests/test_calculate.py` |
| M4 缺口验收 | 查看签收判定 | `POST /api/stages/policy` | `app/modules/policy.py` | `tests/test_policy.py` |
| M5 运行对账 | 对照输入、采信和隔离行 | `POST /api/stages/balance` | `app/modules/reconcile.py` | `tests/test_reconcile.py` |
| M6 批次复核 | 执行批次并签发或暂缓 | `POST /api/runs、PATCH /api/runs/<id>` | `app/review/service.py` | `tests/test_review.py` |
| M7 证据交付 | 下载复核清单 | `GET /api/runs/<id>/evidence` | `app/evidence/render.py` | `tests/test_evidence.py` |
| M8 补测打包 | 按业务组和连通性切分缺口包 | `GET /api/runs/<id>/packages` | `app/modules/gaps.py` | `tests/test_packages.py`、`tests/test_gap_geometry.py` |
| M9 补测派发 | 四项对平后派发并登记覆盖、关闭包 | `POST /api/runs/<id>/dispatch、POST /api/packages/<id>/coverage` | `app/modules/dispatch.py`、`app/modules/closure.py` | `tests/test_packages.py` |

## 输入陷阱

| 编号 | 规则 | 处理 | 测试 |
|---|---|---|---|
| TRAP-02 | 去除 BOM | `app/intake/reader.py` | `tests/test_intake.py::test_bom_preserves_identifier` |
| TRAP-03 | 按逻辑记录读取引号内换行 | `app/intake/reader.py` | `tests/test_intake.py::test_quoted_newline_is_one_logical_record` |
| TRAP-04 | 重复表头计入忽略行 | `app/intake/service.py` | `tests/test_intake.py::test_repeated_header_is_counted` |
| TRAP-05 | 异常列数隔离 | `app/intake/schema.py` | `tests/test_intake.py::test_extra_column_is_isolated` |
| TRAP-06 | 归一化全角数字和千分位 | `app/intake/numeric.py` | `tests/test_intake.py::test_full_width_and_grouping_are_canonical` |
| TRAP-07 | 空值行隔离 | `app/intake/numeric.py` | `tests/test_intake.py::test_sentinel_keeps_row_out_of_total` |
| TRAP-08 | 记录键保留前导零 | `app/intake/schema.py` | `tests/test_intake.py::test_bom_preserves_identifier` |
| TRAP-14 | 冲突版本都进入隔离 | `app/intake/resolve.py` | `tests/test_intake.py::test_duplicate_conflict_removes_both_copies` |
| TRAP-16 | 引号未闭合时拒收文件 | `app/intake/reader.py` | `tests/test_intake.py::test_unclosed_quote_invalidates_source` |
| TRAP-18 | 区分空文件、全空白和仅表头 | `app/intake/reader.py` | `tests/test_intake.py::test_empty_states_have_distinct_causes` |
| TRAP-26 | 拒绝旧版本复核 | `app/review/store.py` | `tests/test_review.py::test_review_optimistic_lock` |

## 领域反例

瓦片为整数网格上的左闭右开矩形。扫过相邻 X 边界，按 Y 区间并集求有效像元。输入重叠多计量与真实缺口独立提供。

逐组预期结论见 `tests/test_policy.py`，计算过程证据见 `tests/test_calculate.py`。

## 补测包规则

- 未覆盖像元按业务组分别求连通分量：同一业务组内按边相邻（四邻域）的未覆盖像元进入同一个包，角接触不连通；不同业务组即使几何相邻也不并包。
- 每个未覆盖像元恰好进入一个包。作业区外面积和覆盖交叠多计的面积不进入补测范围。
- 包身份包含业务组、规则版本、来源指纹、作业区和包内矩形；同一来源重跑得到相同的包，不会新增包，也不会覆盖已有覆盖登记。
- 派发前四项逐项对平，全部相符才可派发：
  - 来源：输入行账面闭合，清单的 sha256、字节数和规则版本能还原批次 id；
  - 采信：业务组记录数合计等于采信行，且记录键不重复；
  - 隔离：隔离行数、原因计数与拒收行数一致，行号唯一且指向数据行；
  - 缺口：每组 `覆盖 + 缺口 = 作业区像元`，包内像元合计等于缺口，包都在作业区内且互不重叠。
- 包的状态：`PENDING` → `DISPATCHED` → `CLOSED`。只有已派发的包能登记覆盖；净覆盖（落在包内、作业区内的并集）到齐后才关闭，重复报送和区外面积不加速关闭。
- 规则版本更新后旧范围失效：旧的未关闭包标记 `SUPERSEDED`，已下发的包保留并记录与同组新包的对应关系；已关闭的包保持关闭。
- 批次签发仍以运行对账为准；补测包的关闭状态单独记录，不改变已存批次的复核状态。
