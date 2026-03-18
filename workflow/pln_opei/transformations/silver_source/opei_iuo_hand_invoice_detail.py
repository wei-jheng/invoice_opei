from pipeline_ingestion_framework.factory.registration import (
    register_silver_source_table,
)

from invoice_opei.config.constants import OPEI_IUO_HAND_INVOICE_DETAIL_CDC

try:
    spark  # noqa: F821, B018 — injected by Databricks DLT runtime
except NameError:
    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()

register_silver_source_table(spark, OPEI_IUO_HAND_INVOICE_DETAIL_CDC)
