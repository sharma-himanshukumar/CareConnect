from pyspark.sql import SparkSession
from pyspark.sql.functions import col

def create_hospital_table():
    spark = SparkSession.builder.getOrCreate()

    df = spark.read.option("header", "true").csv("core\Inputs\hospital_Data\all_india_hospital_list.csv")

    cleaned_df = df.select(
        col("Hospital Name").alias("hospital_name"),
        col("Address").alias("address"),
        col("CITY").alias("city"),
        col("STATE").alias("state"),
        col("PIN CODE").alias("pin_code"),
        col("PPN / NON PPN").alias("ppn_status")
    )

    spark.sql("CREATE DATABASE IF NOT EXISTS careconnect")

    cleaned_df.write.mode("overwrite").saveAsTable("careconnect.default.hospitals")
