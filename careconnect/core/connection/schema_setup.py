from pyspark.sql import SparkSession
from datetime import date
import uuid
from core.connection.schema_setup import setup_catalog_schema, create_users_table, create_medical_conditions_table

spark = SparkSession.builder.getOrCreate()

def insert_sample_users():
    users = [
        (str(uuid.uuid4()), "Alice", "Smith", 30, "Female", "alice@example.com", True),
        (str(uuid.uuid4()), "Bob", "Johnson", 35, "Male", "bob@example.com", False),
        (str(uuid.uuid4()), "Carol", "Williams", 28, "Female", "carol@example.com", True),
        (str(uuid.uuid4()), "David", "Brown", 40, "Male", "david@example.com", False)
    ]
    user_columns = ["user_id", "first_name", "last_name", "age", "gender", "email", "if_pregnant"]
    df_users = spark.createDataFrame(users, user_columns)
    df_users.write.mode("append").format("delta").saveAsTable("users")

def insert_sample_medical_conditions():
    user_df = spark.table("users").select("user_id", "email").toPandas()
    user_map = dict(zip(user_df["email"], user_df["user_id"]))

    conditions = [
        (str(uuid.uuid4()), user_map["alice@example.com"], "Hypertension", date(2020, 5, 20), True, "Managed with medication"),
        (str(uuid.uuid4()), user_map["bob@example.com"], "Asthma", date(2015, 3, 10), True, "Mild condition"),
        (str(uuid.uuid4()), user_map["carol@example.com"], "Anemia", date(2023, 1, 5), False, "Iron supplements prescribed")
    ]
    condition_columns = ["condition_id", "user_id", "condition_name", "diagnosis_date", "is_chronic", "notes"]
    df_conditions = spark.createDataFrame(conditions, condition_columns)
    df_conditions.write.mode("append").format("delta").saveAsTable("medical_conditions")

if __name__ == "__main__":
    setup_catalog_schema()                      # Create catalog & schema if needed
    create_users_table()                        # Create users table
    create_medical_conditions_table()           # Create medical_conditions table
    insert_sample_users()                       # Insert sample users
    insert_sample_medical_conditions()          # Insert sample medical conditions
