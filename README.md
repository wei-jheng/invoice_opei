# invoice_opei

> OPEI 電子發票 SDP 入庫 pipeline（Databricks Asset Bundle）

[![CI](../../actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)

## 簡介

將 OPEI 電子發票 CSV 從 Databricks Volume（`/Volumes/prod_bronze_stage/set_opei/merchant_portal_invoice_carrier`）
入庫至 `bronze_raw` → `silver_source` 兩層 Delta 表，共 4 張表：

| 表名 | 說明 |
|------|------|
| `opei_frontend_invoice_list` | 電子發票主檔 |
| `opei_iuo_invoice_detail` | 統一發票明細（bu） |
| `opei_iuo_carrier_inv_detail` | 載具發票明細 |
| `opei_iuo_hand_invoice_detail` | 手開發票明細 |

## 安裝

```bash
uv sync
```

## 部署

```bash
# 部署到 sandbox（預設）
databricks bundle deploy

# 部署到 dev / uat / prod
databricks bundle deploy -t dev
databricks bundle deploy -t uat
databricks bundle deploy -t prod
```

| 分支 | 觸發條件 | 目標環境 |
|------|----------|----------|
| `main` | PR 合併後自動 | dev |
| `uat` | push 後自動 | uat |
| `prod` | push 後需 Required Reviewers 核准 | prod |

## 開發

```bash
uv run pytest                          # 執行測試
uv run ruff check src/                 # Lint
uv run mypy src/                       # 型別檢查
databricks bundle validate -t sandbox  # 驗證 bundle
uv build --wheel                       # 建置 wheel
```

## 依賴套件

| 套件 | 說明 |
|------|------|
| `pipeline_ingestion_framework` | 共用 SDP 入庫邏輯（本地 path dependency） |
| `data_validation_framework` | 資料驗證框架（Databricks whl） |

## 相關文件

詳細架構、資料表設定、DAB variables、新增資料表步驟見 [wiki.md](wiki.md)。
