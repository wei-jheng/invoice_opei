from data_validation_framework.schema.set.opei.opei_iuo_carrier_inv_detail import schema
from pipeline_ingestion_framework.factory.registration import (
    BronzeRawTableSpec,
    register_bronze_raw_table,
)

from invoice_opei.config.constants import (
    OPEI_IUO_CARRIER_INV_DETAIL,
    OPEI_IUO_CARRIER_INV_DETAIL_CDC,
)

try:
    spark  # noqa: F821, B018 — injected by Databricks DLT runtime
except NameError:
    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()

register_bronze_raw_table(
    spark,
    BronzeRawTableSpec(
        OPEI_IUO_CARRIER_INV_DETAIL, OPEI_IUO_CARRIER_INV_DETAIL_CDC, schema
    ),
)
