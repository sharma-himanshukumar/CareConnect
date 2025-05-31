# Databricks notebook source
db_hostname = dbutils.secrets.get("prod", "DB_HOSTNAME")
db_http_path = dbutils.secrets.get("prod", "DB_HTTP_PATH")

# COMMAND ----------


