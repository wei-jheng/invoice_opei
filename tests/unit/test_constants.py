from pipeline_ingestion_framework.config.types import CdcFlowTableConfig, TableConfig

from invoice_opei.config.constants import (
    OPEI_INVOICE,
    OPEI_INVOICE_CDC,
    OPEI_IUO_CARRIER_INV_DETAIL,
    OPEI_IUO_CARRIER_INV_DETAIL_CDC,
    OPEI_IUO_HAND_INVOICE_DETAIL,
    OPEI_IUO_HAND_INVOICE_DETAIL_CDC,
    OPEI_IUO_INVOICE_DETAIL,
    OPEI_IUO_INVOICE_DETAIL_CDC,
)

_ALL_TABLE_CONFIGS = [
    OPEI_INVOICE,
    OPEI_IUO_INVOICE_DETAIL,
    OPEI_IUO_CARRIER_INV_DETAIL,
    OPEI_IUO_HAND_INVOICE_DETAIL,
]

_ALL_CDC_CONFIGS = [
    OPEI_INVOICE_CDC,
    OPEI_IUO_INVOICE_DETAIL_CDC,
    OPEI_IUO_CARRIER_INV_DETAIL_CDC,
    OPEI_IUO_HAND_INVOICE_DETAIL_CDC,
]


def test_all_opei_table_configs_defined():
    assert len(_ALL_TABLE_CONFIGS) == 4


def test_all_opei_cdc_configs_defined():
    assert len(_ALL_CDC_CONFIGS) == 4


def test_all_table_configs_are_set_opei():
    for conf in _ALL_TABLE_CONFIGS:
        assert isinstance(conf, TableConfig)
        assert conf.file_source == 'set_opei'


def test_all_table_configs_have_toml_config_file():
    for conf in _ALL_TABLE_CONFIGS:
        assert conf.toml_config_file.startswith('set_opei/')
        assert conf.toml_config_file.endswith('.toml')


def test_cdc_configs_pk_keys_not_empty():
    for conf in _ALL_CDC_CONFIGS:
        assert isinstance(conf, CdcFlowTableConfig)
        assert len(conf.pk_keys) > 0, f'{conf.table} has empty pk_keys'


def test_cdc_configs_sequence_cols_not_empty():
    for conf in _ALL_CDC_CONFIGS:
        assert len(conf.sequence_cols) > 0, f'{conf.table} has empty sequence_cols'


def test_cdc_table_matches_table_config():
    assert OPEI_INVOICE_CDC.table == OPEI_INVOICE.table
    assert OPEI_IUO_INVOICE_DETAIL_CDC.table == OPEI_IUO_INVOICE_DETAIL.table
    assert OPEI_IUO_CARRIER_INV_DETAIL_CDC.table == OPEI_IUO_CARRIER_INV_DETAIL.table
    assert OPEI_IUO_HAND_INVOICE_DETAIL_CDC.table == OPEI_IUO_HAND_INVOICE_DETAIL.table
