# invoice_opei Wiki

> OPEI 電子發票 SDP 入庫 pipeline（Databricks Asset Bundle）

---

## 目錄

1. [專案概述](#1-專案概述)
2. [目錄結構](#2-目錄結構)
3. [架構說明](#3-架構說明)
4. [資料表說明](#4-資料表說明)
5. [資料驗證](#5-資料驗證)
6. [設定參數說明](#6-設定參數說明)
7. [新增資料表步驟](#7-新增資料表步驟)
8. [部署流程](#8-部署流程)
9. [本地開發](#9-本地開發)
10. [Backfill 操作](#10-backfill-操作)
11. [依賴套件](#11-依賴套件)

---

## 1. 專案概述

`invoice_opei` 將 OPEI（Online Platform Electronic Invoice）電子發票 CSV 從 Databricks Volume
（`/Volumes/prod_bronze_stage/set_opei/merchant_portal_invoice_carrier`）入庫至兩層 Delta 表：

- **bronze_raw**：原始入庫，append only，保留所有歷史版本
- **silver_source**：CDC upsert，以 PK + sequence cols 只保留最新版本

共處理 4 張表：

| 表名 | 說明 |
|------|------|
| `opei_frontend_invoice_list` | 電子發票主檔 |
| `opei_iuo_invoice_detail` | 統一發票明細（bu） |
| `opei_iuo_carrier_inv_detail` | 載具發票明細 |
| `opei_iuo_hand_invoice_detail` | 手開發票明細 |

---

## 2. 目錄結構

```
invoice_opei/
├── src/invoice_opei/
│   └── config/
│       └── constants.py              # 4 張表的 TableConfig / CdcFlowTableConfig 常數
├── workflow/pln_opei/transformations/
│   ├── bronze_raw/                   # DLT bronze_raw flow 腳本（4 支）
│   │   ├── opei_frontend_invoice_list.py
│   │   ├── opei_iuo_invoice_detail.py
│   │   ├── opei_iuo_carrier_inv_detail.py
│   │   └── opei_iuo_hand_invoice_detail.py
│   └── silver_source/                # DLT silver_source CDC flow 腳本（4 支）
│       ├── opei_frontend_invoice_list.py
│       ├── opei_iuo_invoice_detail.py
│       ├── opei_iuo_carrier_inv_detail.py
│       └── opei_iuo_hand_invoice_detail.py
├── bundle/
│   ├── jobs/ing_set_opei.yml         # Job J001：先驗證後觸發 pipeline
│   └── pipelines/pln_opei.yml        # Pipeline PPL001：serverless DLT
├── resources/config/set_opei/        # 資料驗證 TOML 設定（4 張表各一份）
│   ├── invoice_data_validation.toml
│   ├── bu_data_validation.toml
│   ├── carrier_data_validation.toml
│   └── hand_data_validation.toml
├── tests/unit/                       # Unit tests
│   ├── conftest.py
│   └── test_constants.py
├── databricks.yml                    # Bundle 主設定（variables + targets）
├── pyproject.toml                    # Python 套件設定（hatchling + hatch-vcs）
└── requirements.txt                  # uv export 產生的 lock（無 dev deps）
```

---

## 3. 架構說明

### 整體資料流

```
CSV（Databricks Volume）
        │
        ▼
┌──────────────────────────────────────────┐
│  Job: ing_set_opei (J001)                │
│                                          │
│  validate_invoice ──┐                    │
│  validate_bu       ──┼── 全部通過 ──► dlt_opei_pipeline ─┐
│  validate_carrier  ──┤                   │               │
│  validate_hand     ──┘                   │               │
└──────────────────────────────────────────┘               │
                                                           ▼
                                     ┌─────────────────────────────────┐
                                     │  Pipeline: pln_opei (PPL001)    │
                                     │  serverless DLT                 │
                                     │                                 │
                                     │  bronze_raw flow × 4           │
                                     │    CSV → bronze_raw Delta 表    │
                                     │           │                     │
                                     │           ▼                     │
                                     │  silver_source CDC flow × 4    │
                                     │    bronze_raw → silver_source   │
                                     └─────────────────────────────────┘
```

### ing_set_opei Job（J001）

- **job_id tag**: `J001`
- **環境**: serverless（Python Wheel Task，environment version 5）
- **依賴 wheels**: `invoice_opei`, `pipeline_ingestion_framework`, `data_validation_framework`

Job 包含 5 個 task：

| task_key | 類型 | 說明 |
|----------|------|------|
| `validate_invoice` | python_wheel_task | 驗證 opei_frontend_invoice_list 來源 CSV |
| `validate_bu` | python_wheel_task | 驗證 opei_iuo_invoice_detail 來源 CSV |
| `validate_carrier` | python_wheel_task | 驗證 opei_iuo_carrier_inv_detail 來源 CSV |
| `validate_hand` | python_wheel_task | 驗證 opei_iuo_hand_invoice_detail 來源 CSV |
| `dlt_opei_pipeline` | pipeline_task | 觸發 pln_opei，依賴以上 4 個 validate task 全部成功 |

4 個 validate task 平行執行，全數通過後才觸發 `dlt_opei_pipeline`。

### pln_opei Pipeline（PPL001）

- **pipeline_id tag**: `PPL001`
- **模式**: serverless DLT
- **catalog（bronze_raw）**: `${var.catalog_name}`
- **catalog（silver_source）**: `${var.catalog_name_silver_source}`
- **schema**: `${var.schema_opei}`

#### bronze_raw flow

每張表各有一支 transformation 腳本（`workflow/pln_opei/transformations/bronze_raw/`）。
腳本呼叫 `pipeline_ingestion_framework` 的 `register_bronze_raw_table()`，流程如下：

1. 根據 `file_date_regex` 掃描 Volume 目錄中符合的 CSV 檔案
2. 讀取 CSV（依 schema 定義，pipe 分隔，無 header，UTF-8）
3. 附加系統欄位（`_file_dt`, `_ingest_dt`, `_source_file`）
4. 寫入 `{catalog}.{schema}.{table}{bronze_raw_table_suffix}`（append only）

#### silver_source CDC flow

每張表各有一支 transformation 腳本（`workflow/pln_opei/transformations/silver_source/`）。
腳本呼叫 `pipeline_ingestion_framework` 的 `register_silver_source_table()`，流程如下：

1. 讀取 bronze_raw 表的增量資料
2. 以 `pk_keys` 作為主鍵、`sequence_cols`（`_file_dt`, `_ingest_dt`）決定新舊版本
3. DLT APPLY CHANGES（CDC upsert）寫入 silver_source 表

### 資料層定義

| 層 | 命名規則 | 說明 |
|----|---------|------|
| **bronze_raw** | `{catalog_name}.{schema_opei}.{table}[{bronze_raw_table_suffix}]` | 原始入庫，append only，保留所有歷史版本 |
| **silver_source** | `{catalog_name_silver_source}.{schema_opei}.{table}` | CDC upsert，只保留最新版本 |

> sandbox 環境的 `bronze_raw_table_suffix = "_raw"`，避免與 prod 表名衝突。

### Slack 通知

dev / uat / prod 環境的 `ing_set_opei` job 配有 Slack webhook notifications：

- **on_start / on_success** → `#data-team-notify`（`var.slack_notify_destination_id`）
- **on_failure** → `#data-team-alert`（`var.slack_alert_destination_id`）

---

## 4. 資料表說明

### 總覽

| 表名 | 來源檔案 regex | 來源 TOML | Job validate task |
|------|--------------|-----------|------------------|
| `opei_frontend_invoice_list` | `^(\d{8})\.csv` | `invoice_data_validation.toml` | `validate_invoice` |
| `opei_iuo_invoice_detail` | `^bd_(\d{8})\.csv` | `bu_data_validation.toml` | `validate_bu` |
| `opei_iuo_carrier_inv_detail` | `^cd_(\d{8})\.csv` | `carrier_data_validation.toml` | `validate_carrier` |
| `opei_iuo_hand_invoice_detail` | `^hd_(\d{8})\.csv` | `hand_data_validation.toml` | `validate_hand` |

**來源 Volume 根目錄（`base_path_opei`）**：`/Volumes/prod_bronze_stage/set_opei/merchant_portal_invoice_carrier`

CSV 格式：pipe（`|`）分隔，無 header，UTF-8 編碼。

---

### opei_frontend_invoice_list

電子發票主檔（OPEI frontend invoice list）。

**PK**

| 欄位 | 說明 |
|------|------|
| `invoice_number` | 發票號碼（fixed 10 碼） |
| `invoice_date` | 發票日期（yyyyMMdd） |
| `gid` | 全球識別碼（fixed 17 碼） |

**CDC sequence cols**：`_file_dt`（檔案日期）、`_ingest_dt`（入庫時間戳）

**日期欄位**：`invoice_date`, `cre_date`, `upd_date`

---

### opei_iuo_invoice_detail

統一發票明細（business unit / IUO invoice detail）。

**PK**

| 欄位 | 說明 |
|------|------|
| `invoice_number` | 發票號碼（fixed 10 碼） |
| `invoice_date` | 發票日期（yyyyMMdd） |
| `seq_number` | 序號（fixed 3 碼） |
| `gid` | 全球識別碼（fixed 17 碼） |

**CDC sequence cols**：`_file_dt`、`_ingest_dt`

**日期欄位**：`invoice_date`, `data_cre_date`, `cre_date`, `upd_date`

---

### opei_iuo_carrier_inv_detail

載具發票明細（carrier invoice detail）。

**PK**

| 欄位 | 說明 |
|------|------|
| `invoice_number` | 發票號碼 |
| `invoice_date` | 發票日期（yyyyMMdd） |
| `seq_number` | 序號 |
| `gid` | 全球識別碼 |

**CDC sequence cols**：`_file_dt`、`_ingest_dt`

---

### opei_iuo_hand_invoice_detail

手開發票明細（hand invoice detail）。

**PK**

| 欄位 | 說明 |
|------|------|
| `invoice_number` | 發票號碼 |
| `invoice_date` | 發票日期（yyyyMMdd） |
| `seq_number` | 序號 |
| `gid` | 全球識別碼 |

**CDC sequence cols**：`_file_dt`、`_ingest_dt`

---

### 系統欄位（bronze_raw 共用）

| 欄位 | 說明 |
|------|------|
| `_file_dt` | 從檔名 regex 解析出的日期（date 型別） |
| `_ingest_dt` | pipeline 執行時的入庫時間戳 |
| `_source_file` | 完整來源檔案路徑 |

### Python 常數（`src/invoice_opei/config/constants.py`）

```python
# TableConfig：bronze_raw 入庫設定
OPEI_INVOICE                  # opei_frontend_invoice_list
OPEI_IUO_INVOICE_DETAIL       # opei_iuo_invoice_detail
OPEI_IUO_CARRIER_INV_DETAIL   # opei_iuo_carrier_inv_detail
OPEI_IUO_HAND_INVOICE_DETAIL  # opei_iuo_hand_invoice_detail

# CdcFlowTableConfig：silver_source CDC 設定
OPEI_INVOICE_CDC
OPEI_IUO_INVOICE_DETAIL_CDC
OPEI_IUO_CARRIER_INV_DETAIL_CDC
OPEI_IUO_HAND_INVOICE_DETAIL_CDC
```

---

## 5. 資料驗證

`ing_set_opei` job 在觸發 DLT pipeline 前，對 4 張表的來源 CSV 各自執行一組驗證任務，確保資料品質後才允許入庫。驗證邏輯由 `data_validation_framework` wheel 執行，設定檔位於 `resources/config/set_opei/`。

### 9 項驗證 Task

每份 TOML 設定檔包含 task_1 ~ task_9 共 9 個驗證任務，依序執行：

| task_id | task name | 說明 |
|---------|-----------|------|
| task_1 | `FileExistenceCheck` | 確認來源 CSV 檔案存在 |
| task_2 | `FileTimestampCheck` | 確認檔案時間戳在合理範圍內（`min_age_minutes=1`, `max_age_minutes=60`） |
| task_3 | `FileReadableCheck` | 確認檔案可正常讀取 |
| task_4 | `FileSchemaCheck` | 確認欄位 schema 符合預期 |
| task_5 | `FileRowCountCheck` | 確認列數 >= 1、<= 100,000,000 |
| task_6 | `FilePrimaryKeyCheck` | 確認 PK 欄位組合無重複 |
| task_7 | `FileNullOrEmptyCheck` | 確認 PK 欄位無 NULL 或空值 |
| task_8 | `FileDateCheck` | 確認日期欄位格式為 `yyyyMMdd`，不允許未來日期 |
| task_9 | `FileLengthCheck` | 確認關鍵欄位長度符合固定規格 |

### 各表差異

**task_6 / task_7：PK 欄位**

| 表名 | PK 欄位 |
|------|---------|
| `opei_frontend_invoice_list` | `gid`, `invoice_number`, `invoice_date` |
| `opei_iuo_invoice_detail` | `invoice_number`, `invoice_date`, `seq_number`, `gid` |
| `opei_iuo_carrier_inv_detail` | `invoice_number`, `invoice_date`, `seq_number`, `gid` |
| `opei_iuo_hand_invoice_detail` | `invoice_number`, `invoice_date`, `seq_number`, `gid` |

**task_8：日期欄位**

| 表名 | 驗證日期欄位 |
|------|------------|
| `opei_frontend_invoice_list` | `invoice_date`, `cre_date`, `upd_date` |
| `opei_iuo_invoice_detail` | `invoice_date`, `data_cre_date`, `cre_date`, `upd_date` |
| `opei_iuo_carrier_inv_detail` | （詳見 `carrier_data_validation.toml`） |
| `opei_iuo_hand_invoice_detail` | （詳見 `hand_data_validation.toml`） |

**task_9：欄位長度規則**

| 表名 | 長度規則 |
|------|---------|
| `opei_frontend_invoice_list` | `gid`=17（fixed）、`invoice_number`=10（fixed） |
| `opei_iuo_invoice_detail` | `invoice_number`=10、`seq_number`=3、`gid`=17（全部 fixed） |
| `opei_iuo_carrier_inv_detail` | （詳見 `carrier_data_validation.toml`） |
| `opei_iuo_hand_invoice_detail` | （詳見 `hand_data_validation.toml`） |

### Backfill 驗證

各 TOML 的 `[backfill]` 區塊設有 `task_ids`，Backfill 時只跑 task_4 ~ task_9（跳過 task_1/2/3 的檔案存在/時間/可讀性檢查）：

```toml
[backfill]
enabled = true
start_date = "2025-09-25"
end_date   = "2025-09-26"
task_ids = ["task_4", "task_5", "task_6", "task_7", "task_8", "task_9"]
```

### 設定檔位置

```
resources/config/set_opei/
├── invoice_data_validation.toml   # opei_frontend_invoice_list
├── bu_data_validation.toml        # opei_iuo_invoice_detail
├── carrier_data_validation.toml   # opei_iuo_carrier_inv_detail
└── hand_data_validation.toml      # opei_iuo_hand_invoice_detail
```

---

## 6. 設定參數說明

所有 variables 定義於 `databricks.yml` 的 `variables:` 區塊，可在各 target 中覆寫。

### Wheel 版本

| Variable | 預設值 | 說明 |
|----------|--------|------|
| `whl_version` | `0.1.0` | invoice_opei wheel 版本，需與 git tag 一致。CI 自動解析帶入。 |
| `pif_whl_version` | `0.1.0` | pipeline_ingestion_framework wheel 版本。CI 自動從 Workspace 讀取。 |
| `dvf_whl_version` | `0.1.5` | data_validation_framework wheel 版本。CI 自動從 Workspace 讀取。 |

### Artifact 路徑

| Variable | 說明 |
|----------|------|
| `pif_artifact_base_path` | PIF whl 在 Databricks Workspace 的存放目錄 |
| `dvf_artifact_base_path` | DVF whl 在 Databricks Workspace 的存放目錄 |

dev/uat/prod 環境設為 `/Workspace/Shared/bundles/{package}/{env}/artifacts/.internal`。

### 資料路徑

| Variable | 預設值 | 說明 |
|----------|--------|------|
| `base_path_opei` | `/Volumes/prod_bronze_stage/set_opei/merchant_portal_invoice_carrier` | OPEI 來源 CSV 的 Volume 根目錄 |

### Catalog / Schema

| Variable | sandbox | dev | uat | prod | 說明 |
|----------|---------|-----|-----|------|------|
| `catalog_name` | `sandbox` | `dev_bronze_raw` | `uat_bronze_raw` | `prod_bronze_raw` | bronze_raw 層 Unity Catalog |
| `catalog_name_silver_source` | `sandbox` | `dev_silver_source` | `uat_silver_source` | `prod_silver_source` | silver_source 層 Unity Catalog |
| `schema_opei` | `set_wei_jheng` | `set_opei` | `set_opei` | `set_opei` | pln_opei 使用的 schema |
| `bronze_raw_table_suffix` | `_raw` | `""` | `""` | `""` | sandbox 環境加後綴以區分 prod 表 |

### Backfill 日期

| Variable | 預設值 | 說明 |
|----------|--------|------|
| `start_date` | `""` | Backfill 起始日期（格式 `yyyyMMdd`）。空值 = 昨天 |
| `end_date` | `""` | Backfill 結束日期（格式 `yyyyMMdd`）。空值 = `start_date` |

### Flow Version（強制重算用）

遞增某張表的 flow version variable 可強制 DLT 重算該 flow 的所有歷史資料。

| Variable | 預設值 | 說明 |
|----------|--------|------|
| `bronze_raw_flow_version_opei_frontend_invoice_list` | `1` | bronze_raw flow 版本 |
| `bronze_raw_flow_version_opei_iuo_invoice_detail` | `1` | bronze_raw flow 版本 |
| `bronze_raw_flow_version_opei_iuo_carrier_inv_detail` | `1` | bronze_raw flow 版本 |
| `bronze_raw_flow_version_opei_iuo_hand_invoice_detail` | `1` | bronze_raw flow 版本 |
| `silver_source_flow_version_opei_frontend_invoice_list` | `1` | silver_source flow 版本 |
| `silver_source_flow_version_opei_iuo_invoice_detail` | `1` | silver_source flow 版本 |
| `silver_source_flow_version_opei_iuo_carrier_inv_detail` | `1` | silver_source flow 版本 |
| `silver_source_flow_version_opei_iuo_hand_invoice_detail` | `1` | silver_source flow 版本 |

### 其他

| Variable | 預設值 | 說明 |
|----------|--------|------|
| `log_level` | `INFO`（sandbox: `DEBUG`） | Pipeline log 等級（DEBUG / INFO / WARNING / ERROR） |
| `slack_notify_destination_id` | `""` | Slack Notification Destination ID（#data-team-notify） |
| `slack_alert_destination_id` | `""` | Slack Notification Destination ID（#data-team-alert） |

---

## 7. 新增資料表步驟

新增一張 OPEI 表需同步修改以下 4 個地方：

### 1. `src/invoice_opei/config/constants.py`

新增 `TableConfig` 和 `CdcFlowTableConfig` 常數：

```python
NEW_TABLE = TableConfig(
    table='opei_<table_name>',
    file_date_regex=r'^<prefix>_(\d{8})\.csv',
    file_source='set_opei',
    toml_config_file='set_opei/<table>_data_validation.toml',
)
NEW_TABLE_CDC = CdcFlowTableConfig(
    table=NEW_TABLE.table,
    pk_keys=('invoice_number', 'invoice_date', '<other_pk>'),
    sequence_cols=('_file_dt', '_ingest_dt'),
)
```

### 2. `resources/config/set_opei/<table>_data_validation.toml`

新增驗證設定檔，參考 `invoice_data_validation.toml` 結構，填入對應的 schema、PK 欄位、日期欄位、長度規則。

### 3. `workflow/pln_opei/transformations/`

新增兩支 transformation 腳本：

**`bronze_raw/opei_<table_name>.py`**：
```python
from data_validation_framework.schema.set.opei.<table_name> import schema
from pipeline_ingestion_framework.factory.registration import (
    BronzeRawTableSpec,
    register_bronze_raw_table,
)
from invoice_opei.config.constants import NEW_TABLE, NEW_TABLE_CDC

try:
    spark  # noqa: F821, B018
except NameError:
    from pyspark.sql import SparkSession
    spark = SparkSession.builder.getOrCreate()

register_bronze_raw_table(spark, BronzeRawTableSpec(NEW_TABLE, NEW_TABLE_CDC, schema))
```

**`silver_source/opei_<table_name>.py`**：
```python
from pipeline_ingestion_framework.factory.registration import register_silver_source_table
from invoice_opei.config.constants import NEW_TABLE_CDC

try:
    spark  # noqa: F821, B018
except NameError:
    from pyspark.sql import SparkSession
    spark = SparkSession.builder.getOrCreate()

register_silver_source_table(spark, NEW_TABLE_CDC)
```

### 4. `databricks.yml`

在 `variables:` 區塊新增 flow version variables：

```yaml
bronze_raw_flow_version_opei_<table_name>:
  description: "bronze_raw flow version for opei_<table_name>. Increment to force full reprocess."
  default: "1"
silver_source_flow_version_opei_<table_name>:
  description: "silver_source flow version for opei_<table_name>. Increment to force full reprocess."
  default: "1"
```

並在 `bundle/pipelines/pln_opei.yml` 的 `configuration:` 和 `libraries:` 區塊補上對應設定。

---

## 8. 部署流程

### 分支策略

```
feature/xxx
     │
     │  PR review
     ▼
   main ────────────────────► dev（自動）
     │
     │  合併 main → uat
     ▼
    uat ────────────────────► uat（自動）
     │
     │  合併 uat → prod
     ▼
   prod ── Required Reviewers 核准 ──► prod（部署）
```

| 分支 | 觸發條件 | Workflow 檔案 | 目標環境 | 需人工核准 |
|------|----------|--------------|----------|-----------|
| `main`（PR） | PR 開啟 / 更新 | `ci.yml` | — | 否（品質檢查） |
| `main`（push） | PR 合併至 main | `deploy-dev.yml` | dev | 否 |
| `uat`（push） | 合併 main → uat | `deploy-uat.yml` | uat | 否 |
| `prod`（push） | 合併 uat → prod | `deploy-prod.yml` | prod | **是** |

### ci.yml — PR 品質檢查

觸發條件：`pull_request` → `main`

1. `uv sync --all-groups --locked`
2. `uv run ruff check src/`
3. `uv run ruff format --check src/`
4. `uv run mypy src/`
5. `uv run pytest`
6. `databricks bundle validate -t dev`

### deploy-dev.yml — 部署至 dev

觸發條件：`push` → `main`

1. 執行品質檢查
2. `uv build --wheel`
3. 從 dev Workspace 自動偵測 PIF / DVF 最新版本號
4. `databricks bundle deploy -t dev --var=whl_version=... --var=pif_whl_version=... --var=dvf_whl_version=...`

### deploy-uat.yml — 部署至 uat

觸發條件：`push` → `uat`

1. `uv build --wheel`
2. 從 uat Workspace 自動偵測 PIF / DVF 最新版本號
3. `databricks bundle validate -t uat`
4. `databricks bundle deploy -t uat`

### deploy-prod.yml — 部署至 prod

觸發條件：`push` → `prod`

GitHub Environment `prod` 需設置 **Required Reviewers**，workflow 在部署步驟前暫停等待核准。

1. `uv build --wheel`
2. 從 prod Workspace 自動偵測 PIF / DVF 最新版本號
3. `databricks bundle validate -t prod`
4. **等待 Required Reviewers 核准**
5. `databricks bundle deploy -t prod`

### Whl 版本自動解析機制

CI 部署腳本會：
1. 以 `ls dist/*.whl | head -1` 取得本次 build 的 whl 檔名，解析 `whl_version`
2. 以 `databricks workspace list` 查詢對應環境 Workspace 中 PIF / DVF 的最新 whl，解析版本號
3. 三個版本號一起帶入 `databricks bundle deploy --var=...`

若 Workspace 中找不到 PIF 或 DVF whl，腳本會以 `sys.exit('ERROR: ...')` 中止部署。

### 認證

所有環境使用 GitHub Actions OIDC 認證（`id-token: write`）：
- `DATABRICKS_HOST`：各環境 Workspace URL（GitHub Variables）
- `DATABRICKS_CLIENT_ID`：Service Principal Client ID（`DATABRICKS_AUDIT_CLIENT_ID`）
- `DATABRICKS_TOKEN`：設為空字串（使用 OIDC，不用 PAT）

---

## 9. 本地開發

### 環境需求

- Python 3.12+
- `uv`（套件管理）
- Databricks CLI（bundle validate / deploy）

### 快速開始

```bash
# 安裝依賴（包含 dev deps：pytest, mypy, ruff 等）
uv sync --all-groups

# 執行 unit tests
uv run pytest

# Lint 檢查
uv run ruff check src/

# Format 檢查
uv run ruff format --check src/

# Type check
uv run mypy src/

# 驗證 bundle 結構（sandbox）
databricks bundle validate -t sandbox
```

### 本地依賴

`pipeline_ingestion_framework` 在 `pyproject.toml` 設為 path dependency：

```toml
[tool.uv.sources]
pipeline-ingestion-framework = { path = "../pipeline_ingestion_framework", editable = true }
```

確保 `../pipeline_ingestion_framework` 目錄存在且已 `uv sync`。

### 測試架構

- 測試框架：`pytest` with `pytest-cov`
- 測試檔位置：`tests/unit/`
- SparkSession 以 `local` mode 建立（`conftest.py`）
- 目前 7 個 tests，全數通過

### Toolchain

| 工具 | 說明 |
|------|------|
| `uv` | 套件管理（取代 pip） |
| `hatchling` + `hatch-vcs` | build backend，版本從 git tag 讀取，fallback `0.1.0` |
| `ruff` | lint + format（line-length 88，single quotes） |
| `mypy --strict` | type check（ignore_missing_imports = true） |
| `pytest` | 單元測試 |

---

## 10. Backfill 操作

### 觸發方式

透過 Databricks Job UI 或 CLI 手動觸發 `ing_set_opei` job，並帶入 `start_date` / `end_date` 參數：

```bash
databricks jobs run-now \
  --job-id <job_id> \
  --python-named-params '{"start_date": "20250901", "end_date": "20250930"}'
```

或透過 `databricks bundle run` 帶入 variables：

```bash
databricks bundle run ing_set_opei \
  --var=start_date=20250901 \
  --var=end_date=20250930
```

### 日期格式

- `start_date`、`end_date`：`yyyyMMdd`（例如 `20250901`）
- 空值（`""`）表示使用昨天作為 start_date，start_date 作為 end_date

### Backfill 驗證範圍

Backfill 時資料驗證只執行 task_4 ~ task_9（跳過 task_1/2/3 的檔案時效性檢查），設定在各 TOML 的 `[backfill].task_ids`。

### 強制重算 Flow

若需強制 DLT 重算某張表的所有歷史資料，遞增對應的 flow version variable，再重新部署 bundle：

```bash
databricks bundle deploy -t prod \
  --var=bronze_raw_flow_version_opei_frontend_invoice_list=2
```

---

## 11. 依賴套件

### Runtime Wheels（Pipeline）

| Wheel | 說明 | 版本 variable |
|-------|------|--------------|
| `invoice_opei` | 本 repo 的 domain config | `var.whl_version` |
| `pipeline_ingestion_framework` | 共用 bronze_raw / silver_source SDP 邏輯 | `var.pif_whl_version` |
| `data_validation_framework` | 資料驗證框架（validate_* task） | `var.dvf_whl_version` |

### Dev Dependencies

| 套件 | 說明 |
|------|------|
| `pytest` (>=9.0.2) | 單元測試 |
| `pytest-cov` (>=7.0.0) | 測試覆蓋率 |
| `pyspark` (>=4.0.0) | 本地 SparkSession（tests） |
| `pyarrow` (>=23.0.0) | PySpark 依賴 |
| `mypy` (>=1.19.1) | Type checking |
| `ruff` (>=0.15.0) | Lint / format |
| `pre-commit` (>=4.5.1) | Git hooks |
| `pipeline-ingestion-framework` | 本地 path dependency |

---

*最後更新：2026-03-20*
