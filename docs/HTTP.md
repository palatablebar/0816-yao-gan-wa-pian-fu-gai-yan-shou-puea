# 阶段接口

`POST /api/stages/<stage>` 接收 `multipart/form-data`。字段 `sample=dirty`、`sample=clean` 或 `file=<CSV>` 三选一。阶段为 `intake`、`prepare`、`calculate`、`policy`、`balance`。预览不入库。

`POST /api/runs` 接收同样的输入，执行全批并返回运行报告。`GET /api/runs` 返回最近 50 批。`GET /api/runs/<id>` 查询一批和当前复核状态。

`PATCH /api/runs/<id>` 接收 `revision`、`status` 和 `note`。状态使用 `APPROVED` 或 `HELD`。冲突返回 409，客户端读取新版本后重试。

## 补测包

`GET /api/runs/<id>/packages` 列出该批次的补测包；`POST /api/runs/<id>/dispatch` 派发。来源、采信、隔离、缺口四项未对平时返回 409 `DISPATCH_BLOCKED`，不会改动任何包。

`GET /api/packages` 按状态列出全部补测包，`GET /api/packages/<id>` 查询单个包和累计覆盖报送。

`POST /api/packages/<id>/coverage` 接收 `{"rects":[[x0,y0,x1,y1],…]}`，登记实际新增覆盖。作业区外面积和重复报送的重叠多计量不计入净覆盖；净覆盖等于包内缺口像元数时包才关闭。包未派发返回 409 `PACKAGE_NOT_DISPATCHED`，已关闭返回 409 `PACKAGE_CLOSED`，规则升级后旧的未关闭包返回 409 `PACKAGE_SUPERSEDED`。

`GET /api/runs/<id>/evidence` 下载内含运行清单、行号隔离、业务证据、四项对平、补测包及关闭结果和复核信息的 JSON。
