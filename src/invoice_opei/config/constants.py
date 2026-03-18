from pipeline_ingestion_framework.config.types import CdcFlowTableConfig, TableConfig

OPEI_INVOICE = TableConfig(
    table='opei_frontend_invoice_list',
    file_date_regex=r'^(\d{8})\.csv',
    file_source='set_opei',
    toml_config_file='set_opei/invoice_data_validation.toml',
)
OPEI_IUO_INVOICE_DETAIL = TableConfig(
    table='opei_iuo_invoice_detail',
    file_date_regex=r'^bd_(\d{8})\.csv',
    file_source='set_opei',
    toml_config_file='set_opei/bu_data_validation.toml',
)
OPEI_IUO_CARRIER_INV_DETAIL = TableConfig(
    table='opei_iuo_carrier_inv_detail',
    file_date_regex=r'^cd_(\d{8})\.csv',
    file_source='set_opei',
    toml_config_file='set_opei/carrier_data_validation.toml',
)
OPEI_IUO_HAND_INVOICE_DETAIL = TableConfig(
    table='opei_iuo_hand_invoice_detail',
    file_date_regex=r'^hd_(\d{8})\.csv',
    file_source='set_opei',
    toml_config_file='set_opei/hand_data_validation.toml',
)

OPEI_INVOICE_CDC = CdcFlowTableConfig(
    table=OPEI_INVOICE.table,
    pk_keys=('invoice_number', 'invoice_date', 'gid'),
    sequence_cols=('_file_dt', '_ingest_dt'),
)
OPEI_IUO_INVOICE_DETAIL_CDC = CdcFlowTableConfig(
    table=OPEI_IUO_INVOICE_DETAIL.table,
    pk_keys=('invoice_number', 'invoice_date', 'seq_number', 'gid'),
    sequence_cols=('_file_dt', '_ingest_dt'),
)
OPEI_IUO_CARRIER_INV_DETAIL_CDC = CdcFlowTableConfig(
    table=OPEI_IUO_CARRIER_INV_DETAIL.table,
    pk_keys=('invoice_number', 'invoice_date', 'seq_number', 'gid'),
    sequence_cols=('_file_dt', '_ingest_dt'),
)
OPEI_IUO_HAND_INVOICE_DETAIL_CDC = CdcFlowTableConfig(
    table=OPEI_IUO_HAND_INVOICE_DETAIL.table,
    pk_keys=('invoice_number', 'invoice_date', 'seq_number', 'gid'),
    sequence_cols=('_file_dt', '_ingest_dt'),
)
