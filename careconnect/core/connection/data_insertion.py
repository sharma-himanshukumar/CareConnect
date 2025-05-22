from pyspark.sql import SparkSession
spark = SparkSession.builder.getOrCreate()
def setup_catalog_schema(catalog_name="careconnect", schema_name="default"):
    catalogs = spark.sql("SHOW CATALOGS").rdd.map(lambda row: row.catalog).collect()
    if catalog_name not in catalogs:
        spark.sql(f"CREATE CATALOG {catalog_name}")
    
    spark.sql(f"USE CATALOG {catalog_name}")
    
    schemas = spark.sql(f"SHOW SCHEMAS IN {catalog_name}").rdd.map(lambda row: row.databaseName).collect()
    if schema_name not in schemas:
        spark.sql(f"CREATE SCHEMA {catalog_name}.{schema_name}")
    
    spark.sql(f"USE SCHEMA {schema_name}")

def create_users_table():
    spark.sql("""
    CREATE TABLE IF NOT EXISTS users (
        user_id STRING,
        first_name STRING,
        last_name STRING,
        age INT,
        gender STRING,
        email STRING,
        if_pregnant BOOLEAN
    )
    USING DELTA
    """)

def create_medical_conditions_table():
    spark.sql("""
    CREATE TABLE IF NOT EXISTS medical_conditions (
        condition_id STRING,
        user_id STRING,
        condition_name STRING,
        diagnosis_date DATE,
        is_chronic BOOLEAN,
        notes STRING
    )
    USING DELTA
    """)
